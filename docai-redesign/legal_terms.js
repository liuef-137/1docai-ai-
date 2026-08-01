window.LegalTerms = (function() {
    'use strict';
    
    var glossary = [
        // 合同通用
        { term: '违约金', alias: ['违约金条款', '违约赔偿'], plain: '一方不履行合同约定时，需要向对方支付的赔偿金额。简单说就是"爽约的代价"。', category: 'contract' },
        { term: '定金', alias: ['订金', '预付款'], plain: '签订合同时提前支付的一笔钱，作为履行合同的担保。注意："定金"有法律效力，"订金"一般只算预付款。', category: 'contract' },
        { term: '不可抗力', alias: ['force majeure'], plain: '不能预见、不能避免且不能克服的客观情况（如地震、战争、疫情），导致无法履行合同时可以免责。', category: 'contract' },
        { term: '管辖权', alias: ['管辖法院', '管辖条款', '争议管辖'], plain: '发生纠纷时由哪个法院来审理。合同中通常会约定"由XX地法院管辖"，这决定了你要去哪里打官司。', category: 'contract' },
        { term: '保密条款', alias: ['保密义务', 'NDA', '保密协议'], plain: '要求合同双方不得向第三方泄露合同内容的约定。违反保密条款可能需要赔偿损失。', category: 'contract' },
        { term: '违约责任', alias: ['违约', 'breach of contract'], plain: '一方不履行或不完全履行合同义务时需要承担的法律后果，包括赔偿损失、继续履行、支付违约金等。', category: 'contract' },
        { term: '合同解除', alias: ['解除合同', '终止合同'], plain: '在特定条件下提前结束合同的效力。分为协商解除和法定解除两种情况。', category: 'contract' },
        { term: '连带责任', alias: ['连带'], plain: '多个债务人对同一债务共同承担责任，债权人可以向其中任何一人追讨全部债务。', category: 'contract' },
        { term: '免责条款', alias: ['免责', '豁免条款'], plain: '合同中约定在某些特定情况下免除一方责任的条款。但免除人身伤害或故意/重大过失的责任通常无效。', category: 'contract' },
        { term: '仲裁', alias: ['仲裁条款', 'arbitration'], plain: '由双方选定的仲裁机构而非法院来裁决纠纷。仲裁一裁终局，不能上诉，但执行力和法院判决相同。', category: 'contract' },
        { term: '要约', alias: ['offer', '报价'], plain: '一方向对方发出的希望订立合同的意思表示，内容要具体确定。比如"我愿以100万元卖你这套房"。', category: 'contract' },
        { term: '承诺', alias: ['acceptance', '承诺书'], plain: '受要约人同意要约的意思表示。承诺到达要约人时合同即告成立。', category: 'contract' },
        { term: '保证', alias: ['保证人', '担保', '保证责任'], plain: '由第三人为债务人的债务提供担保，债务人还不上时保证人要代为偿还。', category: 'contract' },
        { term: '善意第三人', alias: ['善意取得', '善意相对人'], plain: '不知情且无重大过失的第三方。法律会保护善意第三人的合法权益。', category: 'general' },
        { term: '赔偿损失', alias: ['损害赔偿', '赔偿'], plain: '因违约或侵权行为给对方造成经济损失时，需要支付等额的赔偿金。赔偿范围包括直接损失和可预见的间接损失。', category: 'contract' },
        { term: '竞业限制', alias: ['竞业禁止', '竞业'], plain: '员工离职后一段时间内不得从事与原单位竞争的工作。单位通常需要支付竞业限制补偿金。', category: 'labor' },
        { term: '试用期', alias: ['试用期限'], plain: '劳动合同中约定的考察期。试用期内工资不得低于正式工资的80%，且同一用人单位与同一劳动者只能约定一次试用期。', category: 'labor' },
        { term: '经济补偿金', alias: ['经济补偿', '遣散费', 'N+1'], plain: '劳动合同解除或终止时，用人单位依法向劳动者支付的经济补偿。工作满一年补偿一个月工资（即"N"），有时加代通知金（"+1"）。', category: 'labor' },
        { term: '知识产权', alias: ['IP', '著作权', '专利权', '商标权'], plain: '人们对自己的智力成果（发明、作品、商标等）享有的专有权利。未经许可他人不得使用。', category: 'general' },
        { term: '诉讼时效', alias: ['时效', '诉讼时效期间'], plain: '法律保护权利的时间限制。一般民事权利的诉讼时效为3年，过期后法院不再强制保护。', category: 'general' },
        { term: '抗辩权', alias: ['抗辩'], plain: '一方对抗对方请求的权利。比如对方没先履行义务，你可以拒绝先履行。', category: 'contract' },
        { term: '抵押', alias: ['抵押权', '抵押物'], plain: '债务人或不特定的第三人将财产作为担保，不转移占有。还不上钱时债权人可以拍卖该财产优先受偿。', category: 'property' },
        { term: '质押', alias: ['质权', '质押物'], plain: '债务人将动产或权利凭证交给债权人占有作为担保。和抵押的区别是质押需要转移占有。', category: 'property' },
        { term: '留置权', alias: ['留置'], plain: '债权人按合同占有债务人的动产，债务人不履行义务时，债权人有权扣留该财产。', category: 'property' },
        { term: '法人', alias: ['法定代表人', '法人代表'], plain: '依法成立、有独立财产、能独立承担民事责任的组织（如公司）。注意：法人是组织，不是具体的自然人。', category: 'corporate' },
        { term: '甲方/乙方', alias: ['甲方', '乙方'], plain: '合同中的双方当事人。"甲方"通常是提出合同的一方（如雇主、出租方），"乙方"是接受合同的一方（如员工、承租方）。', category: 'contract' },
        { term: '生效条件', alias: ['生效', '合同生效'], plain: '合同开始产生法律效力的条件。一般自双方签字盖章之日起生效，也可约定特定条件达成后生效。', category: 'contract' },
        { term: '变更', alias: ['合同变更', '条款变更'], plain: '对已成立合同的内容进行修改或补充。变更需双方协商一致，一般应采用书面形式。', category: 'contract' },
        { term: '转让', alias: ['权利转让', '合同转让', '债务转让'], plain: '将合同中的权利或义务转移给第三方。权利转让需通知对方，债务转让需经对方同意。', category: 'contract' },
        { term: '标的', alias: ['合同标的', '标的物'], plain: '合同中双方权利义务所指向的对象，如买卖合同中的商品、租赁合同中的房屋。', category: 'contract' },
        { term: '履行', alias: ['履行义务', '合同履行'], plain: '按照合同约定完成各自应当做的事情，如支付价款、交付货物、提供服务。', category: 'contract' },
        { term: '解除权', alias: ['单方解除', '法定解除'], plain: '在一方根本违约等法定情形下，另一方可以不经对方同意直接解除合同的权利。', category: 'contract' },
        { term: '格式条款', alias: ['格式合同', '标准条款', '霸王条款'], plain: '一方预先拟定、不可协商的合同条款。提供方需履行提示说明义务，否则对方可主张该条款不成为合同内容。', category: 'contract' },
        { term: '情势变更', alias: ['情势变更原则'], plain: '合同成立后，非因双方原因发生了重大变化（如政策变化），继续履行明显不公平的，可以请求法院变更或解除合同。', category: 'contract' },
        { term: '缔约过失', alias: ['缔约过失责任'], plain: '在合同订立过程中，一方因违背诚信原则给对方造成损失的赔偿责任。', category: 'contract' },
        { term: '代位权', alias: ['代位求偿'], plain: '债务人怠于行使对第三人的债权时，债权人可以代替债务人向第三人主张权利。', category: 'contract' },
        { term: '撤销权', alias: ['合同撤销', '可撤销合同'], plain: '因欺诈、胁迫、重大误解等原因订立的合同，受害方可以在法定期限内请求法院或仲裁机构撤销。', category: 'contract' },
        { term: '社会保险', alias: ['社保', '五险'], plain: '国家强制用人单位为劳动者缴纳的保险，包括养老、医疗、失业、工伤、生育五项保险。不缴纳社保是违法行为。', category: 'labor' },
        { term: '加班费', alias: ['加班工资', ' overtime'], plain: '用人单位安排劳动者在法定工作时间之外工作的，应当支付高于正常工资的报酬：平时1.5倍，周末2倍，法定节假日3倍。', category: 'labor' },
        { term: '违约方解除', alias: ['违约方解除权'], plain: '2021年《民法典》新增制度：非违约方违约后，违约方在某些特定情况下也可以请求解除合同（需承担违约责任）。', category: 'contract' },
        { term: '惩罚性赔偿', alias: ['惩罚性赔偿金', '惩罚赔偿'], plain: '超过实际损失数额的赔偿，用于惩罚恶意或严重违法行为（如消费者权益保护中的3倍赔偿）。', category: 'general' },
        { term: '实际履行', alias: ['继续履行'], plain: '一方违约后，对方可以要求其按照合同约定继续完成义务，而不是仅仅赔偿了事。', category: 'contract' },
    ];

    var glossaryEn = [
        { term: 'Indemnification', alias: ['indemnify', 'indemnifies', 'indemnified'], plain: 'One party compensates another for losses or third-party claims. In plain words: "I\'ve got your back if someone sues."', category: 'contract' },
        { term: 'Force Majeure', alias: ['force majeure'], plain: 'Unforeseeable events (earthquakes, wars, pandemics) that excuse a party from performing its obligations.', category: 'contract' },
        { term: 'Governing Law', alias: ['governing law', 'applicable law'], plain: 'The law of a specific country or state used to interpret the contract and resolve disputes.', category: 'contract' },
        { term: 'Jurisdiction', alias: ['jurisdiction', 'venue'], plain: 'The court or arbitration forum that will hear disputes under the contract.', category: 'contract' },
        { term: 'Confidentiality', alias: ['confidential', 'non-disclosure', 'NDA'], plain: 'An obligation to keep contract information and trade secrets secret from third parties.', category: 'contract' },
        { term: 'Termination', alias: ['terminate', 'termination', 'terminated'], plain: 'Ending the contract relationship before its natural expiration, either by agreement or for cause.', category: 'contract' },
        { term: 'Liquidated Damages', alias: ['liquidated damages'], plain: 'A pre-agreed sum payable if a party breaches the contract, designed to simplify damage calculation.', category: 'contract' },
        { term: 'Intellectual Property', alias: ['IP', 'intellectual property rights'], plain: 'Exclusive rights to creations of the mind, such as inventions, works, and trademarks.', category: 'general' },
        { term: 'Non-Compete', alias: ['non-compete', 'non-competition'], plain: 'A restriction preventing one party from competing with the other for a period after the contract ends.', category: 'contract' },
        { term: 'Arbitration', alias: ['arbitrate', 'arbitrator'], plain: 'Resolving disputes through a private arbitrator instead of a public court; usually final and binding.', category: 'contract' },
        { term: 'Breach of Contract', alias: ['breach', 'breached'], plain: 'Failure to perform or improper performance of contractual obligations.', category: 'contract' },
        { term: 'Limitation of Liability', alias: ['liability cap', 'limit liability'], plain: 'A clause that sets a maximum amount one party must pay for damages.', category: 'contract' },
        { term: 'Warranty', alias: ['warranties'], plain: 'A guarantee that certain facts are true or that future performance will meet standards.', category: 'contract' },
        { term: 'Assignment', alias: ['assign', 'assigns', 'assigned'], plain: 'Transferring contractual rights or duties to a third party.', category: 'contract' },
        { term: 'Severability', alias: ['severable'], plain: 'If one provision is invalid, the rest of the contract remains in effect.', category: 'contract' },
        { term: 'Consideration', alias: ['consideration'], plain: 'Something of value exchanged by the parties to form a binding contract.', category: 'contract' },
        { term: 'Representations and Warranties', alias: ['representations', 'warranties'], plain: 'Statements of present fact and promises about future conditions made by a party.', category: 'contract' },
        { term: 'Dispute Resolution', alias: ['dispute resolution'], plain: 'The agreed process for resolving conflicts, such as negotiation, mediation, arbitration, or litigation.', category: 'contract' },
    ];

    // Simple CJK detection for client-side language hint (mirrors server logic)
    function detectLanguage(text) {
        if (!text) return 'zh';
        var cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]/g) || []).length;
        return cjk / text.length > 0.15 ? 'zh' : 'en';
    }
    
    return {
        glossary: glossary,
        glossaryEn: glossaryEn,
        detectLanguage: detectLanguage,
        
        /**
         * Auto-highlight legal terms in a text container.
         * Wraps matched terms with <span class="legal-term" data-term-index="i">...</span>
         * and attaches a click handler to show a tooltip.
         * @param {HTMLElement} container
         * @param {string} lang - 'zh' or 'en'; defaults to auto-detect from container text
         */
        highlight: function(container, lang) {
            if (!container) return;
            
            // Determine glossary to use
            var useLang = lang || detectLanguage(container.textContent || '');
            var terms = (useLang === 'en') ? glossaryEn : glossary;
            if (!terms.length) return;
            
            // Skip if already highlighted
            if (container.classList.contains('lt-highlighted')) return;
            container.classList.add('lt-highlighted');
            container.setAttribute('data-legal-lang', useLang);
            
            // Build a combined pattern of all terms and aliases, sorted by length (longest first)
            var allPatterns = [];
            terms.forEach(function(entry, idx) {
                var termList = [entry.term].concat(entry.alias || []);
                termList.forEach(function(pattern) {
                    allPatterns.push({ text: pattern, index: idx });
                });
            });
            // Sort by length descending to match longer terms first
            allPatterns.sort(function(a, b) { return b.text.length - a.text.length; });
            
            // Escape and join into alternation pattern
            var escaped = allPatterns.map(function(p) {
                return p.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            });
            var combinedRegex = new RegExp('(' + escaped.join('|') + ')', 'gi');
            
            // Walk text nodes and replace
            var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
            var textNodes = [];
            var node;
            while ((node = walker.nextNode())) {
                // Skip text inside script, style, code, or already-highlighted spans
                var parent = node.parentElement;
                if (parent && (parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE' ||
                    parent.tagName === 'CODE' || parent.tagName === 'TEXTAREA' || parent.tagName === 'INPUT' ||
                    parent.tagName === 'OPTION' || parent.classList.contains('legal-term') ||
                    parent.getAttribute('data-i18n'))) {
                    continue;
                }
                textNodes.push(node);
            }
            
            var patternMap = {};
            allPatterns.forEach(function(p) { patternMap[p.text.toLowerCase()] = p.index; });
            
            textNodes.forEach(function(textNode) {
                var text = textNode.textContent;
                if (!combinedRegex.test(text)) return;
                combinedRegex.lastIndex = 0; // Reset after test
                
                var frag = document.createDocumentFragment();
                var lastIndex = 0;
                var match;
                
                while ((match = combinedRegex.exec(text)) !== null) {
                    // Add text before match
                    if (match.index > lastIndex) {
                        frag.appendChild(document.createTextNode(text.substring(lastIndex, match.index)));
                    }
                    
                    // Create highlighted span
                    var span = document.createElement('span');
                    span.className = 'legal-term';
                    var termIdx = patternMap[match[0].toLowerCase()];
                    span.setAttribute('data-term-idx', termIdx);
                    span.setAttribute('data-legal-lang', useLang);
                    span.setAttribute('tabindex', '0');
                    span.setAttribute('role', 'button');
                    span.setAttribute('aria-label', 'Legal term: ' + terms[termIdx].term);
                    span.textContent = match[0];
                    frag.appendChild(span);
                    
                    lastIndex = match.index + match[0].length;
                }
                
                // Add remaining text
                if (lastIndex < text.length) {
                    frag.appendChild(document.createTextNode(text.substring(lastIndex)));
                }
                
                // Replace original text node with fragment
                textNode.parentNode.replaceChild(frag, textNode);
            });
            
            // Attach click/keydown handlers
            var self = this;
            container.querySelectorAll('.legal-term').forEach(function(el) {
                el.addEventListener('click', function(e) {
                    e.stopPropagation();
                    self.showTooltip(el, parseInt(el.getAttribute('data-term-idx')));
                });
                el.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        self.showTooltip(el, parseInt(el.getAttribute('data-term-idx')));
                    }
                });
            });
        },
        
        /**
         * Show a tooltip popup near the clicked term.
         */
        showTooltip: function(anchorEl, termIdx) {
            // Remove existing tooltip
            LegalTerms.hideTooltip();
            
            var useLang = anchorEl.getAttribute('data-legal-lang') || 'zh';
            var terms = (useLang === 'en') ? glossaryEn : glossary;
            var entry = terms[termIdx];
            if (!entry) return;
            
            var tooltip = document.createElement('div');
            tooltip.id = 'legal-term-tooltip';
            tooltip.className = 'legal-term-tooltip';
            tooltip.innerHTML = '<div class="ltt-title">' + entry.term + '</div>' +
                '<div class="ltt-category">' + entry.category + '</div>' +
                '<div class="ltt-body">' + entry.plain + '</div>';
            document.body.appendChild(tooltip);
            
            // Position near anchor
            var rect = anchorEl.getBoundingClientRect();
            var scrollY = window.scrollY || window.pageYOffset;
            var tooltipWidth = 300;
            var tooltipHeight = tooltip.offsetHeight || 120;
            var gap = 8;
            
            // Try placing below, fall back to above
            var top = rect.bottom + scrollY + gap;
            if (top + tooltipHeight > scrollY + window.innerHeight - 16) {
                top = rect.top + scrollY - tooltipHeight - gap;
            }
            tooltip.style.top = top + 'px';
            
            // Horizontal: center on anchor, keep within viewport
            var left = rect.left + rect.width / 2;
            if (left + tooltipWidth / 2 > window.innerWidth - 16) {
                left = window.innerWidth - 16 - tooltipWidth / 2;
            }
            if (left - tooltipWidth / 2 < 16) {
                left = 16 + tooltipWidth / 2;
            }
            tooltip.style.left = (left - tooltipWidth / 2) + 'px';
            tooltip.style.position = 'absolute';
            
            // Auto-dismiss on outside click
            setTimeout(function() {
                document.addEventListener('click', LegalTerms.hideTooltip, { once: true });
            }, 10);
        },
        
        hideTooltip: function() {
            var existing = document.getElementById('legal-term-tooltip');
            if (existing) existing.remove();
        }
    };
})();
