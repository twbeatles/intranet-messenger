// 유틸리티 함수 모음

// 디바운스
export function debounce(func, wait) {
    var timeout;
    return function () {
        var context = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function () {
            func.apply(context, args);
        }, wait);
    };
}

// 쓰로틀
export function throttle(func, limit) {
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

export function scheduleUpdate(updateFn) {
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

// HTML 이스케이프
export function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 시간 포맷팅
export function formatTime(dateStr) {
    if (!dateStr) return '';

    let d;
    if (dateStr.includes('T')) {
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    if (isNaN(d.getTime())) return '';

    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '방금';
    if (diffMins < 60) return `${diffMins}분 전`;

    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
        return '어제';
    }

    return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

// 날짜 포맷팅
export function formatDate(dateStr) {
    if (!dateStr) return '';

    let d;
    if (dateStr.includes('T')) {
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    if (isNaN(d.getTime())) return '';

    const today = new Date();
    if (d.toDateString() === today.toDateString()) return '오늘';

    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return '어제';

    return d.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
}

// 날짜 레이블 (오늘, 어제, MM월 DD일)
export function formatDateLabel(dateStr) {
    var today = new Date();
    var msgDate = new Date(dateStr);

    if (today.toDateString() === msgDate.toDateString()) {
        return '오늘';
    }

    var yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (yesterday.toDateString() === msgDate.toDateString()) {
        return '어제';
    }

    return (msgDate.getMonth() + 1) + '월 ' + msgDate.getDate() + '일';
}

// 클립보드 복사
export async function copyToClipboard(text) {
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

// 유저 색상 팔레트
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

export function getUserColor(userId) {
    var index = Math.abs(userId) % userColorPalette.length;
    return userColorPalette[index];
}

// 아바타 HTML 생성
export function createAvatarHtml(name, imagePath, userId, cssClass) {
    cssClass = cssClass || 'message-avatar';
    var initial = (name && name.length > 0) ? name[0].toUpperCase() : '?';
    var color = getUserColor(userId || 0);

    if (imagePath) {
        return '<div class="' + cssClass + ' has-image"><img src="/uploads/' + imagePath + '" alt="프로필"></div>';
    } else {
        return '<div class="' + cssClass + '" style="background:' + color + '">' + initial + '</div>';
    }
}

// E2E 암호화 (클라이언트)
export const E2E = {
    encrypt: function (plaintext, key) {
        try {
            if (!plaintext || !key) return plaintext || '';
            // CryptoJS is loaded globally
            return CryptoJS.AES.encrypt(String(plaintext), String(key)).toString();
        } catch (e) {
            console.error('암호화 오류:', e);
            return plaintext || '';
        }
    },
    decrypt: function (ciphertext, key) {
        try {
            if (!ciphertext || !key) return ciphertext || '';
            if (typeof ciphertext !== 'string') return String(ciphertext);

            if (!ciphertext.includes('U2FsdGVkX')) {
                return ciphertext;
            }

            var bytes = CryptoJS.AES.decrypt(ciphertext, String(key));
            var decrypted = bytes.toString(CryptoJS.enc.Utf8);

            if (!decrypted || decrypted.length === 0) {
                console.warn('복호화 결과 비어있음, 원본 반환');
                return ciphertext;
            }

            return decrypted;
        } catch (e) {
            console.error('복호화 오류:', e.message || e);
            return ciphertext || '[암호화된 메시지]';
        }
    }
};

// 멘션 파싱
export function parseMentions(text) {
    return text.replace(/@([가-힣a-zA-Z0-9]+)/g, '<span class="mention">@$1</span>');
}
