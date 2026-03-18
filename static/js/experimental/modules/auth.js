// 인증 모듈

import { state, getElement, setCurrentUser } from './state.js';
import { AuthAPI } from './api.js';
import { initApp } from './main.js'; // Cyclic dependency handled by initApp calling initSocket? No, auth calls initApp.

export async function checkSession() {
    try {
        const result = await AuthAPI.checkSession();
        if (result.logged_in && result.user) {
            setCurrentUser(result.user);
            initApp();
        }
    } catch (err) {
        console.log('세션 체크 실패, 로그인 필요');
    }
}

export function showLoginForm() {
    getElement('registerForm').classList.add('hidden');
    getElement('loginForm').classList.remove('hidden');
    getElement('switchToLoginWrap').style.display = 'none';
    getElement('switchToRegisterWrap').style.display = 'inline';
    getElement('authError').classList.add('hidden');
}

export function showRegisterForm() {
    getElement('loginForm').classList.add('hidden');
    getElement('registerForm').classList.remove('hidden');
    getElement('switchToRegisterWrap').style.display = 'none';
    getElement('switchToLoginWrap').style.display = 'inline';
}

function showAuthError(msg) {
    const el = getElement('authError');
    el.textContent = msg;
    el.classList.remove('hidden', 'success-message');
    el.classList.add('error-message');
}

function showAuthSuccess(msg) {
    const el = getElement('authError');
    el.textContent = msg;
    el.classList.remove('hidden', 'error-message');
    el.classList.add('success-message');
}

export async function doLogin() {
    const username = getElement('loginUsername').value.trim();
    const password = getElement('loginPassword').value;

    if (!username || !password) {
        showAuthError('아이디와 비밀번호를 입력하세요.');
        return;
    }

    try {
        const result = await AuthAPI.login(username, password);
        if (result.success) {
            setCurrentUser(result.user);
            initApp();
        } else {
            showAuthError(result.error || '로그인 실패');
        }
    } catch (err) {
        console.error('로그인 오류:', err);
        showAuthError('서버 연결 오류');
    }
}

export async function doRegister() {
    const username = getElement('regUsername').value.trim();
    const password = getElement('regPassword').value;
    const nickname = getElement('regNickname').value.trim();

    if (!username || !password) {
        showAuthError('아이디와 비밀번호를 입력하세요.');
        return;
    }

    try {
        const result = await AuthAPI.register(username, password, nickname);
        if (result.success) {
            showAuthSuccess('회원가입 완료! 로그인해주세요.');
            showLoginForm();
        } else {
            showAuthError(result.error || '회원가입 실패');
        }
    } catch (err) {
        console.error('회원가입 오류:', err);
        showAuthError('서버 연결 오류');
    }
}

export async function logout() {
    await AuthAPI.logout();
    location.reload();
}
