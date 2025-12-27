// 설정 및 테마 관리

import { getElement } from './state.js';

let themeSettings = {
    mode: 'dark',
    color: 'emerald',
    chatBg: 'none'
};

export function initTheme() {
    const saved = localStorage.getItem('messengerTheme');
    if (saved) {
        try {
            themeSettings = JSON.parse(saved);
        } catch (e) {
            console.error('테마 설정 로드 오류:', e);
        }
    }
    applyTheme();
    updateSettingsUI();
}

export function applyTheme() {
    const html = document.documentElement;

    if (themeSettings.mode === 'system') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
        html.setAttribute('data-theme', themeSettings.mode);
    }

    html.setAttribute('data-color', themeSettings.color);
    html.setAttribute('data-chat-bg', themeSettings.chatBg);
}

function saveThemeSettings() {
    localStorage.setItem('messengerTheme', JSON.stringify(themeSettings));
}

export function updateSettingsUI() {
    document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === themeSettings.mode);
    });

    document.querySelectorAll('.color-option').forEach(option => {
        option.classList.toggle('active', option.dataset.color === themeSettings.color);
    });

    document.querySelectorAll('.bg-option').forEach(option => {
        option.classList.toggle('active', option.dataset.bg === themeSettings.chatBg);
    });
}

export function setThemeMode(mode) {
    themeSettings.mode = mode;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

export function setThemeColor(color) {
    themeSettings.color = color;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

export function setChatBackground(bg) {
    themeSettings.chatBg = bg;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

export function resetSettings() {
    themeSettings = {
        mode: 'dark',
        color: 'emerald',
        chatBg: 'none'
    };
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

// System theme listener
if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (themeSettings.mode === 'system') {
            applyTheme();
        }
    });
}
