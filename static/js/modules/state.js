// 상태 관리

export const state = {
    currentUser: null,
    currentRoom: null,
    currentRoomKey: null,
    rooms: [],
    socket: null,
    elements: {},

    // UI 상태
    replyingTo: null,
    mentionUsers: [],
    mentionSelectedIndex: 0,
    lightboxImages: [],
    currentImageIndex: 0,

    // 채팅 검색
    chatSearchMatches: [],
    chatSearchCurrentIndex: 0,

    // 기타
    typingTimeout: null,
    reconnectAttempts: 0,
    newMessageCount: 0,

    // 캐시
    userCache: {} // {userId: {color: string}}
};

export function setCurrentUser(user) {
    state.currentUser = user;
}

export function setCurrentRoom(room) {
    state.currentRoom = room;
}

export function setRooms(rooms) {
    state.rooms = rooms;
}

export function setSocket(socket) {
    state.socket = socket;
}

// DOM 요소 캐싱
export function cacheElements() {
    const $ = id => document.getElementById(id);
    const ids = [
        'authContainer', 'appContainer', 'loginForm', 'registerForm', 'authError',
        'loginUsername', 'loginPassword', 'regUsername', 'regPassword', 'regNickname',
        'roomList', 'messagesContainer', 'messageInput', 'sendBtn', 'emojiPicker',
        'emptyState', 'chatContent', 'chatName', 'chatAvatar', 'chatStatus',
        'typingIndicator', 'userName', 'userAvatar', 'newChatModal', 'inviteModal',
        'userList', 'inviteUserList', 'roomName', 'connectionStatus', 'onlineUsersList',
        'roomSettingsMenu', 'pinRoomText', 'muteRoomText', 'searchInput', 'sidebar',
        'membersModal', 'membersList', 'membersInfo', 'replyPreview', 'mentionAutocomplete',
        'lightbox', 'lightboxImage', 'chatArea', 'mobileMenuBtn', 'scrollToBottomBtn',
        'profileModal', 'profileNickname', 'profileStatusMessage', 'profileImagePreview',
        'profileInitial', 'profileImageInput', 'settingsModal'
    ];

    ids.forEach(id => {
        const el = $(id);
        if (el) state.elements[id] = el;
    });
}

export function getElement(id) {
    return state.elements[id] || document.getElementById(id);
}
