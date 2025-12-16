/**
 * 사내 메신저 v3.3 메인 애플리케이션
 */

// ============================================================================
// 성능 최적화 유틸리티
// ============================================================================
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
// 토스트 알림 시스템
// ============================================================================
var toastContainer = null;

function initToast() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
}

function showToast(message, type, duration) {
    type = type || 'info';
    duration = duration || 3000;

    initToast();

    var icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span class="toast-icon">' + icons[type] + '</span>' +
        '<span class="toast-message">' + message + '</span>' +
        '<button class="toast-close">✕</button>';

    toast.querySelector('.toast-close').onclick = function () {
        closeToast(toast);
    };

    toastContainer.appendChild(toast);

    setTimeout(function () {
        closeToast(toast);
    }, duration);

    return toast;
}

function closeToast(toast) {
    if (toast && toast.parentNode) {
        toast.classList.add('hiding');
        setTimeout(function () {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
}

// ============================================================================
// 답장 기능
// ============================================================================
var replyingTo = null;

function setReplyTo(message) {
    replyingTo = message;
    updateReplyPreview();
}

function clearReply() {
    replyingTo = null;
    updateReplyPreview();
}

function updateReplyPreview() {
    var container = document.getElementById('replyPreview');
    if (!container) return;

    if (replyingTo) {
        container.innerHTML = '<div class="reply-preview">' +
            '<div class="reply-preview-content">' +
            '<div class="reply-preview-sender">' + escapeHtml(replyingTo.sender_name) + '</div>' +
            '<div class="reply-preview-text">' + escapeHtml(replyingTo.content || '[파일]') + '</div>' +
            '</div>' +
            '<button class="reply-preview-close" onclick="clearReply()">✕</button>' +
            '</div>';
        container.classList.remove('hidden');
    } else {
        container.innerHTML = '';
        container.classList.add('hidden');
    }
}

// ============================================================================
// @멘션 기능
// ============================================================================
var mentionUsers = [];
var mentionSelectedIndex = 0;

function setupMention() {
    var input = document.getElementById('messageInput');
    var autocomplete = document.getElementById('mentionAutocomplete');
    if (!input || !autocomplete) return;

    input.addEventListener('input', function (e) {
        var cursorPos = input.selectionStart;
        var text = input.value.substring(0, cursorPos);
        // 한글, 영문, 숫자 모두 지원하는 멘션 패턴
        var mentionMatch = text.match(/@([가-힣a-zA-Z0-9]*)$/);

        if (mentionMatch) {
            showMentionAutocomplete(mentionMatch[1].toLowerCase());
        } else {
            hideMentionAutocomplete();
        }
    });

    input.addEventListener('keydown', function (e) {
        if (!autocomplete.classList.contains('hidden')) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                mentionSelectedIndex = Math.min(mentionSelectedIndex + 1, mentionUsers.length - 1);
                updateMentionSelection();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                mentionSelectedIndex = Math.max(mentionSelectedIndex - 1, 0);
                updateMentionSelection();
            } else if (e.key === 'Enter' && mentionUsers.length > 0) {
                e.preventDefault();
                selectMention(mentionUsers[mentionSelectedIndex]);
            } else if (e.key === 'Escape') {
                hideMentionAutocomplete();
            }
        }
    });
}

function showMentionAutocomplete(query) {
    var autocomplete = document.getElementById('mentionAutocomplete');
    if (!autocomplete || !currentRoom) return;

    fetch('/api/rooms/' + currentRoom.id + '/info')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.members) return;

            mentionUsers = data.members.filter(function (m) {
                // 대소문자 무시, 한글 포함 검색
                return m.id !== currentUser.id && m.nickname.toLowerCase().includes(query.toLowerCase());
            }).slice(0, 5);

            if (mentionUsers.length === 0) {
                hideMentionAutocomplete();
                return;
            }

            mentionSelectedIndex = 0;
            autocomplete.innerHTML = mentionUsers.map(function (user, i) {
                return '<div class="mention-item' + (i === 0 ? ' selected' : '') + '" data-user-id="' + user.id + '">' +
                    '<div class="mention-item-avatar">' + user.nickname[0].toUpperCase() + '</div>' +
                    '<div class="mention-item-name">' + escapeHtml(user.nickname) + '</div>' +
                    '</div>';
            }).join('');

            autocomplete.querySelectorAll('.mention-item').forEach(function (item, idx) {
                item.onclick = function () { selectMention(mentionUsers[idx]); };
            });

            autocomplete.classList.remove('hidden');
        });
}

function hideMentionAutocomplete() {
    var ac = document.getElementById('mentionAutocomplete');
    if (ac) ac.classList.add('hidden');
}

function updateMentionSelection() {
    document.querySelectorAll('.mention-item').forEach(function (item, i) {
        item.classList.toggle('selected', i === mentionSelectedIndex);
    });
}

function selectMention(user) {
    var input = document.getElementById('messageInput');
    var cursorPos = input.selectionStart;
    var text = input.value;
    var before = text.substring(0, cursorPos).replace(/@[가-힣a-zA-Z0-9]*$/, '');
    var after = text.substring(cursorPos);

    input.value = before + '@' + user.nickname + ' ' + after;
    input.focus();
    var newPos = before.length + user.nickname.length + 2;
    input.setSelectionRange(newPos, newPos);
    hideMentionAutocomplete();
}

function parseMentions(text) {
    // 한글, 영문, 숫자 닉네임 지원
    return text.replace(/@([가-힣a-zA-Z0-9]+)/g, '<span class="mention">@$1</span>');
}

// ============================================================================
// 이미지 라이트박스
// ============================================================================
var lightboxImages = [];
var currentImageIndex = 0;

function openLightbox(imageSrc) {
    var lightbox = document.getElementById('lightbox');
    var lightboxImg = document.getElementById('lightboxImage');
    if (!lightbox || !lightboxImg) return;

    lightboxImages = Array.from(document.querySelectorAll('.message-image')).map(function (img) { return img.src; });
    currentImageIndex = lightboxImages.indexOf(imageSrc);
    if (currentImageIndex === -1) currentImageIndex = 0;

    lightboxImg.src = imageSrc;
    lightbox.classList.add('active');
    document.addEventListener('keydown', handleLightboxKeydown);

    // 배경 클릭 시 닫기
    lightbox.onclick = function (e) {
        if (e.target === lightbox) closeLightbox();
    };
}

function closeLightbox() {
    var lightbox = document.getElementById('lightbox');
    if (lightbox) lightbox.classList.remove('active');
    document.removeEventListener('keydown', handleLightboxKeydown);
}

function prevImage() {
    if (lightboxImages.length === 0) return;
    currentImageIndex = (currentImageIndex - 1 + lightboxImages.length) % lightboxImages.length;
    document.getElementById('lightboxImage').src = lightboxImages[currentImageIndex];
}

function nextImage() {
    if (lightboxImages.length === 0) return;
    currentImageIndex = (currentImageIndex + 1) % lightboxImages.length;
    document.getElementById('lightboxImage').src = lightboxImages[currentImageIndex];
}

function handleLightboxKeydown(e) {
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowLeft') prevImage();
    else if (e.key === 'ArrowRight') nextImage();
}

// ============================================================================
// 이모지 반응
// ============================================================================
var reactionEmojis = ['👍', '❤️', '😂', '😮', '😢', '😡'];

function addReaction(messageId, emoji) {
    socket.emit('add_reaction', { message_id: messageId, emoji: emoji });
}

function toggleReaction(messageId, emoji) {
    socket.emit('toggle_reaction', { message_id: messageId, emoji: emoji });
}

// ============================================================================
// 클라이언트 측 E2E 암호화 (개선된 버전)
// ============================================================================
var E2E = {
    encrypt: function (plaintext, key) {
        try {
            if (!plaintext || !key) return plaintext || '';
            return CryptoJS.AES.encrypt(String(plaintext), String(key)).toString();
        } catch (e) {
            console.error('암호화 오류:', e);
            return plaintext || '';
        }
    },
    decrypt: function (ciphertext, key) {
        try {
            // 빈 값이나 이미 복호화된 값 처리
            if (!ciphertext || !key) return ciphertext || '';
            if (typeof ciphertext !== 'string') return String(ciphertext);

            // 이미 복호화된 일반 텍스트인 경우 (Base64가 아닌 경우)
            if (!ciphertext.includes('U2FsdGVkX')) {
                return ciphertext;
            }

            var bytes = CryptoJS.AES.decrypt(ciphertext, String(key));
            var decrypted = bytes.toString(CryptoJS.enc.Utf8);

            // 복호화 결과가 비어있으면 원본 반환
            if (!decrypted || decrypted.length === 0) {
                console.warn('복호화 결과 비어있음, 원본 반환');
                return ciphertext;
            }

            return decrypted;
        } catch (e) {
            console.error('복호화 오류:', e.message || e);
            // 실패 시 원본 메시지 반환 (사용자 경험 개선)
            return ciphertext || '[암호화된 메시지]';
        }
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
document.addEventListener('DOMContentLoaded', function () {
    cacheElements();
    setupEventListeners();
    initEmojiPicker();
    initTheme();  // 테마 초기화
});

function cacheElements() {
    const ids = [
        'authContainer', 'appContainer', 'loginForm', 'registerForm', 'authError',
        'loginUsername', 'loginPassword', 'regUsername', 'regPassword', 'regNickname',
        'roomList', 'messagesContainer', 'messageInput', 'sendBtn', 'emojiPicker',
        'emptyState', 'chatContent', 'chatName', 'chatAvatar', 'chatStatus',
        'typingIndicator', 'userName', 'userAvatar', 'newChatModal', 'inviteModal',
        'userList', 'inviteUserList', 'roomName', 'connectionStatus', 'onlineUsersList',
        'roomSettingsMenu', 'pinRoomText', 'muteRoomText', 'searchInput', 'sidebar',
        'membersModal', 'membersList', 'membersInfo'
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
        // 멘션 자동완성이 열려있으면 메시지 전송하지 않음
        var mentionAc = $('mentionAutocomplete');
        if (mentionAc && !mentionAc.classList.contains('hidden')) {
            return; // 멘션 핸들러에서 처리
        }
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

    // 멤버 모달 이벤트
    $('closeMembersModal').onclick = () => $('membersModal').classList.remove('active');
    $('closeMembersBtn').onclick = () => $('membersModal').classList.remove('active');
    $('leaveFromMembersBtn').onclick = () => {
        $('membersModal').classList.remove('active');
        leaveRoom();
    };

    // 설정 버튼 클릭
    $('settingsBtn').onclick = openSettingsModal;

    // 프로필 모달 이벤트
    $('profileBtn').onclick = openProfileModal;
    $('userAvatar').onclick = openProfileModal;
    $('userInfoClick').onclick = openProfileModal;
    $('closeProfileModal').onclick = closeProfileModal;
    $('cancelProfileBtn').onclick = closeProfileModal;
    $('saveProfileBtn').onclick = saveProfile;
    $('changeProfileImageBtn').onclick = function () { $('profileImageInput').click(); };
    $('profileImageInput').onchange = handleProfileImageUpload;
    $('deleteProfileImageBtn').onclick = deleteProfileImage;

    // 설정 모달 이벤트
    $('closeSettingsModal').onclick = closeSettingsModal;
    $('closeSettingsBtn').onclick = closeSettingsModal;
    $('resetSettingsBtn').onclick = resetSettings;

    // 도움말 모달 이벤트
    $('helpBtn').onclick = function () { $('helpModal').classList.add('active'); };
    $('closeHelpModal').onclick = function () { $('helpModal').classList.remove('active'); };
    $('closeHelpBtn').onclick = function () { $('helpModal').classList.remove('active'); };

    // 테마 토글 버튼
    document.querySelectorAll('.theme-toggle-btn').forEach(function (btn) {
        btn.onclick = function () { setThemeMode(btn.dataset.theme); };
    });

    // 색상 팔레트
    document.querySelectorAll('.color-option').forEach(function (option) {
        option.onclick = function () { setThemeColor(option.dataset.color); };
    });

    // 배경 옵션
    document.querySelectorAll('.bg-option').forEach(function (option) {
        option.onclick = function () { setChatBackground(option.dataset.bg); };
    });

    // 모바일 메뉴
    $('mobileMenuBtn').onclick = function () { $('sidebar').classList.toggle('active'); };

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

    // 드래그앤드롭 파일 업로드
    setupDragDrop();
}

// ============================================================================
// 드래그앤드롭 파일 업로드
// ============================================================================
function setupDragDrop() {
    var dropZone = $('messagesContainer');
    var dropOverlay = $('dropOverlay');

    if (!dropZone || !dropOverlay) return;

    dropZone.addEventListener('dragenter', function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropOverlay.classList.add('active');
    });

    dropZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.stopPropagation();
    });

    dropZone.addEventListener('dragleave', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (e.target === dropZone || !dropZone.contains(e.relatedTarget)) {
            dropOverlay.classList.remove('active');
        }
    });

    dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropOverlay.classList.remove('active');

        var files = e.dataTransfer.files;
        if (files.length > 0) {
            handleDroppedFiles(files);
        }
    });

    // 붙여넣기 이미지 지원
    document.addEventListener('paste', function (e) {
        if (!currentRoom) return;

        var items = e.clipboardData.items;
        for (var i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                var file = items[i].getAsFile();
                handleDroppedFiles([file]);
                break;
            }
        }
    });
}

function handleDroppedFiles(files) {
    if (!currentRoom) {
        showToast('먼저 대화방을 선택해주세요.', 'warning');
        return;
    }

    for (var i = 0; i < files.length; i++) {
        var file = files[i];

        if (file.size > 10 * 1024 * 1024) {
            showToast('파일 크기는 10MB 이하여야 합니다.', 'warning');
            continue;
        }

        uploadFile(file);
    }
}

async function uploadFile(file) {
    var formData = new FormData();
    formData.append('file', file);
    formData.append('room_id', currentRoom.id);

    try {
        var response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        var result = await response.json();

        if (result.success) {
            var messageType = file.type.startsWith('image/') ? 'image' : 'file';

            socket.emit('message', {
                room_id: currentRoom.id,
                content: '',
                message_type: messageType,
                file_path: result.file_path,
                file_name: result.file_name,
                reply_to: replyingTo ? replyingTo.id : null
            });

            clearReply();
            showToast('파일이 전송되었습니다.', 'success');
        } else {
            showToast(result.error || '파일 업로드 실패', 'error');
        }
    } catch (err) {
        console.error('파일 업로드 오류:', err);
        showToast('파일 업로드에 실패했습니다.', 'error');
    }
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

    // 멘션 기능 초기화
    setupMention();
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
    socket.on('room_updated', function () { loadRooms(); });
    socket.on('room_name_updated', handleRoomNameUpdated);
    socket.on('room_members_updated', handleRoomMembersUpdated);
    socket.on('message_deleted', handleMessageDeleted);
    socket.on('message_edited', handleMessageEdited);
    socket.on('user_profile_updated', handleUserProfileUpdated);  // 프로필 변경 알림
    socket.on('error', function (data) { console.error('Socket 오류:', data.message); });
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
    elements.roomList.innerHTML = rooms.map(function (room) {
        var isActive = currentRoom && currentRoom.id === room.id;
        var name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
        var time = room.last_message_time ? formatTime(room.last_message_time) : '';
        var preview = room.last_message ? '[암호화됨]' : '새 대화';
        var pinnedClass = room.pinned ? 'pinned' : '';
        var pinnedIcon = room.pinned ? '<span class="pin-icon">📌</span>' : '';

        // 프로필 이미지 처리
        var avatarHtml = '';
        if (room.type === 'direct' && room.partner && room.partner.profile_image) {
            avatarHtml = '<div class="room-avatar has-image"><img src="/uploads/' + room.partner.profile_image + '" alt="프로필"></div>';
        } else {
            var avatar = room.type === 'direct' && room.partner
                ? room.partner.nickname[0].toUpperCase()
                : (room.name || '그')[0].toUpperCase();
            avatarHtml = '<div class="room-avatar">' + avatar + '</div>';
        }

        var unreadBadge = room.unread_count > 0 ? '<span class="unread-badge">' + room.unread_count + '</span>' : '';

        return '<div class="room-item ' + (isActive ? 'active' : '') + ' ' + pinnedClass + '" data-room-id="' + room.id + '">' +
            avatarHtml +
            '<div class="room-info">' +
            '<div class="room-name">' + escapeHtml(name) + ' 🔒 ' + pinnedIcon + '</div>' +
            '<div class="room-preview">' + preview + '</div>' +
            '</div>' +
            '<div class="room-meta">' +
            '<div class="room-time">' + time + '</div>' +
            unreadBadge +
            '</div>' +
            '</div>';
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
function formatDateLabel(dateStr) {
    var today = new Date();
    var msgDate = new Date(dateStr);

    // 오늘인지 확인
    if (today.toDateString() === msgDate.toDateString()) {
        return '오늘';
    }

    // 어제인지 확인
    var yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (yesterday.toDateString() === msgDate.toDateString()) {
        return '어제';
    }

    // 그 외는 날짜 표시
    return (msgDate.getMonth() + 1) + '월 ' + msgDate.getDate() + '일';
}

function renderMessages(messages) {
    elements.messagesContainer.innerHTML = '';
    let lastDate = null;
    var todayStr = new Date().toISOString().split('T')[0];
    var todayDividerShown = false;

    messages.forEach(msg => {
        const msgDate = msg.created_at.split('T')[0];

        // 날짜가 바뀌었고, (오늘이 아니거나, 오늘인데 아직 구분선이 없는 경우)
        if (msgDate !== lastDate) {
            var isToday = msgDate === todayStr;

            // 오늘이면 첫 메시지에서만 구분선 표시
            if (!isToday || (isToday && !todayDividerShown)) {
                lastDate = msgDate;
                const divider = document.createElement('div');
                divider.className = 'date-divider';
                divider.innerHTML = `<span>${formatDateLabel(msgDate)}</span>`;
                elements.messagesContainer.appendChild(divider);

                if (isToday) todayDividerShown = true;
            }
        }
        appendMessage(msg);
    });

    scrollToBottom();
}

function appendMessage(msg) {
    var isSent = msg.sender_id === currentUser.id;
    var div = document.createElement('div');
    div.className = 'message ' + (isSent ? 'sent' : '');
    div.dataset.messageId = msg.id;
    div.dataset.senderId = msg.sender_id;  // 프로필 업데이트용

    var content = '';
    if (msg.message_type === 'image') {
        content = '<img src="/uploads/' + msg.file_path + '" class="message-image" onclick="openLightbox(this.src)">';
    } else if (msg.message_type === 'file') {
        content = '<div class="message-file">' +
            '<span>📄</span>' +
            '<div class="message-file-info">' +
            '<div class="message-file-name">' + escapeHtml(msg.file_name) + '</div>' +
            '</div>' +
            '<a href="/uploads/' + msg.file_path + '" download="' + msg.file_name + '" class="icon-btn">⬇</a>' +
            '</div>';
    } else {
        var decrypted = currentRoomKey && msg.encrypted ? E2E.decrypt(msg.content, currentRoomKey) : msg.content;
        content = '<div class="message-bubble">' + parseMentions(escapeHtml(decrypted)) + '</div>';
    }

    var unreadHtml = msg.unread_count > 0 ? '<span class="unread-count">' + msg.unread_count + '</span>' : '';

    // 프로필 이미지 처리
    var avatarHtml = '';
    if (msg.sender_image) {
        avatarHtml = '<div class="message-avatar has-image"><img src="/uploads/' + msg.sender_image + '" alt="프로필"></div>';
    } else {
        avatarHtml = '<div class="message-avatar">' + msg.sender_name[0].toUpperCase() + '</div>';
    }

    // 답장 버튼
    var actionsHtml = '<div class="message-actions">' +
        '<button class="message-action-btn" onclick="replyToMessage(' + msg.id + ')" title="답장">↩</button>' +
        '</div>';

    // 답장 원본 메시지 표시
    var replyHtml = '';
    if (msg.reply_to && msg.reply_content) {
        // 암호화된 답장 내용 복호화
        var decryptedReply = currentRoomKey ? E2E.decrypt(msg.reply_content, currentRoomKey) : msg.reply_content;
        // 복호화 실패 시 원본 표시
        if (!decryptedReply || decryptedReply === '') {
            decryptedReply = msg.reply_content;
        }
        replyHtml = '<div class="message-reply" onclick="scrollToMessage(' + msg.reply_to + ')" style="cursor:pointer;">' +
            '<div class="reply-indicator">↩ ' + escapeHtml(msg.reply_sender || '사용자') + '에게 답장</div>' +
            '<div class="reply-text">' + escapeHtml(decryptedReply) + '</div>' +
            '</div>';
    }

    div.innerHTML = avatarHtml +
        '<div class="message-content">' +
        '<div class="message-sender">' + escapeHtml(msg.sender_name) + '</div>' +
        replyHtml +
        content +
        '<div class="message-meta">' +
        unreadHtml +
        '<span>' + formatTime(msg.created_at) + '</span>' +
        '</div>' +
        '</div>' +
        actionsHtml;

    // 메시지 객체 저장 (답장용)
    div._messageData = msg;

    elements.messagesContainer.appendChild(div);
}

function replyToMessage(messageId) {
    var msgEl = document.querySelector('[data-message-id="' + messageId + '"]');
    if (msgEl && msgEl._messageData) {
        setReplyTo(msgEl._messageData);
        elements.messageInput.focus();
    }
}

function scrollToMessage(messageId) {
    var msgEl = document.querySelector('[data-message-id="' + messageId + '"]');
    if (msgEl) {
        // 스크롤 이동
        msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // 하이라이트 효과
        msgEl.classList.add('highlight');
        setTimeout(function () {
            msgEl.classList.remove('highlight');
        }, 2000);
    }
}

function sendMessage() {
    const content = elements.messageInput.value.trim();
    if (!content || !currentRoom || !currentRoomKey) return;

    const encrypted = E2E.encrypt(content, currentRoomKey);
    socket.emit('send_message', {
        room_id: currentRoom.id,
        content: encrypted,
        type: 'text',
        encrypted: true,
        reply_to: replyingTo ? replyingTo.id : null
    });

    elements.messageInput.value = '';
    elements.messageInput.style.height = 'auto';
    clearReply();
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

function handleUserProfileUpdated(data) {
    // 대화방 목록 새로고침 (프로필 변경된 사용자의 닉네임/이미지 반영)
    loadRooms();
    loadOnlineUsers();

    // 현재 열린 대화방의 메시지 영역에서 해당 사용자 프로필 업데이트
    if (currentRoom) {
        var userMessages = document.querySelectorAll('[data-sender-id="' + data.user_id + '"]');
        userMessages.forEach(function (msgEl) {
            // 발신자 이름 업데이트
            var senderEl = msgEl.querySelector('.message-sender');
            if (senderEl && data.nickname) {
                senderEl.textContent = data.nickname;
            }
            // 아바타 업데이트
            var avatarEl = msgEl.querySelector('.message-avatar');
            if (avatarEl) {
                if (data.profile_image) {
                    avatarEl.innerHTML = '<img src="/uploads/' + data.profile_image + '" alt="프로필">';
                    avatarEl.classList.add('has-image');
                } else if (data.nickname) {
                    avatarEl.classList.remove('has-image');
                    avatarEl.textContent = data.nickname[0].toUpperCase();
                }
            }
        });
    }
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
            const roomName = currentRoom.name || (currentRoom.partner ? currentRoom.partner.nickname : '대화방');
            const membersCount = result.members.length;

            // 멤버 정보 표시
            elements.membersInfo.innerHTML = `
                <div class="members-room-name">${escapeHtml(roomName)}</div>
                <div class="members-count">👥 총 ${membersCount}명 참여 중</div>
            `;

            // 멤버 목록 렌더링 (온라인 우선 정렬)
            const sortedMembers = result.members.sort((a, b) => {
                if (a.status === 'online' && b.status !== 'online') return -1;
                if (a.status !== 'online' && b.status === 'online') return 1;
                return a.nickname.localeCompare(b.nickname);
            });

            elements.membersList.innerHTML = sortedMembers.map(m => {
                const isMe = m.id === currentUser.id;
                const statusClass = m.status === 'online' ? 'online' : 'offline';
                const statusText = m.status === 'online' ? '🟢 온라인' : '⚪ 오프라인';

                return `
                    <div class="user-item member-item ${statusClass}">
                        <div class="user-item-avatar ${statusClass}">${m.nickname[0].toUpperCase()}</div>
                        <div class="user-item-info">
                            <div class="user-item-name">
                                ${escapeHtml(m.nickname)}
                                ${isMe ? '<span class="me-badge">(나)</span>' : ''}
                            </div>
                            <div class="user-item-status ${statusClass}">${statusText}</div>
                        </div>
                    </div>
                `;
            }).join('');

            $('membersModal').classList.add('active');
        }
    } catch (err) {
        console.error('멤버 조회 실패:', err);
        showToast('멤버 정보를 불러오는데 실패했습니다.', 'error');
    }

    $('roomSettingsMenu').classList.remove('active');
}

async function leaveRoom() {
    if (!currentRoom) return;

    const roomName = currentRoom.name || (currentRoom.partner ? currentRoom.partner.nickname : '대화방');
    const confirmMsg = `"${roomName}" 대화방을 나가시겠습니까?\n\n⚠️ 나가면 대화 내역을 더 이상 볼 수 없습니다.`;

    if (!confirm(confirmMsg)) return;

    try {
        await api(`/api/rooms/${currentRoom.id}/leave`, { method: 'POST' });
        currentRoom = null;
        currentRoomKey = null;
        elements.chatContent.classList.add('hidden');
        elements.emptyState.classList.remove('hidden');
        loadRooms();
    } catch (err) {
        console.error('대화방 나가기 실패:', err);
        showToast('대화방 나가기에 실패했습니다.', 'error');
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
        (r.name && r.name.toLowerCase().includes(q)) ||
        (r.partner && r.partner.nickname && r.partner.nickname.toLowerCase().includes(q))
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
    if (!dateStr) return '';

    // 서버에서 오는 시간을 로컬 시간으로 변환
    let d;
    if (dateStr.includes('T')) {
        // ISO 형식 (예: 2024-01-01T12:00:00)
        // UTC가 아닌 경우 Z가 없으므로 로컬로 처리
        d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + '+09:00');
    } else if (dateStr.includes(' ')) {
        // SQLite 형식 (예: 2024-01-01 12:00:00)
        d = new Date(dateStr.replace(' ', 'T') + '+09:00');
    } else {
        d = new Date(dateStr);
    }

    // 유효하지 않은 날짜 처리
    if (isNaN(d.getTime())) {
        return '';
    }

    // 현재 시간과의 차이 계산
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);

    // 1분 이내: "방금"
    if (diffMins < 1) return '방금';
    // 60분 이내: "N분 전"
    if (diffMins < 60) return `${diffMins}분 전`;

    // 오늘이면 시간만
    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    // 어제면
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
        return '어제';
    }

    // 그 외: 날짜만
    return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

function formatDate(dateStr) {
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
// 프로필 관리
// ============================================================================
function openProfileModal() {
    if (!currentUser) return;

    var preview = $('profileImagePreview');
    var initial = $('profileInitial');

    // 프로필 이미지 표시
    if (currentUser.profile_image) {
        preview.innerHTML = '<img src="/uploads/' + currentUser.profile_image + '" alt="프로필">';
        preview.classList.add('has-image');
    } else {
        preview.classList.remove('has-image');
        initial.textContent = currentUser.nickname ? currentUser.nickname[0].toUpperCase() : 'U';
    }

    // 현재 정보 채우기
    $('profileNickname').value = currentUser.nickname || '';
    $('profileStatusMessage').value = currentUser.status_message || '';

    $('profileModal').classList.add('active');
}

function closeProfileModal() {
    $('profileModal').classList.remove('active');
}

async function saveProfile() {
    var nickname = $('profileNickname').value.trim();
    var statusMessage = $('profileStatusMessage').value.trim();

    if (nickname && nickname.length < 2) {
        showToast('닉네임은 2자 이상이어야 합니다.', 'warning');
        return;
    }

    try {
        var result = await api('/api/profile', {
            method: 'PUT',
            body: JSON.stringify({
                nickname: nickname || undefined,
                status_message: statusMessage || undefined
            })
        });

        if (result.success) {
            // 로컬 사용자 정보 업데이트
            if (nickname) {
                currentUser.nickname = nickname;
                elements.userName.textContent = nickname;
                elements.userAvatar.textContent = nickname[0].toUpperCase();
            }
            if (statusMessage !== undefined) {
                currentUser.status_message = statusMessage;
            }

            // 소켓으로 다른 사용자들에게 알림
            if (socket) {
                socket.emit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: currentUser.profile_image
                });
            }

            closeProfileModal();
            showToast('프로필이 업데이트되었습니다.', 'success');
        } else {
            showToast(result.error || '프로필 업데이트에 실패했습니다.', 'error');
        }
    } catch (err) {
        console.error('프로필 저장 오류:', err);
        showToast('프로필 저장에 실패했습니다.', 'error');
    }
}

async function handleProfileImageUpload(e) {
    var file = e.target.files[0];
    if (!file) return;

    // 파일 크기 체크 (5MB)
    if (file.size > 5 * 1024 * 1024) {
        showToast('파일 크기는 5MB 이하여야 합니다.', 'warning');
        return;
    }

    // 이미지 타입 체크 (MIME 타입 또는 확장자)
    var allowedImageTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff', 'image/svg+xml', 'image/x-icon'];
    var allowedExtensions = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'ico', 'svg', 'heic', 'heif'];
    var ext = file.name.split('.').pop().toLowerCase();

    if (!file.type.startsWith('image/') && allowedExtensions.indexOf(ext) === -1) {
        showToast('이미지 파일만 업로드 가능합니다. (PNG, JPG, GIF, WEBP, BMP, HEIC 등)', 'warning');
        return;
    }

    var formData = new FormData();
    formData.append('file', file);

    try {
        var response = await fetch('/api/profile/image', {
            method: 'POST',
            body: formData
        });

        var result = await response.json();

        if (result.success) {
            currentUser.profile_image = result.profile_image;

            // 미리보기 업데이트
            var preview = $('profileImagePreview');
            preview.innerHTML = '<img src="/uploads/' + result.profile_image + '" alt="프로필">';
            preview.classList.add('has-image');

            // 사이드바 아바타 업데이트
            updateUserAvatar();

            // 소켓으로 알림
            if (socket) {
                socket.emit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: result.profile_image
                });
            }

            showToast('프로필 사진이 변경되었습니다.', 'success');
        } else {
            showToast(result.error || '사진 업로드에 실패했습니다.', 'error');
        }
    } catch (err) {
        console.error('프로필 사진 업로드 오류:', err);
        showToast('사진 업로드에 실패했습니다.', 'error');
    }

    // 입력 초기화
    e.target.value = '';
}

async function deleteProfileImage() {
    if (!currentUser.profile_image) {
        showToast('삭제할 프로필 사진이 없습니다.', 'warning');
        return;
    }

    if (!confirm('프로필 사진을 기본 이미지로 변경하시겠습니까?')) {
        return;
    }

    try {
        var result = await api('/api/profile/image', { method: 'DELETE' });

        if (result.success) {
            currentUser.profile_image = null;

            // 미리보기 업데이트
            var preview = $('profileImagePreview');
            preview.innerHTML = '<span id="profileInitial">' + currentUser.nickname[0].toUpperCase() + '</span>';
            preview.classList.remove('has-image');

            // 사이드바 아바타 업데이트
            updateUserAvatar();

            // 소켓으로 알림
            if (socket) {
                socket.emit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: null
                });
            }

            showToast('프로필 사진이 기본 이미지로 변경되었습니다.', 'success');
        } else {
            showToast(result.error || '삭제에 실패했습니다.', 'error');
        }
    } catch (err) {
        console.error('프로필 사진 삭제 오류:', err);
        showToast('삭제에 실패했습니다.', 'error');
    }
}

function updateUserAvatar() {
    if (!currentUser) return;

    var avatar = elements.userAvatar;
    if (currentUser.profile_image) {
        avatar.innerHTML = '<img src="/uploads/' + currentUser.profile_image + '" alt="프로필">';
        avatar.classList.add('has-image');
    } else {
        avatar.classList.remove('has-image');
        avatar.innerHTML = '';
        avatar.textContent = currentUser.nickname ? currentUser.nickname[0].toUpperCase() : 'U';
    }
}

// ============================================================================
// 테마 관리
// ============================================================================
var themeSettings = {
    mode: 'dark',
    color: 'emerald',
    chatBg: 'none'
};

function initTheme() {
    // localStorage에서 설정 로드
    var saved = localStorage.getItem('messengerTheme');
    if (saved) {
        try {
            themeSettings = JSON.parse(saved);
        } catch (e) {
            console.error('테마 설정 로드 오류:', e);
        }
    }

    // 테마 적용
    applyTheme();
    updateSettingsUI();
}

function applyTheme() {
    var html = document.documentElement;

    // 테마 모드
    if (themeSettings.mode === 'system') {
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
        html.setAttribute('data-theme', themeSettings.mode);
    }

    // 색상
    html.setAttribute('data-color', themeSettings.color);

    // 채팅 배경
    html.setAttribute('data-chat-bg', themeSettings.chatBg);
}

function saveThemeSettings() {
    localStorage.setItem('messengerTheme', JSON.stringify(themeSettings));
}

function updateSettingsUI() {
    // 테마 모드 버튼
    document.querySelectorAll('.theme-toggle-btn').forEach(function (btn) {
        btn.classList.toggle('active', btn.dataset.theme === themeSettings.mode);
    });

    // 색상 옵션
    document.querySelectorAll('.color-option').forEach(function (option) {
        option.classList.toggle('active', option.dataset.color === themeSettings.color);
    });

    // 배경 옵션
    document.querySelectorAll('.bg-option').forEach(function (option) {
        option.classList.toggle('active', option.dataset.bg === themeSettings.chatBg);
    });
}

function openSettingsModal() {
    updateSettingsUI();
    $('settingsModal').classList.add('active');
}

function closeSettingsModal() {
    $('settingsModal').classList.remove('active');
}

function setThemeMode(mode) {
    themeSettings.mode = mode;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

function setThemeColor(color) {
    themeSettings.color = color;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

function setChatBackground(bg) {
    themeSettings.chatBg = bg;
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

function resetSettings() {
    themeSettings = {
        mode: 'dark',
        color: 'emerald',
        chatBg: 'none'
    };
    applyTheme();
    saveThemeSettings();
    updateSettingsUI();
}

// 시스템 테마 변경 감지
if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if (themeSettings.mode === 'system') {
            applyTheme();
        }
    });
}
