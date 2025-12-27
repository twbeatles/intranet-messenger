// Socket.IO 관리

import { state, getElement } from './state.js';
import { RoomAPI, UserAPI } from './api.js';
import { E2E, escapeHtml, formatDateLabel } from './utils.js';
import * as UI from './ui.js';
import * as Chat from './chat.js';

export function initSocket() {
    state.socket = io();

    state.socket.on('connect', () => {
        console.log('Socket.IO 연결됨');
        state.reconnectAttempts = 0;
        updateConnectionStatus('connected');

        if (state.currentRoom) {
            state.socket.emit('join_room', { room_id: state.currentRoom.id });
        }
    });

    state.socket.on('disconnect', () => {
        console.log('Socket.IO 연결 끊김');
        updateConnectionStatus('disconnected');
    });

    state.socket.on('connect_error', () => {
        state.reconnectAttempts++;
        updateConnectionStatus('reconnecting');
    });

    state.socket.on('new_message', handleNewMessage);
    state.socket.on('read_updated', handleReadUpdated);
    state.socket.on('user_typing', handleUserTyping);
    state.socket.on('user_status', handleUserStatus);
    state.socket.on('room_updated', () => loadRooms());
    state.socket.on('room_name_updated', handleRoomNameUpdated);
    state.socket.on('room_members_updated', handleRoomMembersUpdated);
    state.socket.on('message_deleted', handleMessageDeleted);
    state.socket.on('message_edited', handleMessageEdited);
    state.socket.on('user_profile_updated', handleUserProfileUpdated);
    state.socket.on('error', (data) => console.error('Socket 오류:', data.message));
}

function updateConnectionStatus(status) {
    const statusEl = getElement('connectionStatus');
    if (!statusEl) return;

    statusEl.className = 'connection-status';

    switch (status) {
        case 'connected':
            statusEl.classList.add('connected');
            statusEl.querySelector('.status-text').textContent = '연결됨';
            setTimeout(() => statusEl.classList.remove('visible'), 2000);
            break;
        case 'disconnected':
            statusEl.classList.add('visible', 'disconnected');
            statusEl.querySelector('.status-text').textContent = '연결 끊김';
            break;
        case 'reconnecting':
            statusEl.classList.add('visible');
            statusEl.querySelector('.status-text').textContent = `재연결 중... (${state.reconnectAttempts})`;
            break;
    }
}

export async function loadRooms() {
    try {
        const rooms = await RoomAPI.getRooms();
        state.rooms = rooms;
        UI.renderRoomList();
    } catch (err) {
        console.error('대화방 로드 실패:', err);
    }
}

export async function loadOnlineUsers() {
    try {
        const users = await UserAPI.getOnlineUsers();
        UI.renderOnlineUsers(users);
    } catch (err) {
        console.error('온라인 사용자 로드 실패:', err);
    }
}

// 이벤트 핸들러들
function handleNewMessage(msg) {
    if (state.currentRoom && msg.room_id === state.currentRoom.id) {
        // 날짜 구분선 처리는 renderMessages/appendMessage 내에서 로직을 좀 더 다듬어야 하지만
        // 여기서는 단순화하여 UI 모듈에 위임.
        // 하지만 기존 코드는 여기서 날짜 구분선 로직을 수행했음.
        // UI.appendMessage에 날짜 구분선 체크 로직을 포함시키는게 좋음.

        // 날짜 구분선 체크를 위해 컨테이너의 마지막 메시지 날짜 확인 필요할 수도 있음.
        // 일단 UI.appendMessage가 처리하도록 하고 여기서는 그냥 호출.

        // 날짜 구분선 중복 방지 로직 (UI.js 로 이동 권장되지만, 여기서 처리)
        const container = getElement('messagesContainer');
        const msgDate = msg.created_at.split(' ')[0] || msg.created_at.split('T')[0];
        const existingDivider = container.querySelector(`.date-divider[data-date="${msgDate}"]`);

        // 오늘 날짜인지
        const todayStr = new Date().toISOString().split('T')[0];
        const isToday = msgDate === todayStr;
        const todayDividerExists = container.querySelector(`.date-divider[data-date="${todayStr}"]`);

        if (!existingDivider && (!isToday || !todayDividerExists)) {
             const divider = document.createElement('div');
             divider.className = 'date-divider';
             divider.setAttribute('data-date', msgDate);
             divider.innerHTML = `<span>${formatDateLabel(msgDate)}</span>`;
             container.appendChild(divider);
        }

        UI.appendMessage(msg);
        Chat.scrollToBottom();
        state.socket.emit('message_read', { room_id: state.currentRoom.id, message_id: msg.id });
    } else {
        if (window.MessengerNotification && msg.sender_id !== state.currentUser.id) {
            const room = state.rooms.find(r => r.id === msg.room_id);
            const roomKey = room ? room.encryption_key : null;
            const decrypted = roomKey && msg.encrypted ? E2E.decrypt(msg.content, roomKey) : msg.content;
            MessengerNotification.show(msg.sender_name, decrypted, msg.room_id);
        }
    }
    loadRooms();
}

function handleReadUpdated(data) {
    if (state.currentRoom && data.room_id === state.currentRoom.id) {
        // updateUnreadCounts logic
        // This usually requires re-fetching messages or updating DOM directly
        // Simple way: re-fetch messages invisibly or update counters
        RoomAPI.getMessages(state.currentRoom.id).then(res => {
            res.messages.forEach(msg => {
                const el = document.querySelector(`[data-message-id="${msg.id}"] .unread-count`);
                if (el) {
                    if (msg.unread_count > 0) el.textContent = msg.unread_count;
                    else el.remove();
                }
            });
        });
    }
}

function handleUserTyping(data) {
    if (state.currentRoom && data.room_id === state.currentRoom.id) {
        const indicator = getElement('typingIndicator');
        if (indicator) {
            if (data.is_typing) {
                indicator.textContent = `${data.nickname}님이 입력 중...`;
                indicator.classList.remove('hidden');
            } else {
                indicator.classList.add('hidden');
            }
        }
    }
}

function handleUserStatus(data) {
    loadRooms();
    loadOnlineUsers();
}

function handleRoomNameUpdated(data) {
    loadRooms();
    if (state.currentRoom && state.currentRoom.id === data.room_id) {
        state.currentRoom.name = data.name;
        const chatName = getElement('chatName');
        if (chatName) chatName.innerHTML = `${escapeHtml(data.name)} 🔒`;
    }
}

function handleRoomMembersUpdated(data) {
    loadRooms();
}

function handleMessageDeleted(data) {
    const msgEl = document.querySelector(`[data-message-id="${data.message_id}"] .message-bubble`);
    if (msgEl) {
        msgEl.textContent = '[삭제된 메시지]';
        msgEl.style.opacity = '0.5';
    }
    loadRooms(); // update last message preview
}

function handleMessageEdited(data) {
    const msgEl = document.querySelector(`[data-message-id="${data.message_id}"]`);
    if (msgEl) {
        if (msgEl._messageData) {
            msgEl._messageData.content = data.content;
            msgEl._messageData.encrypted = data.encrypted;
        }

        const bubble = msgEl.querySelector('.message-bubble');
        if (bubble) {
            const decrypted = state.currentRoomKey && data.encrypted
                ? E2E.decrypt(data.content, state.currentRoomKey)
                : data.content;
            // parseMentions logic needed
            bubble.innerHTML = escapeHtml(decrypted) + ' <span class="edited-indicator">(수정됨)</span>'; // Simplified
        }
    }
}

function handleUserProfileUpdated(data) {
    loadRooms();
    loadOnlineUsers();

    if (state.currentRoom) {
        const userMessages = document.querySelectorAll(`[data-sender-id="${data.user_id}"]`);
        userMessages.forEach(msgEl => {
            const senderEl = msgEl.querySelector('.message-sender');
            if (senderEl && data.nickname) senderEl.textContent = data.nickname;

            const avatarEl = msgEl.querySelector('.message-avatar');
            if (avatarEl) {
                if (data.profile_image) {
                    avatarEl.innerHTML = `<img src="/uploads/${data.profile_image}" alt="프로필">`;
                    avatarEl.classList.add('has-image');
                } else if (data.nickname) {
                    avatarEl.classList.remove('has-image');
                    avatarEl.textContent = data.nickname[0].toUpperCase();
                }
            }
        });
    }
}
