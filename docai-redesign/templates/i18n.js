// I18N Engine - Internationalization for DocAI
(function() {
    'use strict';

    const I18N_DATA = {{ i18n_data | safe }};

    window.I18N = {
        data: I18N_DATA,
        currentLang: 'zh',

        init: function() {
            var saved = localStorage.getItem('docai_lang');
            if (saved && I18N_DATA[saved]) {
                I18N.currentLang = saved;
            }
            I18N.applyAll();
        },

        t: function(key) {
            var lang = I18N.currentLang;
            if (I18N_DATA[lang] && I18N_DATA[lang][key]) {
                return I18N_DATA[lang][key];
            }
            // Fallback to zh
            if (I18N_DATA['zh'] && I18N_DATA['zh'][key]) {
                return I18N_DATA['zh'][key];
            }
            return key;
        },

        switchLang: function(lang) {
            if (!I18N_DATA[lang]) return;
            I18N.currentLang = lang;
            localStorage.setItem('docai_lang', lang);
            I18N.applyAll();
            document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
        },

        applyAll: function() {
            var lang = I18N.currentLang;
            // Apply data-i18n text
            document.querySelectorAll('[data-i18n]').forEach(function(el) {
                var key = el.getAttribute('data-i18n');
                if (I18N_DATA[lang] && I18N_DATA[lang][key]) {
                    el.textContent = I18N_DATA[lang][key];
                }
            });
            // Apply data-i18n-placeholder
            document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
                var key = el.getAttribute('data-i18n-placeholder');
                if (I18N_DATA[lang] && I18N_DATA[lang][key]) {
                    el.setAttribute('placeholder', I18N_DATA[lang][key]);
                }
            });
            // Update lang toggle button text
            var toggleBtn = document.getElementById('lang-toggle-btn');
            if (toggleBtn) {
                toggleBtn.textContent = lang === 'zh' ? 'EN' : '中文';
            }
        }
    };

    // Init on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { I18N.init(); });
    } else {
        I18N.init();
    }
})();
