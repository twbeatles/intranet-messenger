/**
 * 토스트 알림 시스템 모듈
 * 사용자에게 알림 메시지를 표시하는 토스트 UI 컴포넌트
 */

// ============================================================================
// 토스트 컨테이너 상태
// ============================================================================
var toastContainer = null;

/**
 * 토스트 컨테이너 초기화
 */
function initToast() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        toastContainer.setAttribute('role', 'alert');
        toastContainer.setAttribute('aria-live', 'polite');
        document.body.appendChild(toastContainer);
    }
}

/**
 * 토스트 메시지 표시
 * @param {string} message - 표시할 메시지
 * @param {string} type - 타입 (success, error, warning, info)
 * @param {number} duration - 표시 시간 (ms)
 * @param {string} title - 제목 (선택)
 * @returns {HTMLElement} 생성된 토스트 요소
 */
function showToast(message, type, duration, title) {
    type = type || 'info';
    duration = duration || 4000;

    initToast();

    var icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    var titles = {
        success: '성공',
        error: '오류',
        warning: '주의',
        info: '알림'
    };

    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span class="toast-icon">' + icons[type] + '</span>' +
        '<div class="toast-body">' +
        '<div class="toast-title">' + escapeHtml(title || titles[type]) + '</div>' +
        '<div class="toast-message">' + escapeHtml(message) + '</div>' +
        '</div>' +
        '<button class="toast-close" aria-label="닫기">✕</button>' +
        '<div class="toast-progress" style="animation-duration:' + duration + 'ms;"></div>';

    toast.querySelector('.toast-close').onclick = function () {
        closeToast(toast);
    };

    // 최대 5개까지만 표시
    while (toastContainer.children.length >= 5) {
        closeToast(toastContainer.firstChild);
    }

    toastContainer.appendChild(toast);

    var timeoutId = setTimeout(function () {
        closeToast(toast);
    }, duration);

    // 마우스 오버 시 일시정지
    toast.onmouseenter = function () {
        clearTimeout(timeoutId);
        var progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'paused';
    };

    toast.onmouseleave = function () {
        var progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'running';
        timeoutId = setTimeout(function () {
            closeToast(toast);
        }, 2000);
    };

    return toast;
}

/**
 * 토스트 닫기
 * @param {HTMLElement} toast - 닫을 토스트 요소
 */
function closeToast(toast) {
    if (toast && toast.parentNode) {
        toast.classList.add('hiding');
        setTimeout(function () {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.initToast = initToast;
window.showToast = showToast;
window.closeToast = closeToast;
