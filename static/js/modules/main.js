// 메인 엔트리 포인트

import { state, cacheElements, getElement, getUserColor } from './state.js';
import * as Auth from './auth.js';
import * as Socket from './socket.js';
import * as UI from './ui.js';
import * as Chat from './chat.js';
import * as Settings from './settings.js';
import * as API from './api.js';
import { scheduleUpdate, escapeHtml } from './utils.js';

// 전역 UI 객체 노출 (HTML onclick 이벤트용)
window.UI = {
    openLightbox: UI.openLightbox,
    closeLightbox: UI.closeLightbox,
    prevImage: UI.prevImage,
    nextImage: UI.nextImage
};
// window.Chat = Chat; // needed for onclicks in appended HTML? Yes.
// Actually, `onclick` handlers in HTML string need global functions.
// I refactored `appendMessage` to use `window.UI` or add event listeners.
// However, `renderRoomList` and `renderOnlineUsers` use `onclick` property assignment which is fine.
// But `appendMessage` used `onclick="replyToMessage..."` in original code.
// In my `ui.js`, I changed them to use `div.querySelectorAll(...).onclick`.
// So globals might not be needed for those actions.
// But `openLightbox` is used in `innerHTML`. So `window.UI` is needed.

document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    setupEventListeners();
    initEmojiPicker();
    Settings.initTheme();
    Auth.checkSession();
});

export function initApp() {
    getElement('authContainer').style.display = 'none';
    getElement('appContainer').classList.add('active');

    const user = state.currentUser;
    getElement('userName').textContent = user.nickname;

    const userAvatar = getElement('userAvatar');
    if (user.profile_image) {
        userAvatar.innerHTML = `<img src="/uploads/${user.profile_image}" alt="프로필">`;
        userAvatar.classList.add('has-image');
    } else {
        userAvatar.textContent = (user.nickname && user.nickname.length > 0) ? user.nickname[0].toUpperCase() : '?';
        userAvatar.style.background = getUserColor(user.id);
    }

    if (window.MessengerNotification) MessengerNotification.requestPermission();
    if (window.MessengerStorage) MessengerStorage.init();

    Socket.initSocket();
    Socket.loadRooms();
    Socket.loadOnlineUsers();

    // Interval for online users
    setInterval(Socket.loadOnlineUsers, 30000);
}

function setupEventListeners() {
    const $ = getElement;

    $('loginBtn').onclick = Auth.doLogin;
    $('registerBtn').onclick = Auth.doRegister;
    $('showRegister').onclick = Auth.showRegisterForm;
    $('showLogin').onclick = Auth.showLoginForm;

    $('loginPassword').onkeydown = e => { if (e.key === 'Enter') Auth.doLogin(); };
    $('regNickname').onkeydown = e => { if (e.key === 'Enter') Auth.doRegister(); };

    $('sendBtn').onclick = Chat.sendMessage;
    $('messageInput').onkeydown = e => {
        const mentionAc = $('mentionAutocomplete');
        if (mentionAc && !mentionAc.classList.contains('hidden')) return;
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            Chat.sendMessage();
        }
    };
    $('messageInput').oninput = Chat.handleTyping;

    $('emojiBtn').onclick = () => $('emojiPicker').classList.toggle('active');
    $('attachBtn').onclick = () => $('fileInput').click();

    $('fileInput').onchange = async (e) => {
        const file = e.target.files[0];
        if (!file || !state.currentRoom) return;
        try {
            const result = await API.MessageAPI.uploadFile(file, state.currentRoom.id);
            if (result.success) {
                if (!result.upload_token) {
                    console.error('업로드 토큰이 없습니다.');
                    return;
                }
                const isImage = file.type && file.type.startsWith('image/');
                state.socket.emit('send_message', {
                    room_id: state.currentRoom.id,
                    content: file.name,
                    type: isImage ? 'image' : 'file',
                    upload_token: result.upload_token,
                    file_path: result.file_path,
                    file_name: result.file_name,
                    encrypted: false
                });
            }
        } catch (err) {
            console.error(err);
        }
        e.target.value = '';
    };

    $('newChatBtn').onclick = () => {
        API.UserAPI.getUsers().then(users => {
            const list = $('userList');
            list.innerHTML = users.map(u => {
                const initial = (u.nickname && u.nickname.length > 0) ? u.nickname[0].toUpperCase() : '?';
                const avatar = u.profile_image
                    ? `<div class="user-item-avatar has-image"><img src="/uploads/${u.profile_image}"></div>`
                    : `<div class="user-item-avatar">${initial}</div>`;
                return `
                    <div class="user-item" data-user-id="${u.id}">
                        ${avatar}
                        <div class="user-item-info">
                            <div class="user-item-name">${escapeHtml(u.nickname)}</div>
                            <div class="user-item-status ${u.status}">${u.status}</div>
                        </div>
                        <input type="checkbox" class="user-checkbox">
                    </div>`;
            }).join('');

            list.querySelectorAll('.user-item').forEach(el => {
                el.onclick = () => {
                    const cb = el.querySelector('.user-checkbox');
                    cb.checked = !cb.checked;
                    el.classList.toggle('selected', cb.checked);
                };
            });
            UI.openModal('newChatModal');
        });
    };

    $('closeNewChatModal').onclick = () => UI.closeModal('newChatModal');

    $('createRoomBtn').onclick = () => {
        const selected = [...document.querySelectorAll('#userList .user-item.selected')]
            .map(el => parseInt(el.dataset.userId));
        if (selected.length === 0) return;

        API.RoomAPI.createRoom(selected, $('roomName').value.trim())
            .then(result => {
                if(result.success) {
                    UI.closeModal('newChatModal');
                    Socket.loadRooms().then(() => {
                        const room = state.rooms.find(r => r.id === result.room_id);
                        if(room) Chat.openRoom(room);
                    });
                }
            });
    };

    $('logoutBtn').onclick = Auth.logout;

    // ... Add more event listeners for other buttons (settings, profile, etc.)
    // For brevity, I'm adding essential ones.

    $('settingsBtn').onclick = () => {
        Settings.updateSettingsUI();
        UI.openModal('settingsModal');
    };
    $('closeSettingsBtn').onclick = () => UI.closeModal('settingsModal');
    $('closeSettingsModal').onclick = () => UI.closeModal('settingsModal');
    $('resetSettingsBtn').onclick = Settings.resetSettings;

    document.querySelectorAll('.theme-toggle-btn').forEach(btn =>
        btn.onclick = () => Settings.setThemeMode(btn.dataset.theme));
    document.querySelectorAll('.color-option').forEach(opt =>
        opt.onclick = () => Settings.setThemeColor(opt.dataset.color));
    document.querySelectorAll('.bg-option').forEach(opt =>
        opt.onclick = () => Settings.setChatBackground(opt.dataset.bg));

    // Global click to close menus
    document.addEventListener('click', e => {
        if (!e.target.closest('#emojiBtn') && !e.target.closest('#emojiPicker')) {
            $('emojiPicker').classList.remove('active');
        }
        if (!e.target.closest('#roomSettingsMenu') && !e.target.closest('#roomSettingsBtn')) {
            $('roomSettingsMenu').classList.remove('active');
        }
    });

    // Room settings menu
    $('roomSettingsBtn').onclick = (e) => {
        e.stopPropagation();
        $('roomSettingsMenu').classList.toggle('active');
    };

    $('leaveRoomBtn').onclick = async () => {
        if (!state.currentRoom) return;
        if (!confirm('나가시겠습니까?')) return;
        await API.RoomAPI.leaveRoom(state.currentRoom.id);
        state.currentRoom = null;
        getElement('chatContent').classList.add('hidden');
        getElement('emptyState').classList.remove('hidden');
        Socket.loadRooms();
    };

    // Profile
    $('profileBtn').onclick = openProfileModal;
    $('userAvatar').onclick = openProfileModal;
    $('closeProfileModal').onclick = () => UI.closeModal('profileModal');
    $('cancelProfileBtn').onclick = () => UI.closeModal('profileModal');

    $('saveProfileBtn').onclick = async () => {
        const nickname = $('profileNickname').value.trim();
        const statusMsg = $('profileStatusMessage').value.trim();

        const res = await API.UserAPI.updateProfile({
            nickname: nickname || null,
            status_message: statusMsg || null
        });

        if (res.success) {
            state.currentUser.nickname = nickname;
            $('userName').textContent = nickname;
            UI.showToast('프로필 저장됨', 'success');
            UI.closeModal('profileModal');
            state.socket.emit('profile_updated', { nickname });
        }
    };
}

function openProfileModal() {
    const $ = getElement;
    $('profileNickname').value = state.currentUser.nickname || '';
    $('profileStatusMessage').value = state.currentUser.status_message || '';

    // Preview update logic needed here or simplified
    UI.openModal('profileModal');
}

function initEmojiPicker() {
    const emojis = ['😀', '😂', '😊', '😍', '🥰', '😎', '🤔', '😅', '😭', '😤', '👍', '👎', '❤️', '🔥', '✨', '🎉'];
    getElement('emojiPicker').innerHTML = emojis.map(e => `<button class="emoji-btn">${e}</button>`).join('');
    getElement('emojiPicker').querySelectorAll('.emoji-btn').forEach(btn => {
        btn.onclick = () => {
            const input = getElement('messageInput');
            input.value += btn.textContent;
            input.focus();
        };
    });
}
