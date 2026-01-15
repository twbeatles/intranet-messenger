/**
 * 유틸리티 모듈
 * 공통으로 사용되는 헬퍼 함수들을 모아놓은 모듈입니다.
 */

// Global Variables
var currentUser = null;
var currentRoom = null;
var currentRoomKey = null;  // 현재 방 암호화 키
var rooms = [];

// ============================================================================
// DOM 헬퍼
// ============================================================================

/**
 * 간편한 DOM 요소 선택
 * @param {string} id - 요소 ID
 * @returns {HTMLElement|null}
 */
function $(id) {
    try {
        return document.getElementById(id);
    } catch (e) {
        return null;
    }
}

// ============================================================================
// 성능 최적화 유틸리티
// ============================================================================

/**
 * Debounce 함수 - 연속 호출 시 마지막 호출만 실행
 * @param {Function} func - 실행할 함수
 * @param {number} wait - 대기 시간 (ms)
 */
function debounce(func, wait) {
    var timeout;
    return function () {
        var context = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function () {
            func.apply(context, args);
        }, wait);
    };
}

/**
 * Throttle 함수 - 지정된 시간 동안 한 번만 실행
 * @param {Function} func - 실행할 함수
 * @param {number} limit - 제한 시간 (ms)
 */
function throttle(func, limit) {
    var inThrottle;
    return function () {
        var context = this, args = arguments;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(function () { inThrottle = false; }, limit);
        }
    };
}

// requestAnimationFrame 배치 업데이트
var pendingUpdates = [];
var rafScheduled = false;

/**
 * RAF를 사용한 배치 업데이트 스케줄링
 * @param {Function} updateFn - 업데이트 함수
 */
function scheduleUpdate(updateFn) {
    pendingUpdates.push(updateFn);
    if (!rafScheduled) {
        rafScheduled = true;
        requestAnimationFrame(function () {
            var updates = pendingUpdates;
            pendingUpdates = [];
            rafScheduled = false;
            updates.forEach(function (fn) { fn(); });
        });
    }
}

// ============================================================================
// 문자열 유틸리티
// ============================================================================

/**
 * HTML 특수문자 이스케이프
 * @param {string} text - 이스케이프할 텍스트
 * @returns {string}
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    var map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function (m) { return map[m]; });
}

// ============================================================================
// 날짜/시간 유틸리티
// ============================================================================

/**
 * 시간 포맷팅 (상대적 시간 표시)
 * @param {string} dateStr - 날짜 문자열
 * @returns {string}
 */
function formatTime(dateStr) {
    if (!dateStr) return '';

    var d;
    if (dateStr.includes('T')) {
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    if (isNaN(d.getTime())) return '';

    var now = new Date();
    var diffMs = now - d;
    var diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '방금';
    if (diffMins < 60) return diffMins + '분 전';

    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    var yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
        return '어제';
    }

    return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

/**
 * 날짜 포맷팅 (날짜만 표시)
 * @param {string} dateStr - 날짜 문자열
 * @returns {string}
 */
function formatDate(dateStr) {
    if (!dateStr) return '';

    var d;
    if (dateStr.includes('T')) {
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    if (isNaN(d.getTime())) return '';

    var today = new Date();
    if (d.toDateString() === today.toDateString()) return '오늘';

    var yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return '어제';

    return d.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
}

/**
 * 날짜 구분선 라벨 포맷팅
 * @param {string} dateStr - 날짜 문자열
 * @returns {string}
 */
function formatDateLabel(dateStr) {
    if (!dateStr) return '';

    var d;
    if (dateStr.includes('T')) {
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    if (isNaN(d.getTime())) return '';

    var today = new Date();
    if (d.toDateString() === today.toDateString()) return '오늘';

    var yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return '어제';

    var year = d.getFullYear();
    var month = d.getMonth() + 1;
    var day = d.getDate();
    var weekdays = ['일', '월', '화', '수', '목', '금', '토'];
    var weekday = weekdays[d.getDay()];

    return year + '년 ' + month + '월 ' + day + '일 ' + weekday + '요일';
}

// ============================================================================
// 유저 프로필 색상
// ============================================================================

var userColorPalette = [
    'hsl(210, 70%, 50%)',   // 파랑
    'hsl(340, 70%, 50%)',   // 핑크
    'hsl(150, 70%, 40%)',   // 초록
    'hsl(25, 80%, 50%)',    // 주황
    'hsl(270, 60%, 55%)',   // 보라
    'hsl(180, 70%, 40%)',   // 청록
    'hsl(45, 80%, 45%)',    // 노랑
    'hsl(0, 70%, 50%)',     // 빨강
    'hsl(240, 60%, 55%)',   // 남색
    'hsl(320, 60%, 50%)',   // 마젠타
    'hsl(90, 60%, 40%)',    // 라임
    'hsl(200, 70%, 45%)'    // 하늘색
];

/**
 * 유저 ID 기반 일관된 색상 반환
 * @param {number} userId - 유저 ID
 * @returns {string} HSL 색상 문자열
 */
function getUserColor(userId) {
    var index = Math.abs(userId) % userColorPalette.length;
    return userColorPalette[index];
}

/**
 * 아바타 HTML 생성 헬퍼 함수
 * @param {string} name - 사용자 이름
 * @param {string} imagePath - 프로필 이미지 경로
 * @param {number} userId - 사용자 ID
 * @param {string} cssClass - CSS 클래스
 * @returns {string} HTML 문자열
 */
function createAvatarHtml(name, imagePath, userId, cssClass) {
    cssClass = cssClass || 'message-avatar';
    var initial = (name && name.length > 0) ? name[0].toUpperCase() : '?';
    var color = getUserColor(userId || 0);

    if (imagePath) {
        return '<div class="' + cssClass + ' has-image"><img src="/uploads/' + imagePath + '" alt="프로필"></div>';
    } else {
        return '<div class="' + cssClass + '" style="background:' + color + '">' + initial + '</div>';
    }
}

// ============================================================================
// 클립보드 유틸리티
// ============================================================================

/**
 * 클립보드에 텍스트 복사 (폴백 포함)
 * @param {string} text - 복사할 텍스트
 * @returns {Promise<boolean>}
 */
async function copyToClipboard(text) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            var textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
        return true;
    } catch (err) {
        console.error('클립보드 복사 실패:', err);
        return false;
    }
}

// ============================================================================
// Interval 관리 (메모리 누수 방지)
// ============================================================================

var activeIntervals = [];

/**
 * Interval 등록
 * @param {number} intervalId - setInterval 반환값
 */
function registerInterval(intervalId) {
    activeIntervals.push(intervalId);
    return intervalId;
}

/**
 * 모든 등록된 Interval 정리
 */
function clearAllIntervals() {
    activeIntervals.forEach(function (id) { clearInterval(id); });
    activeIntervals = [];
}

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', function () {
    clearAllIntervals();
});

// ============================================================================
// Socket 안전성 유틸리티 [v4.21]
// ============================================================================

/**
 * 안전한 Socket.emit 래퍼
 * CLAUDE.md 가이드라인: socket.emit 전 socket.connected 확인 필수
 * @param {string} event - 이벤트명
 * @param {Object} data - 전송 데이터
 * @returns {boolean} 전송 성공 여부
 */
function safeSocketEmit(event, data) {
    if (typeof socket === 'undefined' || !socket || !socket.connected) {
        console.warn('[Socket] Not connected, skipping emit:', event);
        return false;
    }
    socket.emit(event, data);
    return true;
}

/**
 * 안전한 이미지 경로 생성
 * XSS 방지를 위한 경로 검증 및 인코딩
 * @param {string} path - 이미지 경로
 * @returns {string|null} 안전한 경로
 */
function safeImagePath(path) {
    if (!path || typeof path !== 'string') return null;
    // 위험 문자 필터링
    if (path.includes('<') || path.includes('>') || path.includes('"') || path.includes("'")) {
        console.warn('[Security] Invalid image path detected:', path);
        return null;
    }
    // 경로 컴포넌트만 인코딩
    return path.split('/').map(function (p) {
        return encodeURIComponent(p);
    }).join('/');
}

/**
 * 안전한 아바타 HTML 생성 (이미지 경로 검증 포함)
 * @param {string} name - 사용자 이름
 * @param {string} imagePath - 프로필 이미지 경로
 * @param {number} userId - 사용자 ID
 * @param {string} cssClass - CSS 클래스
 * @returns {string} HTML 문자열
 */
function createSafeAvatarHtml(name, imagePath, userId, cssClass) {
    cssClass = cssClass || 'message-avatar';
    var initial = (name && name.length > 0) ? escapeHtml(name[0].toUpperCase()) : '?';
    var color = getUserColor(userId || 0);

    if (imagePath) {
        var safePath = safeImagePath(imagePath);
        if (safePath) {
            return '<div class="' + cssClass + ' has-image"><img src="/uploads/' + safePath + '" alt="프로필"></div>';
        }
    }
    return '<div class="' + cssClass + '" style="background:' + color + '">' + initial + '</div>';
}

// ============================================================================
// [v4.30] 성능 최적화 유틸리티
// ============================================================================

/**
 * DOM 배치 업데이트 - DocumentFragment 사용
 * @param {HTMLElement} container - 대상 컨테이너
 * @param {string} html - 삽입할 HTML
 * @param {boolean} append - true면 추가, false면 교체
 */
function batchDOMUpdate(container, html, append) {
    if (!container) return;

    var template = document.createElement('template');
    template.innerHTML = html;

    if (!append) {
        container.innerHTML = '';
    }
    container.appendChild(template.content);
}

/**
 * 여러 요소를 DocumentFragment로 배치 추가
 * @param {HTMLElement} container - 대상 컨테이너
 * @param {Array<HTMLElement>} elements - 추가할 요소들
 */
function batchAppendElements(container, elements) {
    if (!container || !elements || !elements.length) return;

    var fragment = document.createDocumentFragment();
    elements.forEach(function (el) {
        if (el) fragment.appendChild(el);
    });
    container.appendChild(fragment);
}

/**
 * 이벤트 위임 헬퍼
 * @param {HTMLElement} parent - 부모 요소
 * @param {string} selector - 대상 선택자
 * @param {string} eventType - 이벤트 타입
 * @param {Function} handler - 핸들러 함수
 */
function delegateEvent(parent, selector, eventType, handler) {
    if (!parent) return;

    parent.addEventListener(eventType, function (e) {
        var target = e.target.closest(selector);
        if (target && parent.contains(target)) {
            handler.call(target, e, target);
        }
    });
}

/**
 * DOM 요소 캐시 (성능 향상)
 */
var elementCache = {};
var CACHE_MAX_SIZE = 100;

function getCachedElement(id) {
    if (elementCache[id]) {
        // 캐시된 요소가 여전히 DOM에 있는지 확인
        if (document.body.contains(elementCache[id])) {
            return elementCache[id];
        }
        delete elementCache[id];
    }

    var el = document.getElementById(id);
    if (el) {
        // 캐시 크기 제한
        var keys = Object.keys(elementCache);
        if (keys.length >= CACHE_MAX_SIZE) {
            delete elementCache[keys[0]];
        }
        elementCache[id] = el;
    }
    return el;
}

function clearElementCache() {
    elementCache = {};
}

/**
 * 이미지 lazy loading 속성 추가
 * @param {string} src - 이미지 경로
 * @param {string} alt - 대체 텍스트
 * @param {string} className - CSS 클래스
 */
function createLazyImage(src, alt, className) {
    return '<img src="' + escapeHtml(src) + '" alt="' + escapeHtml(alt || '') +
        '" class="' + (className || '') + '" loading="lazy">';
}

/**
 * IntersectionObserver 기반 lazy load 초기화
 * @param {string} selector - 대상 선택자
 * @param {Function} loadCallback - 로드 콜백
 */
function initLazyLoad(selector, loadCallback) {
    if (!('IntersectionObserver' in window)) {
        // fallback: 모든 요소 즉시 로드
        document.querySelectorAll(selector).forEach(loadCallback);
        return null;
    }

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                loadCallback(entry.target);
                observer.unobserve(entry.target);
            }
        });
    }, { rootMargin: '50px' });

    document.querySelectorAll(selector).forEach(function (el) {
        observer.observe(el);
    });

    return observer;
}

/**
 * requestIdleCallback 폴리필 및 래퍼
 * @param {Function} callback - 실행할 함수
 */
function runWhenIdle(callback) {
    if ('requestIdleCallback' in window) {
        requestIdleCallback(callback, { timeout: 2000 });
    } else {
        setTimeout(callback, 1);
    }
}

/**
 * 메모리 효율적인 배열 청크 처리
 * @param {Array} array - 처리할 배열
 * @param {number} chunkSize - 청크 크기
 * @param {Function} processor - 처리 함수
 * @param {Function} onComplete - 완료 콜백
 */
function processInChunks(array, chunkSize, processor, onComplete) {
    var index = 0;

    function processChunk() {
        var chunk = array.slice(index, index + chunkSize);
        chunk.forEach(processor);
        index += chunkSize;

        if (index < array.length) {
            runWhenIdle(processChunk);
        } else if (onComplete) {
            onComplete();
        }
    }

    if (array.length > 0) {
        runWhenIdle(processChunk);
    } else if (onComplete) {
        onComplete();
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.$ = $;
window.debounce = debounce;
window.throttle = throttle;
window.scheduleUpdate = scheduleUpdate;
window.escapeHtml = escapeHtml;
window.formatTime = formatTime;
window.formatDate = formatDate;
window.formatDateLabel = formatDateLabel;
window.getUserColor = getUserColor;
window.createAvatarHtml = createAvatarHtml;
window.createSafeAvatarHtml = createSafeAvatarHtml;
window.copyToClipboard = copyToClipboard;
window.registerInterval = registerInterval;
window.clearAllIntervals = clearAllIntervals;
// [v4.21] Socket/Security
window.safeSocketEmit = safeSocketEmit;
window.safeImagePath = safeImagePath;
// [v4.30] Performance
window.batchDOMUpdate = batchDOMUpdate;
window.batchAppendElements = batchAppendElements;
window.delegateEvent = delegateEvent;
window.getCachedElement = getCachedElement;
window.clearElementCache = clearElementCache;
window.createLazyImage = createLazyImage;
window.initLazyLoad = initLazyLoad;
window.runWhenIdle = runWhenIdle;
window.processInChunks = processInChunks;
