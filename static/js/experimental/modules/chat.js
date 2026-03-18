// 채팅 기능 모듈

import { state, getElement } from './state.js';
import { E2E, escapeHtml } from './utils.js';
import { RoomAPI, MessageAPI } from './api.js';
import * as UI from './ui.js';
import * as Socket from './socket.js';

export async function openRoom(room) {
    if (state.currentRoom) {
        state.socket.emit('leave_room', { room_id: state.currentRoom.id });
    }

    state.currentRoom = room;
    state.socket.emit('join_room', { room_id: room.id });

    const emptyState = getElement('emptyState');
    const chatContent = getElement('chatContent');
    const chatName = getElement('chatName');
    const chatAvatar = getElement('chatAvatar');
    const chatStatus = getElement('chatStatus');
    const sidebar = getElement('sidebar');

    if (emptyState) emptyState.classList.add('hidden');
    if (chatContent) chatContent.classList.remove('hidden');

    const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
    if (chatName) chatName.innerHTML = `${escapeHtml(name)} 🔒`;
    if (chatAvatar) chatAvatar.textContent = name[0].toUpperCase();

    if (chatStatus) {
        chatStatus.textContent = room.type === 'direct' && room.partner
            ? (room.partner.status === 'online' ? '온라인' : '오프라인')
            : `${room.member_count}명 참여 중`;
    }

    const pinText = getElement('pinRoomText');
    const muteText = getElement('muteRoomText');
    if (pinText) pinText.textContent = room.pinned ? '고정 해제' : '상단 고정';
    if (muteText) muteText.textContent = room.muted ? '알림 켜기' : '알림 끄기';

    try {
        const result = await RoomAPI.getMessages(room.id);
        state.currentRoomKey = result.encryption_key;

        let lastReadId = 0;
        if (result.members) {
            const currentMember = result.members.find(m => m.id === state.currentUser.id);
            if (currentMember) lastReadId = currentMember.last_read_message_id || 0;
        }

        UI.renderMessages(result.messages, lastReadId);

        if (result.messages.length > 0) {
            state.socket.emit('message_read', {
                room_id: room.id,
                message_id: result.messages[result.messages.length - 1].id
            });
        }

        // Storage caching if available
        if (window.MessengerStorage) {
            MessengerStorage.cacheMessages(room.id, result.messages);
        }

    } catch (err) {
        console.error('메시지 로드 실패:', err);
        if (window.MessengerStorage) {
            const cached = await MessengerStorage.getCachedMessages(room.id);
            if (cached.length > 0) {
                UI.renderMessages(cached, 0);
            }
        }
    }

    UI.renderRoomList();
    if (sidebar) sidebar.classList.remove('active');
}

export function sendMessage() {
    const input = getElement('messageInput');
    const content = input.value.trim();

    if (!content || !state.currentRoom || !state.currentRoomKey) return;

    const encrypted = E2E.encrypt(content, state.currentRoomKey);

    state.socket.emit('send_message', {
        room_id: state.currentRoom.id,
        content: encrypted,
        type: 'text',
        encrypted: true,
        reply_to: state.replyingTo ? state.replyingTo.id : null
    });

    input.value = '';
    input.style.height = 'auto';
    clearReply();
}

export function handleTyping() {
    const input = getElement('messageInput');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';

    if (state.currentRoom) {
        state.socket.emit('typing', { room_id: state.currentRoom.id, is_typing: true });

        clearTimeout(state.typingTimeout);
        state.typingTimeout = setTimeout(() => {
            state.socket.emit('typing', { room_id: state.currentRoom.id, is_typing: false });
        }, 2000);
    }
}

export function scrollToBottom() {
    const container = getElement('messagesContainer');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

export function startDirectChat(userId) {
    RoomAPI.createRoom([userId])
        .then(async (result) => {
            if (result.success) {
                await Socket.loadRooms();
                const room = state.rooms.find(r => r.id === result.room_id);
                if (room) openRoom(room);
            }
        })
        .catch(err => console.error(err));
}

// 답장 기능
export function setReplyTo(message) {
    state.replyingTo = message;
    updateReplyPreview();
    const input = getElement('messageInput');
    if(input) input.focus();
}

export function clearReply() {
    state.replyingTo = null;
    updateReplyPreview();
}

function updateReplyPreview() {
    const container = getElement('replyPreview');
    if (!container) return;

    if (state.replyingTo) {
        container.innerHTML = `
            <div class="reply-preview">
                <div class="reply-preview-content">
                    <div class="reply-preview-sender">${escapeHtml(state.replyingTo.sender_name)}</div>
                    <div class="reply-preview-text">${escapeHtml(state.replyingTo.content || '[파일]')}</div>
                </div>
                <button class="reply-preview-close">✕</button>
            </div>`;
        container.classList.remove('hidden');
        container.querySelector('.reply-preview-close').onclick = clearReply;
    } else {
        container.innerHTML = '';
        container.classList.add('hidden');
    }
}

export function replyToMessage(messageId) {
    // DOM에서 메시지 데이터를 찾음
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    if (msgEl && msgEl._messageData) {
        setReplyTo(msgEl._messageData);
    }
}

export function scrollToMessage(messageId, retryCount = 0) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);

    if (msgEl) {
        msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        msgEl.classList.add('highlight');
        setTimeout(() => msgEl.classList.remove('highlight'), 2000);
    } else if (retryCount < 5) {
        setTimeout(() => scrollToMessage(messageId, retryCount + 1), 100);
    }
}

export function editMessage(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    if (!msgEl || !msgEl._messageData) return;

    const msg = msgEl._messageData;
    const currentContent = state.currentRoomKey && msg.encrypted
        ? E2E.decrypt(msg.content, state.currentRoomKey)
        : msg.content;

    const newContent = prompt('메시지 수정:', currentContent);
    if (newContent === null || newContent.trim() === '' || newContent === currentContent) return;

    const encryptedContent = state.currentRoomKey
        ? E2E.encrypt(newContent.trim(), state.currentRoomKey)
        : newContent.trim();

    state.socket.emit('edit_message', {
        message_id: messageId,
        room_id: state.currentRoom.id,
        content: encryptedContent,
        encrypted: !!state.currentRoomKey
    });
}

export function deleteMessage(messageId) {
    if (!confirm('이 메시지를 삭제하시겠습니까?')) return;

    state.socket.emit('delete_message', {
        message_id: messageId,
        room_id: state.currentRoom.id
    });
}
