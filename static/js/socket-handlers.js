/**
 * Socket.IO 핸들러 모듈
 * 웹소켓 연결 및 실시간 이벤트 처리
 */

// ============================================================================
// Socket.IO 초기화
// ============================================================================

var socket = null;
var reconnectAttempts = 0;

/**
 * Socket.IO 초기화
 */
function initSocket() {
    if (socket) {
        socket.disconnect();
    }

    socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20000
    });

    // 연결 이벤트
    socket.on('connect', function () {
        console.log('Socket connected:', socket.id);
        reconnectAttempts = 0;
        updateConnectionStatus('connected');

        // 현재 방이 있으면 다시 참여
        if (currentRoom) {
            socket.emit('join_room', { room_id: currentRoom.id });
        }
    });

    socket.on('disconnect', function (reason) {
        console.log('Socket disconnected:', reason);
        updateConnectionStatus('disconnected');
    });

    socket.on('connect_error', function (error) {
        console.error('Socket connection error:', error);
        reconnectAttempts++;
        updateConnectionStatus('reconnecting');
    });

    socket.on('reconnect_attempt', function (attemptNumber) {
        reconnectAttempts = attemptNumber;
        updateConnectionStatus('reconnecting');
    });

    socket.on('reconnect', async function () {
        console.log('Socket reconnected');
        reconnectAttempts = 0;
        updateConnectionStatus('connected');
        if (typeof loadRooms === 'function') loadRooms();

        // [v4.21] 재연결 시 현재 방의 누락된 메시지 동기화
        if (currentRoom && typeof api === 'function') {
            try {
                var messagesContainer = document.getElementById('messagesContainer');
                var lastMessage = messagesContainer ? messagesContainer.querySelector('.message:last-child') : null;
                var lastMessageId = lastMessage ? parseInt(lastMessage.dataset.messageId) || 0 : 0;

                var result = await api('/api/rooms/' + currentRoom.id + '/messages');
                if (result.messages && result.messages.length > 0) {
                    // 마지막 메시지 ID 이후의 새 메시지만 추가
                    var newMessages = result.messages.filter(function (msg) {
                        return msg.id > lastMessageId;
                    });

                    if (newMessages.length > 0) {
                        newMessages.forEach(function (msg) {
                            if (typeof appendMessage === 'function') appendMessage(msg);
                        });
                        if (typeof scrollToBottom === 'function') scrollToBottom();
                        console.log('Synced ' + newMessages.length + ' missed messages');
                    }
                }

                // [v4.32] 재연결 시 방 기능 재초기화 (투표, 공지 등)
                if (typeof initRoomV4Features === 'function') {
                    initRoomV4Features();
                }
            } catch (err) {
                console.warn('Failed to sync messages on reconnect:', err);
            }
        }
    });

    // [v4.4] 메시지 배치 처리 (성능 최적화)
    var pendingMessages = [];
    var messageRafScheduled = false;

    function processPendingMessages() {
        if (pendingMessages.length === 0) return;
        var messages = pendingMessages;
        pendingMessages = [];
        messageRafScheduled = false;
        messages.forEach(function (msg) {
            if (typeof handleNewMessage === 'function') {
                handleNewMessage(msg);
            }
        });
    }

    function batchNewMessage(msg) {
        pendingMessages.push(msg);
        if (!messageRafScheduled) {
            messageRafScheduled = true;
            requestAnimationFrame(processPendingMessages);
        }
    }

    // ========================================================================
    // 메시지 이벤트
    // ========================================================================
    socket.on('new_message', batchNewMessage);

    socket.on('message_deleted', function (data) {
        if (typeof handleMessageDeleted === 'function') {
            handleMessageDeleted(data);
        }
    });

    socket.on('message_edited', function (data) {
        if (typeof handleMessageEdited === 'function') {
            handleMessageEdited(data);
        }
    });

    socket.on('read_updated', function (data) {
        if (typeof handleReadUpdated === 'function') {
            handleReadUpdated(data);
        }
    });

    // ========================================================================
    // 타이핑 이벤트
    // ========================================================================
    socket.on('user_typing', function (data) {
        if (typeof handleUserTyping === 'function') {
            handleUserTyping(data);
        }
    });

    // ========================================================================
    // 사용자 상태 이벤트
    // ========================================================================
    socket.on('user_status', function (data) {
        if (typeof handleUserStatus === 'function') {
            handleUserStatus(data);
        }
    });

    socket.on('user_profile_updated', function (data) {
        if (typeof handleUserProfileUpdated === 'function') {
            handleUserProfileUpdated(data);
        }
    });

    // ========================================================================
    // 대화방 이벤트
    // ========================================================================
    socket.on('room_name_updated', function (data) {
        if (typeof handleRoomNameUpdated === 'function') {
            handleRoomNameUpdated(data);
        }
    });

    socket.on('room_members_updated', function (data) {
        if (typeof handleRoomMembersUpdated === 'function') {
            handleRoomMembersUpdated(data);
        }
    });

    socket.on('room_updated', function (data) {
        if (typeof loadRooms === 'function') loadRooms();
    });

    // ========================================================================
    // 리액션 이벤트
    // ========================================================================
    socket.on('reaction_updated', function (data) {
        if (typeof handleReactionUpdated === 'function') {
            handleReactionUpdated(data);
        }
    });

    // ========================================================================
    // 공지 이벤트
    // ========================================================================
    socket.on('pin_updated', function (data) {
        if (currentRoom && data.room_id === currentRoom.id) {
            if (typeof loadPinnedMessages === 'function') loadPinnedMessages();
        }
    });

    // ========================================================================
    // 투표 이벤트
    // ========================================================================
    socket.on('poll_created', function (data) {
        if (currentRoom && data.room_id === currentRoom.id) {
            if (typeof loadRoomPolls === 'function') loadRoomPolls();
        }
    });

    socket.on('poll_updated', function (data) {
        if (data.poll && typeof updatePollDisplay === 'function') {
            updatePollDisplay(data.poll);
        }
    });

    // ========================================================================
    // 관리자 이벤트
    // ========================================================================
    socket.on('admin_updated', function (data) {
        if (currentRoom && data.room_id === currentRoom.id) {
            if (typeof checkAdminStatus === 'function') checkAdminStatus();
        }
    });

    // 전역 노출
    window.socket = socket;
}

// ============================================================================
// 연결 상태 UI
// ============================================================================

/**
 * 연결 상태 표시 업데이트
 */
function updateConnectionStatus(status) {
    var statusEl = document.getElementById('connectionStatus');
    if (!statusEl) return;

    statusEl.className = 'connection-status';
    var textEl = statusEl.querySelector('.status-text');

    switch (status) {
        case 'connected':
            statusEl.classList.add('connected');
            if (textEl) textEl.textContent = '연결됨';
            setTimeout(function () {
                statusEl.classList.remove('visible');
            }, 2000);
            break;
        case 'disconnected':
            statusEl.classList.add('visible', 'disconnected');
            if (textEl) textEl.textContent = '연결 끊김';
            break;
        case 'reconnecting':
            statusEl.classList.add('visible');
            if (textEl) textEl.textContent = '재연결 중... (' + reconnectAttempts + ')';
            break;
    }
}

// ============================================================================
// Socket.IO 이벤트 핸들러
// ============================================================================

/**
 * 새 메시지 수신 처리
 * [v4.31] 멘션 알림 기능 추가
 */
function handleNewMessage(msg) {
    var messagesContainer = document.getElementById('messagesContainer');

    if (currentRoom && msg.room_id === currentRoom.id) {
        // 날짜 구분선 처리
        var msgDate = msg.created_at.split(' ')[0] || msg.created_at.split('T')[0];
        var todayStr = new Date().toISOString().split('T')[0];
        var existingDivider = messagesContainer.querySelector('.date-divider[data-date="' + msgDate + '"]');

        if (!existingDivider) {
            var isToday = msgDate === todayStr;
            var todayDividerExists = messagesContainer.querySelector('.date-divider[data-date="' + todayStr + '"]');

            if (!isToday || !todayDividerExists) {
                var divider = document.createElement('div');
                divider.className = 'date-divider';
                divider.setAttribute('data-date', msgDate);
                divider.innerHTML = '<span>' + formatDateLabel(msgDate) + '</span>';
                messagesContainer.appendChild(divider);
            }
        }

        if (typeof appendMessage === 'function') appendMessage(msg);
        if (typeof scrollToBottom === 'function') scrollToBottom();
        // [v4.22] socket 연결 확인 추가
        if (socket && socket.connected) {
            socket.emit('message_read', { room_id: currentRoom.id, message_id: msg.id });
        }

        // [v4.31] 멘션 알림: 현재 방에서 내가 멘션된 경우 알림 표시
        if (msg.sender_id !== currentUser.id && currentUser.nickname) {
            var mentionPattern = new RegExp('@' + currentUser.nickname + '(?:\\s|$)', 'i');
            if (mentionPattern.test(msg.content)) {
                showMentionNotification(msg);
            }
        }
    } else {
        // 다른 방 알림
        if (window.MessengerNotification && msg.sender_id !== currentUser.id) {
            var room = rooms.find(function (r) { return r.id === msg.room_id; });
            var roomKey = room ? room.encryption_key : null;
            var decrypted = roomKey && msg.encrypted ? E2E.decrypt(msg.content, roomKey) : msg.content;
            MessengerNotification.show(msg.sender_name, decrypted, msg.room_id);
        }
    }

    if (typeof throttledLoadRooms === 'function') throttledLoadRooms();
}

/**
 * [v4.31] 멘션 알림 표시
 */
function showMentionNotification(msg) {
    // 토스트 알림
    if (typeof showToast === 'function') {
        showToast('💬 ' + msg.sender_name + '님이 회원님을 언급했습니다', 'info');
    }

    // 브라우저 알림 (권한 있는 경우)
    if ('Notification' in window && Notification.permission === 'granted') {
        try {
            var notification = new Notification('멘션됨 - ' + msg.sender_name, {
                body: msg.content.substring(0, 100),
                icon: '/static/img/icon.png',
                tag: 'mention-' + msg.id,
                requireInteraction: false
            });
            notification.onclick = function () {
                window.focus();
                notification.close();
            };
            // 5초 후 자동 닫기
            setTimeout(function () { notification.close(); }, 5000);
        } catch (e) {
            console.warn('멘션 알림 생성 실패:', e);
        }
    }
}

/**
 * 읽음 상태 업데이트 처리
 * [v4.32] 이벤트 데이터를 updateUnreadCounts에 전달
 */
function handleReadUpdated(data) {
    if (currentRoom && data.room_id === currentRoom.id) {
        if (typeof updateUnreadCounts === 'function') updateUnreadCounts(data);
    }
}

/**
 * 읽지 않은 메시지 수 업데이트
 * [v4.32] 성능 최적화: 전체 메시지 재조회 대신 UI만 업데이트
 * [v4.35] 정확한 읽음 처리: message_id 기준으로 업데이트, user_id 중복 방지
 */
function updateUnreadCounts(data) {
    if (!currentRoom) return;
    if (!data || !data.message_id || !data.user_id) return;

    // 자신이 읽은 이벤트는 무시 (자신의 메시지 읽음 표시에 영향 없음)
    if (data.user_id === currentUser.id) return;

    var messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    // 내가 보낸 메시지들 중 읽음 처리된 메시지까지만 업데이트
    var myMessages = messagesContainer.querySelectorAll('.message.sent');
    myMessages.forEach(function (msgEl) {
        var msgId = parseInt(msgEl.dataset.messageId);
        // data.message_id 이하의 메시지만 업데이트 (이 사용자가 여기까지 읽음)
        if (msgId > data.message_id) return;

        var readIndicator = msgEl.querySelector('.message-read-indicator');
        if (readIndicator && !readIndicator.classList.contains('all-read')) {
            // 이 메시지를 이미 이 사용자가 읽었는지 확인 (중복 방지)
            var readByUsers = msgEl._readByUsers || [];
            if (readByUsers.includes(data.user_id)) return;

            // 이 사용자가 읽은 것으로 기록
            readByUsers.push(data.user_id);
            msgEl._readByUsers = readByUsers;

            // 카운트 감소
            var match = readIndicator.textContent.match(/(\d+)명/);
            if (match) {
                var count = parseInt(match[1]) - 1;
                if (count <= 0) {
                    readIndicator.classList.add('all-read');
                    readIndicator.innerHTML = '<span class="read-icon">✓✓</span>모두 읽음';
                } else {
                    readIndicator.innerHTML = '<span class="read-icon">✓</span>' + count + '명 안읽음';
                }
            }
        }
    });
}

/**
 * 타이핑 처리
 * [v4.31] 다중 사용자 타이핑 지원
 */
var typingUsers = {};  // {user_id: {nickname, timeout}}

function handleUserTyping(data) {
    var typingIndicator = document.getElementById('typingIndicator');
    if (!typingIndicator) return;

    if (currentRoom && data.room_id === currentRoom.id) {
        if (data.is_typing) {
            // 타이핑 사용자 추가/업데이트
            if (typingUsers[data.user_id]) {
                clearTimeout(typingUsers[data.user_id].timeout);
            }
            typingUsers[data.user_id] = {
                nickname: data.nickname,
                timeout: setTimeout(function () {
                    delete typingUsers[data.user_id];
                    updateTypingIndicator();
                }, 3000)  // 3초 후 자동 제거
            };
        } else {
            // 타이핑 사용자 제거
            if (typingUsers[data.user_id]) {
                clearTimeout(typingUsers[data.user_id].timeout);
                delete typingUsers[data.user_id];
            }
        }
        updateTypingIndicator();
    }
}

function updateTypingIndicator() {
    var typingIndicator = document.getElementById('typingIndicator');
    if (!typingIndicator) return;

    var names = Object.values(typingUsers).map(function (u) { return u.nickname; });

    if (names.length === 0) {
        typingIndicator.classList.add('hidden');
    } else if (names.length === 1) {
        typingIndicator.textContent = names[0] + '님이 입력 중...';
        typingIndicator.classList.remove('hidden');
    } else if (names.length === 2) {
        typingIndicator.textContent = names[0] + ', ' + names[1] + '님이 입력 중...';
        typingIndicator.classList.remove('hidden');
    } else {
        typingIndicator.textContent = names[0] + ' 외 ' + (names.length - 1) + '명이 입력 중...';
        typingIndicator.classList.remove('hidden');
    }
}

// [v4.31] 방 전환 시 타이핑 상태 초기화
function clearTypingUsers() {
    Object.values(typingUsers).forEach(function (u) {
        if (u.timeout) clearTimeout(u.timeout);
    });
    typingUsers = {};
    updateTypingIndicator();
}

/**
 * 사용자 상태 처리
 */
function handleUserStatus(data) {
    if (typeof loadRooms === 'function') loadRooms();
    if (typeof loadOnlineUsers === 'function') loadOnlineUsers();
}

/**
 * 대화방 이름 업데이트 처리
 */
function handleRoomNameUpdated(data) {
    if (typeof loadRooms === 'function') loadRooms();
    if (currentRoom && currentRoom.id === data.room_id) {
        currentRoom.name = data.name;
        var chatName = document.getElementById('chatName');
        if (chatName) chatName.innerHTML = escapeHtml(data.name) + ' 🔒';
    }
}

/**
 * 대화방 멤버 업데이트 처리
 */
function handleRoomMembersUpdated(data) {
    if (typeof loadRooms === 'function') loadRooms();
    // [v4.21] 멘션 캐시 무효화
    if (typeof invalidateMentionCache === 'function') {
        invalidateMentionCache();
    }
}

/**
 * 사용자 프로필 업데이트 처리
 */
function handleUserProfileUpdated(data) {
    if (typeof loadRooms === 'function') loadRooms();
    if (typeof loadOnlineUsers === 'function') loadOnlineUsers();

    if (currentRoom) {
        var userMessages = document.querySelectorAll('[data-sender-id="' + data.user_id + '"]');
        userMessages.forEach(function (msgEl) {
            var senderEl = msgEl.querySelector('.message-sender');
            if (senderEl && data.nickname) {
                senderEl.textContent = data.nickname;
            }
            var avatarEl = msgEl.querySelector('.message-avatar');
            if (avatarEl) {
                if (data.profile_image) {
                    // [v4.21] XSS 방지: safeImagePath 사용
                    var safePath = typeof safeImagePath === 'function' ? safeImagePath(data.profile_image) : data.profile_image;
                    if (safePath) {
                        avatarEl.innerHTML = '<img src="/uploads/' + safePath + '" alt="프로필">';
                        avatarEl.classList.add('has-image');
                    }
                } else if (data.nickname) {
                    avatarEl.classList.remove('has-image');
                    avatarEl.textContent = (data.nickname && data.nickname.length > 0) ? data.nickname[0].toUpperCase() : '?';
                }
            }
        });
    }
}

/**
 * 리액션 업데이트 처리
 */
function handleReactionUpdated(data) {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    if (typeof updateMessageReactions === 'function') {
        updateMessageReactions(data.message_id, data.reactions);
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.initSocket = initSocket;
window.updateConnectionStatus = updateConnectionStatus;
window.handleNewMessage = handleNewMessage;
window.handleReadUpdated = handleReadUpdated;
window.updateUnreadCounts = updateUnreadCounts;
window.handleUserTyping = handleUserTyping;
window.handleUserStatus = handleUserStatus;
window.handleRoomNameUpdated = handleRoomNameUpdated;
window.handleRoomMembersUpdated = handleRoomMembersUpdated;
window.handleUserProfileUpdated = handleUserProfileUpdated;
window.handleReactionUpdated = handleReactionUpdated;
// [v4.31] 다중 타이핑 지원 함수
window.clearTypingUsers = clearTypingUsers;
window.updateTypingIndicator = updateTypingIndicator;
// [v4.31] 멘션 알림 함수
window.showMentionNotification = showMentionNotification;
