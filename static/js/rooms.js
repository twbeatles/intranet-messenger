/**
 * 대화방 모듈
 * 대화방 목록 로드, 렌더링, 생성, 설정 관련 함수
 */

// ============================================================================
// 대화방 목록
// ============================================================================

/**
 * 대화방 목록 로드
 */
async function loadRooms() {
    try {
        var result = await api('/api/rooms');
        if (window.DEBUG) console.log('loadRooms fetched:', result);
        rooms = result;
        window.rooms = rooms;  // 전역 노출 (notification.js에서 사용)
        renderRoomList();
        try {
            if (typeof safeSocketEmit === 'function' && window.socket && window.socket.connected && Array.isArray(rooms)) {
                safeSocketEmit('subscribe_rooms', { room_ids: rooms.map(function (r) { return r.id; }) });
            }
        } catch (e) { }
    } catch (err) {
        console.error('대화방 로드 실패:', err);
        showToast('대화방 목록 로드 실패: ' + (err.message || err), 'error');
    }
}

// Throttled version
var throttledLoadRooms = throttle(loadRooms, 2000);
var throttledLoadOnlineUsers = null;


/**
 * 대화방 목록 렌더링
 */
function renderRoomList() {
    var roomListEl = document.getElementById('roomList');
    if (!roomListEl) return;

    if (!rooms || rooms.length === 0) {
        roomListEl.innerHTML = '<div class="empty-state-small">대화방이 없습니다,<br>새 대화를 시작해보세요!</div>';
        return;
    }

    roomListEl.innerHTML = rooms.map(function (room) {
        var isActive = currentRoom && currentRoom.id === room.id;
        var name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
        var time = room.last_message_time ? formatTime(room.last_message_time) : '';

        // [v4.32] 메시지 타입에 따른 미리보기 개선
        var preview = '새 대화';
        if (room.last_message_preview) {
            preview = escapeHtml(room.last_message_preview);
        } else if (room.last_message) {
            var lastMsgType = room.last_message_type || 'text';
            switch (lastMsgType) {
                case 'image':
                    preview = '📷 이미지';
                    break;
                case 'file':
                    preview = '📎 파일';
                    break;
                case 'system':
                    preview = '📢 시스템 메시지';
                    break;
                default:
                    // [v4.32] 텍스트 메시지 미리보기 개선
                    // 서버에서 제공하는 미리보기 또는 마지막 메시지 사용
                    if (room.last_message_preview) {
                        preview = escapeHtml(room.last_message_preview);
                    } else if (room.last_message && room.last_message.length > 0) {
                        // 암호화된 메시지인 경우 (Base64 인코딩 패턴 확인)
                        var isEncrypted = /^[A-Za-z0-9+/=]{20,}$/.test(room.last_message);
                        if (isEncrypted) {
                            preview = '🔒 암호화된 메시지';
                        } else {
                            var lastMessageText = room.last_message.length > 25
                                ? room.last_message.substring(0, 25) + '...'
                                : room.last_message;
                            preview = escapeHtml(lastMessageText);
                        }
                    } else {
                        preview = '메시지';
                    }
            }
        }

        // XSS 방지: preview는 room-preview에 HTML로 삽입되므로 항상 escape된 문자열이어야 함
        // (이미 escape된 경우에도 안전하게 동작하도록 string으로 강제)
        if (typeof preview !== 'string') preview = String(preview);

        var pinnedClass = room.pinned ? 'pinned' : '';
        var pinnedIcon = room.pinned ? '<span class="pin-icon">📌</span>' : '';

        // 프로필 이미지 및 색상 처리
        var avatarUserId = room.type === 'direct' && room.partner ? room.partner.id : room.id;
        var avatarName = room.type === 'direct' && room.partner ? room.partner.nickname : (room.name || '그');
        var avatarImage = room.type === 'direct' && room.partner ? room.partner.profile_image : null;
        var avatarHtml = createAvatarHtml(avatarName, avatarImage, avatarUserId, 'room-avatar');

        var unreadBadge = room.unread_count > 0 ? '<span class="unread-badge">' + room.unread_count + '</span>' : '';

        return '<div class="room-item ' + (isActive ? 'active' : '') + ' ' + pinnedClass + '" data-room-id="' + room.id + '" draggable="true">' +
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

    // [v4.30] 이벤트 위임으로 성능 최적화 (initRoomListEvents에서 한 번만 바인딩)
}

// [v4.30] 대화방 목록 이벤트 위임 초기화 (한 번만 실행)
var roomListEventsInitialized = false;

function initRoomListEvents() {
    if (roomListEventsInitialized) return;

    var roomListEl = document.getElementById('roomList');
    if (!roomListEl) return;

    roomListEl.addEventListener('click', function (e) {
        var roomItem = e.target.closest('.room-item');
        if (roomItem) {
            var roomId = parseInt(roomItem.dataset.roomId);
            var room = rooms.find(function (r) { return r.id === roomId; });
            if (room) openRoom(room);
        }
    });

    roomListEventsInitialized = true;
}

// ============================================================================
// 대화방 열기
// ============================================================================

var currentOpenRequestId = 0;
var isOpeningRoom = false;

/**
 * 대화방 열기
 */
async function openRoom(room) {
    // 이미 보고 있는 방이면 무시
    if (currentRoom && currentRoom.id === room.id) return;

    // Re-entry guard
    if (isOpeningRoom) {
        console.warn('Prevented recursive openRoom call');
        return;
    }

    isOpeningRoom = true;
    if (window.DEBUG) console.log('Entering openRoom for room:', room.id);

    try {
        var requestId = ++currentOpenRequestId;

        // [v4.21] 방 전환 시 정리 작업 (safeSocketEmit 사용)
        if (currentRoom) {
            // 타이핑 상태 초기화
            if (typeof safeSocketEmit === 'function') {
                safeSocketEmit('typing', { room_id: currentRoom.id, is_typing: false });
            }
        }

        // [v4.21] 타이핑 타임아웃 정리 (다른 방에 stale 이벤트 전송 방지)
        if (typeof typingTimeout !== 'undefined' && typingTimeout) {
            clearTimeout(typingTimeout);
            typingTimeout = null;
        }

        // [v4.21] 리액션 피커 정리 (메모리 누수 방지)
        if (typeof closeAllReactionPickers === 'function') {
            closeAllReactionPickers();
        }

        // [v4.21] 멘션 자동완성 정리
        if (typeof hideMentionAutocomplete === 'function') {
            hideMentionAutocomplete();
        }

        // [v4.31] 타이핑 사용자 상태 정리
        if (typeof clearTypingUsers === 'function') {
            clearTypingUsers();
        }

        // [v4.31] LazyLoadObserver 정리 (메모리 누수 방지)
        if (typeof cleanupLazyLoadObserver === 'function') {
            cleanupLazyLoadObserver();
        }

        if (typeof cleanupLazyDecryptObserver === 'function') {
            cleanupLazyDecryptObserver();
        }

        currentRoom = room;
        cachedRoomMembers = null;
        cachedRoomId = null;

        // [v4.21] safeSocketEmit 사용
        if (typeof safeSocketEmit === 'function') {
            safeSocketEmit('join_room', { room_id: room.id });
        }


        var emptyState = document.getElementById('emptyState');
        var chatContent = document.getElementById('chatContent');
        var chatName = document.getElementById('chatName');
        var chatAvatar = document.getElementById('chatAvatar');
        var chatStatus = document.getElementById('chatStatus');
        var sidebar = document.getElementById('sidebar');

        if (emptyState) emptyState.classList.add('hidden');
        if (chatContent) chatContent.classList.remove('hidden');

        var name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
        if (chatName) chatName.innerHTML = escapeHtml(name) + ' 🔒';
        if (chatAvatar) chatAvatar.textContent = name[0].toUpperCase();
        if (chatStatus) {
            chatStatus.textContent = room.type === 'direct' && room.partner
                ? (room.partner.status === 'online' ? '온라인' : '오프라인')
                : (room.member_count || 0) + '명 참여 중';
        }

        // 기능 초기화
        if (typeof initRoomV4Features === 'function') {
            initRoomV4Features();
        }

        // 핀/음소거 상태 업데이트
        var pinRoomText = $('pinRoomText');
        var muteRoomText = $('muteRoomText');
        if (pinRoomText) pinRoomText.textContent = room.pinned ? '고정 해제' : '상단 고정';
        if (muteRoomText) muteRoomText.textContent = room.muted ? '알림 켜기' : '알림 끄기';

        try {
            var result = await api('/api/rooms/' + room.id + '/messages');

            // Stale Request Check
            if (requestId !== currentOpenRequestId) {
                if (window.DEBUG) console.log('Ignoring stale openRoom response');
                return;
            }

            currentRoomKey = result.encryption_key;

            currentRoom.members = result.members || [];
            // 마지막 읽은 메시지 ID 찾기
            var lastReadId = 0;
            if (result.members) {
                var currentMember = result.members.find(function (m) { return m.id === currentUser.id; });
                if (currentMember) {
                    lastReadId = currentMember.last_read_message_id || 0;
                }
            }

            if (typeof renderMessages === 'function') {
                renderMessages(result.messages, lastReadId);
            }

            if (result.messages.length > 0 && typeof socket !== 'undefined' && socket && socket.connected) {
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
            if (requestId !== currentOpenRequestId) return;

            console.error('메시지 로드 실패:', err);
            showToast('메시지 로드 실패: ' + (err.message || err), 'error');

            // 오프라인 캐시에서 로드 시도
            if (window.MessengerStorage) {
                var cached = await MessengerStorage.getCachedMessages(room.id);
                if (cached.length > 0 && typeof renderMessages === 'function') {
                    renderMessages(cached, 0);
                }
            }
        }

        setTimeout(renderRoomList, 0);

        // 모바일에서 사이드바 닫기
        if (sidebar) sidebar.classList.remove('active');
    } finally {
        isOpeningRoom = false;
    }
}

// 전역 함수 노출
var _openRoomImpl = openRoom;
window.openRoom = function (room) {
    _openRoomImpl(room);
};

// ============================================================================
// 대화방 생성
// ============================================================================

var isCreatingRoom = false;

/**
 * 새 대화 모달 열기
 */
async function openNewChatModal() {
    try {
        var result = await api('/api/users');
        var userList = document.getElementById('userList');
        if (!userList) return;

        userList.innerHTML = result.map(function (u) {
            var initial = (u.nickname && u.nickname.length > 0) ? u.nickname[0].toUpperCase() : '?';
            // [v4.30] XSS 방지: safeImagePath 사용
            var safePath = u.profile_image && typeof safeImagePath === 'function' ? safeImagePath(u.profile_image) : null;
            var avatarHtml = safePath
                ? '<div class="user-item-avatar has-image"><img src="/uploads/' + safePath + '" alt="프로필"></div>'
                : '<div class="user-item-avatar">' + initial + '</div>';
            return '<div class="user-item" data-user-id="' + u.id + '">' +
                avatarHtml +
                '<div class="user-item-info">' +
                '<div class="user-item-name">' + escapeHtml(u.nickname || '사용자') + '</div>' +
                '<div class="user-item-status ' + u.status + '">' + (u.status === 'online' ? '온라인' : '오프라인') + '</div>' +
                '</div>' +
                '<input type="checkbox" class="user-checkbox">' +
                '</div>';
        }).join('');

        userList.querySelectorAll('.user-item').forEach(function (el) {
            el.onclick = function () {
                var cb = el.querySelector('.user-checkbox');
                cb.checked = !cb.checked;
                el.classList.toggle('selected', cb.checked);
            };
        });

        var newChatModal = $('newChatModal');
        if (newChatModal) newChatModal.classList.add('active');
    } catch (err) {
        console.error('사용자 목록 로드 실패:', err);
        showToast('사용자 목록을 불러오지 못했습니다.', 'error');
    }
}

/**
 * 대화방 생성
 */
async function createRoom() {
    if (isCreatingRoom) return;

    var selected = Array.from(document.querySelectorAll('#userList .user-item.selected'))
        .map(function (el) { return parseInt(el.dataset.userId); });

    if (selected.length === 0) return;

    var btn = $('createRoomBtn');
    if (btn) btn.disabled = true;
    isCreatingRoom = true;

    try {
        var result = await api('/api/rooms', {
            method: 'POST',
            body: JSON.stringify({ members: selected, name: $('roomName').value.trim() })
        });

        if (result.success) {
            $('newChatModal').classList.remove('active');
            await loadRooms();
            var room = rooms.find(function (r) { return r.id === result.room_id; });
            if (room) {
                setTimeout(function () { openRoom(room); }, 0);
            }
        }
    } catch (err) {
        console.error('대화방 생성 실패:', err);
        showToast('대화방 생성 실패: ' + (err.message || err), 'error');
    } finally {
        isCreatingRoom = false;
        if (btn) btn.disabled = false;
    }
}

// ============================================================================
// 초대
// ============================================================================

/**
 * 초대 모달 열기
 */
async function openInviteModal() {
    if (!currentRoom) return;

    try {
        var result = await api('/api/users');
        var memberIds = (currentRoom.members || []).map(function (m) { return m.id; });
        var inviteUserList = document.getElementById('inviteUserList');
        if (!inviteUserList) return;

        inviteUserList.innerHTML = result
            .filter(function (u) { return !memberIds.includes(u.id); })
            .map(function (u) {
                var initial = (u.nickname && u.nickname.length > 0) ? u.nickname[0].toUpperCase() : '?';
                // [v4.30] XSS 방지: safeImagePath 사용
                var safePath = u.profile_image && typeof safeImagePath === 'function' ? safeImagePath(u.profile_image) : null;
                var avatarHtml = safePath
                    ? '<div class="user-item-avatar has-image"><img src="/uploads/' + safePath + '" alt="프로필"></div>'
                    : '<div class="user-item-avatar">' + initial + '</div>';
                return '<div class="user-item" data-user-id="' + u.id + '">' +
                    avatarHtml +
                    '<div class="user-item-info">' +
                    '<div class="user-item-name">' + escapeHtml(u.nickname || '사용자') + '</div>' +
                    '</div>' +
                    '<input type="checkbox" class="user-checkbox">' +
                    '</div>';
            }).join('');

        inviteUserList.querySelectorAll('.user-item').forEach(function (el) {
            el.onclick = function () {
                var cb = el.querySelector('.user-checkbox');
                cb.checked = !cb.checked;
                el.classList.toggle('selected', cb.checked);
            };
        });

        $('inviteModal').classList.add('active');
    } catch (err) {
        console.error('사용자 목록 로드 실패:', err);
    }
}

/**
 * 초대 확인
 * [v4.30] 에러 toast 추가
 * [v4.32] 병렬 API 호출 최적화
 */
async function confirmInvite() {
    var selected = Array.from(document.querySelectorAll('#inviteUserList .user-item.selected'))
        .map(function (el) { return parseInt(el.dataset.userId); });

    if (selected.length === 0) {
        showToast('초대할 사용자를 선택해주세요.', 'warning');
        return;
    }

    try {
        // [v4.32] 병렬 호출로 성능 개선
        await Promise.all(selected.map(function (userId) {
            return api('/api/rooms/' + currentRoom.id + '/members', {
                method: 'POST',
                body: JSON.stringify({ user_id: userId })
            });
        }));

        $('inviteModal').classList.remove('active');
        showToast('멤버를 초대했습니다.', 'success');
        if (typeof throttledLoadRooms === 'function') throttledLoadRooms(); else loadRooms();
    } catch (err) {
        console.error('초대 실패:', err);
        showToast('초대에 실패했습니다: ' + (err.message || err), 'error');
    }
}

// ============================================================================
// 대화방 설정
// ============================================================================

/**
 * 대화방 이름 변경
 */
async function editRoomName() {
    if (!currentRoom) return;

    var newName = prompt('새 대화방 이름:', currentRoom.name || '');
    if (newName && newName.trim()) {
        try {
            var result = await api('/api/rooms/' + currentRoom.id + '/name', {
                method: 'PUT',
                body: JSON.stringify({ name: newName.trim() })
            });

            if (result.success) {
                currentRoom.name = newName.trim();
                var chatName = document.getElementById('chatName');
                if (chatName) chatName.innerHTML = escapeHtml(newName.trim()) + ' 🔒';
                if (typeof throttledLoadRooms === 'function') throttledLoadRooms(); else loadRooms();
            }
        } catch (err) {
            console.error('이름 변경 실패:', err);
        }
    }

    $('roomSettingsMenu').classList.remove('active');
}

/**
 * 대화방 고정 토글
 */
async function togglePinRoom() {
    if (!currentRoom) return;

    var isPinned = currentRoom.pinned;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/pin', {
            method: 'POST',
            body: JSON.stringify({ pinned: !isPinned })
        });

        if (result.success) {
            currentRoom.pinned = !isPinned;
            $('pinRoomText').textContent = currentRoom.pinned ? '고정 해제' : '상단 고정';
            if (typeof throttledLoadRooms === 'function') throttledLoadRooms(); else loadRooms();
        }
    } catch (err) {
        console.error('고정 설정 실패:', err);
    }

    $('roomSettingsMenu').classList.remove('active');
}

/**
 * 알림 음소거 토글
 */
async function toggleMuteRoom() {
    if (!currentRoom) return;

    var isMuted = currentRoom.muted;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/mute', {
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

/**
 * 멤버 보기
 */
async function viewMembers() {
    if (!currentRoom) return;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/info');
        if (result.members) {
            var roomName = currentRoom.name || (currentRoom.partner ? currentRoom.partner.nickname : '대화방');
            var membersCount = result.members.length;

            var membersInfo = document.getElementById('membersInfo');
            var membersList = document.getElementById('membersList');

            if (membersInfo) {
                membersInfo.innerHTML = '<div class="members-room-name">' + escapeHtml(roomName) + '</div>' +
                    '<div class="members-count">👥 총 ' + membersCount + '명 참여 중</div>';
            }

            // 온라인 우선 정렬
            var sortedMembers = result.members.sort(function (a, b) {
                if (a.status === 'online' && b.status !== 'online') return -1;
                if (a.status !== 'online' && b.status === 'online') return 1;
                return (a.nickname || '').localeCompare(b.nickname || '');
            });

            if (membersList) {
                membersList.innerHTML = sortedMembers.map(function (m) {
                    var isMe = m.id === currentUser.id;
                    var statusClass = m.status === 'online' ? 'online' : 'offline';
                    var statusText = m.status === 'online' ? '🟢 온라인' : '⚪ 오프라인';
                    var initial = (m.nickname && m.nickname.length > 0) ? m.nickname[0].toUpperCase() : '?';
                    // [v4.30] XSS 방지: safeImagePath 사용
                    var safePath = m.profile_image && typeof safeImagePath === 'function' ? safeImagePath(m.profile_image) : null;
                    var avatarHtml = safePath
                        ? '<div class="user-item-avatar ' + statusClass + ' has-image"><img src="/uploads/' + safePath + '" alt="프로필"></div>'
                        : '<div class="user-item-avatar ' + statusClass + '">' + initial + '</div>';

                    return '<div class="user-item member-item ' + statusClass + '">' +
                        avatarHtml +
                        '<div class="user-item-info">' +
                        '<div class="user-item-name">' + escapeHtml(m.nickname || '사용자') +
                        (isMe ? '<span class="me-badge">(나)</span>' : '') +
                        '</div>' +
                        '<div class="user-item-status ' + statusClass + '">' + statusText + '</div>' +
                        '</div>' +
                        '</div>';
                }).join('');
            }

            var membersModal = $('membersModal');
            if (membersModal) membersModal.classList.add('active');
        }
    } catch (err) {
        console.error('멤버 조회 실패:', err);
        showToast('멤버 정보를 불러오는데 실패했습니다.', 'error');
    }

    var roomSettingsMenu = $('roomSettingsMenu');
    if (roomSettingsMenu) roomSettingsMenu.classList.remove('active');
}

/**
 * 대화방 나가기
 * [v4.32] 나가기 후 멤버 변경 알림 추가
 */
async function leaveRoom() {
    if (!currentRoom) return;

    var roomName = currentRoom.name || (currentRoom.partner ? currentRoom.partner.nickname : '대화방');
    var confirmMsg = '"' + roomName + '" 대화방을 나가시겠습니까?\n\n⚠️ 나가면 대화 내역을 더 이상 볼 수 없습니다.';

    if (!confirm(confirmMsg)) return;

    var leftRoomId = currentRoom.id;  // 나가기 전 ID 저장

    try {
        await api('/api/rooms/' + currentRoom.id + '/leave', { method: 'POST' });

        // [v4.32] 다른 멤버들에게 멤버 변경 알림
        // [v4.36] socket safety check
        if (socket && socket.connected) {
            safeSocketEmit('room_members_updated', { room_id: leftRoomId });
        }

        currentRoom = null;
        currentRoomKey = null;

        var chatContent = document.getElementById('chatContent');
        var emptyState = document.getElementById('emptyState');
        if (chatContent) chatContent.classList.add('hidden');
        if (emptyState) emptyState.classList.remove('hidden');

        if (typeof throttledLoadRooms === 'function') throttledLoadRooms(); else loadRooms();
        showToast('대화방을 나갔습니다.', 'success');
    } catch (err) {
        console.error('대화방 나가기 실패:', err);
        showToast('대화방 나가기에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 온라인 사용자
// ============================================================================

/**
 * 온라인 사용자 목록 로드
 * [v4.32] 중복 클릭 방지 추가
 */
var isStartingChat = false;

async function loadOnlineUsers() {
    try {
        var users = await api('/api/users/online');

        var onlineUsersList = document.getElementById('onlineUsersList');
        if (!onlineUsersList) return;

        if (!Array.isArray(users)) {
            console.warn('온라인 사용자 API 응답이 배열이 아닙니다:', users);
            onlineUsersList.innerHTML = '';
            return;
        }

        if (users.length === 0) {
            onlineUsersList.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">온라인 사용자가 없습니다</span>';
            return;
        }

        onlineUsersList.innerHTML = users.map(function (u) {
            var initial = (u.nickname && u.nickname.length > 0) ? u.nickname[0].toUpperCase() : '?';
            var name = u.nickname || '사용자';
            return '<div class="online-user" data-user-id="' + u.id + '" title="' + escapeHtml(name) + '">' +
                initial +
                '<span class="online-user-tooltip">' + escapeHtml(name) + '</span>' +
                '</div>';
        }).join('');

        onlineUsersList.querySelectorAll('.online-user').forEach(function (el) {
            el.onclick = async function () {
                // [v4.32] 중복 클릭 방지
                if (isStartingChat) return;
                isStartingChat = true;

                try {
                    var userId = parseInt(el.dataset.userId);

                    // [v4.32] 기존 1:1 채팅방 확인 (중복 생성 방지)
                    var existingRoom = rooms.find(function (r) {
                        return r.type === 'direct' && r.partner && r.partner.id === userId;
                    });

                    if (existingRoom) {
                        openRoom(existingRoom);
                        return;
                    }

                    var result = await api('/api/rooms', {
                        method: 'POST',
                        body: JSON.stringify({ members: [userId] })
                    });
                    if (result.success) {
                        await loadRooms();
                        var room = rooms.find(function (r) { return r.id === result.room_id; });
                        if (room) {
                            setTimeout(function () { openRoom(room); }, 0);
                        }
                    } else {
                        showToast('대화 시작 실패: ' + (result.error || '알 수 없는 오류'), 'error');
                    }
                } catch (err) {
                    console.error('대화 시작 오류:', err);
                    showToast('대화 시작 오류: ' + (err.message || err), 'error');
                } finally {
                    isStartingChat = false;
                }
            };
        });
    } catch (err) {
        console.error('온라인 사용자 로드 실패:', err);
    }
}


// Throttled online users refresh (used by socket events)
try {
    if (typeof throttle === 'function') {
        throttledLoadOnlineUsers = throttle(loadOnlineUsers, 3000);
    }
} catch (e) { }

// expose
window.throttledLoadOnlineUsers = throttledLoadOnlineUsers;
// [v4.7] Start polling explicitly called by initApp
// [v4.21] Tab visibility-aware polling
// [v4.30] 리스너 중복 등록 방지 플래그
var onlinePollingInterval = null;
var visibilityListenerRegistered = false;

function startOnlineUsersPolling() {
    loadOnlineUsers(); // Initial load

    // Start polling
    onlinePollingInterval = setInterval(loadOnlineUsers, 300000); // fallback (5min)
    registerInterval(onlinePollingInterval);

    // [v4.21] Pause polling when tab is hidden
    // [v4.30] 중복 등록 방지
    if (!visibilityListenerRegistered) {
        visibilityListenerRegistered = true;
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                // Tab is hidden - pause polling
                if (onlinePollingInterval) {
                    clearInterval(onlinePollingInterval);
                    onlinePollingInterval = null;
                }
            } else {
                // Tab is visible again - refresh and resume polling
                loadOnlineUsers();
                if (!onlinePollingInterval) {
                    onlinePollingInterval = setInterval(loadOnlineUsers, 300000);
                    registerInterval(onlinePollingInterval);
                }
            }
        });
    }
}

// ============================================================================
// 검색
// ============================================================================

/**
 * 대화방 검색
 * [v4.30] null safety 추가
 */
function handleSearch() {
    var searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    var query = searchInput.value.toLowerCase();
    document.querySelectorAll('.room-item').forEach(function (el) {
        var nameEl = el.querySelector('.room-name');
        if (!nameEl) return;
        var name = nameEl.textContent.toLowerCase();
        el.style.display = name.includes(query) ? '' : 'none';
    });
}

// ============================================================================
// [v4.33] 온라인 섹션 토글
// ============================================================================

/**
 * 온라인 사용자 섹션 접기/펴기
 */
function toggleOnlineSection() {
    var section = document.getElementById('onlineSection');
    if (!section) return;

    section.classList.toggle('collapsed');

    // ARIA 상태 업데이트
    var header = section.querySelector('.online-section-header');
    if (header) {
        var isCollapsed = section.classList.contains('collapsed');
        header.setAttribute('aria-expanded', !isCollapsed);
    }

    // 상태 저장 (로컬 스토리지)
    try {
        localStorage.setItem('onlineSectionCollapsed', section.classList.contains('collapsed'));
    } catch (e) { }
}

/**
 * 온라인 섹션 상태 복원
 */
function restoreOnlineSectionState() {
    try {
        var isCollapsed = localStorage.getItem('onlineSectionCollapsed') === 'true';
        var section = document.getElementById('onlineSection');
        if (section && isCollapsed) {
            section.classList.add('collapsed');
            var header = section.querySelector('.online-section-header');
            if (header) header.setAttribute('aria-expanded', 'false');
        }
    } catch (e) { }
}

// ============================================================================
// [v4.33] 대화방 컨텍스트 메뉴
// ============================================================================

var activeContextMenu = null;

/**
 * 대화방 컨텍스트 메뉴 표시
 * @param {Event} e - 마우스 이벤트
 * @param {Object} room - 대화방 객체
 */
function showRoomContextMenu(e, room) {
    e.preventDefault();
    closeRoomContextMenu();

    var menu = document.createElement('div');
    menu.className = 'room-context-menu';
    menu.innerHTML =
        '<div class="context-item" data-action="open">💬 열기</div>' +
        '<div class="context-item" data-action="pin">' + (room.pinned ? '📌 고정 해제' : '📌 상단 고정') + '</div>' +
        '<div class="context-item" data-action="mute">' + (room.muted ? '🔔 알림 켜기' : '🔕 알림 끄기') + '</div>' +
        '<div class="context-divider"></div>' +
        '<div class="context-item danger" data-action="leave">🚪 나가기</div>';

    // 위치 계산
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';

    // 화면 벗어남 방지
    document.body.appendChild(menu);
    var rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        menu.style.left = (window.innerWidth - rect.width - 10) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
        menu.style.top = (window.innerHeight - rect.height - 10) + 'px';
    }

    // 클릭 핸들러
    menu.querySelectorAll('.context-item').forEach(function (item) {
        item.onclick = function () {
            var action = item.dataset.action;
            closeRoomContextMenu();

            switch (action) {
                case 'open':
                    openRoom(room);
                    break;
                case 'pin':
                    currentRoom = room;
                    togglePinRoom();
                    break;
                case 'mute':
                    currentRoom = room;
                    toggleMuteRoom();
                    break;
                case 'leave':
                    currentRoom = room;
                    leaveRoom();
                    break;
            }
        };
    });

    activeContextMenu = menu;

    // 다른 곳 클릭시 닫기
    setTimeout(function () {
        document.addEventListener('click', closeRoomContextMenu, { once: true });
    }, 0);
}

/**
 * 컨텍스트 메뉴 닫기
 */
function closeRoomContextMenu() {
    if (activeContextMenu && activeContextMenu.parentNode) {
        activeContextMenu.parentNode.removeChild(activeContextMenu);
        activeContextMenu = null;
    }
}

/**
 * 대화방 목록 컨텍스트 메뉴 이벤트 설정
 */
function initRoomContextMenu() {
    var roomListEl = document.getElementById('roomList');
    if (!roomListEl) return;

    roomListEl.addEventListener('contextmenu', function (e) {
        var roomItem = e.target.closest('.room-item');
        if (roomItem) {
            var roomId = parseInt(roomItem.dataset.roomId);
            var room = rooms.find(function (r) { return r.id === roomId; });
            if (room) {
                showRoomContextMenu(e, room);
            }
        }
    });
}

// ============================================================================
// [v4.34] 대화방 드래그앤드롭 정렬
// ============================================================================

var draggedRoom = null;
var dragStartY = 0;

/**
 * 대화방 드래그앤드롭 초기화
 */
function initRoomDragDrop() {
    var roomListEl = document.getElementById('roomList');
    if (!roomListEl) return;

    roomListEl.addEventListener('dragstart', handleRoomDragStart);
    roomListEl.addEventListener('dragover', handleRoomDragOver);
    roomListEl.addEventListener('dragenter', handleRoomDragEnter);
    roomListEl.addEventListener('dragleave', handleRoomDragLeave);
    roomListEl.addEventListener('drop', handleRoomDrop);
    roomListEl.addEventListener('dragend', handleRoomDragEnd);
}

/**
 * 드래그 시작
 */
function handleRoomDragStart(e) {
    var roomItem = e.target.closest('.room-item');
    if (!roomItem) return;

    draggedRoom = roomItem;
    dragStartY = e.clientY;

    roomItem.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', roomItem.dataset.roomId);

    // 드래그 이미지 설정
    var dragImage = roomItem.cloneNode(true);
    dragImage.style.opacity = '0.7';
    dragImage.style.position = 'absolute';
    dragImage.style.left = '-9999px';
    document.body.appendChild(dragImage);
    e.dataTransfer.setDragImage(dragImage, 0, 0);
    setTimeout(function () {
        document.body.removeChild(dragImage);
    }, 0);
}

/**
 * 드래그 오버
 */
function handleRoomDragOver(e) {
    e.preventDefault();
    if (!draggedRoom) return;

    e.dataTransfer.dropEffect = 'move';

    var roomItem = e.target.closest('.room-item');
    if (!roomItem || roomItem === draggedRoom) return;

    var rect = roomItem.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;

    // 드래그 위치에 따라 위/아래 표시
    var roomList = document.getElementById('roomList');
    var items = Array.from(roomList.querySelectorAll('.room-item'));

    items.forEach(function (item) {
        item.classList.remove('drag-over-top', 'drag-over-bottom');
    });

    if (e.clientY < midY) {
        roomItem.classList.add('drag-over-top');
    } else {
        roomItem.classList.add('drag-over-bottom');
    }
}

/**
 * 드래그 진입
 */
function handleRoomDragEnter(e) {
    e.preventDefault();
}

/**
 * 드래그 이탈
 */
function handleRoomDragLeave(e) {
    var roomItem = e.target.closest('.room-item');
    if (roomItem) {
        roomItem.classList.remove('drag-over-top', 'drag-over-bottom');
    }
}

/**
 * 드롭
 */
function handleRoomDrop(e) {
    e.preventDefault();
    if (!draggedRoom) return;

    var targetItem = e.target.closest('.room-item');
    if (!targetItem || targetItem === draggedRoom) {
        cleanupDrag();
        return;
    }

    var roomList = document.getElementById('roomList');
    var items = Array.from(roomList.querySelectorAll('.room-item'));

    var draggedIndex = items.indexOf(draggedRoom);
    var targetIndex = items.indexOf(targetItem);

    // 드롭 위치 계산
    var rect = targetItem.getBoundingClientRect();
    var midY = rect.top + rect.height / 2;
    var insertBefore = e.clientY < midY;

    // DOM에서 이동
    if (insertBefore) {
        roomList.insertBefore(draggedRoom, targetItem);
    } else {
        roomList.insertBefore(draggedRoom, targetItem.nextSibling);
    }

    // rooms 배열 순서 업데이트
    var draggedRoomId = parseInt(draggedRoom.dataset.roomId);
    var targetRoomId = parseInt(targetItem.dataset.roomId);

    var draggedRoomObj = rooms.find(function (r) { return r.id === draggedRoomId; });
    var targetRoomIndex = rooms.findIndex(function (r) { return r.id === targetRoomId; });

    if (draggedRoomObj && targetRoomIndex !== -1) {
        // 배열에서 제거
        rooms = rooms.filter(function (r) { return r.id !== draggedRoomId; });

        // 새 위치에 삽입
        var newIndex = insertBefore ? targetRoomIndex : targetRoomIndex + 1;
        if (draggedIndex < targetRoomIndex) newIndex--;
        rooms.splice(Math.max(0, newIndex), 0, draggedRoomObj);

        // 순서 저장
        saveRoomOrder();
    }

    cleanupDrag();
    showToast('대화방 순서가 변경되었습니다.', 'success');
}

/**
 * 드래그 종료
 */
function handleRoomDragEnd(e) {
    cleanupDrag();
}

/**
 * 드래그 정리
 */
function cleanupDrag() {
    if (draggedRoom) {
        draggedRoom.classList.remove('dragging');
    }

    var roomList = document.getElementById('roomList');
    if (roomList) {
        roomList.querySelectorAll('.room-item').forEach(function (item) {
            item.classList.remove('drag-over-top', 'drag-over-bottom');
        });
    }

    draggedRoom = null;
}

/**
 * 대화방 순서 저장 (로컬 스토리지)
 */
function saveRoomOrder() {
    try {
        var order = rooms.map(function (r) { return r.id; });
        localStorage.setItem('roomOrder', JSON.stringify(order));
    } catch (e) {
        console.warn('대화방 순서 저장 실패:', e);
    }
}

/**
 * 대화방 순서 복원 (로컬 스토리지에서)
 */
function restoreRoomOrder() {
    try {
        var orderStr = localStorage.getItem('roomOrder');
        if (!orderStr) return;

        var order = JSON.parse(orderStr);
        if (!Array.isArray(order)) return;

        // 순서에 따라 rooms 배열 정렬
        rooms.sort(function (a, b) {
            var indexA = order.indexOf(a.id);
            var indexB = order.indexOf(b.id);

            // 순서에 없는 항목은 맨 뒤로
            if (indexA === -1) indexA = order.length;
            if (indexB === -1) indexB = order.length;

            return indexA - indexB;
        });
    } catch (e) {
        console.warn('대화방 순서 복원 실패:', e);
    }
}

/**
 * 대화방 항목에 draggable 속성 추가
 */
function enableRoomDragging() {
    var roomItems = document.querySelectorAll('.room-item');
    roomItems.forEach(function (item) {
        item.setAttribute('draggable', 'true');
    });
}

// ============================================================================
// 전역 노출
// ============================================================================
window.loadRooms = loadRooms;
window.throttledLoadRooms = throttledLoadRooms;
window.renderRoomList = renderRoomList;
window.openRoom = openRoom;
window.openNewChatModal = openNewChatModal;
window.createRoom = createRoom;
window.openInviteModal = openInviteModal;
window.confirmInvite = confirmInvite;
window.editRoomName = editRoomName;
window.togglePinRoom = togglePinRoom;
window.toggleMuteRoom = toggleMuteRoom;
window.viewMembers = viewMembers;
window.leaveRoom = leaveRoom;
window.loadOnlineUsers = loadOnlineUsers;
window.startOnlineUsersPolling = startOnlineUsersPolling; // [v4.7] Export
window.handleSearch = handleSearch;
window.initRoomListEvents = initRoomListEvents; // [v4.30] 이벤트 위임 초기화
// [v4.33] 온라인 섹션 토글 및 컨텍스트 메뉴
window.toggleOnlineSection = toggleOnlineSection;
window.restoreOnlineSectionState = restoreOnlineSectionState;
window.showRoomContextMenu = showRoomContextMenu;
window.closeRoomContextMenu = closeRoomContextMenu;
window.initRoomContextMenu = initRoomContextMenu;
// [v4.34] 드래그앤드롭 정렬
window.initRoomDragDrop = initRoomDragDrop;
window.restoreRoomOrder = restoreRoomOrder;
window.enableRoomDragging = enableRoomDragging;
