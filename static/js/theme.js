/**
 * 테마 관리 모듈
 * 다크/라이트 모드, 색상 테마, 채팅 배경 관리
 */

// ============================================================================
// 테마 설정 상태
// ============================================================================
var themeSettings = {
    mode: 'dark',
    color: 'emerald',
    chatBg: 'none'
};

/**
 * 테마 초기화
 */
function initTheme() {
    var saved = localStorage.getItem('messengerTheme');
    if (saved) {
        try {
            var parsed = JSON.parse(saved);
            themeSettings = {
                mode: parsed.mode || 'dark',
                color: parsed.color || 'emerald',
                chatBg: parsed.chatBg || 'none'
            };
        } catch (e) {
            console.error('테마 설정 로드 오류:', e);
        }
    }
    applyTheme();
    updateSettingsUI();
}

/**
 * 테마 적용
 */
function applyTheme() {
    var effectiveMode = themeSettings.mode;
    if (effectiveMode === 'system') {
        effectiveMode = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    document.documentElement.setAttribute('data-theme', effectiveMode);
    document.documentElement.setAttribute('data-color', themeSettings.color);
    document.documentElement.setAttribute('data-chat-bg', themeSettings.chatBg);
}

/**
 * 테마 설정 저장
 */
function saveThemeSettings() {
    localStorage.setItem('messengerTheme', JSON.stringify(themeSettings));
}

/**
 * 설정 UI 업데이트
 */
function updateSettingsUI() {
    // 테마 모드 버튼 활성화
    document.querySelectorAll('.theme-toggle-btn').forEach(function (btn) {
        btn.classList.toggle('active', btn.dataset.theme === themeSettings.mode);
    });

    // 색상 옵션 활성화
    document.querySelectorAll('.color-option').forEach(function (option) {
        option.classList.toggle('active', option.dataset.color === themeSettings.color);
    });

    // 배경 옵션 활성화
    document.querySelectorAll('.bg-option').forEach(function (option) {
        option.classList.toggle('active', option.dataset.bg === themeSettings.chatBg);
    });
}

/**
 * 설정 모달 열기
 */
function openSettingsModal() {
    var modal = document.getElementById('settingsModal');
    if (modal) {
        modal.classList.add('active');
        updateSettingsUI();
    }
}

/**
 * 설정 모달 닫기
 */
function closeSettingsModal() {
    var modal = document.getElementById('settingsModal');
    if (modal) modal.classList.remove('active');
}

/**
 * 테마 모드 변경
 * @param {string} mode - 테마 모드 (dark, light, system)
 */
function setThemeMode(mode) {
    themeSettings.mode = mode;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

/**
 * 테마 토글 (다크/라이트 전환)
 */
function toggleTheme() {
    var newMode = themeSettings.mode === 'dark' ? 'light' : 'dark';
    setThemeMode(newMode);
}

/**
 * 테마 색상 변경
 * @param {string} color - 색상 이름
 */
function setThemeColor(color) {
    themeSettings.color = color;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

/**
 * 채팅 배경 변경
 * @param {string} bg - 배경 타입
 */
function setChatBackground(bg) {
    themeSettings.chatBg = bg;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

/**
 * 테마 설정 초기화
 */
function resetSettings() {
    themeSettings = {
        mode: 'dark',
        color: 'emerald',
        chatBg: 'none'
    };
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
    if (typeof showToast === 'function') {
        showToast('설정이 초기화되었습니다', 'info');
    }
}

// 시스템 테마 변경 감지
if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if (themeSettings.mode === 'system') {
            applyTheme();
        }
    });
}

// ============================================================================
// 전역 노출
// ============================================================================
window.themeSettings = themeSettings;
window.initTheme = initTheme;
window.applyTheme = applyTheme;
window.saveThemeSettings = saveThemeSettings;
window.updateSettingsUI = updateSettingsUI;
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.setThemeMode = setThemeMode;
window.toggleTheme = toggleTheme;
window.setThemeColor = setThemeColor;
window.setChatBackground = setChatBackground;
window.resetSettings = resetSettings;

// ============================================================================
// DOM 로드 후 이벤트 바인딩 및 초기화
// ============================================================================
document.addEventListener('DOMContentLoaded', function () {
    // 테마 모드 버튼
    document.querySelectorAll('.theme-toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            setThemeMode(this.dataset.theme);
        });
    });

    // 색상 옵션
    document.querySelectorAll('.color-option').forEach(function (option) {
        option.addEventListener('click', function () {
            setThemeColor(this.dataset.color);
        });
    });

    // 배경 옵션
    document.querySelectorAll('.bg-option').forEach(function (option) {
        option.addEventListener('click', function () {
            setChatBackground(this.dataset.bg);
        });
    });

    // 설정 초기화 버튼
    var resetBtn = document.getElementById('resetSettingsBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetSettings);
    }

    // 테마 초기화
    initTheme();
});
