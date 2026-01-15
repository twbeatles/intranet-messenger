/**
 * 인증 모듈
 * 로그인, 회원가입, 로그아웃 및 API 통신 관련 함수
 */

// ============================================================================
// API 통신
// ============================================================================

/**
 * API 요청 래퍼 함수
 * @param {string} url - API URL
 * @param {Object} options - fetch 옵션
 * @returns {Promise<Object>} 응답 데이터
 */
async function api(url, options = {}) {
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const headers = {
            'Content-Type': 'application/json',
            ...(csrfToken && { 'X-CSRFToken': csrfToken }),
            ...options.headers
        };

        const res = await fetch(url, {
            ...options,
            headers: headers
        });

        // 비 JSON 응답 처리
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return {};
        }

        const json = await res.json();
        if (!res.ok) {
            throw new Error(json.error || `HTTP ${res.status}`);
        }
        return json;
    } catch (err) {
        console.error('API 오류:', url, err);
        throw err;
    }
}

// ============================================================================
// 인증 UI 헬퍼
// ============================================================================

/**
 * 인증 오류 메시지 표시
 * @param {string} msg - 오류 메시지
 */
function showAuthError(msg) {
    var authError = document.getElementById('authError');
    if (authError) {
        authError.textContent = msg;
        authError.classList.remove('hidden', 'success-message');
        authError.classList.add('error-message');
    }
}

/**
 * 인증 성공 메시지 표시
 * @param {string} msg - 성공 메시지
 */
function showAuthSuccess(msg) {
    var authError = document.getElementById('authError');
    if (authError) {
        authError.textContent = msg;
        authError.classList.remove('hidden', 'error-message');
        authError.classList.add('success-message');
    }
}

/**
 * 인증 메시지 숨기기
 */
function hideAuthError() {
    var authError = document.getElementById('authError');
    if (authError) {
        authError.classList.add('hidden');
    }
}

/**
 * 회원가입 폼 표시
 */
function showRegisterForm() {
    var loginForm = $('loginForm');
    var registerForm = $('registerForm');
    var switchReg = $('switchToRegisterWrap');
    var switchLogin = $('switchToLoginWrap');

    if (loginForm) loginForm.classList.add('hidden');
    if (registerForm) registerForm.classList.remove('hidden');
    if (switchReg) switchReg.style.display = 'none';
    if (switchLogin) switchLogin.style.display = 'inline';
}

/**
 * 로그인 폼 표시
 */
function showLoginForm() {
    var registerForm = $('registerForm');
    var loginForm = $('loginForm');
    var switchLogin = $('switchToLoginWrap');
    var switchReg = $('switchToRegisterWrap');

    if (registerForm) registerForm.classList.add('hidden');
    if (loginForm) loginForm.classList.remove('hidden');
    if (switchLogin) switchLogin.style.display = 'none';
    if (switchReg) switchReg.style.display = 'inline';

    hideAuthError();
}

// ============================================================================
// 인증 액션
// ============================================================================

/**
 * 로그인 처리
 */
async function doLogin() {
    const username = $('loginUsername').value.trim();
    const password = $('loginPassword').value;

    if (!username || !password) {
        showAuthError('아이디와 비밀번호를 입력하세요.');
        return;
    }

    try {
        const result = await api('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });

        if (result.success) {
            // CSRF 토큰 갱신
            if (result.csrf_token) {
                const meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) meta.setAttribute('content', result.csrf_token);
            }

            currentUser = result.user;
            showAuthSuccess('로그인 성공!');

            // UI 초기화 및 진입
            if (typeof initApp === 'function') {
                initApp();
            }
        } else {
            showAuthError(result.error || '로그인 실패');
        }
    } catch (err) {
        console.error('로그인 오류:', err);
        showAuthError(err.message || '서버 연결 오류');
    }
}

/**
 * 회원가입 처리
 */
async function doRegister() {
    const username = $('regUsername').value.trim();
    const password = $('regPassword').value;
    const nickname = $('regNickname').value.trim();

    if (!username || !password) {
        showAuthError('아이디와 비밀번호를 입력하세요.');
        return;
    }

    // 클라이언트 측 비밀번호 검증
    if (password.length < 8) {
        showAuthError('비밀번호는 8자 이상이어야 합니다.');
        return;
    }
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
        showAuthError('비밀번호는 영문자와 숫자를 포함해야 합니다.');
        return;
    }

    try {
        const result = await api('/api/register', {
            method: 'POST',
            body: JSON.stringify({ username, password, nickname })
        });

        if (result.success) {
            showAuthSuccess('회원가입 완료! 로그인해주세요.');
            showLoginForm();
        } else {
            showAuthError(result.error || '회원가입 실패');
        }
    } catch (err) {
        console.error('회원가입 오류:', err);
        showAuthError(err.message || '서버 연결 오류');
    }
}

/**
 * 로그아웃 처리
 */
async function logout() {
    try {
        // 모든 등록된 인터벌 정리
        if (typeof clearAllIntervals === 'function') {
            clearAllIntervals();
        }

        await api('/api/logout', { method: 'POST' });
    } catch (err) {
        console.warn('로그아웃 API 오류 (무시됨):', err);
    } finally {
        // 캐시 무효화 및 상태 초기화
        currentUser = null;
        currentRoom = null;
        rooms = [];

        // 로컬 스토리지 정리
        try {
            sessionStorage.clear();
        } catch (e) { }

        // 캐시 방지를 위해 타임스탬프 추가
        location.href = '/?_=' + Date.now();
    }
}

/**
 * 세션 체크 (새로고침 시 자동 로그인)
 */
async function checkSession() {
    try {
        const result = await api('/api/me');
        if (result.logged_in && result.user) {
            currentUser = result.user;
            if (typeof initApp === 'function') {
                initApp();
            }
        }
    } catch (err) {
        console.log('세션 체크 실패, 로그인 필요');
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.api = api;
window.showAuthError = showAuthError;
window.showAuthSuccess = showAuthSuccess;
window.hideAuthError = hideAuthError;
window.showRegisterForm = showRegisterForm;
window.showLoginForm = showLoginForm;
window.doLogin = doLogin;
window.doRegister = doRegister;
window.logout = logout;
window.checkSession = checkSession;
