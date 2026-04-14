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

// [v4.36] Lazy decrypt for E2E messages (reduce PBKDF2 jank on initial render)
var lazyDecryptObserver = null;
var lazyDecryptQueue = [];
var lazyDecryptScheduled = false;
var lazyDecryptQueuedIds = new Set();

function cleanupLazyDecryptObserver() {
    try {
        if (lazyDecryptObserver) lazyDecryptObserver.disconnect();
    } catch (e) { }
    lazyDecryptObserver = null;
    lazyDecryptQueue = [];
    lazyDecryptScheduled = false;
    lazyDecryptQueuedIds = new Set();
}

function decryptPendingInMessageEl(msgEl) {
    if (!msgEl || !msgEl._messageData || !currentRoomKey || !window.E2E) return;
    var msg = msgEl._messageData;

    var bubble = msgEl.querySelector('.message-bubble[data-decrypt-pending="1"]');
    if (bubble && msg.encrypted) {
        var decrypted = E2E.decrypt(msg.content, currentRoomKey);
        if (!decrypted) decrypted = '[\uC554\uD638\uD654\uB41C \uBA54\uC2DC\uC9C0]';
        var parsed = parseCodeBlocks(parseMentions(escapeHtml(decrypted)));
        bubble.innerHTML = parsed;
        bubble.removeAttribute('data-decrypt-pending');
    }

    var replyText = msgEl.querySelector('.reply-text[data-reply-decrypt-pending="1"]');
    if (replyText && msg.reply_content) {
        var decryptedReply = E2E.decrypt(msg.reply_content, currentRoomKey);
        if (!decryptedReply) decryptedReply = '[\uC554\uD638\uD654\uB41C \uBA54\uC2DC\uC9C0]';
        replyText.textContent = decryptedReply;
        replyText.removeAttribute('data-reply-decrypt-pending');
    }
}

function scheduleLazyDecrypt() {
    if (lazyDecryptScheduled) return;
    lazyDecryptScheduled = true;

    var run = function () {
        lazyDecryptScheduled = false;
        var budget = 6;  // max items per tick
        while (lazyDecryptQueue.length > 0 && budget > 0) {
            var msgEl = lazyDecryptQueue.shift();
            var id = msgEl && msgEl.dataset ? msgEl.dataset.messageId : null;
            try { if (id) lazyDecryptQueuedIds.delete(id); } catch (e) { }
            decryptPendingInMessageEl(msgEl);
            budget--;
        }
        if (lazyDecryptQueue.length > 0) scheduleLazyDecrypt();
    };

    if (window.requestIdleCallback) {
        window.requestIdleCallback(run, { timeout: 200 });
    } else {
        setTimeout(run, 0);
    }
}

function enqueueLazyDecryptFromNode(node) {
    if (!node) return;
    var msgEl = node.closest ? node.closest('.message') : null;
    if (!msgEl || !msgEl.dataset || !msgEl.dataset.messageId) return;
    var id = msgEl.dataset.messageId;
    if (lazyDecryptQueuedIds.has(id)) return;
    lazyDecryptQueuedIds.add(id);
    lazyDecryptQueue.push(msgEl);
    scheduleLazyDecrypt();
}

function observePendingDecrypts() {
    var container = document.getElementById('messagesContainer');
    if (!container) return;

    var selector = '.message-bubble[data-decrypt-pending="1"], .reply-text[data-reply-decrypt-pending="1"]';
    if (!('IntersectionObserver' in window)) {
        container.querySelectorAll(selector).forEach(function (el) { enqueueLazyDecryptFromNode(el); });
        return;
    }

    try { if (lazyDecryptObserver) lazyDecryptObserver.disconnect(); } catch (e) { }
    lazyDecryptObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            try { lazyDecryptObserver.unobserve(entry.target); } catch (e) { }
            enqueueLazyDecryptFromNode(entry.target);
        });
    }, { root: container, threshold: 0.1 });

    container.querySelectorAll(selector).forEach(function (el) {
        lazyDecryptObserver.observe(el);
    });
}


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
        var result = await api('/api/rooms/' + currentRoom.id + '/messages?before_id=' + oldestMessageId + '&limit=30&include_meta=0');

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
            observePendingDecrypts();
            if (typeof rebuildReadReceiptIndex === 'function') {
                rebuildReadReceiptIndex();
            }

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
    var lastSenderId = null;
    var lastMessageTime = null;
    var groupStartIndex = -1;

    messages.forEach(function (msg, index) {
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
                // 날짜 구분선 후 그룹화 초기화
                lastSenderId = null;
                lastMessageTime = null;
            }
        }

        // 읽지 않은 메시지 구분선
        if (!unreadDividerShown && lastReadId > 0 && msg.id > lastReadId && msg.sender_id !== currentUser.id) {
            var unreadDivider = document.createElement('div');
            unreadDivider.className = 'unread-divider';
            unreadDivider.innerHTML = '<span>여기서부터 읽지 않음</span>';
            fragment.appendChild(unreadDivider);
            unreadDividerShown = true;
            // 읽지 않음 구분선 후 그룹화 초기화
            lastSenderId = null;
            lastMessageTime = null;
        }

        // [v4.34] 메시지 그룹화 판단
        var msgTime = new Date(msg.created_at.replace(' ', 'T')).getTime();
        var isGrouped = false;
        var isFirstInGroup = false;
        var isLastInGroup = false;
        var nextMsg = messages[index + 1];

        // 같은 발신자이고 3분 이내이면 그룹화
        if (lastSenderId === msg.sender_id && lastMessageTime && (msgTime - lastMessageTime) < 180000) {
            isGrouped = true;
        } else {
            isFirstInGroup = true;
        }

        // 다음 메시지와 그룹화 여부 확인
        if (nextMsg) {
            var nextMsgTime = new Date(nextMsg.created_at.replace(' ', 'T')).getTime();
            if (nextMsg.sender_id !== msg.sender_id || (nextMsgTime - msgTime) >= 180000) {
                isLastInGroup = true;
            }
        } else {
            isLastInGroup = true;
        }

        var msgEl = createMessageElement(msg, isGrouped, isFirstInGroup, isLastInGroup);
        if (msgEl) {
            fragment.appendChild(msgEl);
        }

        lastSenderId = msg.sender_id;
        lastMessageTime = msgTime;
    });

    messagesContainer.appendChild(fragment);
    cleanupLazyDecryptObserver();
    observePendingDecrypts();
    if (typeof rebuildReadReceiptIndex === 'function') {
        rebuildReadReceiptIndex();
    }

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
 * [v4.34] isGrouped, isFirstInGroup, isLastInGroup 파라미터 추가
 */
function createMessageElement(msg, isGrouped, isFirstInGroup, isLastInGroup) {
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

        // [v4.34] 그룹화 클래스 추가
        var classList = ['message'];
        if (isSent) classList.push('sent');
        if (isGrouped) classList.push('grouped');
        if (isFirstInGroup) classList.push('first-in-group');
        if (isLastInGroup) classList.push('last-in-group');
        div.className = classList.join(' ');

        div.dataset.messageId = msg.id;
        div.dataset.senderId = msg.sender_id;

        var content = '';
        if (msg.message_type === 'image') {
            var safeFilePathImg = (typeof safeImagePath === 'function') ? safeImagePath(msg.file_path) : msg.file_path;
            if (safeFilePathImg) {
                content = '<img src="/uploads/' + safeFilePathImg + '" class="message-image" loading="lazy" decoding="async" onclick="openLightbox(this.src)">';
            } else {
                content = '<div class="message-bubble">[잘못된 이미지 경로]</div>';
            }
        } else if (msg.message_type === 'file') {
            var safeFilePath = (typeof safeImagePath === 'function') ? safeImagePath(msg.file_path) : msg.file_path;
            var safeFileName = escapeHtml(msg.file_name || '파일');
            var safeDownloadName = escapeHtml(msg.file_name || 'file');
            content = '<div class="message-file">' +
                '<span>📄</span>' +
                '<div class="message-file-info">' +
                '<div class="message-file-name">' + safeFileName + '</div>' +
                '</div>' +
                (safeFilePath
                    ? '<a href="/uploads/' + safeFilePath + '" download="' + safeDownloadName + '" class="icon-btn">⬇</a>'
                    : '') +
                '</div>';
        } else {
            if (msg.encrypted && currentRoomKey) {
                content = '<div class="message-bubble" data-decrypt-pending="1">[\uBCF5\uD638\uD654 \uC911...]</div>';
            } else {
                var decrypted = msg.encrypted ? '[\uC554\uD638\uD654\uB41C \uBA54\uC2DC\uC9C0]' : msg.content;
                // [v4.34] 코드 블록과 멘션 처리
                var parsedContent = parseCodeBlocks(parseMentions(escapeHtml(decrypted)));
                content = '<div class="message-bubble">' + parsedContent + '</div>';
            }
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
            var replyText = msg.reply_content;
            var replyPending = false;
            
            if (currentRoomKey && typeof msg.reply_content === 'string' && msg.reply_content.indexOf('v2:') === 0) {
                replyText = '[\uBCF5\uD638\uD654 \uC911...]';
                replyPending = true;
            } else if (currentRoomKey) {
                replyText = E2E.decrypt(msg.reply_content, currentRoomKey) || '[\uC554\uD638\uD654\uB41C \uBA54\uC2DC\uC9C0]';
            }
            
            var replyTextHtml = replyPending
                ? '<div class="reply-text" data-reply-decrypt-pending="1">' + escapeHtml(replyText) + '</div>'
                : '<div class="reply-text">' + escapeHtml(replyText) + '</div>';
            
            replyHtml = '<div class="message-reply" onclick="scrollToMessage(' + msg.reply_to + ')" style="cursor:pointer;">' +
                '<div class="reply-indicator">\u21A9 ' + escapeHtml(msg.reply_sender || '\uC54C \uC218 \uC5C6\uC74C') + '\uB2D8\uC758 \uBA54\uC2DC\uC9C0</div>' +
                replyTextHtml +
                '</div>';
        }

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
                var titleText = escapeHtml(data.users.join(', '));
                reactionsHtml += '<span class="reaction-badge' + activeClass + '" onclick="toggleReaction(' + msg.id + ', ' + JSON.stringify(emoji) + ')" title="' + titleText + '">' +
                    emoji + ' <span class="reaction-count">' + data.count + '</span></span>';
            }
            reactionsHtml += '<button class="add-reaction-btn" onclick="showReactionPicker(' + msg.id + ', this)">+</button></div>';
        }

        // [v4.34] 시간 툴팁 (상세 날짜/시간 표시)
        var fullDateTime = escapeHtml(formatFullDateTime(msg.created_at));
        var timeHtml = '<span style="position:relative;cursor:help;">' + formatTime(msg.created_at) +
            '<span class="message-time-tooltip">' + fullDateTime + '</span></span>';

        div.innerHTML = avatarHtml +
            '<div class="message-content">' +
            '<div class="message-sender">' + escapeHtml(senderName) + '</div>' +
            replyHtml +
            content +
            '<div class="message-meta">' +
            timeHtml +
            '</div>' +
            readIndicatorHtml +
            reactionsHtml +
            '</div>' +
            actionsHtml;

        div._messageData = msg;
        if (isSent && typeof msg.unread_count === 'number') {
            div._unreadCount = msg.unread_count;
        }
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
    decryptPendingInMessageEl(div);
    var messagesContainer = document.getElementById('messagesContainer');
    if (div && messagesContainer) {
        messagesContainer.appendChild(div);
    }
    if (div && typeof indexSentMessageEl === 'function') {
        indexSentMessageEl(div);
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
    // [v4.36] safeSocketEmit 사용
    safeSocketEmit('send_message', {
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
        safeSocketEmit('typing', { room_id: currentRoom.id, is_typing: true });

        clearTimeout(typingTimeout);
        // [v4.31] 현재 방 ID 캡처 (타임아웃 후 방이 변경될 수 있음)
        var currentRoomIdForTyping = currentRoom.id;
        typingTimeout = setTimeout(function () {
            // [v4.31] socket 연결 상태 재확인 (CLAUDE.md 가이드라인) - safeSocketEmit 사용
            if (socket && socket.connected) {
                safeSocketEmit('typing', { room_id: currentRoomIdForTyping, is_typing: false });
            }
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
    var currentContent = currentRoomKey && msg.encrypted ? (E2E.decrypt(msg.content, currentRoomKey) || '[\xec\x95\x94\xed\x98\xb8\xed\x99\x94\xeb\x90\x9c \xeb\xa9\x94\xec\x8b\x9c\xec\xa7\x80]') : msg.content;

    var newContent = prompt('메시지 수정:', currentContent);
    if (newContent === null || newContent.trim() === '' || newContent === currentContent) return;

    var encryptedContent = currentRoomKey ? E2E.encrypt(newContent.trim(), currentRoomKey) : newContent.trim();
    // [v4.36] safeSocketEmit 사용
    safeSocketEmit('edit_message', {
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
 * [v4.30] 성능 최적화: loadRooms() 호출 제거, 모션 감소 모드 지원
 * [v4.35] 삭제된 메시지를 참조하는 답장 업데이트
 */
function handleMessageDeleted(data) {
    var msgEl = document.querySelector('[data-message-id="' + data.message_id + '"]');
    if (msgEl) {
        // 모션 감소 모드 확인
        var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (reduceMotion) {
            msgEl.remove();
        } else {
            msgEl.style.transition = 'opacity 0.2s ease';
            msgEl.style.opacity = '0';
            setTimeout(function () {
                msgEl.remove();
            }, 200);
        }
    }

    // [v4.35] 삭제된 메시지를 참조하는 답장들의 표시 업데이트
    var replyElements = document.querySelectorAll('.message-reply[onclick*="scrollToMessage(' + data.message_id + ')"]');
    replyElements.forEach(function (replyEl) {
        var replyText = replyEl.querySelector('.reply-text');
        if (replyText) {
            replyText.textContent = '[삭제된 메시지]';
            replyText.classList.add('deleted-reply');
        }
        // 클릭시 스크롤 비활성화
        replyEl.style.cursor = 'default';
        replyEl.onclick = function (e) { e.stopPropagation(); };
    });

    if (replyingTo && replyingTo.id === data.message_id && typeof clearReply === 'function') {
        clearReply();
    }

    if (typeof throttledLoadRooms === 'function') {
        throttledLoadRooms();
    } else if (typeof loadRooms === 'function') {
        loadRooms();
    }

    var filesModal = document.getElementById('filesModal');
    if (filesModal && filesModal.classList.contains('active') && typeof loadRoomFiles === 'function') {
        loadRoomFiles();
    }
}

/**
 * 메시지 수정 처리
 */
function handleMessageEdited(data) {
    var msgEl = document.querySelector('[data-message-id="' + data.message_id + '"]');
    if (msgEl && msgEl._messageData) {
        msgEl._messageData.content = data.content;
        msgEl._messageData.encrypted = data.encrypted;

        var decrypted = currentRoomKey && data.encrypted ? (E2E.decrypt(data.content, currentRoomKey) || '[\xec\x95\x94\xed\x98\xb8\xed\x99\x94\xeb\x90\x9c \xeb\xa9\x94\xec\x8b\x9c\xec\xa7\x80]') : data.content;

        var bubble = msgEl.querySelector('.message-bubble');
        if (bubble) {
            bubble.innerHTML = parseMentions(escapeHtml(decrypted)) + ' <span class="edited-indicator">(수정됨)</span>';
        }

        msgEl.classList.add('highlight');
        setTimeout(function () {
            msgEl.classList.remove('highlight');
        }, 2000);
    }

    if (typeof throttledLoadRooms === 'function') {
        throttledLoadRooms();
    } else if (typeof loadRooms === 'function') {
        loadRooms();
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

function getUploadMaxSizeBytes() {
    if (!window.MessengerUpload) return 16 * 1024 * 1024;
    return window.MessengerUpload.getUploadMaxSizeBytes();
}

function _inferMessageType(file) {
    if (!window.MessengerUpload) return 'file';
    return window.MessengerUpload.inferMessageType(file);
}

function _emitUploadedFileMessage(file, result, replyToId) {
    if (!window.MessengerUpload) return false;
    return window.MessengerUpload.emitUploadedFileMessage(file, result, replyToId);
}

function _pollUploadScanJob(jobId, file, replyToId, onDone) {
    if (!window.MessengerUpload) {
        if (typeof onDone === 'function') onDone();
        return;
    }
    window.MessengerUpload.pollUploadScanJob(jobId, file, replyToId, onDone);
}

function _handleUploadApiResult(file, result, replyToId, onDone) {
    if (!window.MessengerUpload) {
        if (typeof onDone === 'function') onDone();
        return;
    }
    window.MessengerUpload.handleUploadApiResult(file, result, replyToId, onDone);
}

/**
 * 파일 업로드 처리
 * [v4.31] 업로드 진행률 표시 추가
 */
async function handleFileUpload(e) {
    if (!window.MessengerUpload) return;
    return window.MessengerUpload.handleFileUploadEvent(e);
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
                    // [v4.36] safeSocketEmit 사용
                    safeSocketEmit('reaction_updated', {
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
    // [v4.32] 접근성 개선: aria 속성 추가
    div.setAttribute('role', 'menu');
    div.setAttribute('aria-label', '리액션 선택');
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
        return '<button class="reaction-picker-btn" role="menuitem" aria-label="리액션 ' + emoji + '" onclick="toggleReaction(' + messageId + ', \'' + emoji + '\'); closeAllReactionPickers();" ' +
            'style="background:none; border:none; font-size:1.4rem; cursor:pointer; padding:4px; border-radius:50%;">' +
            emoji + '</button>';
    }).join('');

    document.body.appendChild(div);

    var rect = targetEl.getBoundingClientRect();
    var popupRect = div.getBoundingClientRect();

    // [v4.32] 개선된 뷰포트 경계 처리 (모바일 지원)
    var padding = 10;
    var viewportWidth = window.innerWidth;
    var viewportHeight = window.innerHeight;

    // 기본 위치: 대상 요소 위
    var top = rect.top - popupRect.height - 8;
    var left = rect.left + (rect.width / 2) - (popupRect.width / 2);

    // 상단 경계 체크: 화면 밖이면 아래로 배치
    if (top < padding) {
        top = rect.bottom + 8;
    }

    // 하단 경계 체크: 그래도 화면 밖이면 뷰포트 내 배치
    if (top + popupRect.height > viewportHeight - padding) {
        top = viewportHeight - popupRect.height - padding;
    }

    // 좌측 경계 체크
    if (left < padding) {
        left = padding;
    }

    // 우측 경계 체크
    if (left + popupRect.width > viewportWidth - padding) {
        left = viewportWidth - popupRect.width - padding;
    }

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
    if (!window.MessengerUpload) return;
    return window.MessengerUpload.handleDroppedFiles(files);
}

function uploadFile(file) {
    if (!window.MessengerUpload) return;
    return window.MessengerUpload.uploadFile(file);
}

// ============================================================================
// [v4.35] 메시지 컨텍스트 메뉴 (우클릭)
// ============================================================================

var activeMessageContextMenu = null;

/**
 * 메시지 컨텍스트 메뉴 표시
 */
function showMessageContextMenu(e, messageEl) {
    e.preventDefault();
    closeMessageContextMenu();

    var msgData = messageEl._messageData;
    if (!msgData) return;

    var isSent = msgData.sender_id === currentUser.id;
    var isSystemMessage = msgData.message_type === 'system';

    // 시스템 메시지는 제외
    if (isSystemMessage) return;

    var menu = document.createElement('div');
    menu.className = 'message-context-menu';
    menu.setAttribute('role', 'menu');

    var menuHtml = '';

    // 답장
    menuHtml += '<div class="context-menu-item" data-action="reply" role="menuitem">↩ 답장</div>';

    // 공지로 설정 (텍스트 메시지만)
    if (msgData.message_type === 'text') {
        menuHtml += '<div class="context-menu-item" data-action="pin" role="menuitem">📌 공지로 설정</div>';
    }

    // 리액션
    menuHtml += '<div class="context-menu-item" data-action="reaction" role="menuitem">😊 리액션 추가</div>';

    // 내 메시지인 경우 수정/삭제
    if (isSent) {
        menuHtml += '<div class="context-menu-divider"></div>';
        if (msgData.message_type === 'text') {
            menuHtml += '<div class="context-menu-item" data-action="edit" role="menuitem">✏ 수정</div>';
        }
        menuHtml += '<div class="context-menu-item danger" data-action="delete" role="menuitem">🗑 삭제</div>';
    }

    menu.innerHTML = menuHtml;
    document.body.appendChild(menu);

    // 위치 설정
    var menuRect = menu.getBoundingClientRect();
    var padding = 10;
    var left = e.clientX;
    var top = e.clientY;

    // 우측 경계 처리
    if (left + menuRect.width > window.innerWidth - padding) {
        left = window.innerWidth - menuRect.width - padding;
    }
    // 하단 경계 처리
    if (top + menuRect.height > window.innerHeight - padding) {
        top = window.innerHeight - menuRect.height - padding;
    }

    menu.style.left = left + 'px';
    menu.style.top = top + 'px';

    // 메뉴 항목 클릭 핸들러
    menu.querySelectorAll('.context-menu-item').forEach(function (item) {
        item.onclick = function () {
            var action = item.dataset.action;
            handleContextMenuAction(action, msgData, messageEl);
            closeMessageContextMenu();
        };
    });

    activeMessageContextMenu = menu;

    // 외부 클릭 또는 ESC로 닫기
    setTimeout(function () {
        document.addEventListener('click', closeMessageContextMenu, { once: true });
        document.addEventListener('keydown', handleContextMenuEsc);
    }, 10);
}

function handleContextMenuEsc(e) {
    if (e.key === 'Escape') {
        closeMessageContextMenu();
    }
}

function closeMessageContextMenu() {
    if (activeMessageContextMenu && activeMessageContextMenu.parentNode) {
        activeMessageContextMenu.parentNode.removeChild(activeMessageContextMenu);
    }
    activeMessageContextMenu = null;
    document.removeEventListener('keydown', handleContextMenuEsc);
}

function handleContextMenuAction(action, msgData, messageEl) {
    switch (action) {
        case 'reply':
            setReplyToFromId(msgData.id);
            break;
        case 'pin':
            if (typeof pinCurrentMessage === 'function') {
                // 메시지 내용 복호화
                var content = msgData.content;
                if (typeof currentRoomKey !== 'undefined' && currentRoomKey && msgData.encrypted) {
                    content = E2E.decrypt(msgData.content, currentRoomKey) || msgData.content;
                }
                pinCurrentMessage(msgData.id, content);
            }
            break;
        case 'reaction':
            var reactBtn = messageEl.querySelector('.message-action-btn[title="리액션"]');
            if (reactBtn) {
                showReactionPicker(msgData.id, reactBtn);
            } else {
                showReactionPicker(msgData.id, messageEl);
            }
            break;
        case 'edit':
            editMessage(msgData.id);
            break;
        case 'delete':
            deleteMessage(msgData.id);
            break;
    }
}

/**
 * 메시지 컨텍스트 메뉴 초기화
 * messagesContainer에 이벤트 위임으로 처리
 */
function initMessageContextMenu() {
    var messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    // 이미 초기화되었는지 확인
    if (messagesContainer._contextMenuInitialized) return;
    messagesContainer._contextMenuInitialized = true;

    messagesContainer.addEventListener('contextmenu', function (e) {
        var messageEl = e.target.closest('.message:not(.system)');
        if (messageEl) {
            showMessageContextMenu(e, messageEl);
        }
    });
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
window.cleanupLazyDecryptObserver = cleanupLazyDecryptObserver;
window.initEmojiPicker = initEmojiPicker;
window.setupDragDrop = setupDragDrop;
window.uploadFile = uploadFile;
// [v4.35] 메시지 컨텍스트 메뉴
window.initMessageContextMenu = initMessageContextMenu;
window.showMessageContextMenu = showMessageContextMenu;
window.closeMessageContextMenu = closeMessageContextMenu;

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

    // [v4.36] Null safety checks
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

// [v4.31] LazyLoadObserver 정리 함수
// [v4.32] 상태 변수 초기화 추가 (메모리 누수 및 stale state 방지)
function cleanupLazyLoadObserver() {
    if (lazyLoadObserver) {
        lazyLoadObserver.disconnect();
        lazyLoadObserver = null;
    }
    isLoadingOlderMessages = false;
    hasMoreOlderMessages = true;
    oldestMessageId = null;
}
window.cleanupLazyLoadObserver = cleanupLazyLoadObserver;

// DOMContentLoaded에서 입력창 개선 초기화
document.addEventListener('DOMContentLoaded', function () {
    initInputEnhancements();
    // [v4.34] 모바일인 경우 스와이프 답장 및 사이드바 초기화
    if (window.innerWidth <= 768) {
        initMobileSwipeReply();
        initMobileSidebar();
    }
});

// ============================================================================
// [v4.34] 모바일 스와이프 답장
// ============================================================================

var touchStartX = 0;
var touchStartY = 0;
var swipeThreshold = 80;
var currentSwipingMessage = null;

/**
 * [v4.34] 모바일 스와이프 답장 초기화
 */
function initMobileSwipeReply() {
    var messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    messagesContainer.addEventListener('touchstart', handleTouchStart, { passive: true });
    messagesContainer.addEventListener('touchmove', handleTouchMove, { passive: false });
    messagesContainer.addEventListener('touchend', handleTouchEnd, { passive: true });
}

function handleTouchStart(e) {
    var message = e.target.closest('.message:not(.system)');
    if (!message) return;

    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    currentSwipingMessage = message;

    // 스와이프 인디케이터 추가 (없으면)
    if (!message.querySelector('.swipe-reply-indicator')) {
        var indicator = document.createElement('div');
        indicator.className = 'swipe-reply-indicator';
        indicator.textContent = '↩';
        message.appendChild(indicator);
    }
}

function handleTouchMove(e) {
    if (!currentSwipingMessage) return;

    var touchX = e.touches[0].clientX;
    var touchY = e.touches[0].clientY;
    var deltaX = touchX - touchStartX;
    var deltaY = touchY - touchStartY;

    // 세로 스크롤이 더 크면 스와이프 취소
    if (Math.abs(deltaY) > Math.abs(deltaX)) {
        cancelSwipe();
        return;
    }

    // 보낸 메시지는 왼쪽으로, 받은 메시지는 오른쪽으로만 스와이프
    var isSent = currentSwipingMessage.classList.contains('sent');
    var validSwipe = (isSent && deltaX < 0) || (!isSent && deltaX > 0);

    if (validSwipe && Math.abs(deltaX) > 10) {
        e.preventDefault();
        currentSwipingMessage.classList.add('swiping');

        var maxSwipe = swipeThreshold + 20;
        var swipeAmount = Math.min(Math.abs(deltaX), maxSwipe);
        var direction = deltaX > 0 ? 1 : -1;

        currentSwipingMessage.style.transform = 'translateX(' + (direction * swipeAmount) + 'px)';
    }
}

function handleTouchEnd(e) {
    if (!currentSwipingMessage) return;

    var finalTransform = currentSwipingMessage.style.transform;
    var translateMatch = finalTransform.match(/translateX\(([-\d.]+)px\)/);
    var swipeDistance = translateMatch ? Math.abs(parseFloat(translateMatch[1])) : 0;

    if (swipeDistance >= swipeThreshold) {
        // 답장 설정
        if (currentSwipingMessage._messageData) {
            setReplyToFromId(currentSwipingMessage._messageData.id);
            // 햅틱 피드백 (지원시)
            if (navigator.vibrate) {
                navigator.vibrate(30);
            }
        }
    }

    cancelSwipe();
}

function cancelSwipe() {
    if (currentSwipingMessage) {
        currentSwipingMessage.classList.remove('swiping');
        currentSwipingMessage.style.transform = '';
    }
    currentSwipingMessage = null;
    touchStartX = 0;
    touchStartY = 0;
}

// ============================================================================
// [v4.34] 모바일 사이드바 토글
// ============================================================================

/**
 * [v4.34] 모바일 사이드바 초기화
 */
function initMobileSidebar() {
    // 오버레이가 없으면 생성
    var overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }

    // 오버레이 클릭시 사이드바 닫기
    overlay.addEventListener('click', closeMobileSidebar);
}

/**
 * 모바일 사이드바 열기
 */
function openMobileSidebar() {
    var sidebar = document.querySelector('.sidebar');
    var overlay = document.querySelector('.sidebar-overlay');

    if (sidebar) sidebar.classList.add('open');
    if (overlay) overlay.classList.add('active');

    document.body.style.overflow = 'hidden';
}

/**
 * 모바일 사이드바 닫기
 */
function closeMobileSidebar() {
    var sidebar = document.querySelector('.sidebar');
    var overlay = document.querySelector('.sidebar-overlay');

    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');

    document.body.style.overflow = '';
}

/**
 * 모바일 사이드바 토글
 */
function toggleMobileSidebar() {
    var sidebar = document.querySelector('.sidebar');
    if (sidebar && sidebar.classList.contains('open')) {
        closeMobileSidebar();
    } else {
        openMobileSidebar();
    }
}

// 전역 노출
window.initMobileSwipeReply = initMobileSwipeReply;
window.initMobileSidebar = initMobileSidebar;
window.openMobileSidebar = openMobileSidebar;
window.closeMobileSidebar = closeMobileSidebar;
window.toggleMobileSidebar = toggleMobileSidebar;
