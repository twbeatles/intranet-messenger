/**
 * 사내 메신저 v3.0 메인 애플리케이션
 */

// 클라이언트 측 E2E 암호화
const E2E = {
    encrypt: (plaintext, key) => {
        try {
            return CryptoJS.AES.encrypt(plaintext, key).toString();
        } catch (e) { return plaintext; }
    },
    decrypt: (ciphertext, key) => {
        try {
            const bytes = CryptoJS.AES.decrypt(ciphertext, key);
            return bytes.toString(CryptoJS.enc.Utf8) || '[복호화 실패]';
        } catch (e) { return '[암호화된 메시지]'; }
    }
};

// 앱 상태
let socket = null;
let currentUser = null;
let currentRoom = null;
let rooms = [];
let currentRoomKey = null;
let typingTimeout = null;
let reconnectAttempts = 0;

// 이모지 목록
const emojis = ['😀', '😂', '😊', '😍', '🥰', '😎', '🤔', '😅', '😭', '😤', '👍', '👎', '❤️', '🔥', '✨', '🎉', '👏', '🙏', '💪', '🤝', '👋', '✅', '❌', '⭐', '💯', '🚀', '💡', '📌', '📝', '💬'];

// DOM 요소 캐싱
const $ = id => document.getElementById(id);
const elements = {};

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    setupEventListeners();
    initEmojiPicker();
});

function cacheElements() {
    const ids = [
        'authContainer', 'appContainer', 'loginForm', 'registerForm', 'authError',
        'loginUsername', 'loginPassword', 'regUsername', 'regPassword', 'regNickname',
        'roomList', 'messagesContainer', 'messageInput', 'sendBtn', 'emojiPicker',
        'emptyState', 'chatContent', 'chatName', 'chatAvatar', 'chatStatus',
        'typingIndicator', 'userName', 'userAvatar', 'newChatModal', 'inviteModal',
        'userList', 'inviteUserList', 'roomName', 'connectionStatus', 'onlineUsersList',
        'roomSettingsMenu', 'pinRoomText', 'muteRoomText', 'searchInput', 'sidebar'
    ];
    ids.forEach(id => elements[id] = $(id));
}

function setupEventListeners() {
    // 인증 관련
    $('loginBtn').onclick = doLogin;
    $('registerBtn').onclick = doRegister;
    $('showRegister').onclick = showRegisterForm;
    $('showLogin').onclick = showLoginForm;

    // Enter 키로 로그인/회원가입
    $('loginPassword').onkeydown = e => { if (e.key === 'Enter') doLogin(); };
    $('regNickname').onkeydown = e => { if (e.key === 'Enter') doRegister(); };

    // 메시지 전송
    $('sendBtn').onclick = sendMessage;
    $('messageInput').onkeydown = e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };
    $('messageInput').oninput = handleTyping;

    // 이모지 & 파일
    $('emojiBtn').onclick = () => $('emojiPicker').classList.toggle('active');
    $('attachBtn').onclick = () => $('fileInput').click();
    $('fileInput').onchange = handleFileUpload;

    // 새 대화
    $('newChatBtn').onclick = openNewChatModal;
    $('closeNewChatModal').onclick = () => $('newChatModal').classList.remove('active');
    $('createRoomBtn').onclick = createRoom;

    // 초대
    $('inviteBtn').onclick = openInviteModal;
    $('closeInviteModal').onclick = () => $('inviteModal').classList.remove('active');
    $('confirmInviteBtn').onclick = confirmInvite;

    // 대화방 설정
    $('roomSettingsBtn').onclick = e => {
        e.stopPropagation();
        $('roomSettingsMenu').classList.toggle('active');
    };
    $('editRoomNameBtn').onclick = editRoomName;
    $('pinRoomBtn').onclick = togglePinRoom;
    $('muteRoomBtn').onclick = toggleMuteRoom;
    $('viewMembersBtn').onclick = viewMembers;

    // 나가기 & 로그아웃
    $('leaveRoomBtn').onclick = leaveRoom;
    $('logoutBtn').onclick = logout;

    // 모바일 메뉴
    $('mobileMenuBtn').onclick = () => $('sidebar').classList.toggle('active');

    // 검색
    $('searchInput').oninput = handleSearch;

    // 글로벌 클릭 이벤트
    document.addEventListener('click', e => {
        if (!e.target.closest('#emojiBtn') && !e.target.closest('#emojiPicker')) {
            $('emojiPicker').classList.remove('active');
        }
        if (!e.target.closest('#roomSettingsMenu') && !e.target.closest('#roomSettingsBtn')) {
            $('roomSettingsMenu').classList.remove('active');
        }
        // 컨텍스트 메뉴 닫기
        document.querySelectorAll('.message-context-menu').forEach(m => m.remove());
    });

    // 메시지 우클릭
    $('messagesContainer').addEventListener('contextmenu', handleMessageContextMenu);
}

// ============================================================================
// 인증
// ============================================================================
async function api(url, options = {}) {
    try {
        const res = await fetch(url, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers }
        });

        // 비 JSON 응답 처리
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return {};
        }

        return res.json();
    } catch (err) {
        console.error('API 오류:', url, err);
        throw err;
    }
}

function showAuthError(msg) {
    elements.authError.textContent = msg;
    elements.authError.classList.remove('hidden', 'success-message');
    elements.authError.classList.add('error-message');
}

function showAuthSuccess(msg) {
    elements.authError.textContent = msg;
    elements.authError.classList.remove('hidden', 'error-message');
    elements.authError.classList.add('success-message');
}

function hideAuthError() {
    elements.authError.classList.add('hidden');
}

function showRegisterForm() {
    $('loginForm').classList.add('hidden');
    $('registerForm').classList.remove('hidden');
    $('switchToRegisterWrap').style.display = 'none';
    $('switchToLoginWrap').style.display = 'inline';
}

function showLoginForm() {
    $('registerForm').classList.add('hidden');
    $('loginForm').classList.remove('hidden');
    $('switchToLoginWrap').style.display = 'none';
    $('switchToRegisterWrap').style.display = 'inline';
    hideAuthError();
}

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
            currentUser = result.user;
            initApp();
        } else {
            showAuthError(result.error || '로그인 실패');
        }
    } catch (err) {
        console.error('로그인 오류:', err);
        showAuthError('서버 연결 오류');
    }
}

async function doRegister() {
    const username = $('regUsername').value.trim();
    const password = $('regPassword').value;
    const nickname = $('regNickname').value.trim();

    if (!username || !password) {
        showAuthError('아이디와 비밀번호를 입력하세요.');
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
        showAuthError('서버 연결 오류');
    }
}

async function logout() {
    await api('/api/logout', { method: 'POST' });
    location.reload();
}

// ============================================================================
// 앱 초기화
// ============================================================================
function initApp() {
    elements.authContainer.style.display = 'none';
    elements.appContainer.classList.add('active');
    elements.userName.textContent = currentUser.nickname;
    elements.userAvatar.textContent = currentUser.nickname[0].toUpperCase();

    // 알림 권한 요청
    if (window.MessengerNotification) {
        MessengerNotification.requestPermission();
    }

    // 로컬 스토리지 초기화
    if (window.MessengerStorage) {
        MessengerStorage.init();
    }

    // Socket.IO 연결
    initSocket();

    // 데이터 로드
    loadRooms();
    loadOnlineUsers();
}

function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Socket.IO 연결됨');
        reconnectAttempts = 0;
        updateConnectionStatus('connected');

        // 현재 대화방에 다시 참여
        if (currentRoom) {
            socket.emit('join_room', { room_id: currentRoom.id });
        }
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO 연결 끊김');
        updateConnectionStatus('disconnected');
    });

    socket.on('connect_error', () => {
        reconnectAttempts++;
        updateConnectionStatus('reconnecting');
    });

    socket.on('new_message', handleNewMessage);
    socket.on('read_updated', handleReadUpdated);
    socket.on('user_typing', handleUserTyping);
    socket.on('user_status', handleUserStatus);
    socket.on('room_updated', () => loadRooms());
    socket.on('room_name_updated', handleRoomNameUpdated);
    socket.on('room_members_updated', handleRoomMembersUpdated);
    socket.on('message_deleted', handleMessageDeleted);
    socket.on('message_edited', handleMessageEdited);
    socket.on('error', data => console.error('Socket 오류:', data.message));
}

function updateConnectionStatus(status) {
    const statusEl = $('connectionStatus');
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
            statusEl.querySelector('.status-text').textContent = `재연결 중... (${reconnectAttempts})`;
            break;
    }
}

// ============================================================================
// 대화방
// ============================================================================
async function loadRooms() {
    try {
        const result = await api('/api/rooms');
        rooms = result;
        renderRoomList();
    } catch (err) {
        console.error('대화방 로드 실패:', err);
    }
}

function renderRoomList() {
    elements.roomList.innerHTML = rooms.map(room => {
        const isActive = currentRoom && currentRoom.id === room.id;
        const avatar = room.type === 'direct' && room.partner
            ? room.partner.nickname[0].toUpperCase()
            : (room.name || '그')[0].toUpperCase();
        const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
        const time = room.last_message_time ? formatTime(room.last_message_time) : '';
        const preview = room.last_message ? '[암호화됨]' : '새 대화';
        const pinnedClass = room.pinned ? 'pinned' : '';
        const pinnedIcon = room.pinned ? '<span class="pin-icon">📌</span>' : '';

        return `
            <div class="room-item ${isActive ? 'active' : ''} ${pinnedClass}" data-room-id="${room.id}">
                <div class="room-avatar">${avatar}</div>
                <div class="room-info">
                    <div class="room-name">${escapeHtml(name)} 🔒 ${pinnedIcon}</div>
                    <div class="room-preview">${preview}</div>
                </div>
                <div class="room-meta">
                    <div class="room-time">${time}</div>
                    ${room.unread_count > 0 ? `<span class="unread-badge">${room.unread_count}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');

    // 클릭 이벤트
    document.querySelectorAll('.room-item').forEach(el => {
        el.onclick = () => {
            const room = rooms.find(r => r.id === parseInt(el.dataset.roomId));
            if (room) openRoom(room);
        };
    });
}

async function openRoom(room) {
    if (currentRoom) {
        socket.emit('leave_room', { room_id: currentRoom.id });
    }

    currentRoom = room;
    socket.emit('join_room', { room_id: room.id });

    elements.emptyState.classList.add('hidden');
    elements.chatContent.classList.remove('hidden');

    const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
    elements.chatName.innerHTML = `${escapeHtml(name)} 🔒`;
    elements.chatAvatar.textContent = name[0].toUpperCase();
    elements.chatStatus.textContent = room.type === 'direct' && room.partner
        ? (room.partner.status === 'online' ? '온라인' : '오프라인')
        : `${room.member_count}명 참여 중`;

    // 핀/음소거 상태 업데이트
    $('pinRoomText').textContent = room.pinned ? '고정 해제' : '상단 고정';
    $('muteRoomText').textContent = room.muted ? '알림 켜기' : '알림 끄기';

    try {
        const result = await api(`/api/rooms/${room.id}/messages`);
        currentRoomKey = result.encryption_key;
        renderMessages(result.messages);

        if (result.messages.length > 0) {
            socket.emit('message_read', {
                room_id: room.id,
                message_id: result.messages[result.messages.length - 1].id
            });
        }

        // 로컬 캐시 저장
        if (window.MessengerStorage) {
            MessengerStorage.cacheMessages(room.id, result.messages);
        }
    } catch (err) {
        console.error('메시지 로드 실패:', err);
        // 오프라인 캐시에서 로드 시도
        if (window.MessengerStorage) {
            const cached = await MessengerStorage.getCachedMessages(room.id);
            if (cached.length > 0) {
                renderMessages(cached);
            }
        }
    }

    renderRoomList();

    // 모바일에서 사이드바 닫기
    elements.sidebar.classList.remove('active');
}

// ============================================================================
// 메시지
// ============================================================================
function renderMessages(messages) {
    elements.messagesContainer.innerHTML = '';
    let lastDate = null;

    messages.forEach(msg => {
        const msgDate = msg.created_at.split('T')[0];
        if (msgDate !== lastDate) {
            lastDate = msgDate;
            const divider = document.createElement('div');
            divider.className = 'date-divider';
            divider.innerHTML = `<span>${formatDate(msgDate)}</span>`;
            elements.messagesContainer.appendChild(divider);
        }
        appendMessage(msg);
    });

    scrollToBottom();
}

function appendMessage(msg) {
    const isSent = msg.sender_id === currentUser.id;
    const div = document.createElement('div');
    div.className = `message ${isSent ? 'sent' : ''}`;
    div.dataset.messageId = msg.id;

    let content = '';
    if (msg.message_type === 'image') {
        content = `<img src="/uploads/${msg.file_path}" class="message-image" onclick="window.open(this.src)">`;
    } else if (msg.message_type === 'file') {
        content = `
            <div class="message-file">
                <span>📄</span>
                <div class="message-file-info">
                    <div class="message-file-name">${escapeHtml(msg.file_name)}</div>
                </div>
                <a href="/uploads/${msg.file_path}" download="${msg.file_name}" class="icon-btn">⬇</a>
            </div>
        `;
    } else {
        const decrypted = currentRoomKey && msg.encrypted ? E2E.decrypt(msg.content, currentRoomKey) : msg.content;
        content = `<div class="message-bubble">${escapeHtml(decrypted)}</div>`;
    }

    const unreadHtml = msg.unread_count > 0 ? `<span class="unread-count">${msg.unread_count}</span>` : '';

    div.innerHTML = `
        <div class="message-avatar">${msg.sender_name[0].toUpperCase()}</div>
        <div class="message-content">
            <div class="message-sender">${escapeHtml(msg.sender_name)}</div>
            ${content}
            <div class="message-meta">
                ${unreadHtml}
                <span>${formatTime(msg.created_at)}</span>
            </div>
        </div>
    `;

    elements.messagesContainer.appendChild(div);
}

function sendMessage() {
    const content = elements.messageInput.value.trim();
    if (!content || !currentRoom || !currentRoomKey) return;

    const encrypted = E2E.encrypt(content, currentRoomKey);
    socket.emit('send_message', {
        room_id: currentRoom.id,
        content: encrypted,
        type: 'text',
        encrypted: true
    });

    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
}

function handleTyping() {
    elements.messageInput.style.height = 'auto';
    elements.messageInput.style.height = Math.min(elements.messageInput.scrollHeight, 120) + 'px';

    if (currentRoom) {
        socket.emit('typing', { room_id: currentRoom.id, is_typing: true });

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('typing', { room_id: currentRoom.id, is_typing: false });
        }, 2000);
    }
}

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file || !currentRoom) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const result = await res.json();

        if (result.success) {
            const isImage = ['png', 'jpg', 'jpeg', 'gif'].includes(file.name.split('.').pop().toLowerCase());
            socket.emit('send_message', {
                room_id: currentRoom.id,
                content: file.name,
                type: isImage ? 'image' : 'file',
                file_path: result.file_path,
                file_name: result.file_name,
                encrypted: false
            });
        }
    } catch (err) {
        console.error('파일 업로드 실패:', err);
    }

    e.target.value = '';
}

// ============================================================================
// Socket.IO 이벤트 핸들러
// ============================================================================
function handleNewMessage(msg) {
    if (currentRoom && msg.room_id === currentRoom.id) {
        appendMessage(msg);
        scrollToBottom();
        socket.emit('message_read', { room_id: currentRoom.id, message_id: msg.id });
    } else {
        // 알림 표시
        if (window.MessengerNotification && msg.sender_id !== currentUser.id) {
            const room = rooms.find(r => r.id === msg.room_id);
            const roomKey = room ? room.encryption_key : null;
            const decrypted = roomKey && msg.encrypted ? E2E.decrypt(msg.content, roomKey) : msg.content;
            MessengerNotification.show(msg.sender_name, decrypted, msg.room_id);
        }
    }
    loadRooms();
}

function handleReadUpdated(data) {
    if (currentRoom && data.room_id === currentRoom.id) {
        updateUnreadCounts();
    }
}

function handleUserTyping(data) {
    if (currentRoom && data.room_id === currentRoom.id) {
        if (data.is_typing) {
            elements.typingIndicator.textContent = `${data.nickname}님이 입력 중...`;
            elements.typingIndicator.classList.remove('hidden');
        } else {
            elements.typingIndicator.classList.add('hidden');
        }
    }
}

function handleUserStatus(data) {
    loadRooms();
    loadOnlineUsers();
}

function handleRoomNameUpdated(data) {
    loadRooms();
    if (currentRoom && currentRoom.id === data.room_id) {
        currentRoom.name = data.name;
        elements.chatName.innerHTML = `${escapeHtml(data.name)} 🔒`;
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
}

function handleMessageEdited(data) {
    const msgEl = document.querySelector(`[data-message-id="${data.message_id}"] .message-bubble`);
    if (msgEl) {
        msgEl.textContent = data.content;
    }
}

async function updateUnreadCounts() {
    if (!currentRoom) return;

    try {
        const result = await api(`/api/rooms/${currentRoom.id}/messages`);
        result.messages.forEach(msg => {
            const el = document.querySelector(`[data-message-id="${msg.id}"] .unread-count`);
            if (el) {
                if (msg.unread_count > 0) {
                    el.textContent = msg.unread_count;
                } else {
                    el.remove();
                }
            }
        });
    } catch (err) {
        console.error('읽음 수 업데이트 실패:', err);
    }
}

// ============================================================================
// 온라인 사용자
// ============================================================================
async function loadOnlineUsers() {
    try {
        const users = await api('/api/users/online');

        if (users.length === 0) {
            elements.onlineUsersList.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">온라인 사용자가 없습니다</span>';
            return;
        }

        elements.onlineUsersList.innerHTML = users.map(u => `
            <div class="online-user" data-user-id="${u.id}" title="${escapeHtml(u.nickname)}">
                ${u.nickname[0].toUpperCase()}
                <span class="online-user-tooltip">${escapeHtml(u.nickname)}</span>
            </div>
        `).join('');

        elements.onlineUsersList.querySelectorAll('.online-user').forEach(el => {
            el.onclick = async () => {
                const userId = parseInt(el.dataset.userId);
                const result = await api('/api/rooms', {
                    method: 'POST',
                    body: JSON.stringify({ members: [userId] })
                });
                if (result.success) {
                    await loadRooms();
                    const room = rooms.find(r => r.id === result.room_id);
                    if (room) openRoom(room);
                }
            };
        });
    } catch (err) {
        console.error('온라인 사용자 로드 실패:', err);
    }
}

// 30초마다 새로고침
setInterval(loadOnlineUsers, 30000);

// ============================================================================
// 모달
// ============================================================================
async function openNewChatModal() {
    try {
        const result = await api('/api/users');
        elements.userList.innerHTML = result.map(u => `
            <div class="user-item" data-user-id="${u.id}">
                <div class="user-item-avatar">${u.nickname[0].toUpperCase()}</div>
                <div class="user-item-info">
                    <div class="user-item-name">${escapeHtml(u.nickname)}</div>
                    <div class="user-item-status ${u.status}">${u.status === 'online' ? '온라인' : '오프라인'}</div>
                </div>
                <input type="checkbox" class="user-checkbox">
            </div>
        `).join('');

        elements.userList.querySelectorAll('.user-item').forEach(el => {
            el.onclick = () => {
                const cb = el.querySelector('.user-checkbox');
                cb.checked = !cb.checked;
                el.classList.toggle('selected', cb.checked);
            };
        });

        $('newChatModal').classList.add('active');
    } catch (err) {
        console.error('사용자 목록 로드 실패:', err);
    }
}

async function createRoom() {
    const selected = [...document.querySelectorAll('#userList .user-item.selected')]
        .map(el => parseInt(el.dataset.userId));

    if (selected.length === 0) return;

    try {
        const result = await api('/api/rooms', {
            method: 'POST',
            body: JSON.stringify({ members: selected, name: $('roomName').value.trim() })
        });

        if (result.success) {
            $('newChatModal').classList.remove('active');
            await loadRooms();
            const room = rooms.find(r => r.id === result.room_id);
            if (room) openRoom(room);
        }
    } catch (err) {
        console.error('대화방 생성 실패:', err);
    }
}

async function openInviteModal() {
    if (!currentRoom) return;

    try {
        const result = await api('/api/users');
        const memberIds = (currentRoom.members || []).map(m => m.id);

        elements.inviteUserList.innerHTML = result
            .filter(u => !memberIds.includes(u.id))
            .map(u => `
                <div class="user-item" data-user-id="${u.id}">
                    <div class="user-item-avatar">${u.nickname[0].toUpperCase()}</div>
                    <div class="user-item-info">
                        <div class="user-item-name">${escapeHtml(u.nickname)}</div>
                    </div>
                    <input type="checkbox" class="user-checkbox">
                </div>
            `).join('');

        elements.inviteUserList.querySelectorAll('.user-item').forEach(el => {
            el.onclick = () => {
                const cb = el.querySelector('.user-checkbox');
                cb.checked = !cb.checked;
                el.classList.toggle('selected', cb.checked);
            };
        });

        $('inviteModal').classList.add('active');
    } catch (err) {
        console.error('사용자 목록 로드 실패:', err);
    }
}

async function confirmInvite() {
    const selected = [...document.querySelectorAll('#inviteUserList .user-item.selected')]
        .map(el => parseInt(el.dataset.userId));

    try {
        for (const userId of selected) {
            await api(`/api/rooms/${currentRoom.id}/members`, {
                method: 'POST',
                body: JSON.stringify({ user_id: userId })
            });
        }

        $('inviteModal').classList.remove('active');
        loadRooms();
    } catch (err) {
        console.error('초대 실패:', err);
    }
}

// ============================================================================
// 대화방 설정
// ============================================================================
async function editRoomName() {
    if (!currentRoom) return;

    const newName = prompt('새 대화방 이름:', currentRoom.name || '');
    if (newName && newName.trim()) {
        try {
            const result = await api(`/api/rooms/${currentRoom.id}/name`, {
                method: 'PUT',
                body: JSON.stringify({ name: newName.trim() })
            });

            if (result.success) {
                currentRoom.name = newName.trim();
                elements.chatName.innerHTML = `${escapeHtml(newName.trim())} 🔒`;
                loadRooms();
            }
        } catch (err) {
            console.error('이름 변경 실패:', err);
        }
    }

    $('roomSettingsMenu').classList.remove('active');
}

async function togglePinRoom() {
    if (!currentRoom) return;

    const isPinned = currentRoom.pinned;

    try {
        const result = await api(`/api/rooms/${currentRoom.id}/pin`, {
            method: 'POST',
            body: JSON.stringify({ pinned: !isPinned })
        });

        if (result.success) {
            currentRoom.pinned = !isPinned;
            $('pinRoomText').textContent = currentRoom.pinned ? '고정 해제' : '상단 고정';
            loadRooms();
        }
    } catch (err) {
        console.error('고정 설정 실패:', err);
    }

    $('roomSettingsMenu').classList.remove('active');
}

async function toggleMuteRoom() {
    if (!currentRoom) return;

    const isMuted = currentRoom.muted;

    try {
        const result = await api(`/api/rooms/${currentRoom.id}/mute`, {
            method: 'POST',
            body: JSON.stringify({ muted: !isMuted })
        });

        if (result.success) {
            currentRoom.muted = !isMuted;
            $('muteRoomText').textContent = currentRoom.muted ? '알림 켜기' : '알림 끄기';
        }
    } catch (err) {
        console.error('알림 설정 실패:', err);
    }

    $('roomSettingsMenu').classList.remove('active');
}

async function viewMembers() {
    if (!currentRoom) return;

    try {
        const result = await api(`/api/rooms/${currentRoom.id}/info`);
        if (result.members) {
            alert('참여자:\n' + result.members.map(m =>
                `• ${m.nickname} (${m.status === 'online' ? '온라인' : '오프라인'})`
            ).join('\n'));
        }
    } catch (err) {
        console.error('멤버 조회 실패:', err);
    }

    $('roomSettingsMenu').classList.remove('active');
}

async function leaveRoom() {
    if (!currentRoom || !confirm('대화방을 나가시겠습니까?')) return;

    try {
        await api(`/api/rooms/${currentRoom.id}/leave`, { method: 'POST' });
        currentRoom = null;
        elements.chatContent.classList.add('hidden');
        elements.emptyState.classList.remove('hidden');
        loadRooms();
    } catch (err) {
        console.error('대화방 나가기 실패:', err);
    }
}

// ============================================================================
// 컨텍스트 메뉴
// ============================================================================
function handleMessageContextMenu(e) {
    const msgEl = e.target.closest('.message');
    if (!msgEl) return;

    e.preventDefault();

    const msgId = msgEl.dataset.messageId;
    const isSent = msgEl.classList.contains('sent');

    if (isSent) {
        const menu = document.createElement('div');
        menu.className = 'message-context-menu';
        menu.innerHTML = `
            <div class="context-menu-item" data-action="copy">📋 복사</div>
            <div class="context-menu-item danger" data-action="delete">🗑 삭제</div>
        `;
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        document.body.appendChild(menu);

        menu.querySelector('[data-action="copy"]').onclick = async () => {
            const bubble = msgEl.querySelector('.message-bubble');
            if (bubble) {
                await navigator.clipboard.writeText(bubble.textContent);
            }
            menu.remove();
        };

        menu.querySelector('[data-action="delete"]').onclick = async () => {
            if (confirm('메시지를 삭제하시겠습니까?')) {
                try {
                    const result = await api(`/api/messages/${msgId}`, { method: 'DELETE' });
                    if (result.success) {
                        msgEl.querySelector('.message-bubble').textContent = '[삭제된 메시지]';
                        msgEl.querySelector('.message-bubble').style.opacity = '0.5';
                    }
                } catch (err) {
                    console.error('삭제 실패:', err);
                }
            }
            menu.remove();
        };
    }
}

// ============================================================================
// 검색
// ============================================================================
function handleSearch(e) {
    const q = e.target.value.trim().toLowerCase();

    if (q.length < 2) {
        renderRoomList();
        return;
    }

    const filtered = rooms.filter(r =>
        r.name?.toLowerCase().includes(q) ||
        r.partner?.nickname?.toLowerCase().includes(q)
    );

    // 임시로 필터링된 목록 표시
    elements.roomList.innerHTML = filtered.map(room => {
        const isActive = currentRoom && currentRoom.id === room.id;
        const avatar = room.type === 'direct' && room.partner
            ? room.partner.nickname[0].toUpperCase()
            : (room.name || '그')[0].toUpperCase();
        const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');

        return `
            <div class="room-item ${isActive ? 'active' : ''}" data-room-id="${room.id}">
                <div class="room-avatar">${avatar}</div>
                <div class="room-info">
                    <div class="room-name">${escapeHtml(name)} 🔒</div>
                </div>
            </div>
        `;
    }).join('');

    document.querySelectorAll('.room-item').forEach(el => {
        el.onclick = () => {
            const room = rooms.find(r => r.id === parseInt(el.dataset.roomId));
            if (room) openRoom(room);
        };
    });
}

// ============================================================================
// 이모지
// ============================================================================
function initEmojiPicker() {
    $('emojiPicker').innerHTML = emojis.map(e =>
        `<button class="emoji-btn">${e}</button>`
    ).join('');

    $('emojiPicker').querySelectorAll('.emoji-btn').forEach(btn => {
        btn.onclick = () => {
            elements.messageInput.value += btn.textContent;
            elements.messageInput.focus();
        };
    });
}

// ============================================================================
// 유틸리티
// ============================================================================
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function formatTime(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const today = new Date();

    if (d.toDateString() === today.toDateString()) return '오늘';

    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return '어제';

    return d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
}

function scrollToBottom() {
    if (elements.messagesContainer) {
        elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
    }
}

// 클립보드 복사 (폴백 포함)
async function copyToClipboard(text) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            // 폴백: 오래된 브라우저 지원
            const textarea = document.createElement('textarea');
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
