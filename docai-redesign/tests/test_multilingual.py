import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from multilingual import (
    detect_language,
    build_analysis_prompt,
    get_legal_terms,
    get_legal_basis,
    get_review_stance_prompt,
    get_plain_language_injection,
)


def test_detect_chinese():
    text = "本合同由甲方（出租方）与乙方（承租方）签订。"
    assert detect_language(text) == 'zh'


def test_detect_english():
    text = "This Agreement is entered into between Landlord and Tenant."
    assert detect_language(text) == 'en'


def test_detect_unknown_defaults_en():
    assert detect_language("") == 'en'
    assert detect_language("   ") == 'en'


def test_build_analysis_prompt_en():
    prompt = build_analysis_prompt('en', 'risk', type_focus='', stance='', plain='')
    assert 'senior contract review attorney' in prompt
    assert 'STRICTLY VALID JSON' in prompt


def test_build_analysis_prompt_zh():
    prompt = build_analysis_prompt('zh', 'risk', type_focus='', stance='', plain='')
    assert '资深合同审查律师' in prompt
    assert 'JSON' in prompt


def test_get_legal_terms():
    assert '违约金' in get_legal_terms('zh')
    assert 'Indemnification' in get_legal_terms('en')


def test_get_legal_basis():
    assert '民法典' in get_legal_basis('zh', 'contract')
    assert 'UCC' in get_legal_basis('en', 'contract')


def test_review_stance_prompts():
    assert '甲方' in get_review_stance_prompt('zh', 'party_a')
    assert 'Party A' in get_review_stance_prompt('en', 'party_a')


def test_plain_language_injection():
    assert 'plain_explanation' in get_plain_language_injection('en')
    assert 'plain_explanation' in get_plain_language_injection('zh')
