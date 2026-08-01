"""Multilingual contract analysis support for DocAI.

This module provides:
- Lightweight language detection (zh / en)
- Language-specific legal term glossaries
- Multilingual system prompts for risk / summary / plain-language analysis
- English contract few-shot training examples
- Legal basis mapping per jurisdiction
"""

import json
import re
from typing import List, Dict, Any

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

SUPPORTED_LANGUAGES = {'zh', 'en'}
DEFAULT_LANGUAGE = 'en'

# Regex ranges for CJK characters (used as a fast pre-filter for Chinese text)
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]')

# ---------------------------------------------------------------------------
# Legal term glossaries (mirrored in legal_terms.js for frontend highlighting)
# ---------------------------------------------------------------------------

LEGAL_TERMS_ZH = {
    '违约金': '一方不履行合同约定时向对方支付的赔偿金额',
    '不可抗力': '不能预见、避免且克服的客观情况导致无法履约可免责',
    '管辖权': '发生纠纷时由哪个法院来审理',
    '保密条款': '要求合同双方不得向第三方泄露合同内容的约定',
    '违约责任': '一方不履行或不完全履行合同义务时需要承担的法律后果',
    '合同解除': '在特定条件下提前结束合同的效力',
    '连带责任': '多个债务人对同一债务共同承担责任',
    '免责条款': '约定在某些特定情况下免除一方责任的条款',
    '仲裁': '由双方选定的仲裁机构而非法院来裁决纠纷',
    '保证': '由第三人为债务人的债务提供担保',
    '赔偿损失': '因违约或侵权行为给对方造成经济损失时支付等额赔偿金',
    '竞业限制': '员工离职后一段时间内不得从事与原单位竞争的工作',
    '试用期': '劳动合同中约定的考察期',
    '经济补偿金': '劳动合同解除或终止时用人单位依法向劳动者支付的经济补偿',
    '知识产权': '人们对自己的智力成果享有的专有权利',
    '诉讼时效': '法律保护权利的时间限制',
    '抵押': '将财产作为担保，不转移占有',
    '质押': '将动产或权利凭证交给债权人占有作为担保',
    '法人': '依法成立、有独立财产、能独立承担民事责任的组织',
    '生效条件': '合同开始产生法律效力的条件',
    '格式条款': '一方预先拟定、不可协商的合同条款',
}

LEGAL_TERMS_EN = {
    'Indemnification': 'One party compensates another for losses or third-party claims',
    'Force Majeure': 'Unforeseeable events excusing performance',
    'Governing Law': 'The law used to interpret the contract',
    'Jurisdiction': 'The court or forum that hears disputes',
    'Confidentiality': 'Obligation to keep contract information secret',
    'Termination': 'Ending the contract before natural expiration',
    'Liquidated Damages': 'Pre-agreed sum payable on breach',
    'Intellectual Property': 'Exclusive rights to creations of the mind',
    'Non-Compete': 'Restriction on competing after contract ends',
    'Arbitration': 'Dispute resolution by an arbitrator instead of court',
    'Breach of Contract': 'Failure to perform contractual obligations',
    'Limitation of Liability': 'Cap on damages one party must pay',
    'Warranty': 'A guarantee about facts or future performance',
    'Assignment': 'Transfer of contractual rights or duties',
    'Severability': 'Invalid provisions do not void the entire contract',
    'Consideration': 'Something of value exchanged to form a contract',
    'Representations and Warranties': 'Statements of fact and promises about future conditions',
    'Dispute Resolution': 'Process for resolving conflicts under the contract',
}

LEGAL_BASIS_MAP = {
    'zh': {
        'contract': '《中华人民共和国民法典》合同编',
        'labor': '《中华人民共和国劳动合同法》',
        'consumer': '《中华人民共和国消费者权益保护法》',
        'ip': '《中华人民共和国著作权法》《专利法》《商标法》',
    },
    'en': {
        'contract': 'Uniform Commercial Code (UCC) / common law contract principles',
        'labor': 'Fair Labor Standards Act (FLSA) and applicable state employment law',
        'consumer': 'Consumer Protection Act / FTC Act',
        'ip': 'Copyright Act, Patent Act, Lanham Act (US)',
    }
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

RISK_ANALYSIS_PROMPT_ZH = """你是一位资深合同审查律师，拥有 10 年以上的合同审查经验。你的任务是找出合同中的所有潜在风险点。

{type_focus}{stance_prompt}{plain_lang_prompt}

请以严格的 JSON 格式返回分析结果，不要包含任何其他文字说明。JSON 结构如下：
{{
  "contract_type": "<合同类型，如 labor/rental/purchase/service/nda/loan/other>",
  "score": <0-100 的整数，100=极安全，0=极高风险>,
  "risk_level": "<high/medium/low>",
  "one_line_summary": "<一句话总结该合同的核心风险，不超过 50 字>",
  "risk_items": [
    {{
      "clause_name": "<条款名称>",
      "clause_location": "<条款所在位置，如'第三条第二款'>",
      "risk_level": "<high/medium/low>",
      "description": "<具体风险描述，2-3 句话>",
      "plain_explanation": "<大白话解读，不超过30字>",
      "suggestion": "<修改建议，具体的操作性建议>",
      "legal_basis": "<相关法律依据，如'《民法典》第585条'>"
    }}
  ],
  "suggestions": ["<总体改进建议1>", "<总体改进建议2>"],
  "key_obligations": [
    {{"party": "<甲方/乙方>", "obligation": "<核心义务>"}}
  ]
}}

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

RISK_ANALYSIS_PROMPT_EN = """You are a senior contract review attorney with 10+ years of experience. Identify all potential risks in the contract below.

{type_focus}{stance_prompt}{plain_lang_prompt}

Return STRICTLY VALID JSON with this structure:
{{
  "contract_type": "labor/rental/purchase/service/nda/loan/other",
  "score": <integer 0-100>,
  "risk_level": "high/medium/low",
  "one_line_summary": "One-sentence core risk summary, max 80 characters",
  "risk_items": [
    {{
      "clause_name": "Clause name, e.g. Indemnification Clause",
      "clause_location": "Clause location, e.g. Section 3.2",
      "risk_level": "high/medium/low",
      "description": "2-3 sentences explaining why this clause is risky",
      "plain_explanation": "Plain-language explanation, max 50 words",
      "suggestion": "Actionable revision suggestion",
      "legal_basis": "Relevant legal basis, e.g. UCC 2-207 / common law"
    }}
  ],
  "suggestions": ["Overall improvement 1", "Overall improvement 2"],
  "key_obligations": [
    {{"party": "Party A / Party B", "obligation": "Core obligation"}}
  ]
}}

Scoring:
- 90-100: well-drafted, very low risk
- 70-89: minor low-risk issues
- 50-69: moderate risk, revisions recommended
- 30-49: multiple high-risk clauses, major revisions needed
- 0-29: severe problems, not recommended for signing

Requirements:
1. Identify at least 3 and at most 10 risk clauses
2. Each risk must include a concrete revision suggestion
3. Focus on unfair terms, mandatory-law violations, and ambiguous language
4. Flag any blank fields awaiting completion

Ensure the response is valid JSON."""

SUMMARY_PROMPT_ZH = """你是一位专业的合同分析助手。请对以下合同文本进行全面的摘要分析。

请以严格的 JSON 格式返回分析结果：
{{
  "one_line_summary": "<一句话概括合同核心内容>",
  "key_points": [{{"point": "<要点标题>", "detail": "<详细说明>"}}],
  "parties": [{{"name": "<甲方/乙方名称>", "role": "<角色描述>"}}],
  "important_dates": [{{"date": "<日期>", "event": "<事件描述>"}}],
  "obligations": [{{"party": "<义务方>", "obligation": "<义务内容>"}}]
}}

请确保返回有效的 JSON。"""

SUMMARY_PROMPT_EN = """You are a professional contract analyst. Provide a comprehensive summary of the contract below.

Return STRICTLY VALID JSON:
{{
  "one_line_summary": "One-sentence summary of the contract core content",
  "key_points": [{{"point": "Key point title", "detail": "Detailed explanation"}}],
  "parties": [{{"name": "Party name", "role": "Role description"}}],
  "important_dates": [{{"date": "Date", "event": "Event description"}}],
  "obligations": [{{"party": "Obligor", "obligation": "Obligation content"}}]
}}

Ensure the response is valid JSON."""

PLAIN_LANGUAGE_PROMPT_ZH = """你是一位擅长将法律文书翻译为通俗语言的专家。请将以下合同文本翻译成普通人也能理解的通俗语言。

请以严格的 JSON 格式返回分析结果：
{{
  "one_line_summary": "<一句话通俗概括>",
  "plain_explanation": "<完整的通俗语言版本>",
  "key_terms": [{{"term": "<专业术语>", "plain_explanation": "<通俗解释>"}}],
  "things_to_watch": [{{"item": "<需要注意的事项>", "why_important": "<为什么重要>", "suggestion": "<建议>"}}]
}}

请确保返回有效的 JSON。"""

PLAIN_LANGUAGE_PROMPT_EN = """You are an expert at translating legal documents into plain language. Convert the contract below into language an ordinary person can understand.

Return STRICTLY VALID JSON:
{{
  "one_line_summary": "One-sentence plain summary",
  "plain_explanation": "Full plain-language version",
  "key_terms": [{{"term": "Professional term", "plain_explanation": "Plain explanation"}}],
  "things_to_watch": [{{"item": "Thing to watch", "why_important": "Why it matters", "suggestion": "Suggestion"}}]
}}

Ensure the response is valid JSON."""

PLAIN_LANGUAGE_INJECTION_ZH = """\n\n重要补充要求：在返回的 risk_items 中，每个风险条款额外增加一个 "plain_explanation" 字段，用通俗易懂的大白话解释该风险（不超过30字），让没有法律背景的人也能理解。同时在 suggestion 字段中给出具体的修改建议措辞。"""

PLAIN_LANGUAGE_INJECTION_EN = """\n\nImportant: In each risk_items entry, include a "plain_explanation" field that explains the risk in plain language (max 50 words) so non-lawyers can understand. Also provide concrete suggested revision wording in the suggestion field."""

REVIEW_STANCE_PROMPTS_ZH = {
    'party_a': '\n\n审查立场：你代表甲方（合同中提供产品/服务/资金的一方）。请特别关注保护甲方权益的条款，如付款条件、交付标准、违约责任上限、知识产权归属、保密期限等。',
    'party_b': '\n\n审查立场：你代表乙方（合同中接收产品/服务/资金的一方）。请特别关注保护乙方权益的条款，如付款期限、验收标准、违约金合理性、免责条款、竞业限制补偿、合同解除权等。',
}

REVIEW_STANCE_PROMPTS_EN = {
    'party_a': '\n\nReview stance: You represent Party A (the provider of products/services/funds). Focus on protecting Party A interests, such as payment terms, delivery standards, liability caps, IP ownership, and confidentiality periods.',
    'party_b': '\n\nReview stance: You represent Party B (the recipient of products/services/funds). Focus on protecting Party B interests, such as payment deadlines, acceptance criteria, reasonableness of liquidated damages, exclusion clauses, non-compete compensation, and termination rights.',
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """Detect contract language; return 'zh' or 'en'.

    Uses a fast CJK-character pre-filter before falling back to langdetect,
    because short Chinese contract snippets are occasionally misclassified.
    """
    if not text or not text.strip():
        return DEFAULT_LANGUAGE

    cleaned = text.strip()
    total_chars = len(cleaned)
    cjk_chars = len(CJK_RE.findall(cleaned))

    # If more than 15% of characters are CJK, treat it as Chinese.
    # This threshold catches mixed short texts while avoiding false positives.
    if total_chars > 0 and cjk_chars / total_chars > 0.15:
        return 'zh'

    try:
        lang = detect(cleaned)
        if lang in SUPPORTED_LANGUAGES:
            return lang
        if lang.startswith('zh'):
            return 'zh'
        return DEFAULT_LANGUAGE
    except LangDetectException:
        return DEFAULT_LANGUAGE


def get_legal_terms(language: str) -> Dict[str, str]:
    """Return the legal term glossary for the given language."""
    if language == 'zh':
        return LEGAL_TERMS_ZH
    return LEGAL_TERMS_EN


def get_legal_basis(language: str, domain: str = 'contract') -> str:
    """Return jurisdiction-specific legal basis hint."""
    return LEGAL_BASIS_MAP.get(language, LEGAL_BASIS_MAP['en']).get(domain, '')


def get_review_stance_prompt(language: str, stance: str) -> str:
    """Return language-appropriate review stance prompt."""
    prompts = REVIEW_STANCE_PROMPTS_ZH if language == 'zh' else REVIEW_STANCE_PROMPTS_EN
    return prompts.get(stance, '')


def build_analysis_prompt(language: str, mode: str, **kwargs) -> str:
    """Build the system prompt for a given language and analysis mode."""
    if mode == 'risk':
        base = RISK_ANALYSIS_PROMPT_ZH if language == 'zh' else RISK_ANALYSIS_PROMPT_EN
        type_focus = kwargs.get('type_focus', '')
        stance = kwargs.get('stance', '')
        plain = kwargs.get('plain', '')
        return base.format(type_focus=type_focus, stance_prompt=stance, plain_lang_prompt=plain)
    if mode == 'summary':
        return SUMMARY_PROMPT_ZH if language == 'zh' else SUMMARY_PROMPT_EN
    if mode == 'plain':
        return PLAIN_LANGUAGE_PROMPT_ZH if language == 'zh' else PLAIN_LANGUAGE_PROMPT_EN
    return RISK_ANALYSIS_PROMPT_ZH


def get_plain_language_injection(language: str) -> str:
    return PLAIN_LANGUAGE_INJECTION_ZH if language == 'zh' else PLAIN_LANGUAGE_INJECTION_EN


# ---------------------------------------------------------------------------
# Few-shot training examples for English contracts
# ---------------------------------------------------------------------------

def build_few_shot_messages(language: str, mode: str) -> List[Dict[str, str]]:
    """Build few-shot example messages for English risk analysis."""
    if language != 'en' or mode != 'risk':
        return []
    try:
        from training_data.english_contract_examples import ENGLISH_EXAMPLES
    except ImportError:
        return []

    messages: List[Dict[str, str]] = []
    for ex in ENGLISH_EXAMPLES:
        messages.append({'role': 'user', 'content': ex['text']})
        messages.append({'role': 'assistant', 'content': json.dumps(ex['expected'], ensure_ascii=False)})
    return messages
