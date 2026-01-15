/**
 * 메시지 모듈
 * 메시지 렌더링, 전송, 수정, 삭제 관련 함수
 */

// ============================================================================
// 전역 변수
// ============================================================================

var typingTimeout = null;  // 타이핑 타임아웃 핸들러

// [v4.21] 지연 로딩 관련 변수
var isLoadingOlderMessages = false;
var hasMoreOlderMessages = true;
var oldestMessageId = null;
var lazyLoadObserver = null;

/**
 * [v4.21] 오래된 메시지 지연 로딩 초기화
 */
function initLazyLoadMessages() {
    if (!('IntersectionObserver' in window)) return;

    if (lazyLoadObserver) {
        lazyLoadObserver.disconnect();
    }

    lazyLoadObserver = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting && !isLoadingOlderMessages && hasMoreOlderMessages && currentRoom) {
            loadOlderMessages();
        }
    }, { threshold: 0.1 });

    // 로더 요소 관찰
    var loader = document.getElementById('olderMessagesLoader');
    if (loader) {
        lazyLoadObserver.observe(loader);
    }
}

/**
 * [v4.21] 오래된 메시지 로드
 */
async function loadOlderMessages() {
    if (isLoadingOlderMessages || !hasMoreOlderMessages || !currentRoom || !oldestMessageId) return;

    isLoadingOlderMessages = true;
    var loader = document.getElementById('olderMessagesLoader');
    if (loader) loader.classList.add('loading');

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/messages?before_id=' + oldestMessageId + '&limit=30');

        if (result.messages && result.messages.length > 0) {
            var messagesContainer = document.getElementById('messagesContainer');
            var scrollHeight = messagesContainer.scrollHeight;
            var scrollTop = messagesContainer.scrollTop;

            // 기존 첫 메시지 앞에 새 메시지 삽입
            var fragment = document.createDocumentFragment();
            var firstChild = messagesContainer.firstChild;

            result.messages.forEach(function (msg) {
                var msgEl = createMessageElement(msg);
                if (msgEl) fragment.appendChild(msgEl);
            });

            // 로더 다음에 삽입
            if (loader) {
                loader.after(fragment);
            } else {
                messagesContainer.insertBefore(fragment, firstChild);
            }

            // 스크롤 위치 유지
            messagesContainer.scrollTop = scrollTop + (messagesContainer.scrollHeight - scrollHeight);

            // 가장 오래된 메시지 ID 업데이트
            oldestMessageId = result.messages[0].id;

            if (result.messages.length < 30) {
                hasMoreOlderMessages = false;
                if (loader) loader.classList.add('hidden');
            }
        } else {
            hasMoreOlderMessages = false;
            if (loader) loader.classList.add('hidden');
        }
    } catch (err) {
        console.error('오래된 메시지 로드 실패:', err);
    } finally {
        isLoadingOlderMessages = false;
        if (loader) loader.classList.remove('loading');
    }
}

// ============================================================================
// 메시지 렌더링
// ============================================================================

/**
 * 메시지 목록 렌더링
 */
function renderMessages(messages, lastReadId) {
    var messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    var fragment = document.createDocumentFragment();
    messagesContainer.innerHTML = '';

    // [v4.21] 지연 로딩 초기화
    hasMoreOlderMessages = messages.length >= 50;  // 50개 미만이면 더 이상 없음
    oldestMessageId = messages.length > 0 ? messages[0].id : null;

    // [v4.21] 오래된 메시지 로더 추가
    if (hasMoreOlderMessages) {
        var loader = document.createElement('div');
        loader.id = 'olderMessagesLoader';
        loader.className = 'older-messages-loader';
        loader.innerHTML = '<span class="loader-spinner"></span><span>이전 메시지 불러오는 중...</span>';
        fragment.appendChild(loader);
    }

    var lastDate = null;
    var todayStr = new Date().toISOString().split('T')[0];
    var localTodayDividerShown = false;
    var unreadDividerShown = false;

    messages.forEach(function (msg) {
        var msgDate = msg.created_at.split(' ')[0] || msg.created_at.split('T')[0];

        // 날짜 구분선
        if (msgDate !== lastDate) {
            var isToday = msgDate === todayStr;

            if (!isToday || (isToday && !localTodayDividerShown)) {
                lastDate = msgDate;
                var divider = document.createElement('div');
                divider.className = 'date-divider';
                divider.setAttribute('data-date', msgDate);
                divider.innerHTML = '<span>' + formatDateLabel(msgDate) + '</span>';
                fragment.appendChild(divider);

                if (isToday) localTodayDividerShown = true;
            }
        }

        // 읽지 않은 메시지 구분선
        if (!unreadDividerShown && lastReadId > 0 && msg.id > lastReadId && msg.sender_id !== currentUser.id) {
            var unreadDivider = document.createElement('div');
            unreadDivider.className = 'unread-divider';
            unreadDivider.innerHTML = '<span>여기서부터 읽지 않음</span>';
            fragment.appendChild(unreadDivider);
            unreadDividerShown = true;
        }

        var msgEl = createMessageElement(msg);
        if (msgEl) {
            fragment.appendChild(msgEl);
        }
    });

    messagesContainer.appendChild(fragment);

    // [v4.21] 지연 로딩 Observer 초기화
    setTimeout(initLazyLoadMessages, 100);

    // 읽지 않은 메시지 위치로 스크롤
    if (unreadDividerShown) {
        var unreadDiv = messagesContainer.querySelector('.unread-divider');
        if (unreadDiv) {
            unreadDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
    }

    scrollToBottom();
}

/**
 * 스크롤을 하단으로 이동
 */
function scrollToBottom() {
    var messagesContainer = document.getElementById('messagesContainer');
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

/**
 * 메시지 요소 생성
 */
function createMessageElement(msg) {
    try {
        // 시스템 메시지 처리
        if (msg.message_type === 'system') {
            var div = document.createElement('div');
            div.className = 'message system';
            div.innerHTML = '<div class="message-content"><div class="message-bubble">' + escapeHtml(msg.content) + '</div></div>';
            return div;
        }

        var isSent = msg.sender_id === currentUser.id;
        var div = document.createElement('div');
        div.className = 'message ' + (isSent ? 'sent' : '');
        div.dataset.messageId = msg.id;
        div.dataset.senderId = msg.sender_id;

        var content = '';
        if (msg.message_type === 'image') {
            content = '<img src="/uploads/' + msg.file_path + '" class="message-image" loading="lazy" decoding="async" onclick="openLightbox(this.src)">';
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

        var senderName = msg.sender_name || '사용자';
        var avatarHtml = createAvatarHtml(senderName, msg.sender_image, msg.sender_id, 'message-avatar');

        // 액션 버튼
        var actionsHtml = '<div class="message-actions">' +
            '<button class="message-action-btn" onclick="setReplyToFromId(' + msg.id + ')" title="답장">↩</button>' +
            '<button class="message-action-btn" onclick="showReactionPicker(' + msg.id + ', this)" title="리액션">😊</button>';

        if (isSent && msg.message_type !== 'image' && msg.message_type !== 'file') {
            actionsHtml += '<button class="message-action-btn edit-btn" onclick="editMessage(' + msg.id + ')" title="수정">✏</button>';
        }
        if (isSent) {
            actionsHtml += '<button class="message-action-btn delete-btn" onclick="deleteMessage(' + msg.id + ')" title="삭제">🗑</button>';
        }
        actionsHtml += '</div>';

        // 답장 표시
        var replyHtml = '';
        if (msg.reply_to && msg.reply_content) {
            var decryptedReply = currentRoomKey ? E2E.decrypt(msg.reply_content, currentRoomKey) : msg.reply_content;
            if (!decryptedReply) decryptedReply = msg.reply_content;

            replyHtml = '<div class="message-reply" onclick="scrollToMessage(' + msg.reply_to + ')" style="cursor:pointer;">' +
                '<div class="reply-indicator">↩ ' + escapeHtml(msg.reply_sender || '사용자') + '에게 답장</div>' +
                '<div class="reply-text">' + escapeHtml(decryptedReply) + '</div>' +
                '</div>';
        }

        // 읽음 표시
        var readIndicatorHtml = '';
        if (isSent) {
            if (msg.unread_count === 0) {
                readIndicatorHtml = '<div class="message-read-indicator all-read"><span class="read-icon">✓✓</span>모두 읽음</div>';
            } else if (msg.unread_count > 0) {
                readIndicatorHtml = '<div class="message-read-indicator"><span class="read-icon">✓</span>' + msg.unread_count + '명 안읽음</div>';
            }
        }

        // 리액션 표시
        var reactionsHtml = '';
        if (msg.reactions && msg.reactions.length > 0) {
            var grouped = {};
            msg.reactions.forEach(function (r) {
                if (!grouped[r.emoji]) {
                    grouped[r.emoji] = { count: 0, users: [], myReaction: false };
                }
                grouped[r.emoji].count++;
                grouped[r.emoji].users.push(r.nickname || r.user_id);
                if (currentUser && r.user_id === currentUser.id) {
                    grouped[r.emoji].myReaction = true;
                }
            });

            reactionsHtml = '<div class="message-reactions">';
            for (var emoji in grouped) {
                var data = grouped[emoji];
                var activeClass = data.myReaction ? ' active' : '';
                reactionsHtml += '<span class="reaction-badge' + activeClass + '" onclick="toggleReaction(' + msg.id + ', \'' + emoji + '\')" title="' + data.users.join(', ') + '">' +
                    emoji + ' <span class="reaction-count">' + data.count + '</span></span>';
            }
            reactionsHtml += '<button class="add-reaction-btn" onclick="showReactionPicker(' + msg.id + ', this)">+</button></div>';
        }

        div.innerHTML = avatarHtml +
            '<div class="message-content">' +
            '<div class="message-sender">' + escapeHtml(senderName) + '</div>' +
            replyHtml +
            content +
            '<div class="message-meta">' +
            '<span>' + formatTime(msg.created_at) + '</span>' +
            '</div>' +
            readIndicatorHtml +
            reactionsHtml +
            '</div>' +
            actionsHtml;

        div._messageData = msg;
        return div;

    } catch (err) {
        console.error('메시지 생성 오류:', err);
        var errDiv = document.createElement('div');
        errDiv.className = 'message system error';
        errDiv.textContent = '메시지 렌더링 오류';
        return errDiv;
    }
}

/**
 * 메시지 추가
 */
function appendMessage(msg) {
    var div = createMessageElement(msg);
    var messagesContainer = document.getElementById('messagesContainer');
    if (div && messagesContainer) {
        messagesContainer.appendChild(div);
    }
}

// ============================================================================
// 메시지 전송
// ============================================================================

/**
 * 메시지 전송
 */
function sendMessage() {
    var messageInput = document.getElementById('messageInput');
    if (!messageInput) return;

    var content = messageInput.value.trim();
    if (!content || !currentRoom || !currentRoomKey) return;

    // [v4.21] Socket 연결 상태 확인
    if (!socket || !socket.connected) {
        if (typeof showToast === 'function') {
            showToast('서버 연결이 끊어졌습니다. 잠시 후 다시 시도해주세요.', 'error');
        }
        return;
    }

    var encrypted = E2E.encrypt(content, currentRoomKey);
    socket.emit('send_message', {
        room_id: currentRoom.id,
        content: encrypted,
        type: 'text',
        encrypted: true,
        reply_to: replyingTo ? replyingTo.id : null
    });

    messageInput.value = '';
    messageInput.style.height = 'auto';
    clearReply();

    // 드래프트 삭제
    if (typeof clearDraft === 'function' && currentRoom) {
        clearDraft(currentRoom.id);
    }
}


/**
 * 타이핑 처리
 */
function handleTyping() {
    var messageInput = document.getElementById('messageInput');
    if (!messageInput) return;

    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';

    if (currentRoom && typeof socket !== 'undefined' && socket && socket.connected) {
        socket.emit('typing', { room_id: currentRoom.id, is_typing: true });

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(function () {
            socket.emit('typing', { room_id: currentRoom.id, is_typing: false });
        }, 2000);
    }
}

// ============================================================================
// 메시지 수정/삭제
// ============================================================================

/**
 * 메시지 수정
 */
function editMessage(messageId) {
    var msgEl = document.querySelector('[data-message-id="' + messageId + '"]');
    if (!msgEl || !msgEl._messageData) return;

    // [v4.22] socket 연결 확인 (CLAUDE.md 가이드라인)
    if (!socket || !socket.connected) {
        if (typeof showToast === 'function') {
            showToast('서버 연결이 끊어졌습니다.', 'error');
        }
        return;
    }

    var msg = msgEl._messageData;
    var currentContent = currentRoomKey && msg.encrypted ? E2E.decrypt(msg.content, currentRoomKey) : msg.content;

    var newContent = prompt('메시지 수정:', currentContent);
    if (newContent === null || newContent.trim() === '' || newContent === currentContent) return;

    var encryptedContent = currentRoomKey ? E2E.encrypt(newContent.trim(), currentRoomKey) : newContent.trim();
    socket.emit('edit_message', {
        message_id: messageId,
        room_id: currentRoom.id,
        content: encryptedContent,
        encrypted: !!currentRoomKey
    });
}

/**
 * 메시지 삭제
 */
function deleteMessage(messageId) {
    if (!confirm('이 메시지를 삭제하시겠습니까?')) return;

    // [v4.22] socket 연결 확인 (CLAUDE.md 가이드라인)
    if (!socket || !socket.connected) {
        if (typeof showToast === 'function') {
            showToast('서버 연결이 끊어졌습니다.', 'error');
        }
        return;
    }

    socket.emit('delete_message', {
        message_id: messageId,
        room_id: currentRoom.id
    });
}

/**
 * 메시지 삭제 처리
 */
function handleMessageDeleted(data) {
    var msgEl = document.querySelector('[data-message-id="' + data.message_id + '"]');
    if (msgEl) {
        msgEl.style.transition = 'opacity 0.3s, transform 0.3s';
        msgEl.style.opacity = '0';
        msgEl.style.transform = 'translateX(-20px)';
        setTimeout(function () {
            msgEl.remove();
        }, 300);
    }
    loadRooms();
}

/**
 * 메시지 수정 처리
 */
function handleMessageEdited(data) {
    var msgEl = document.querySelector('[data-message-id="' + data.message_id + '"]');
    if (msgEl && msgEl._messageData) {
        msgEl._messageData.content = data.content;
        msgEl._messageData.encrypted = data.encrypted;

        var decrypted = currentRoomKey && data.encrypted ? E2E.decrypt(data.content, currentRoomKey) : data.content;

        var bubble = msgEl.querySelector('.message-bubble');
        if (bubble) {
            bubble.innerHTML = parseMentions(escapeHtml(decrypted)) + ' <span class="edited-indicator">(수정됨)</span>';
        }

        msgEl.classList.add('highlight');
        setTimeout(function () {
            msgEl.classList.remove('highlight');
        }, 2000);
    }
}

// ============================================================================
// 답장
// ============================================================================

var replyingTo = null;

/**
 * 답장 설정
 */
function setReplyTo(message) {
    replyingTo = message;
    updateReplyPreview();
}

/**
 * 답장 취소
 */
function clearReply() {
    replyingTo = null;
    updateReplyPreview();
}

/**
 * 답장 미리보기 업데이트
 */
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

/**
 * ID로 답장 설정
 */
function setReplyToFromId(msgId) {
    var msgEl = document.querySelector('[data-message-id="' + msgId + '"]');
    if (msgEl && msgEl._messageData) {
        var bubble = msgEl.querySelector('.message-bubble');
        var content = bubble ? bubble.textContent.trim() : msgEl._messageData.content;

        var replyData = {
            id: msgEl._messageData.id,
            sender_name: msgEl._messageData.sender_name,
            sender_id: msgEl._messageData.sender_id,
            content: content,
            encrypted: msgEl._messageData.encrypted
        };

        setReplyTo(replyData);
        var messageInput = document.getElementById('messageInput');
        if (messageInput) messageInput.focus();
    }
}

/**
 * 메시지로 스크롤
 */
function scrollToMessage(messageId, retryCount) {
    retryCount = retryCount || 0;
    var msgEl = document.querySelector('[data-message-id="' + messageId + '"]');

    if (msgEl) {
        msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        msgEl.classList.add('highlight');
        setTimeout(function () {
            msgEl.classList.remove('highlight');
        }, 2000);
    } else if (retryCount < 5) {
        setTimeout(function () {
            scrollToMessage(messageId, retryCount + 1);
        }, 100);
    }
}

// ============================================================================
// 멘션
// ============================================================================

var mentionUsers = [];
var mentionSelectedIndex = 0;
var cachedRoomMembers = null;
var cachedRoomId = null;

/**
 * 멘션 기능 초기화
 */
function setupMention() {
    var input = document.getElementById('messageInput');
    var autocomplete = document.getElementById('mentionAutocomplete');
    if (!input || !autocomplete) return;

    input.addEventListener('input', function (e) {
        var cursorPos = input.selectionStart;
        var text = input.value.substring(0, cursorPos);
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

    if (cachedRoomMembers && cachedRoomId === currentRoom.id) {
        filterAndShowMentions(query, cachedRoomMembers, autocomplete);
        return;
    }

    fetch('/api/rooms/' + currentRoom.id + '/info')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.members) return;
            cachedRoomMembers = data.members;
            cachedRoomId = currentRoom.id;
            filterAndShowMentions(query, data.members, autocomplete);
        });
}

function filterAndShowMentions(query, members, autocomplete) {
    mentionUsers = members.filter(function (m) {
        return m.id !== currentUser.id && m.nickname.toLowerCase().includes(query.toLowerCase());
    }).slice(0, 5);

    if (mentionUsers.length === 0) {
        hideMentionAutocomplete();
        return;
    }

    mentionSelectedIndex = 0;
    autocomplete.innerHTML = mentionUsers.map(function (user, i) {
        return '<div class="mention-item' + (i === 0 ? ' selected' : '') + '" data-user-id="' + user.id + '">' +
            '<div class="mention-item-avatar">' + ((user.nickname && user.nickname.length > 0) ? user.nickname[0].toUpperCase() : '?') + '</div>' +
            '<div class="mention-item-name">' + escapeHtml(user.nickname) + '</div>' +
            '</div>';
    }).join('');

    autocomplete.querySelectorAll('.mention-item').forEach(function (item, idx) {
        item.onclick = function () { selectMention(mentionUsers[idx]); };
    });

    autocomplete.classList.remove('hidden');
}

function hideMentionAutocomplete() {
    var ac = document.getElementById('mentionAutocomplete');
    if (ac) ac.classList.add('hidden');
}

/**
 * [v4.21] 멘션 캐시 무효화 - 방 멤버 변경 시 호출
 */
function invalidateMentionCache() {
    cachedRoomMembers = null;
    cachedRoomId = null;
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
    return text.replace(/@([가-힣a-zA-Z0-9]+)/g, '<span class="mention">@$1</span>');
}

// ============================================================================
// 파일 업로드
// ============================================================================

/**
 * 파일 업로드 처리
 */
async function handleFileUpload(e) {
    var file = e.target.files[0];
    if (!file || !currentRoom) return;

    var formData = new FormData();
    formData.append('file', file);

    // CSRF 토큰 추가
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = {};
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken.getAttribute('content');
    }

    try {
        var res = await fetch('/api/upload', {
            method: 'POST',
            headers: headers,
            body: formData
        });
        var result = await res.json();

        if (result.success) {
            // [v4.21] Socket 연결 상태 확인
            if (!socket || !socket.connected) {
                if (typeof showToast === 'function') {
                    showToast('서버 연결이 끊어졌습니다. 파일은 업로드되었으나 메시지 전송에 실패했습니다.', 'warning');
                }
                e.target.value = '';
                return;
            }

            var isImage = ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(file.name.split('.').pop().toLowerCase());
            socket.emit('send_message', {
                room_id: currentRoom.id,
                content: file.name,
                type: isImage ? 'image' : 'file',
                file_path: result.file_path,
                file_name: result.file_name,
                encrypted: false
            });
        } else {
            if (typeof showToast === 'function') {
                showToast(result.error || '파일 업로드 실패', 'error');
            }
        }
    } catch (err) {
        console.error('파일 업로드 실패:', err);
        if (typeof showToast === 'function') {
            showToast('파일 업로드에 실패했습니다.', 'error');
        }
    }

    e.target.value = '';
}


// ============================================================================
// 리액션
// ============================================================================

var quickReactions = ['👍', '❤️', '😂', '😮', '😢', '🔥'];

/**
 * 리액션 토글
 */
function toggleReaction(messageId, emoji) {
    if (!currentRoom) return;

    api('/api/messages/' + messageId + '/reactions', {
        method: 'POST',
        body: JSON.stringify({ emoji: emoji })
    })
        .then(function (data) {
            if (data.success) {
                updateMessageReactions(messageId, data.reactions);
                // [v4.22] socket 연결 확인 (CLAUDE.md 가이드라인)
                if (socket && socket.connected) {
                    socket.emit('reaction_updated', {
                        room_id: currentRoom.id,
                        message_id: messageId,
                        reactions: data.reactions
                    });
                }
            }
        })
        .catch(function (err) {
            console.error('Reaction error:', err);
            // [v4.22] 사용자 피드백 추가
            if (typeof showToast === 'function') {
                showToast('리액션 처리에 실패했습니다.', 'error');
            }
        });
}

/**
 * 메시지 리액션 업데이트
 */
function updateMessageReactions(messageId, reactions) {
    var msgEl = document.querySelector('[data-message-id="' + messageId + '"]');
    if (!msgEl) return;

    var reactionsContainer = msgEl.querySelector('.message-reactions');
    if (!reactionsContainer) {
        reactionsContainer = document.createElement('div');
        reactionsContainer.className = 'message-reactions';
        var metaEl = msgEl.querySelector('.message-meta');
        if (metaEl) metaEl.after(reactionsContainer);
    }

    if (!reactions || reactions.length === 0) {
        reactionsContainer.innerHTML = '';
        return;
    }

    reactionsContainer.innerHTML = reactions.map(function (r) {
        // [v4.21] 두 가지 데이터 구조 모두 지원: user_ids (배열) 또는 user_id (단일 값)
        var isMine = false;
        if (currentUser) {
            if (r.user_ids && Array.isArray(r.user_ids)) {
                isMine = r.user_ids.includes(currentUser.id);
            } else if (r.user_id !== undefined) {
                isMine = r.user_id === currentUser.id;
            }
        }
        return '<span class="reaction-item' + (isMine ? ' my-reaction' : '') + '" onclick="toggleReaction(' + messageId + ', \'' + r.emoji + '\')">' +
            '<span>' + r.emoji + '</span><span class="reaction-count">' + r.count + '</span>' +
            '</span>';
    }).join('');
}

/**
 * 리액션 피커 표시
 */
function showReactionPicker(messageId, targetEl) {
    // 기존 피커 제거
    closeAllReactionPickers();

    var div = document.createElement('div');
    div.className = 'reaction-picker-popup';
    Object.assign(div.style, {
        position: 'fixed',
        zIndex: '10000',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '24px',
        padding: '6px 10px',
        boxShadow: '0 4px 15px rgba(0,0,0,0.2)',
        display: 'flex',
        gap: '4px'
    });

    div.innerHTML = quickReactions.map(function (emoji) {
        return '<button class="reaction-picker-btn" onclick="toggleReaction(' + messageId + ', \'' + emoji + '\'); closeAllReactionPickers();" ' +
            'style="background:none; border:none; font-size:1.4rem; cursor:pointer; padding:4px; border-radius:50%;">' +
            emoji + '</button>';
    }).join('');

    document.body.appendChild(div);

    var rect = targetEl.getBoundingClientRect();
    var popupRect = div.getBoundingClientRect();

    var top = rect.top - popupRect.height - 8;
    var left = rect.left;

    if (top < 10) top = rect.bottom + 8;
    if (left + popupRect.width > window.innerWidth) left = window.innerWidth - popupRect.width - 10;

    div.style.top = top + 'px';
    div.style.left = left + 'px';

    // 클릭 및 ESC 키로 닫기
    function closeHandler(e) {
        if (!div.contains(e.target)) {
            div.remove();
            document.removeEventListener('click', closeHandler);
            document.removeEventListener('keydown', escHandler);
        }
    }

    function escHandler(e) {
        if (e.key === 'Escape') {
            div.remove();
            document.removeEventListener('click', closeHandler);
            document.removeEventListener('keydown', escHandler);
        }
    }

    setTimeout(function () {
        document.addEventListener('click', closeHandler);
        document.addEventListener('keydown', escHandler);
    }, 10);
}

/**
 * 모든 리액션 피커 닫기 (메모리 누수 방지)
 */
function closeAllReactionPickers() {
    document.querySelectorAll('.reaction-picker-popup').forEach(function (e) { e.remove(); });
}

// ============================================================================
// 전역 노출
// ============================================================================
// ============================================================================
// 이모지 & 드래그앤드롭 (Ported from app.js)
// ============================================================================
const emojis = ['😀', '😂', '😊', '😍', '🥰', '😎', '🤔', '😅', '😭', '😤', '👍', '👎', '❤️', '🔥', '✨', '🎉', '👏', '🙏', '💪', '🤝', '👋', '✅', '❌', '⭐', '💯', '🚀', '💡', '📌', '📝', '💬'];

function initEmojiPicker() {
    var picker = document.getElementById('emojiPicker');
    var input = document.getElementById('messageInput');
    if (!picker || !input) return;

    picker.innerHTML = emojis.map(function (e) {
        return '<button class="emoji-btn">' + e + '</button>';
    }).join('');

    picker.querySelectorAll('.emoji-btn').forEach(function (btn) {
        btn.onclick = function () {
            input.value += btn.textContent;
            input.focus();
        };
    });
}

function setupDragDrop() {
    var dropZone = document.getElementById('messagesContainer');
    var dropOverlay = document.getElementById('dropOverlay');

    if (!dropZone || !dropOverlay) return;

    dropZone.addEventListener('dragenter', function (e) {
        e.preventDefault(); e.stopPropagation();
        dropOverlay.classList.add('active');
    });
    dropZone.addEventListener('dragover', function (e) {
        e.preventDefault(); e.stopPropagation();
    });
    dropZone.addEventListener('dragleave', function (e) {
        e.preventDefault(); e.stopPropagation();
        if (e.target === dropZone || !dropZone.contains(e.relatedTarget)) {
            dropOverlay.classList.remove('active');
        }
    });
    dropZone.addEventListener('drop', function (e) {
        e.preventDefault(); e.stopPropagation();
        dropOverlay.classList.remove('active');
        var files = e.dataTransfer.files;
        if (files.length > 0) handleDroppedFiles(files);
    });

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
        if (typeof showToast === 'function') showToast('먼저 대화방을 선택해주세요.', 'warning');
        return;
    }
    for (var i = 0; i < files.length; i++) {
        var file = files[i];
        if (file.size > 10 * 1024 * 1024) {
            if (typeof showToast === 'function') showToast('파일 크기는 10MB 이하여야 합니다.', 'warning');
            continue;
        }
        uploadFile(file);
    }
}

async function uploadFile(file) {
    if (!currentRoom) return;
    var formData = new FormData();
    formData.append('file', file);
    formData.append('room_id', currentRoom.id);

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const headers = {};
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    try {
        var response = await fetch('/api/upload', {
            method: 'POST',
            headers: headers,
            body: formData
        });
        var result = await response.json();
        if (result.success) {
            var messageType = file.type.startsWith('image/') ? 'image' : 'file';
            // [v4.21] Socket 연결 상태 확인 개선
            if (window.socket && window.socket.connected) {
                window.socket.emit('send_message', {
                    room_id: currentRoom.id,
                    content: '',
                    type: messageType,
                    file_path: result.file_path,
                    file_name: result.file_name,
                    encrypted: false,
                    reply_to: (typeof replyingTo !== 'undefined' && replyingTo) ? replyingTo.id : null
                });
                if (typeof clearReply === 'function') clearReply();
                if (typeof showToast === 'function') showToast('파일이 전송되었습니다.', 'success');
            } else {
                if (typeof showToast === 'function') {
                    showToast('서버 연결이 끊어졌습니다. 파일은 업로드되었으나 메시지 전송에 실패했습니다.', 'warning');
                }
            }
        } else {
            if (typeof showToast === 'function') showToast(result.error || '파일 업로드 실패', 'error');
        }
    } catch (err) {
        console.error('파일 업로드 오류:', err);
        if (typeof showToast === 'function') showToast('파일 업로드에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.renderMessages = renderMessages;
window.scrollToBottom = scrollToBottom;
window.createMessageElement = createMessageElement;
window.appendMessage = appendMessage;
window.sendMessage = sendMessage;
window.handleTyping = handleTyping;
window.editMessage = editMessage;
window.deleteMessage = deleteMessage;
window.handleMessageDeleted = handleMessageDeleted;
window.handleMessageEdited = handleMessageEdited;
window.setReplyTo = setReplyTo;
window.clearReply = clearReply;
window.setReplyToFromId = setReplyToFromId;
window.scrollToMessage = scrollToMessage;
window.setupMention = setupMention;
window.parseMentions = parseMentions;
window.hideMentionAutocomplete = hideMentionAutocomplete;
window.invalidateMentionCache = invalidateMentionCache;
window.handleFileUpload = handleFileUpload;
window.toggleReaction = toggleReaction;
window.updateMessageReactions = updateMessageReactions;
window.showReactionPicker = showReactionPicker;
window.closeAllReactionPickers = closeAllReactionPickers;
// [v4.21] 지연 로딩 함수
window.initLazyLoadMessages = initLazyLoadMessages;
window.loadOlderMessages = loadOlderMessages;
window.initEmojiPicker = initEmojiPicker;
window.setupDragDrop = setupDragDrop;
window.uploadFile = uploadFile;

// ============================================================================
// [v4.30] UI/UX 개선 함수
// ============================================================================

/**
 * 스켈레톤 로딩 표시
 */
function showSkeletonLoading(container, count) {
    count = count || 3;
    if (!container) return;

    var html = '';
    for (var i = 0; i < count; i++) {
        html += '<div class="skeleton-message">' +
            '<div class="skeleton skeleton-avatar"></div>' +
            '<div class="skeleton-content">' +
            '<div class="skeleton skeleton-line"></div>' +
            '<div class="skeleton skeleton-line"></div>' +
            '</div>' +
            '</div>';
    }
    container.innerHTML = html;
}

/**
 * 스켈레톤 로딩 제거
 */
function hideSkeletonLoading(container) {
    if (!container) return;
    var skeletons = container.querySelectorAll('.skeleton-message');
    skeletons.forEach(function (el) {
        el.remove();
    });
}

/**
 * 입력창 상태 업데이트 (버튼 강조)
 */
function updateInputState() {
    var messageInput = document.getElementById('messageInput');
    var sendBtn = document.getElementById('sendBtn');
    if (!messageInput || !sendBtn) return;

    var hasContent = messageInput.value.trim().length > 0;

    if (hasContent) {
        sendBtn.classList.add('has-content');
        sendBtn.disabled = false;
    } else {
        sendBtn.classList.remove('has-content');
    }
}

/**
 * 입력창 이벤트 초기화
 */
function initInputEnhancements() {
    var messageInput = document.getElementById('messageInput');
    if (!messageInput) return;

    // 입력 상태 업데이트
    messageInput.addEventListener('input', debounce(updateInputState, 100));

    // 초기 상태 설정
    updateInputState();
}

// 전역 노출 (v4.30)
window.showSkeletonLoading = showSkeletonLoading;
window.hideSkeletonLoading = hideSkeletonLoading;
window.updateInputState = updateInputState;
window.initInputEnhancements = initInputEnhancements;

// DOMContentLoaded에서 입력창 개선 초기화
document.addEventListener('DOMContentLoaded', function () {
    initInputEnhancements();
});
