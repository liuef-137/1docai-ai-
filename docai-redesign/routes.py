import json
import re
import hashlib
import requests as http_requests
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, request, jsonify, current_app, make_response, render_template
)
from sqlalchemy import or_, func

from models import db, User, Analysis, RiskPreference, ContractCompare, Feedback, Conversation, UserQuota
from auth import create_token, get_current_user, admin_required

api_bp = Blueprint('api', __name__)

# ---------------------------------------------------------------------------
# DeepSeek API helper
# ---------------------------------------------------------------------------

def call_deepseek(messages, stream=False):
    """
    Call the DeepSeek chat completions API.

    Args:
        messages: list of dicts with 'role' and 'content'
        stream: if True, return a generator yielding content chunks

    Returns:
        str (full content) or generator of str chunks

    Raises:
        RuntimeError on API errors
    """
    config = current_app.config
    api_key = config.get('DEEPSEEK_API_KEY', '')
    base_url = config.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
    model = config.get('DEEPSEEK_MODEL', 'deepseek-chat')

    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY 未配置，请在 .env 文件中设置')

    url = f'{base_url}/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 4096,
        'stream': stream,
    }

    try:
        resp = http_requests.post(url, headers=headers, json=payload, timeout=120, stream=stream)
    except http_requests.RequestException as e:
        raise RuntimeError(f'请求 DeepSeek API 失败: {str(e)}')

    if resp.status_code != 200:
        try:
            err_body = resp.json()
            err_msg = err_body.get('error', {}).get('message', resp.text)
        except Exception:
            err_msg = resp.text
        raise RuntimeError(f'DeepSeek API 错误 ({resp.status_code}): {err_msg}')

    if stream:
        def _stream():
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
        return _stream()
    else:
        try:
            body = resp.json()
            return body['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            raise RuntimeError(f'解析 DeepSeek 响应失败: {str(e)}')


def _safe_parse_json(text):
    """Try to extract and parse JSON from an AI response text."""
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown code fences
    # Match ```json ... ``` or ``` ... ```
    patterns = [
        r'```json\s*\n?(.*?)\n?\s*```',
        r'```\s*\n?(.*?)\n?\s*```',
        r'\{[\s\S]*\}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1) if match.lastindex else match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    return None


# ---------------------------------------------------------------------------
# Mode-specific system prompts
# ---------------------------------------------------------------------------

REVIEW_STANCE_PROMPTS = {
    'party_a': '\n\n审查立场：你代表甲方（合同中提供产品/服务/资金的一方）。请特别关注保护甲方权益的条款，如付款条件、交付标准、违约责任上限、知识产权归属、保密期限等。',
    'party_b': '\n\n审查立场：你代表乙方（合同中接收产品/服务/资金的一方）。请特别关注保护乙方权益的条款，如付款期限、验收标准、违约金合理性、免责条款、竞业限制补偿、合同解除权等。',
}

PLAIN_LANGUAGE_INJECTION = """\n\n重要补充要求：在返回的 risk_items 中，每个风险条款额外增加一个 "plain_explanation" 字段，用通俗易懂的大白话解释该风险（不超过30字），让没有法律背景的人也能理解。同时在 suggestion 字段中给出具体的修改建议措辞。"""

RISK_ANALYSIS_PROMPT = """你是一位资深合同审查律师，拥有 10 年以上的合同审查经验。你的任务是找出合同中的所有潜在风险点。

{type_focus}{stance_prompt}{plain_lang_prompt}

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{
  "contract_type": "<合同类型，如 labor/rental/purchase/service/nda/loan/other>",
  "score": <0-100 的整数，100=极安全，0=极高风险>,
  "risk_level": "<high/medium/low>",
  "one_line_summary": "<一句话总结该合同的核心风险，不超过 50 字>",
  "risk_items": [
    {
      "clause_name": "<条款名称，如'违约金条款'、'保密期限'>",
      "clause_location": "<条款所在位置，如'第三条第二款'>",
      "risk_level": "<high/medium/low>",
      "description": "<具体风险描述，2-3 句话，说明该条款为什么有问题>",
      "plain_explanation": "<大白话解读，不超过30字，让普通人也能理解>",
      "suggestion": "<修改建议，具体的操作性建议，如'建议将违约金上限设定为合同总额的20%'>",
      "legal_basis": "<相关法律依据，如'《民法典》第585条'>"
    }
  ],
  "suggestions": ["<总体改进建议1>", "<总体改进建议2>"],
  "key_obligations": [
    {"party": "<甲方/乙方>", "obligation": "<核心义务>"},
    {"party": "<甲方/乙方>", "obligation": "<核心义务>"}
  ]
}

评分标准：
- 90-100：合同条款完善，风险很低
- 70-89：有少量低风险条款，需要轻微调整
- 50-69：存在中等风险条款，建议修改
- 30-49：有较多高风险条款，建议重大修改
- 0-29：合同存在严重问题，不建议签署

分析要求：
1. 至少找出 3 个风险条款，最多 10 个
2. 每个风险条款必须给出具体的修改建议
3. 优先关注显失公平的条款、违反法律强制性规定的条款、模糊不清的条款
4. 如果合同中有空白待填项，标记为风险

请确保返回有效的 JSON。"""

SUMMARY_PROMPT = """你是一位专业的合同分析助手。请对以下合同文本进行全面的摘要分析。

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{
  "one_line_summary": "<一句话概括合同核心内容>",
  "key_points": [
    {"point": "<要点标题>", "detail": "<详细说明>"}
  ],
  "parties": [
    {"name": "<甲方/乙方名称>", "role": "<角色描述>"}
  ],
  "important_dates": [
    {"date": "<日期>", "event": "<事件描述>"}
  ],
  "obligations": [
    {"party": "<义务方>", "obligation": "<义务内容>"}
  ]
}

请确保返回有效的 JSON。"""

PLAIN_LANGUAGE_PROMPT = """你是一位擅长将法律文书翻译为通俗语言的专家。请将以下合同文本翻译成普通人也能理解的通俗语言。

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{
  "one_line_summary": "<一句话通俗概括>",
  "plain_explanation": "<完整的通俗语言版本>",
  "key_terms": [
    {"term": "<专业术语>", "plain_explanation": "<通俗解释>"}
  ],
  "things_to_watch": [
    {"item": "<需要注意的事项>", "why_important": "<为什么重要>", "suggestion": "<建议>"}
  ]
}

请确保返回有效的 JSON。"""

COMPARE_PROMPT = """你是一位资深合同律师。请对比分析以下两份合同文本的差异，并从法律风险角度解读这些变更。

原始合同：
{original_text}

修改后合同：
{modified_text}

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{
  "changes": [
    {
      "type": "<added/modified/deleted>",
      "location": "<变更位置描述>",
      "original": "<原始内容>",
      "modified": "<修改后内容>",
      "impact": "<变更影响分析>",
      "risk_level": "<high/medium/low/none>",
      "suggestion": "<建议>"
    }
  ],
  "overall_assessment": "<整体评估>",
  "risk_summary": "<风险总结>"
}

请确保返回有效的 JSON。"""

FOLLOWUP_PROMPT = """你是 DocAI 的合同分析助手。用户之前对一份合同进行了分析，现在想继续追问。

请根据之前的分析结果和用户的追问，给出专业、清晰、通俗易懂的回答。

重要规则：
1. 回答要具体，引用合同中的具体条款和之前的分析结果
2. 如果用户问的是法律建议，请声明"以下仅为 AI 分析参考，不构成法律意见"
3. 用通俗语言解释专业法律概念
4. 如果追问与当前分析无关，请礼貌地引导回合同分析话题
5. 回答控制在 500 字以内，重点突出"""

# ---------------------------------------------------------------------------
# Contract Type Detection
# ---------------------------------------------------------------------------

CONTRACT_TYPE_PROMPT = """请识别以下合同文本的类型。只返回一个 JSON，不要有其他文字：
{"type": "<contract_type>", "confidence": <0.0-1.0>}

合同类型可选值：
- labor: 劳动合同
- rental: 房屋租赁合同
- purchase: 买卖合同 / 购销合同
- service: 服务合同 / 技术服务合同
- nda: 保密协议 / 保密合同
- loan: 借款合同 / 借贷合同
- partnership: 合伙协议 / 合作协议
- franchise: 加盟合同 / 特许经营合同
- agency: 委托合同 / 代理合同
- construction: 建设工程合同
- insurance: 保险合同
- other: 其他

合同文本：
{contract_text}
"""

CONTRACT_TYPE_FOCUS = {
    'labor': {
        'zh': '劳动合同专项审查',
        'focus': '重点关注：试用期时长与工资、社保缴纳、竞业限制补偿、加班费计算、解除条件、违约金合法性、经济补偿金标准。注意《劳动合同法》对上述条款的强制性规定。',
    },
    'rental': {
        'zh': '房屋租赁合同专项审查',
        'focus': '重点关注：租期与违约金、押金退还条件、维修责任划分、转租限制、装修补偿、提前解约权、面积与用途约定。注意《民法典》关于租赁合同的规定。',
    },
    'purchase': {
        'zh': '买卖合同专项审查',
        'focus': '重点关注：标的物描述、价格与支付方式、交付条件、质量保证期、验收标准、违约责任、所有权转移时机、风险承担。注意《民法典》买卖合同章节。',
    },
    'service': {
        'zh': '技术服务合同专项审查',
        'focus': '重点关注：服务范围与边界、交付里程碑、验收标准、知识产权归属、保密条款、人员配置、付款节点、维护期与SLA、违约与解约。',
    },
    'nda': {
        'zh': '保密协议专项审查',
        'focus': '重点关注：保密范围界定、保密期限（是否过长）、例外条款、违约赔偿计算、竞业限制关联、信息返还/销毁义务、员工离职后的保密义务。',
    },
    'loan': {
        'zh': '借款合同专项审查',
        'focus': '重点关注：借款利率（是否超过LPR 4倍/司法保护上限）、担保方式、还款计划、提前还款违约金、逾期罚息、抵押物处置、保证人责任范围。',
    },
    'other': {
        'zh': '合同通用审查',
        'focus': '请按照通用合同审查标准进行分析。',
    },
}


def _robust_json_parse(text):
    """
    Parse JSON from LLM output with resilience.
    Handles: markdown code blocks, trailing commas, comments, BOM.
    """
    if not text:
        return None

    # Remove BOM
    text = text.strip('\ufeff\ufffe').strip()

    # Extract JSON from markdown code block if present
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    # Remove single-line comments
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)

    # Remove multi-line comments (/* ... */)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    brace_start = text.find('{')
    if brace_start >= 0:
        try:
            return json.loads(text[brace_start:])
        except json.JSONDecodeError:
            pass

    # Last resort: try to fix common issues
    try:
        # Remove control characters except newline
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _detect_contract_type(contract_text, api_key):
    """Detect contract type using a lightweight AI call."""
    truncated = contract_text[:3000] if len(contract_text) > 3000 else contract_text
    messages = [
        {'role': 'system', 'content': '你是一个合同类型分类器。只返回 JSON。'},
        {'role': 'user', 'content': CONTRACT_TYPE_PROMPT.format(contract_text=truncated)},
    ]
    try:
        result = call_deepseek(messages, stream=False)
        parsed = _robust_json_parse(result)
        if parsed and 'type' in parsed:
            return parsed.get('type', 'other'), parsed.get('confidence', 0.5)
    except Exception:
        pass
    return 'other', 0.0


def _compute_text_hash(text):
    """Compute a stable hash for contract text to enable caching."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sensitive Data Desensitization
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS = [
    # ID card (18 digits, last may be X)
    ('id_card', r'\b([1-9]\d{5})(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'),
    # Mobile phone (China)
    ('phone', r'\b1[3-9]\d{9}\b'),
    # Bank card (16-19 digits)
    ('bank_card', r'\b\d{16,19}\b'),
    # Email (basic)
    ('email', r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
]

def _desensitize_text(text):
    """
    Mask sensitive data in contract text for storage/display.
    Returns (masked_text, mask_map) where mask_map describes what was masked.
    """
    mask_map = []
    masked = text

    for field_type, pattern in SENSITIVE_PATTERNS:
        for match in re.finditer(pattern, masked):
            original = match.group(0)
            start, end = match.start(), match.end()

            # Check if this region was already masked (avoid double-masking)
            before = masked[:start]
            if '****' in before[max(0, start-20):start]:
                continue

            if field_type == 'id_card':
                replacement = original[:4] + '****' + original[-4:]
            elif field_type == 'phone':
                replacement = original[:3] + '****' + original[-4:]
            elif field_type == 'bank_card':
                replacement = original[:4] + '****' + original[-4:]
            elif field_type == 'email':
                at_idx = original.index('@')
                name_part = original[:at_idx]
                replacement = name_part[:2] + '****' + original[at_idx:]
            else:
                replacement = '****'

            masked = masked[:start] + replacement + masked[end:]
            mask_map.append({'type': field_type, 'original': original, 'masked': replacement})

    return masked, mask_map


def _find_cached_analysis(user_id, text_hash, mode):
    """Find a recent cached analysis for the same text."""
    # Look in last 24 hours
    since = datetime.utcnow() - timedelta(hours=24)
    cached = Analysis.query.filter(
        Analysis.user_id == user_id,
        Analysis.created_at >= since
    ).order_by(Analysis.created_at.desc()).first()

    if cached and cached.text_hash == text_hash and cached.analysis_mode == mode:
        return cached
    return None


def _get_mode_prompt(mode):
    prompts = {
        'risk': RISK_ANALYSIS_PROMPT,
        'summary': SUMMARY_PROMPT,
        'plain': PLAIN_LANGUAGE_PROMPT,
    }
    return prompts.get(mode, RISK_ANALYSIS_PROMPT)


def _inject_preferences(system_prompt, preferences):
    """Inject user risk preferences into the system prompt."""
    if not preferences:
        return system_prompt
    pref_text = '、'.join(preferences)
    injection = f"\n\n用户设定的风控红线: {pref_text}。请特别关注这些条款是否触碰红线。"
    return system_prompt + injection


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not username or not email or not password:
        return jsonify({'error': '用户名、邮箱和密码不能为空'}), 400

    if len(username) < 2 or len(username) > 80:
        return jsonify({'error': '用户名长度需在 2-80 个字符之间'}), 400

    if len(password) < 6:
        return jsonify({'error': '密码长度不能少于 6 个字符'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({'error': '邮箱已被注册'}), 409

    user = User(username=username, email=email)
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'注册失败: {str(e)}'}), 500

    token = create_token(user.id)
    resp = make_response(jsonify({
        'message': '注册成功',
        'token': token,
        'user': user.to_dict(),
    }))
    resp.set_cookie('token', token, httponly=True, max_age=60 * 60 * 24 * 7, samesite='Lax')
    return resp, 201


@api_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': '用户名或密码错误'}), 401

    token = create_token(user.id)
    resp = make_response(jsonify({
        'message': '登录成功',
        'token': token,
        'user': user.to_dict(),
    }))
    resp.set_cookie('token', token, httponly=True, max_age=60 * 60 * 24 * 7, samesite='Lax')
    return resp


@api_bp.route('/api/auth/me', methods=['GET'])
@get_current_user()
def get_me(current_user):
    return jsonify({'user': current_user.to_dict()})


@api_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify({'message': '已退出登录'}))
    resp.delete_cookie('token')
    return resp


# ---------------------------------------------------------------------------
# Analysis Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/analysis', methods=['POST'])
@get_current_user()
def create_analysis(current_user):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    mode = (data.get('mode') or 'risk').strip()
    filename = (data.get('filename') or '').strip() or None
    review_stance = (data.get('review_stance') or '').strip()  # 'party_a' or 'party_b'

    if not text:
        return jsonify({'error': '合同文本不能为空'}), 400

    if review_stance and review_stance not in ('party_a', 'party_b'):
        review_stance = ''

    allowed, remaining, limit = UserQuota.check_and_increment(current_user.id, 'analysis')
    if not allowed:
        return jsonify({'error': f'今日分析次数已达上限（{limit}次），请明天再试', 'remaining': 0, 'daily_limit': limit}), 429

    max_len = current_app.config.get('MAX_TEXT_LENGTH', 10000)
    if len(text) > max_len:
        return jsonify({
            'error': f'合同文本过长，请控制在 {max_len} 字以内',
            'count': len(text),
            'max': max_len,
        }), 400

    if mode not in ('risk', 'summary', 'plain'):
        mode = 'risk'

    # Compute text hash for caching
    text_hash = _compute_text_hash(text)

    # Check cache — if found, return cached result immediately
    cached = _find_cached_analysis(current_user.id, text_hash, mode)
    if cached:
        return jsonify({
            'message': '分析完成（缓存）',
            'analysis': cached.to_dict(),
            'cached': True,
        }), 200

    # Detect contract type (only for risk mode)
    contract_type = 'other'
    if mode == 'risk':
        api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
        contract_type, _ = _detect_contract_type(text, api_key)

    # Load user risk preferences for risk analysis mode
    user_prefs = []
    if mode == 'risk':
        pref_obj = RiskPreference.query.filter_by(user_id=current_user.id).first()
        if pref_obj:
            user_prefs = pref_obj.get_preferences_list()

    # Build prompt with type-specific focus for risk mode
    system_prompt = _get_mode_prompt(mode)
    if mode == 'risk':
        type_info = CONTRACT_TYPE_FOCUS.get(contract_type, CONTRACT_TYPE_FOCUS['other'])
        stance_prompt = REVIEW_STANCE_PROMPTS.get(review_stance, '')
        plain_lang_prompt = PLAIN_LANGUAGE_INJECTION
        system_prompt = system_prompt.format(
            type_focus=f"\n{type_info['zh']}：{type_info['focus']}",
            stance_prompt=stance_prompt,
            plain_lang_prompt=plain_lang_prompt,
        )
        if user_prefs:
            system_prompt = _inject_preferences(system_prompt, user_prefs)

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': text},
    ]

    try:
        ai_response = call_deepseek(messages)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 502

    # Parse the AI response
    parsed = _robust_json_parse(ai_response)

    # Extract fields
    score = None
    risk_level = None
    one_line_summary = None
    suggestions_json = None
    risk_items_json = None
    result_json = None

    if parsed and isinstance(parsed, dict):
        score = parsed.get('score')
        risk_level = parsed.get('risk_level')
        one_line_summary = parsed.get('one_line_summary')

        suggestions = parsed.get('suggestions')
        if suggestions is not None:
            try:
                suggestions_json = json.dumps(suggestions, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

        risk_items = parsed.get('risk_items')
        if risk_items is not None:
            try:
                risk_items_json = json.dumps(risk_items, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

        try:
            result_json = json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            result_json = ai_response

        # Fallback: if score/risk_level missing in parsed data
        if score is None and risk_level is None:
            risk_level = 'medium'
    else:
        # JSON parse failed, store raw response
        result_json = ai_response
        one_line_summary = ai_response[:200] if ai_response else None

    # Convert score to int if possible
    if score is not None:
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = None

    # Desensitize contract text before storage
    masked_text, _ = _desensitize_text(text)

    # Create analysis record
    analysis = Analysis(
        user_id=current_user.id,
        filename=filename,
        contract_text=masked_text,
        text_hash=text_hash,
        contract_type=contract_type,
        analysis_mode=mode,
        result=result_json,
        score=score,
        risk_level=risk_level,
        one_line_summary=one_line_summary,
        suggestions=suggestions_json,
        risk_items=risk_items_json,
    )

    try:
        db.session.add(analysis)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'保存分析结果失败: {str(e)}'}), 500

    return jsonify({
        'message': '分析完成',
        'analysis': analysis.to_dict(),
    }), 201


@api_bp.route('/api/analysis/history', methods=['GET'])
@get_current_user()
def analysis_history(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    risk_level = request.args.get('risk_level', '').strip()
    mode = request.args.get('mode', '').strip()
    search = request.args.get('search', '').strip()

    per_page = min(max(per_page, 1), 100)

    query = Analysis.query.filter_by(user_id=current_user.id)

    if risk_level and risk_level in ('high', 'medium', 'low'):
        query = query.filter(Analysis.risk_level == risk_level)

    if mode and mode in ('risk', 'summary', 'plain'):
        query = query.filter(Analysis.analysis_mode == mode)

    if search:
        query = query.filter(or_(
            Analysis.filename.contains(search),
            Analysis.contract_text.contains(search),
            Analysis.one_line_summary.contains(search),
        ))

    query = query.order_by(Analysis.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = [a.to_dict() for a in pagination.items]

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/api/analysis/<int:analysis_id>', methods=['GET'])
@get_current_user()
def get_analysis(current_user, analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404
    return jsonify({'analysis': analysis.to_dict()})


@api_bp.route('/api/analysis/<int:analysis_id>', methods=['DELETE'])
@get_current_user()
def delete_analysis(current_user, analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    try:
        db.session.delete(analysis)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

    return jsonify({'message': '已删除'})


@api_bp.route('/api/analysis/<int:analysis_id>/favorite', methods=['POST'])
@get_current_user()
def toggle_favorite(current_user, analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    analysis.is_favorited = not analysis.is_favorited

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'操作失败: {str(e)}'}), 500

    return jsonify({
        'message': '已收藏' if analysis.is_favorited else '已取消收藏',
        'is_favorited': analysis.is_favorited,
    })


# ---------------------------------------------------------------------------
# Risk Preference Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/preferences', methods=['GET'])
@get_current_user()
def get_preferences(current_user):
    pref = RiskPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        return jsonify({'preferences': []})
    return jsonify({'preferences': pref.get_preferences_list()})


@api_bp.route('/api/preferences', methods=['PUT'])
@get_current_user()
def update_preferences(current_user):
    data = request.get_json(silent=True) or {}
    preferences = data.get('preferences')

    if preferences is not None and not isinstance(preferences, list):
        return jsonify({'error': 'preferences 必须是字符串数组'}), 400

    pref = RiskPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        pref = RiskPreference(user_id=current_user.id)
        db.session.add(pref)

    if preferences is not None:
        pref.set_preferences_list(preferences)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'保存偏好设置失败: {str(e)}'}), 500

    return jsonify({
        'message': '偏好设置已更新',
        'preferences': pref.get_preferences_list(),
    })


# ---------------------------------------------------------------------------
# Compare Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/compare', methods=['POST'])
@get_current_user()
def create_compare(current_user):
    data = request.get_json(silent=True) or {}
    original_text = (data.get('original_text') or '').strip()
    modified_text = (data.get('modified_text') or '').strip()

    if not original_text or not modified_text:
        return jsonify({'error': '原始合同和修改后合同文本都不能为空'}), 400

    allowed, remaining, limit = UserQuota.check_and_increment(current_user.id, 'compare')
    if not allowed:
        return jsonify({'error': f'今日对比次数已达上限（{limit}次），请明天再试', 'remaining': 0, 'daily_limit': limit}), 429

    max_len = current_app.config.get('MAX_TEXT_LENGTH', 10000)
    if len(original_text) > max_len or len(modified_text) > max_len:
        return jsonify({
            'error': f'合同文本过长，请控制在 {max_len} 字以内',
        }), 400

    # Call DeepSeek for comparison analysis
    system_prompt = COMPARE_PROMPT.format(
        original_text=original_text,
        modified_text=modified_text,
    )
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': f'请对比分析以上两份合同的差异。'},
    ]

    try:
        ai_response = call_deepseek(messages)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 502

    parsed = _safe_parse_json(ai_response)
    diff_json = None
    interpretation = None

    if parsed and isinstance(parsed, dict):
        try:
            diff_json = json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
        interpretation = parsed.get('overall_assessment') or parsed.get('risk_summary')
    else:
        interpretation = ai_response

    compare = ContractCompare(
        user_id=current_user.id,
        original_text=original_text,
        modified_text=modified_text,
        diff_result=diff_json,
        ai_interpretation=interpretation,
    )

    try:
        db.session.add(compare)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'保存对比结果失败: {str(e)}'}), 500

    return jsonify({
        'message': '对比分析完成',
        'compare': compare.to_dict(),
    }), 201


@api_bp.route('/api/compare/history', methods=['GET'])
@get_current_user()
def compare_history(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 1), 100)

    query = ContractCompare.query.filter_by(user_id=current_user.id).order_by(
        ContractCompare.created_at.desc()
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = [c.to_dict() for c in pagination.items]

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


# ---------------------------------------------------------------------------
# Summary Card Route
# ---------------------------------------------------------------------------

@api_bp.route('/api/card/<int:analysis_id>', methods=['GET'])
@get_current_user()
def get_card(current_user, analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    # Render a summary card as HTML
    risk_level_map = {'high': '高风险', 'medium': '中风险', 'low': '低风险'}
    risk_level_label = risk_level_map.get(analysis.risk_level, '未知')
    mode_map = {'risk': '风险分析', 'summary': '合同摘要', 'plain': '通俗解读'}
    mode_label = mode_map.get(analysis.analysis_mode, analysis.analysis_mode)

    card_html = render_template('card.html', analysis=analysis,
                                 risk_level_label=risk_level_label,
                                 mode_label=mode_label)
    return card_html, 200, {'Content-Type': 'text/html; charset=utf-8'}


# ---------------------------------------------------------------------------
# Streaming analysis endpoint
# ---------------------------------------------------------------------------

@api_bp.route('/api/analysis/stream', methods=['POST'])
@get_current_user()
def stream_analysis(current_user):
    """
    Streaming version of analysis. Returns a SSE (Server-Sent Events) stream.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    mode = (data.get('mode') or 'risk').strip()
    filename = (data.get('filename') or '').strip() or None

    if not text:
        return jsonify({'error': '合同文本不能为空'}), 400

    allowed, remaining, limit = UserQuota.check_and_increment(current_user.id, 'analysis')
    if not allowed:
        return jsonify({'error': f'今日分析次数已达上限（{limit}次），请明天再试', 'remaining': 0, 'daily_limit': limit}), 429

    max_len = current_app.config.get('MAX_TEXT_LENGTH', 10000)
    if len(text) > max_len:
        return jsonify({
            'error': f'合同文本过长，请控制在 {max_len} 字以内',
            'count': len(text),
            'max': max_len,
        }), 400

    if mode not in ('risk', 'summary', 'plain'):
        mode = 'risk'

    # Compute text hash for caching
    text_hash = _compute_text_hash(text)

    # Check cache — if found, return cached result immediately
    cached = _find_cached_analysis(current_user.id, text_hash, mode)
    if cached:
        return jsonify({
            'message': '分析完成（缓存）',
            'analysis': cached.to_dict(),
            'cached': True,
        }), 200

    # Detect contract type (only for risk mode)
    contract_type = 'other'
    if mode == 'risk':
        api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
        contract_type, _ = _detect_contract_type(text, api_key)

    # Build prompt with type-specific focus for risk mode
    system_prompt = _get_mode_prompt(mode)
    if mode == 'risk':
        type_info = CONTRACT_TYPE_FOCUS.get(contract_type, CONTRACT_TYPE_FOCUS['other'])
        system_prompt = system_prompt.format(
            type_focus=f"\n{type_info['zh']}：{type_info['focus']}"
        )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': text},
    ]

    def generate():
        full_response = []
        try:
            stream = call_deepseek(messages, stream=True)
            for chunk in stream:
                full_response.append(chunk)
                yield f'data: {json.dumps({"content": chunk}, ensure_ascii=False)}\n\n'

            # After streaming completes, parse and save the analysis
            raw_text = ''.join(full_response)
            parsed = _robust_json_parse(raw_text)

            # Extract fields
            score = None
            risk_level = None
            one_line_summary = None
            suggestions_json = None
            risk_items_json = None
            result_json = None

            if parsed and isinstance(parsed, dict):
                score = parsed.get('score')
                risk_level = parsed.get('risk_level')
                one_line_summary = parsed.get('one_line_summary')

                suggestions = parsed.get('suggestions')
                if suggestions is not None:
                    try:
                        suggestions_json = json.dumps(suggestions, ensure_ascii=False)
                    except (TypeError, ValueError):
                        pass

                risk_items = parsed.get('risk_items')
                if risk_items is not None:
                    try:
                        risk_items_json = json.dumps(risk_items, ensure_ascii=False)
                    except (TypeError, ValueError):
                        pass

                try:
                    result_json = json.dumps(parsed, ensure_ascii=False)
                except (TypeError, ValueError):
                    result_json = raw_text

                if score is None and risk_level is None:
                    risk_level = 'medium'
            else:
                result_json = raw_text
                one_line_summary = raw_text[:200] if raw_text else None

            if score is not None:
                try:
                    score = int(score)
                except (ValueError, TypeError):
                    score = None

            # Save analysis record
            analysis = Analysis(
                user_id=current_user.id,
                filename=filename,
                contract_text=text,
                text_hash=text_hash,
                contract_type=contract_type,
                analysis_mode=mode,
                result=result_json,
                score=score,
                risk_level=risk_level,
                one_line_summary=one_line_summary,
                suggestions=suggestions_json,
                risk_items=risk_items_json,
            )
            db.session.add(analysis)
            db.session.commit()

            # Send final event with analysis id
            yield f'data: {json.dumps({"done": True, "analysis_id": analysis.id}, ensure_ascii=False)}\n\n'
            yield 'data: [DONE]\n\n'
        except RuntimeError as e:
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'

    return current_app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


# ---------------------------------------------------------------------------
@api_bp.route('/api/analysis/<int:analysis_id>/conversation', methods=['GET'])
@get_current_user()
def get_conversation(current_user, analysis_id):
    """Get the followup conversation history for an analysis."""
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    conv = Conversation.query.filter_by(analysis_id=analysis_id).first()
    if not conv:
        return jsonify({'messages': [], 'conversation_id': None})

    return jsonify({'messages': conv.get_messages(), 'conversation_id': conv.id})


# ---------------------------------------------------------------------------
@api_bp.route('/api/analysis/<int:analysis_id>/followup', methods=['POST'])
@get_current_user()
def analysis_followup(current_user, analysis_id):
    """
    Follow-up question on a previous analysis. Supports streaming.
    """
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': '请输入追问内容'}), 400

    allowed, remaining, limit = UserQuota.check_and_increment(current_user.id, 'followup')
    if not allowed:
        return jsonify({'error': f'今日追问次数已达上限（{limit}次），请明天再试', 'remaining': 0, 'daily_limit': limit}), 429

    # Get or create conversation for persistence
    conv = Conversation.query.filter_by(analysis_id=analysis_id).first()
    if not conv:
        conv = Conversation(user_id=current_user.id, analysis_id=analysis_id)
        db.session.add(conv)
        db.session.commit()

    # Save the user's question to conversation
    conv.add_message('user', question)
    db.session.commit()

    # Build context from previous analysis
    context_parts = [
        f"分析模式: {analysis.analysis_mode}",
        f"评分: {analysis.score}" if analysis.score else None,
        f"风险等级: {analysis.risk_level}" if analysis.risk_level else None,
        f"一句话总结: {analysis.one_line_summary}" if analysis.one_line_summary else None,
    ]
    if analysis.risk_items:
        try:
            risk_items = json.loads(analysis.risk_items)
            context_parts.append("风险条款:")
            for item in risk_items[:5]:
                if isinstance(item, dict):
                    context_parts.append(f"  - {item.get('clause_name', '')}: {item.get('description', '')}")
        except (json.JSONDecodeError, TypeError):
            pass
    if analysis.suggestions:
        try:
            suggestions = json.loads(analysis.suggestions)
            if suggestions:
                context_parts.append("改进建议: " + '、'.join(str(s) for s in suggestions[:5]))
        except (json.JSONDecodeError, TypeError):
            pass

    context = '\n'.join(p for p in context_parts if p)

    # Truncate contract text to save tokens
    contract_text = analysis.contract_text or ''
    if len(contract_text) > 3000:
        contract_text = contract_text[:3000] + '...(已截断)'

    messages = [
        {'role': 'system', 'content': FOLLOWUP_PROMPT},
        {'role': 'assistant', 'content': f'以下是之前的合同分析结果：\n\n{context}\n\n原始合同文本：\n{contract_text}'},
        {'role': 'user', 'content': question},
    ]

    full_response = []

    def generate():
        try:
            stream = call_deepseek(messages, stream=True)
            for chunk in stream:
                full_response.append(chunk)
                yield f'data: {json.dumps({"content": chunk}, ensure_ascii=False)}\n\n'
            # Save full response to conversation after streaming completes
            conv.add_message('assistant', ''.join(full_response))
            db.session.commit()
            yield 'data: [DONE]\n\n'
        except RuntimeError as e:
            yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'

    return current_app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


# Admin Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/admin/stats', methods=['GET'])
@get_current_user()
@admin_required
def admin_stats(current_user):
    total_users = User.query.count()
    total_analyses = Analysis.query.count()

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_analyses = Analysis.query.filter(Analysis.created_at >= today_start).count()

    # Risk distribution
    risk_dist = db.session.query(
        Analysis.risk_level, func.count(Analysis.id)
    ).group_by(Analysis.risk_level).all()
    risk_distribution = {level: count for level, count in risk_dist}

    # ---- Feedback statistics ----
    total_feedback = Feedback.query.count()
    avg_rating = db.session.query(func.avg(Feedback.rating)).filter(Feedback.rating.isnot(None)).scalar()
    avg_rating = round(float(avg_rating), 1) if avg_rating else 0.0

    # NPS: promoters(4-5) - detractors(1-2) / total
    rated = Feedback.query.filter(Feedback.rating.isnot(None)).all()
    if rated:
        promoters = sum(1 for f in rated if f.rating >= 4)
        detractors = sum(1 for f in rated if f.rating <= 2)
        nps = round((promoters - detractors) / len(rated) * 100)
    else:
        nps = 0

    # 7-day daily feedback trend
    daily_feedback = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = Feedback.query.filter(
            func.date(Feedback.created_at) == d
        ).count()
        daily_feedback.append({'date': d.isoformat(), 'count': count})

    # 7-day daily analysis trend
    daily_analysis = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = Analysis.query.filter(
            func.date(Analysis.created_at) == d
        ).count()
        daily_analysis.append({'date': d.isoformat(), 'count': count})

    # Feedback type distribution
    type_dist = db.session.query(
        Feedback.feedback_type, func.count(Feedback.id)
    ).group_by(Feedback.feedback_type).all()
    feedback_type_dist = {ft: count for ft, count in type_dist}

    # Feedback category distribution
    cat_dist = db.session.query(
        Feedback.category, func.count(Feedback.id)
    ).group_by(Feedback.category).all()
    feedback_category_dist = {cat: count for cat, count in cat_dist}

    # Feedback status distribution
    status_dist = db.session.query(
        Feedback.status, func.count(Feedback.id)
    ).group_by(Feedback.status).all()
    feedback_status_dist = {st: count for st, count in status_dist}

    # Rating distribution
    rating_dist = db.session.query(
        Feedback.rating, func.count(Feedback.id)
    ).filter(Feedback.rating.isnot(None)).group_by(Feedback.rating).all()
    feedback_rating_dist = {str(r): count for r, count in rating_dist}

    # Contract type distribution (for admin pie chart)
    ct_dist = db.session.query(
        Analysis.contract_type, func.count(Analysis.id)
    ).filter(Analysis.contract_type.isnot(None)).group_by(Analysis.contract_type).all()
    contract_type_dist = {ct: count for ct, count in ct_dist}

    # User registration trend (7-day)
    daily_registrations = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = User.query.filter(
            func.date(User.created_at) == d
        ).count()
        daily_registrations.append({'date': d.isoformat(), 'count': count})

    # Score distribution (for histogram)
    score_dist = db.session.query(
        Analysis.score, func.count(Analysis.id)
    ).filter(Analysis.score.isnot(None)).group_by(Analysis.score).all()
    score_distribution = {str(s): count for s, count in score_dist}

    # Active users (users who analyzed in last 7 days)
    week_ago = date.today() - timedelta(days=7)
    active_users = db.session.query(func.count(func.distinct(Analysis.user_id))).filter(
        func.date(Analysis.created_at) >= week_ago
    ).scalar()

    # Mode distribution
    mode_dist = db.session.query(
        Analysis.analysis_mode, func.count(Analysis.id)
    ).group_by(Analysis.analysis_mode).all()
    mode_distribution = {m: count for m, count in mode_dist}

    return jsonify({
        'total_users': total_users,
        'total_analyses': total_analyses,
        'today_analyses': today_analyses,
        'risk_distribution': risk_distribution,
        'total_feedback': total_feedback,
        'avg_rating': avg_rating,
        'nps': nps,
        'daily_feedback_trend': daily_feedback,
        'daily_analysis_trend': daily_analysis,
        'feedback_type_dist': feedback_type_dist,
        'feedback_category_dist': feedback_category_dist,
        'feedback_status_dist': feedback_status_dist,
        'feedback_rating_dist': feedback_rating_dist,
        'contract_type_dist': contract_type_dist,
        'daily_registrations': daily_registrations,
        'score_distribution': score_distribution,
        'active_users_7d': active_users or 0,
        'mode_distribution': mode_distribution,
    })


@api_bp.route('/api/admin/users', methods=['GET'])
@get_current_user()
@admin_required
def admin_users(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 1), 100)

    query = db.session.query(
        User, func.count(Analysis.id).label('analysis_count')
    ).outerjoin(Analysis, User.id == Analysis.user_id).group_by(User.id).order_by(User.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for user, count in pagination.items:
        user_dict = user.to_dict()
        user_dict['analysis_count'] = count
        items.append(user_dict)

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/api/admin/analyses', methods=['GET'])
@get_current_user()
@admin_required
def admin_analyses(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 1), 100)

    query = Analysis.query.order_by(Analysis.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = [a.to_dict() for a in pagination.items]

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


# ---------------------------------------------------------------------------
# Feedback Routes
# ---------------------------------------------------------------------------

@api_bp.route('/api/feedback', methods=['POST'])
@get_current_user()
def create_feedback(current_user):
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()

    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400

    feedback = Feedback(
        user_id=current_user.id,
        username=current_user.username,
        title=title,
        content=content,
        feedback_type=(data.get('feedback_type') or 'bug')[:20],
        category=(data.get('category') or '')[:50],
        rating=data.get('rating'),
        contact_email=(data.get('contact_email') or '')[:120],
    )

    try:
        db.session.add(feedback)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Save failed: {str(e)}'}), 500

    return jsonify({'message': 'Feedback submitted', 'feedback': feedback.to_dict()}), 201


@api_bp.route('/api/feedback', methods=['GET'])
@get_current_user()
@admin_required
def list_feedback(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('feedback_type', '').strip()

    query = Feedback.query.order_by(Feedback.created_at.desc())

    if status_filter and status_filter != 'all':
        query = query.filter(Feedback.status == status_filter)
    if type_filter and type_filter != 'all':
        query = query.filter(Feedback.feedback_type == type_filter)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [fb.to_dict() for fb in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/api/feedback/<int:fb_id>', methods=['GET'])
@get_current_user()
@admin_required
def get_feedback(current_user, fb_id):
    fb = db.session.get(Feedback, fb_id)
    if not fb:
        return jsonify({'error': 'Feedback not found'}), 404
    return jsonify({'feedback': fb.to_dict()})


@api_bp.route('/api/feedback/<int:fb_id>', methods=['PUT'])
@get_current_user()
@admin_required
def update_feedback(current_user, fb_id):
    fb = db.session.get(Feedback, fb_id)
    if not fb:
        return jsonify({'error': 'Feedback not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'status' in data:
        fb.status = data['status'][:20]
    if 'admin_reply' in data:
        fb.admin_reply = data.get('admin_reply', '')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Update failed: {str(e)}'}), 500

    return jsonify({'message': 'Updated', 'feedback': fb.to_dict()})


@api_bp.route('/api/feedback/<int:fb_id>', methods=['DELETE'])
@get_current_user()
@admin_required
def delete_feedback(current_user, fb_id):
    fb = db.session.get(Feedback, fb_id)
    if not fb:
        return jsonify({'error': 'Feedback not found'}), 404

    try:
        db.session.delete(fb)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

    return jsonify({'message': 'Deleted'})


@api_bp.route('/api/admin/feedback', methods=['GET'])
@get_current_user()
@admin_required
def admin_feedback_list(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    feedback_type = request.args.get('type', '').strip()
    status = request.args.get('status', '').strip()
    per_page = min(max(per_page, 1, 100), 100)

    query = Feedback.query.order_by(Feedback.created_at.desc())
    if feedback_type:
        query = query.filter_by(feedback_type=feedback_type)
    if status:
        query = query.filter_by(status=status)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = [f.to_dict() for f in pagination.items]

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/api/quota', methods=['GET'])
@get_current_user()
def get_user_quota(current_user):
    """Get current user's remaining analysis quota for today."""
    from models import UserQuota
    quota = UserQuota.get_today_quota(current_user.id)
    daily_limit = 20
    return jsonify({
        'analysis': {
            'used': quota.analysis_count,
            'remaining': max(0, daily_limit - quota.analysis_count),
            'limit': daily_limit,
        },
        'compare': {
            'used': quota.compare_count,
            'remaining': max(0, daily_limit - quota.compare_count),
            'limit': daily_limit,
        },
        'followup': {
            'used': quota.followup_count,
            'remaining': max(0, 50 - quota.followup_count),
            'limit': 50,
        },
    })


# ---------------------------------------------------------------------------
# User Dashboard API
# ---------------------------------------------------------------------------

@api_bp.route('/api/dashboard', methods=['GET'])
@get_current_user()
def user_dashboard(current_user):
    """Get data for the user's personal dashboard."""
    from models import UserQuota

    # Quota
    quota = UserQuota.get_today_quota(current_user.id)
    daily_limit = 20

    # Recent analyses (last 5)
    recent = Analysis.query.filter_by(user_id=current_user.id).order_by(
        Analysis.created_at.desc()
    ).limit(5).all()
    recent_items = [a.to_dict() for a in recent]

    # Total stats
    total_analyses = Analysis.query.filter_by(user_id=current_user.id).count()
    total_compares = ContractCompare.query.filter_by(user_id=current_user.id).count()

    # 7-day trend
    daily_trend = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        count = Analysis.query.filter(
            Analysis.user_id == current_user.id,
            func.date(Analysis.created_at) == d
        ).count()
        daily_trend.append({'date': d.isoformat(), 'count': count})

    # Risk distribution of user's analyses
    risk_dist_query = db.session.query(
        Analysis.risk_level, func.count(Analysis.id)
    ).filter(Analysis.user_id == current_user.id).group_by(Analysis.risk_level).all()
    risk_dist = {level: count for level, count in risk_dist_query}

    # Contract type distribution
    type_dist_query = db.session.query(
        Analysis.contract_type, func.count(Analysis.id)
    ).filter(
        Analysis.user_id == current_user.id,
        Analysis.contract_type.isnot(None)
    ).group_by(Analysis.contract_type).all()
    type_dist = {t: count for t, count in type_dist_query}

    # Average score
    avg_score = db.session.query(func.avg(Analysis.score)).filter(
        Analysis.user_id == current_user.id,
        Analysis.score.isnot(None)
    ).scalar()
    avg_score = round(float(avg_score), 1) if avg_score else None

    # High risk count (needs attention)
    high_risk_count = Analysis.query.filter(
        Analysis.user_id == current_user.id,
        Analysis.risk_level == 'high'
    ).count()

    return jsonify({
        'quota': {
            'analysis_used': quota.analysis_count,
            'analysis_remaining': max(0, daily_limit - quota.analysis_count),
            'analysis_limit': daily_limit,
            'compare_used': quota.compare_count,
            'followup_used': quota.followup_count,
        },
        'recent_analyses': recent_items,
        'stats': {
            'total_analyses': total_analyses,
            'total_compares': total_compares,
            'avg_score': avg_score,
            'high_risk_count': high_risk_count,
        },
        'daily_trend': daily_trend,
        'risk_distribution': risk_dist,
        'contract_type_distribution': type_dist,
    })


# ---------------------------------------------------------------------------
# PDF Export API
# ---------------------------------------------------------------------------

@api_bp.route('/api/analysis/<int:analysis_id>/export', methods=['GET'])
@get_current_user()
def export_analysis_pdf(current_user, analysis_id):
    """Export analysis result as a styled HTML page (printable as PDF)."""
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
    if not analysis:
        return jsonify({'error': '分析记录不存在'}), 404

    # Parse result
    result = {}
    if analysis.result:
        try:
            result = json.loads(analysis.result)
        except (json.JSONDecodeError, TypeError):
            pass

    risk_items = []
    if analysis.risk_items:
        try:
            risk_items = json.loads(analysis.risk_items)
        except (json.JSONDecodeError, TypeError):
            pass

    suggestions = []
    if analysis.suggestions:
        try:
            suggestions = json.loads(analysis.suggestions)
        except (json.JSONDecodeError, TypeError):
            pass

    contract_type_map = {
        'labor': '劳动合同', 'rental': '房屋租赁', 'purchase': '买卖合同',
        'service': '服务合同', 'nda': '保密协议', 'loan': '借款合同',
        'partnership': '合伙协议', 'franchise': '加盟合同', 'agency': '委托合同',
        'construction': '建设工程', 'insurance': '保险合同', 'other': '其他',
    }
    contract_type_label = contract_type_map.get(analysis.contract_type, '其他')

    risk_colors = {'high': '#D45050', 'medium': '#E8A33D', 'low': '#2D9D78'}
    risk_labels = {'high': '高风险', 'medium': '中风险', 'low': '低风险'}

    # Build printable HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>DocAI 合同分析报告 - {escape_html(analysis.filename or "合同分析")}</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', 'Noto Sans SC', -apple-system, sans-serif; color: #1A2332; line-height: 1.6; padding: 40px; max-width: 800px; margin: 0 auto; }}
  .header {{ text-align: center; margin-bottom: 32px; padding-bottom: 20px; border-bottom: 2px solid #1B365D; }}
  .header h1 {{ font-size: 24px; color: #1B365D; margin-bottom: 8px; }}
  .header p {{ font-size: 13px; color: #8892A0; }}
  .meta {{ display: flex; gap: 24px; margin-bottom: 24px; flex-wrap: wrap; }}
  .meta-item {{ font-size: 13px; color: #5A6677; }}
  .meta-item strong {{ color: #1A2332; }}
  .score-section {{ text-align: center; padding: 24px; background: #F1F4F8; border-radius: 12px; margin-bottom: 24px; }}
  .score-number {{ font-size: 48px; font-weight: 700; color: {risk_colors.get(analysis.risk_level, "#2D9D78")}; }}
  .score-label {{ font-size: 14px; color: #5A6677; }}
  .summary-box {{ background: #F1F4F8; border-left: 4px solid #2D9D78; padding: 16px; border-radius: 8px; margin-bottom: 24px; font-size: 14px; color: #1A2332; }}
  .section-title {{ font-size: 18px; font-weight: 700; color: #1B365D; margin: 24px 0 16px; padding-bottom: 8px; border-bottom: 1px solid #E8ECF1; }}
  .risk-item {{ border: 1px solid #E8ECF1; border-radius: 8px; padding: 16px; margin-bottom: 12px; page-break-inside: avoid; }}
  .risk-item-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .risk-badge {{ font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; color: white; }}
  .risk-name {{ font-weight: 600; font-size: 14px; }}
  .risk-field {{ font-size: 13px; color: #5A6677; margin-bottom: 4px; }}
  .risk-field strong {{ color: #1A2332; }}
  .suggestion-item {{ background: #E6F5F0; padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; color: #1F7D5C; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #E8ECF1; text-align: center; font-size: 11px; color: #8892A0; }}
  @media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>DocAI 合同分析报告</h1>
  <p>AI 智能合同分析平台 | 生成时间: {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}</p>
</div>
<div class="meta">
  <div class="meta-item"><strong>文件名:</strong> {escape_html(analysis.filename or "粘贴文本")}</div>
  <div class="meta-item"><strong>分析模式:</strong> {{"风险分析" if analysis.analysis_mode == "risk" else "合同摘要" if analysis.analysis_mode == "summary" else "通俗解读"}}</div>
  <div class="meta-item"><strong>合同类型:</strong> {contract_type_label}</div>
  <div class="meta-item"><strong>分析时间:</strong> {analysis.created_at.strftime("%Y-%m-%d %H:%M") if analysis.created_at else "-"}</div>
</div>'''

    # Score section
    score_val = analysis.score if analysis.score is not None else '--'
    risk_label = risk_labels.get(analysis.risk_level, '未知')
    html += f'''
<div class="score-section">
  <div class="score-number">{score_val}</div>
  <div class="score-label">综合评分 · {risk_label}</div>
</div>'''

    # One-line summary
    if analysis.one_line_summary:
        html += f'''
<div class="summary-box">
  <strong>核心摘要:</strong> {escape_html(analysis.one_line_summary)}
</div>'''

    # Risk items
    if risk_items:
        html += '<div class="section-title">风险条款详情</div>'
        for idx, item in enumerate(risk_items, 1):
            if not isinstance(item, dict):
                continue
            rl = item.get('risk_level', 'medium')
            color = risk_colors.get(rl, '#8892A0')
            rl_label = risk_labels.get(rl, '未知')
            name = escape_html(item.get('clause_name', f'风险条款 {idx}'))
            location = escape_html(item.get('clause_location', ''))
            desc = escape_html(item.get('description', ''))
            plain = escape_html(item.get('plain_explanation', ''))
            suggestion = escape_html(item.get('suggestion', ''))
            legal = escape_html(item.get('legal_basis', ''))

            html += f'''
<div class="risk-item">
  <div class="risk-item-header">
    <span class="risk-badge" style="background: {color};">{rl_label}</span>
    <span class="risk-name">{name}</span>
    {f'<span style="font-size:12px;color:#8892A0;">{location}</span>' if location else ''}
  </div>
  <div class="risk-field">{desc}</div>'''
            if plain:
                html += f'''<div class="risk-field" style="color:#2D9D78;"><strong>通俗解读:</strong> {plain}</div>'''
            if suggestion:
                html += f'''<div class="suggestion-item"><strong>修改建议:</strong> {suggestion}</div>'''
            if legal:
                html += f'''<div class="risk-field"><strong>法律依据:</strong> {legal}</div>'''
            html += '</div>'

    # Suggestions
    if suggestions:
        html += '<div class="section-title">总体改进建议</div>'
        for s in suggestions:
            html += f'<div class="suggestion-item">{escape_html(str(s))}</div>'

    # Footer
    html += '''
<div class="footer">
  <p>本报告由 DocAI AI 智能合同分析平台自动生成，仅供参考，不构成法律意见。</p>
  <p>DocAI &copy; 2026 | 用 AI 守护每一份合同权益</p>
</div>
</body></html>'''

    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


def escape_html(text):
    """Basic HTML escaping for PDF export."""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# ---------------------------------------------------------------------------
# Page routes (render Jinja2 templates)
# ---------------------------------------------------------------------------

@api_bp.route('/')
def page_index():
    return render_template('index.html', current_user=None)

@api_bp.route('/dashboard')
def page_dashboard():
    return render_template('dashboard.html', current_user=None)

@api_bp.route('/analyze')
def page_analyze():
    return render_template('analyze.html', current_user=None)

@api_bp.route('/archive')
def page_archive():
    return render_template('archive.html', current_user=None)

@api_bp.route('/compare')
def page_compare():
    return render_template('compare.html', current_user=None)

@api_bp.route('/pricing')
def page_pricing():
    return render_template('pricing.html', current_user=None)

@api_bp.route('/about')
def page_about():
    return render_template('about.html', current_user=None)

@api_bp.route('/login')
def page_login():
    return render_template('login.html')

@api_bp.route('/admin')
def page_admin():
    return render_template('admin.html', current_user=None)

@api_bp.route('/detail/<int:analysis_id>')
def page_detail(analysis_id):
    return render_template('detail.html', analysis_id=analysis_id, current_user=None)