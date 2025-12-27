// UI 렌더링 및 조작

import { state, getElement } from './state.js';
import {
    escapeHtml, formatTime, formatDateLabel,
    createAvatarHtml, E2E, parseMentions
} from './utils.js';
import * as Chat from './chat.js';

// 토스트 알림
let toastContainer = null;

export function initToast() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        toastContainer.setAttribute('role', 'alert');
        toastContainer.setAttribute('aria-live', 'polite');
        document.body.appendChild(toastContainer);
    }
}

export function showToast(message, type = 'info', duration = 4000, title) {
    initToast();

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const titles = { success: '성공', error: '오류', warning: '주의', info: '알림' };

    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <div class="toast-body">
            <div class="toast-title">${title || titles[type]}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" aria-label="닫기">✕</button>
        <div class="toast-progress" style="animation-duration:${duration}ms;"></div>
    `;

    toast.querySelector('.toast-close').onclick = () => closeToast(toast);

    while (toastContainer.children.length >= 5) {
        closeToast(toastContainer.firstChild);
    }

    toastContainer.appendChild(toast);

    let timeoutId = setTimeout(() => closeToast(toast), duration);

    toast.onmouseenter = () => {
        clearTimeout(timeoutId);
        const progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'paused';
    };

    toast.onmouseleave = () => {
        const progress = toast.querySelector('.toast-progress');
        if (progress) progress.style.animationPlayState = 'running';
        timeoutId = setTimeout(() => closeToast(toast), 2000);
    };

    return toast;
}

function closeToast(toast) {
    if (toast && toast.parentNode) {
        toast.classList.add('hiding');
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }
}

// 모달 조작
export function openModal(modalId) {
    const modal = getElement(modalId);
    if (modal) modal.classList.add('active');
}

export function closeModal(modalId) {
    const modal = getElement(modalId);
    if (modal) modal.classList.remove('active');
}

// 로딩 화면
export function toggleLoading(show) {
    // 구현 필요 시 추가
}

// 룸 리스트 렌더링
export function renderRoomList() {
    const roomListEl = getElement('roomList');
    if (!roomListEl) return;

    roomListEl.innerHTML = state.rooms.map(room => {
        const isActive = state.currentRoom && state.currentRoom.id === room.id;
        const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
        const time = room.last_message_time ? formatTime(room.last_message_time) : '';
        const preview = room.last_message ? '[암호화됨]' : '새 대화';
        const pinnedClass = room.pinned ? 'pinned' : '';
        const pinnedIcon = room.pinned ? '<span class="pin-icon">📌</span>' : '';

        const avatarUserId = room.type === 'direct' && room.partner ? room.partner.id : room.id;
        const avatarName = room.type === 'direct' && room.partner ? room.partner.nickname : (room.name || '그');
        const avatarImage = room.type === 'direct' && room.partner ? room.partner.profile_image : null;
        const avatarHtml = createAvatarHtml(avatarName, avatarImage, avatarUserId, 'room-avatar');

        const unreadBadge = room.unread_count > 0 ? `<span class="unread-badge">${room.unread_count}</span>` : '';

        return `
            <div class="room-item ${isActive ? 'active' : ''} ${pinnedClass}" data-room-id="${room.id}">
                ${avatarHtml}
                <div class="room-info">
                    <div class="room-name">${escapeHtml(name)} 🔒 ${pinnedIcon}</div>
                    <div class="room-preview">${preview}</div>
                </div>
                <div class="room-meta">
                    <div class="room-time">${time}</div>
                    ${unreadBadge}
                </div>
            </div>
        `;
    }).join('');

    // 이벤트 리스너 연결
    roomListEl.querySelectorAll('.room-item').forEach(el => {
        el.onclick = () => {
            const room = state.rooms.find(r => r.id === parseInt(el.dataset.roomId));
            if (room) Chat.openRoom(room);
        };
    });
}

// 메시지 렌더링
export function renderMessages(messages, lastReadId) {
    const container = getElement('messagesContainer');
    if (!container) return;

    container.innerHTML = '';
    let lastDate = null;
    const todayStr = new Date().toISOString().split('T')[0];
    let localTodayDividerShown = false;
    let unreadDividerShown = false;

    messages.forEach(msg => {
        const msgDate = msg.created_at.split(' ')[0] || msg.created_at.split('T')[0];

        if (msgDate !== lastDate) {
            const isToday = msgDate === todayStr;
            if (!isToday || (isToday && !localTodayDividerShown)) {
                lastDate = msgDate;
                const divider = document.createElement('div');
                divider.className = 'date-divider';
                divider.setAttribute('data-date', msgDate);
                divider.innerHTML = `<span>${formatDateLabel(msgDate)}</span>`;
                container.appendChild(divider);

                if (isToday) localTodayDividerShown = true;
            }
        }

        if (!unreadDividerShown && lastReadId > 0 && msg.id > lastReadId && msg.sender_id !== state.currentUser.id) {
            const unreadDivider = document.createElement('div');
            unreadDivider.className = 'unread-divider';
            unreadDivider.innerHTML = '<span>여기서부터 읽지 않음</span>';
            container.appendChild(unreadDivider);
            unreadDividerShown = true;
        }

        appendMessage(msg);
    });

    if (unreadDividerShown) {
        const unreadDiv = container.querySelector('.unread-divider');
        if (unreadDiv) {
            unreadDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
    }

    Chat.scrollToBottom();
}

export function appendMessage(msg) {
    const container = getElement('messagesContainer');
    if (!container) return;

    const isSent = msg.sender_id === state.currentUser.id;
    const div = document.createElement('div');
    div.className = 'message ' + (isSent ? 'sent' : '');
    div.dataset.messageId = msg.id;
    div.dataset.senderId = msg.sender_id;

    let content = '';
    if (msg.message_type === 'image') {
        content = `<img src="/uploads/${msg.file_path}" class="message-image" onclick="window.UI.openLightbox(this.src)">`;
    } else if (msg.message_type === 'file') {
        content = `
            <div class="message-file">
                <span>📄</span>
                <div class="message-file-info">
                    <div class="message-file-name">${escapeHtml(msg.file_name)}</div>
                </div>
                <a href="/uploads/${msg.file_path}" download="${msg.file_name}" class="icon-btn">⬇</a>
            </div>`;
    } else {
        const decrypted = state.currentRoomKey && msg.encrypted
            ? E2E.decrypt(msg.content, state.currentRoomKey)
            : msg.content;
        content = `<div class="message-bubble">${parseMentions(escapeHtml(decrypted))}</div>`;
    }

    const unreadHtml = msg.unread_count > 0 ? `<span class="unread-count">${msg.unread_count}</span>` : '';
    const senderName = msg.sender_name || '사용자';
    const avatarHtml = createAvatarHtml(senderName, msg.sender_image, msg.sender_id, 'message-avatar');

    let actionsHtml = `<div class="message-actions">
        <button class="message-action-btn" data-action="reply" title="답장">↩</button>`;

    if (isSent && msg.message_type !== 'image' && msg.message_type !== 'file') {
        actionsHtml += `<button class="message-action-btn edit-btn" data-action="edit" title="수정">✏</button>`;
    }
    if (isSent) {
        actionsHtml += `<button class="message-action-btn delete-btn" data-action="delete" title="삭제">🗑</button>`;
    }
    actionsHtml += '</div>';

    let replyHtml = '';
    if (msg.reply_to && msg.reply_content) {
        let decryptedReply = state.currentRoomKey
            ? E2E.decrypt(msg.reply_content, state.currentRoomKey)
            : msg.reply_content;
        if (!decryptedReply) decryptedReply = msg.reply_content;

        replyHtml = `
            <div class="message-reply" style="cursor:pointer;">
                <div class="reply-indicator">↩ ${escapeHtml(msg.reply_sender || '사용자')}에게 답장</div>
                <div class="reply-text">${escapeHtml(decryptedReply)}</div>
            </div>`;
    }

    div.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            <div class="message-sender">${escapeHtml(senderName)}</div>
            ${replyHtml}
            ${content}
            <div class="message-meta">
                ${unreadHtml}
                <span>${formatTime(msg.created_at)}</span>
            </div>
        </div>
        ${actionsHtml}
    `;

    div._messageData = msg;

    // 이벤트 바인딩
    div.querySelectorAll('[data-action="reply"]').forEach(btn =>
        btn.onclick = () => Chat.replyToMessage(msg.id));
    div.querySelectorAll('[data-action="edit"]').forEach(btn =>
        btn.onclick = () => Chat.editMessage(msg.id));
    div.querySelectorAll('[data-action="delete"]').forEach(btn =>
        btn.onclick = () => Chat.deleteMessage(msg.id));

    const replyEl = div.querySelector('.message-reply');
    if (replyEl) {
        replyEl.onclick = () => Chat.scrollToMessage(msg.reply_to);
    }

    // 이미지 클릭 바인딩 (innerHTML로 넣었으므로 다시 찾아야 함, 또는 전역 함수 사용)
    // 여기서는 onclick 속성으로 window.UI.openLightbox를 호출하도록 해둠.
    // main.js에서 window.UI = UIModule 형태로 노출 필요.

    container.appendChild(div);
}

// 온라인 사용자 목록
export function renderOnlineUsers(users) {
    const container = getElement('onlineUsersList');
    if (!container) return;

    if (users.length === 0) {
        container.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">온라인 사용자가 없습니다</span>';
        return;
    }

    container.innerHTML = users.map(u => {
        const initial = (u.nickname && u.nickname.length > 0) ? u.nickname[0].toUpperCase() : '?';
        const name = u.nickname || '사용자';
        return `
            <div class="online-user" data-user-id="${u.id}" title="${escapeHtml(name)}">
                ${initial}
                <span class="online-user-tooltip">${escapeHtml(name)}</span>
            </div>
        `;
    }).join('');

    container.querySelectorAll('.online-user').forEach(el => {
        el.onclick = () => Chat.startDirectChat(parseInt(el.dataset.userId));
    });
}

// 라이트박스
export function openLightbox(imageSrc) {
    const lightbox = getElement('lightbox');
    const lightboxImg = getElement('lightboxImage');
    if (!lightbox || !lightboxImg) return;

    state.lightboxImages = Array.from(document.querySelectorAll('.message-image')).map(img => img.src);
    state.currentImageIndex = state.lightboxImages.indexOf(imageSrc);
    if (state.currentImageIndex === -1) state.currentImageIndex = 0;

    lightboxImg.src = imageSrc;
    lightbox.classList.add('active');

    // 키보드 이벤트는 main.js에서 전역으로 관리하거나 여기서 등록/해제
}

export function closeLightbox() {
    const lightbox = getElement('lightbox');
    if (lightbox) lightbox.classList.remove('active');
}

export function nextImage() {
    if (state.lightboxImages.length === 0) return;
    state.currentImageIndex = (state.currentImageIndex + 1) % state.lightboxImages.length;
    const img = getElement('lightboxImage');
    if(img) img.src = state.lightboxImages[state.currentImageIndex];
}

export function prevImage() {
    if (state.lightboxImages.length === 0) return;
    state.currentImageIndex = (state.currentImageIndex - 1 + state.lightboxImages.length) % state.lightboxImages.length;
    const img = getElement('lightboxImage');
    if(img) img.src = state.lightboxImages[state.currentImageIndex];
}
