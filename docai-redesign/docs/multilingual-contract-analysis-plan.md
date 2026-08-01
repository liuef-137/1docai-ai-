# 多语言合同分析实现计划

> **目标：** 让 DocAI 能自动识别合同语言，使用对应语种的法律 NLP 提示与术语库，并通过英文合同模板训练数据提升英文合同分析质量。

> **架构：** 在既有 DeepSeek API 流程前增加轻量语言检测；按检测语言切换 system prompt、法律依据引用、术语高亮库；引入英文合同 few-shot 模板作为上下文示例；数据库新增 `language` 字段记录每份合同语言。

> **技术栈：** Python Flask、SQLite、DeepSeek API、`langdetect`、JavaScript（前端术语高亮）

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `server/multilingual.py` | 语言检测、多语言 prompt 构建、英文合同模板训练数据、术语库加载 |
| `server/models.py` | `Analysis` 表新增 `language` 字段 |
| `server/routes.py` | 在 `/api/analysis` 中接入语言检测与多语言提示 |
| `server/app.py` | 自动迁移 `analysis.language` 列 |
| `legal_terms.js` | 扩展英文法律术语高亮库 |
| `server/templates/analyze.html` | 上传/分析界面显示检测语言、支持语言提示 |
| `server/i18n_translations.py` | 补充多语言相关 i18n key |
| `server/requirements.txt` | 添加 `langdetect` 依赖 |
| `tests/test_multilingual.py` | 语言检测与 prompt 构建单元测试 |

---

## Task 1：添加语言检测依赖与模块

**Files:**
- Modify: `server/requirements.txt`
- Create: `server/multilingual.py`
- Test: `tests/test_multilingual.py`

- [ ] **Step 1：添加依赖**

在 `server/requirements.txt` 末尾追加：
```text
langdetect==1.0.9
```

- [ ] **Step 2：创建语言检测函数测试**

```python
# tests/test_multilingual.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from multilingual import detect_language

def test_detect_chinese():
    text = "本合同由甲方（出租方）与乙方（承租方）签订。"
    assert detect_language(text) == 'zh'

def test_detect_english():
    text = "This Agreement is entered into between Landlord and Tenant."
    assert detect_language(text) == 'en'

def test_detect_unknown_defaults_en():
    text = ""
    assert detect_language(text) == 'en'
```

- [ ] **Step 3：实现语言检测函数**

```python
# server/multilingual.py
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

SUPPORTED_LANGUAGES = {'zh', 'en'}
DEFAULT_LANGUAGE = 'en'


def detect_language(text: str) -> str:
    """Detect contract language; return 'zh' or 'en'."""
    if not text or not text.strip():
        return DEFAULT_LANGUAGE
    try:
        lang = detect(text)
        if lang in SUPPORTED_LANGUAGES:
            return lang
        # Chinese variants fallback
        if lang.startswith('zh'):
            return 'zh'
        return DEFAULT_LANGUAGE
    except LangDetectException:
        return DEFAULT_LANGUAGE
```

- [ ] **Step 4：运行测试**

```bash
cd /workspace/docai-redesign
python -m pytest tests/test_multilingual.py -v
```

Expected: 3 passed

---

## Task 2：扩展多语言法律术语库

**Files:**
- Modify: `legal_terms.js`
- Modify: `server/multilingual.py`

- [ ] **Step 1：在 legal_terms.js 中添加英文术语表**

在 `window.LegalTerms` 中新增 `glossaryEn`：
```javascript
var glossaryEn = [
    { term: 'Indemnification', alias: ['indemnify', 'indemnifies'], plain: '一方因另一方的损失或索赔而进行补偿。简单说就是"替你兜底赔偿"。', category: 'contract' },
    { term: 'Force Majeure', alias: ['force majeure'], plain: '无法预见、避免或克服的事件（如自然灾害、战争），可免除履约责任。', category: 'contract' },
    { term: 'Governing Law', alias: ['governing law', 'applicable law'], plain: '合同适用哪个国家或地区的法律来解释和裁决纠纷。', category: 'contract' },
    { term: 'Jurisdiction', alias: ['jurisdiction', 'venue'], plain: '发生争议时由哪个法院或仲裁机构管辖。', category: 'contract' },
    { term: 'Confidentiality', alias: ['confidential', 'non-disclosure', 'NDA'], plain: '要求一方对合同内容及商业秘密保密，不得泄露给第三方。', category: 'contract' },
    { term: 'Termination', alias: ['terminate', 'termination'], plain: '在约定条件下行使权利提前结束合同关系。', category: 'contract' },
    { term: 'Liquidated Damages', alias: ['liquidated damages'], plain: '双方事先约定的违约赔偿金额，用于简化实际损失计算。', category: 'contract' },
    { term: 'Intellectual Property', alias: ['IP', 'intellectual property rights'], plain: '对发明、作品、商标等智力成果享有的专有权利。', category: 'general' },
    { term: 'Non-Compete', alias: ['non-compete', 'non-competition'], plain: '限制一方在合同结束后从事竞争性业务的条款。', category: 'contract' },
    { term: 'Arbitration', alias: ['arbitrate', 'arbitrator'], plain: '由仲裁机构而非法院裁决争议，通常一裁终局。', category: 'contract' },
    { term: 'Breach of Contract', alias: ['breach'], plain: '一方未履行或未完全履行合同义务的行为。', category: 'contract' },
    { term: 'Limitation of Liability', alias: ['liability cap', 'limit liability'], plain: '对一方可能承担的赔偿责任设置上限。', category: 'contract' },
    { term: 'Warranty', alias: ['warranties'], plain: '一方对某种事实或未来状态作出的保证或承诺。', category: 'contract' },
    { term: 'Assignment', alias: ['assign', 'assigns'], plain: '将合同权利或义务转让给第三方。', category: 'contract' },
    { term: 'Severability', alias: ['severable'], plain: '如果某条款无效，其余条款仍然有效的约定。', category: 'contract' },
];
```

将返回对象扩展为：
```javascript
return {
    glossary: glossary,
    glossaryEn: glossaryEn,
    detectLanguage: function(text) { ... },
    highlight: function(container, lang) { ... },
    ...
};
```

- [ ] **Step 2：修改 highlight 函数支持语言参数**

```javascript
highlight: function(container, lang) {
    if (!container) return;
    var terms = (lang === 'en') ? glossaryEn : glossary;
    // 使用 terms 替代原来的 glossary 构建正则
}
```

- [ ] **Step 3：在 multilingual.py 中同步后端术语库**

```python
# server/multilingual.py
LEGAL_TERMS_ZH = {
    '违约金': '一方不履行合同约定时向对方支付的赔偿金额',
    '不可抗力': '不能预见、避免且克服的客观情况导致无法履约可免责',
    # ... 保留核心中文术语
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
}


def get_legal_terms(language: str) -> dict:
    return LEGAL_TERMS_ZH if language == 'zh' else LEGAL_TERMS_EN
```

---

## Task 3：构建多语言 System Prompt 与法律依据映射

**Files:**
- Modify: `server/multilingual.py`
- Modify: `server/routes.py`

- [ ] **Step 1：创建英文版风险分析 prompt**

```python
# server/multilingual.py
RISK_ANALYSIS_PROMPT_EN = """You are a senior contract review attorney with 10+ years of experience. Identify all potential risks in the contract below.

{type_focus}{stance_prompt}{plain_lang_prompt}

Return STRICTLY VALID JSON with this structure:
{
  "contract_type": "labor/rental/purchase/service/nda/loan/other",
  "score": <integer 0-100>,
  "risk_level": "high/medium/low",
  "one_line_summary": "One-sentence core risk summary, max 80 characters",
  "risk_items": [
    {
      "clause_name": "Clause name, e.g. Indemnification Clause",
      "clause_location": "Clause location, e.g. Section 3.2",
      "risk_level": "high/medium/low",
      "description": "2-3 sentences explaining why this clause is risky",
      "plain_explanation": "Plain-language explanation, max 50 words",
      "suggestion": "Actionable revision suggestion",
      "legal_basis": "Relevant legal basis, e.g. UCC 2-207 / common law"
    }
  ],
  "suggestions": ["Overall improvement 1", "Overall improvement 2"],
  "key_obligations": [
    {"party": "Party A / Party B", "obligation": "Core obligation"}
  ]
}

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
"""
```

- [ ] **Step 2：添加法律依据映射**

```python
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


def get_legal_basis(language: str, domain: str = 'contract') -> str:
    return LEGAL_BASIS_MAP.get(language, LEGAL_BASIS_MAP['en']).get(domain, '')
```

- [ ] **Step 3：创建 prompt 选择器**

```python
def build_analysis_prompt(language: str, mode: str, **kwargs) -> str:
    if mode == 'risk':
        base = RISK_ANALYSIS_PROMPT_ZH if language == 'zh' else RISK_ANALYSIS_PROMPT_EN
        type_focus = kwargs.get('type_focus', '')
        stance = kwargs.get('stance', '')
        plain = kwargs.get('plain', '')
        return base.format(type_focus=type_focus, stance_prompt=stance, plain_lang_prompt=plain)
    # summary / plain modes similarly
    return base
```

- [ ] **Step 4：在 routes.py 中替换 prompt 获取逻辑**

修改 `_get_mode_prompt(mode)` 调用为 `_get_mode_prompt(mode, language)`，并让 `create_analysis` 传入检测语言。

---

## Task 4：英文合同模板训练数据（Few-Shot 示例）

**Files:**
- Create: `server/training_data/english_contract_examples.py`

- [ ] **Step 1：创建英文合同示例与期望输出**

```python
# server/training_data/english_contract_examples.py
ENGLISH_SERVICE_AGREEMENT_EXAMPLE = {
    "text": """SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of January 1, 2024, by and between ABC Tech, Inc. ("Provider") and XYZ Corp ("Client").

1. Services. Provider shall perform software development services as described in Exhibit A.
2. Payment. Client shall pay all fees within sixty (60) days of invoice. Late payments subject to 1.5% monthly service charge.
3. Limitation of Liability. Provider's total liability shall not exceed the total amount paid by Client under this Agreement in the twelve (12) months preceding the claim.
4. Termination. Either party may terminate this Agreement for convenience with thirty (30) days written notice.
5. Governing Law. This Agreement shall be governed by the laws of the State of Delaware.
""",
    "expected": {
        "contract_type": "service",
        "score": 68,
        "risk_level": "medium",
        "one_line_summary": "Payment terms and liability cap create moderate risk for the service provider.",
        "risk_items": [
            {
                "clause_name": "Payment Terms",
                "clause_location": "Section 2",
                "risk_level": "medium",
                "description": "Sixty-day payment period and 1.5% monthly late fee may strain Provider cash flow and may be unenforceable in some jurisdictions.",
                "plain_explanation": "Client has two months to pay, and late fees could be too high to be legal.",
                "suggestion": "Reduce payment term to net 30 and cap late fee at the maximum lawful rate (often 1% per month).",
                "legal_basis": "UCC Article 2 / state usury and contract law"
            },
            {
                "clause_name": "Limitation of Liability",
                "clause_location": "Section 3",
                "risk_level": "medium",
                "description": "Liability cap based on 12-month fees may be insufficient for breaches involving data loss or IP infringement.",
                "plain_explanation": "If something big goes wrong, the most you can recover is one year of fees.",
                "suggestion": "Carve out liability for gross negligence, willful misconduct, data breaches, and IP indemnification from the cap.",
                "legal_basis": "Common law; enforceability varies by jurisdiction"
            }
        ],
        "suggestions": ["Clarify deliverables and acceptance criteria in Exhibit A.", "Add confidentiality and IP ownership clauses."],
        "key_obligations": [
            {"party": "Provider", "obligation": "Perform software development services per Exhibit A"},
            {"party": "Client", "obligation": "Pay fees within 60 days of invoice"}
        ]
    }
}

ENGLISH_EXAMPLES = [ENGLISH_SERVICE_AGREEMENT_EXAMPLE]
```

- [ ] **Step 2：在 multilingual.py 中生成 few-shot 消息**

```python
from training_data.english_contract_examples import ENGLISH_EXAMPLES

def build_few_shot_messages(language: str, mode: str):
    if language != 'en' or mode != 'risk':
        return []
    messages = []
    for ex in ENGLISH_EXAMPLES:
        messages.append({'role': 'user', 'content': ex['text']})
        messages.append({'role': 'assistant', 'content': json.dumps(ex['expected'], ensure_ascii=False)})
    return messages
```

---

## Task 5：改造分析接口以使用多语言流程

**Files:**
- Modify: `server/routes.py`
- Modify: `server/models.py`
- Modify: `server/app.py`

- [ ] **Step 1：修改 Analysis 模型**

```python
# server/models.py
class Analysis(db.Model):
    ...
    language = db.Column(db.String(10), default='zh')  # zh / en
```

- [ ] **Step 2：自动迁移 analysis.language 列**

```python
# server/app.py _auto_migrate
migrations = [
    ("analysis", "text_hash", "VARCHAR(16)"),
    ("analysis", "contract_type", "VARCHAR(20)"),
    ("user", "avatar", "VARCHAR(256)"),
    ("analysis", "language", "VARCHAR(10)"),
]
```

- [ ] **Step 3：修改 create_analysis 流程**

```python
from multilingual import detect_language, build_analysis_prompt, build_few_shot_messages, get_legal_basis

# 在 create_analysis 中：
language = detect_language(text)

# contract type detection 也传入 language
contract_type, _ = _detect_contract_type(text, api_key, language=language)

system_prompt = build_analysis_prompt(language, mode,
    type_focus=..., stance=..., plain=...)

messages = [{'role': 'system', 'content': system_prompt}]
messages.extend(build_few_shot_messages(language, mode))
messages.append({'role': 'user', 'content': text})

# 保存 analysis.language = language
```

- [ ] **Step 4：修改 _detect_contract_type 支持多语言**

```python
def _detect_contract_type(text, api_key, language='zh'):
    if not api_key:
        return 'other', None
    instruction = '判断以下合同属于哪种类型...' if language == 'zh' else 'Classify the contract type...'
    # ...
```

---

## Task 6：前端展示检测语言与多语言术语高亮

**Files:**
- Modify: `server/templates/analyze.html`
- Modify: `server/i18n_translations.py`

- [ ] **Step 1：在 analyze.html 分析结果区域显示语言标签**

```html
<div id="detected-language-badge" class="hidden text-xs font-medium px-2 py-1 rounded-full bg-blue-50 text-blue-600">
    <span data-i18n="analyze.detected_language">检测语言</span>: <span id="detected-language-value">-</span>
</div>
```

- [ ] **Step 2：JS 中接收并显示 language 字段**

```javascript
// 在分析结果回调中
document.getElementById('detected-language-value').textContent = data.analysis.language === 'en' ? 'English' : '中文';
document.getElementById('detected-language-badge').classList.remove('hidden');
```

- [ ] **Step 3：术语高亮按语言切换**

```javascript
LegalTerms.highlight(container, data.analysis.language || 'zh');
```

- [ ] **Step 4：补充 i18n key**

```python
# server/i18n_translations.py 中 zh/en 都加
'detected_language': '检测语言' / 'Detected Language'
'language_zh': '中文' / 'Chinese'
'language_en': 'English' / 'English'
```

---

## Task 7：数据库迁移与回归测试

**Files:**
- Modify: `server/app.py`
- Test: `tests/test_multilingual.py`

- [ ] **Step 1：验证迁移后列存在**

启动服务后检查日志：`[DocAI Migration] Added analysis.language`

- [ ] **Step 2：新增端到端测试（模拟 API）**

```python
def test_build_analysis_prompt_en():
    from multilingual import build_analysis_prompt
    prompt = build_analysis_prompt('en', 'risk', type_focus='', stance='', plain='')
    assert 'senior contract review attorney' in prompt
    assert 'STRICTLY VALID JSON' in prompt
```

- [ ] **Step 3：重启服务并测试**

```bash
cd /workspace/docai-redesign/server
pkill -f "python app.py" || true
nohup python app.py > /tmp/docai_server.log 2>&1 &
```

---

## Task 8：文档更新

**Files:**
- Modify: `docs/multilingual-contract-analysis-plan.md`（标记完成）

- [ ] **Step 1：在 README 或产品文档中补充说明**

简要说明已支持中文和英文合同自动识别，其他语言将逐步扩展。

---

## 执行选项

计划完成后，可选择：
1. **Subagent-Driven**：每 Task 由一个独立子代理执行，主代理复核
2. **Inline Execution**：在当前会话中按 Task 顺序逐步执行

默认推荐 Inline Execution，因为修改集中在同一个代码库，便于连续验证。
