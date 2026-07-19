import json
import requests as http_requests
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, request, jsonify, current_app, make_response, render_template
)
from sqlalchemy import or_, func

from models import db, User, Analysis, RiskPreference, ContractCompare, Feedback
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
    import re
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

RISK_ANALYSIS_PROMPT = """你是一位专业的合同风险分析律师。请仔细分析以下合同文本，找出所有潜在风险点。

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{
  "score": <0-100的整数，分数越低风险越高>,
  "risk_level": "<high/medium/low>",
  "one_line_summary": "<一句话总结该合同的核心风险>",
  "risk_items": [
    {
      "clause_name": "<条款名称>",
      "risk_level": "<high/medium/low>",
      "description": "<具体风险描述>",
      "suggestion": "<修改建议>"
    }
  ],
  "suggestions": ["<总体建议1>", "<总体建议2>"]
}

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

    if not text:
        return jsonify({'error': '合同文本不能为空'}), 400

    max_len = current_app.config.get('MAX_TEXT_LENGTH', 10000)
    if len(text) > max_len:
        return jsonify({
            'error': f'合同文本过长，请控制在 {max_len} 字以内',
            'count': len(text),
            'max': max_len,
        }), 400

    if mode not in ('risk', 'summary', 'plain'):
        mode = 'risk'

    # Load user risk preferences for risk analysis mode
    user_prefs = []
    if mode == 'risk':
        pref_obj = RiskPreference.query.filter_by(user_id=current_user.id).first()
        if pref_obj:
            user_prefs = pref_obj.get_preferences_list()

    # Build prompt
    system_prompt = _get_mode_prompt(mode)
    if mode == 'risk' and user_prefs:
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
    parsed = _safe_parse_json(ai_response)

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

    # Create analysis record
    analysis = Analysis(
        user_id=current_user.id,
        filename=filename,
        contract_text=text,
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

    max_len = current_app.config.get('MAX_TEXT_LENGTH', 10000)
    if len(text) > max_len:
        return jsonify({
            'error': f'合同文本过长，请控制在 {max_len} 字以内',
            'count': len(text),
            'max': max_len,
        }), 400

    if mode not in ('risk', 'summary', 'plain'):
        mode = 'risk'

    # Build prompt
    system_prompt = _get_mode_prompt(mode)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': text},
    ]

    def generate():
        try:
            stream = call_deepseek(messages, stream=True)
            for chunk in stream:
                yield f'data: {json.dumps({"content": chunk}, ensure_ascii=False)}\n\n'
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


# ---------------------------------------------------------------------------
# Page routes (render Jinja2 templates)
# ---------------------------------------------------------------------------

@api_bp.route('/')
def page_index():
    return render_template('index.html', current_user=None)

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