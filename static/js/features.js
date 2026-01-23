/**
 * 추가 기능 모듈
 * 투표, 파일 저장소, 공지사항, 검색, 라이트박스 등 부가 기능
 */

// ============================================================================
// 이미지 라이트박스
// ============================================================================
var lightboxImages = [];
var currentImageIndex = 0;

/**
 * 라이트박스 열기
 * @param {string} imageSrc - 이미지 소스
 */
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

/**
 * 라이트박스 닫기
 */
function closeLightbox() {
    var lightbox = document.getElementById('lightbox');
    if (lightbox) lightbox.classList.remove('active');
    document.removeEventListener('keydown', handleLightboxKeydown);
}

/**
 * 이전 이미지
 */
function prevImage() {
    if (lightboxImages.length === 0) return;
    currentImageIndex = (currentImageIndex - 1 + lightboxImages.length) % lightboxImages.length;
    var img = document.getElementById('lightboxImage');
    if (img) img.src = lightboxImages[currentImageIndex];
}

/**
 * 다음 이미지
 */
function nextImage() {
    if (lightboxImages.length === 0) return;
    currentImageIndex = (currentImageIndex + 1) % lightboxImages.length;
    var img = document.getElementById('lightboxImage');
    if (img) img.src = lightboxImages[currentImageIndex];
}

/**
 * 라이트박스 키보드 이벤트
 */
function handleLightboxKeydown(e) {
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowLeft') prevImage();
    else if (e.key === 'ArrowRight') nextImage();
}

// ============================================================================
// 투표 시스템
// ============================================================================

/**
 * 투표 모달 열기
 */
function openPollModal() {
    var pollModal = $('pollModal');
    var pollQuestion = $('pollQuestion');
    var pollOptions = $('pollOptions');
    var pollMultiple = $('pollMultiple');
    var pollAnonymous = $('pollAnonymous');

    if (!pollModal) return;
    pollModal.classList.add('active');

    if (pollQuestion) pollQuestion.value = '';
    if (pollOptions) {
        pollOptions.innerHTML =
            '<div class="poll-option-input"><input type="text" placeholder="옵션 1" maxlength="100"></div>' +
            '<div class="poll-option-input"><input type="text" placeholder="옵션 2" maxlength="100"></div>';
    }
    if (pollMultiple) pollMultiple.checked = false;
    if (pollAnonymous) pollAnonymous.checked = false;
}

/**
 * 투표 생성
 */
async function createPoll() {
    if (!currentRoom) return;

    var questionEl = $('pollQuestion');
    var optionsEl = $('pollOptions');
    var multipleEl = $('pollMultiple');
    var anonymousEl = $('pollAnonymous');

    if (!questionEl || !optionsEl) return;

    var question = questionEl.value.trim();
    var optionInputs = optionsEl.querySelectorAll('input');
    var options = Array.from(optionInputs).map(function (i) { return i.value.trim(); }).filter(function (v) { return v; });
    var multipleChoice = multipleEl ? multipleEl.checked : false;
    var anonymous = anonymousEl ? anonymousEl.checked : false;

    if (!question) {
        showToast('질문을 입력해주세요.', 'warning');
        return;
    }
    if (options.length < 2) {
        showToast('최소 2개의 옵션이 필요합니다.', 'warning');
        return;
    }

    // [v4.32] 중복 옵션 검사
    var uniqueOptions = options.filter(function (v, i, self) { return self.indexOf(v) === i; });
    if (uniqueOptions.length !== options.length) {
        showToast('중복된 옵션이 있습니다.', 'warning');
        return;
    }
    options = uniqueOptions;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/polls', {
            method: 'POST',
            body: JSON.stringify({ question: question, options: options, multiple_choice: multipleChoice, anonymous: anonymous })
        });
        if (result.success) {
            showToast('투표가 생성되었습니다.', 'success');
            $('pollModal').classList.remove('active');
            if (typeof socket !== 'undefined' && socket && socket.connected) {
                safeSocketEmit('poll_created', { room_id: currentRoom.id, poll: result.poll });
            }
            loadRoomPolls();
        }
    } catch (e) {
        showToast('투표 생성에 실패했습니다.', 'error');
    }
}

/**
 * 투표하기
 */
async function votePoll(pollId, optionId) {
    try {
        var result = await api('/api/polls/' + pollId + '/vote', {
            method: 'POST',
            body: JSON.stringify({ option_id: optionId })
        });
        if (result.success) {
            updatePollDisplay(result.poll);
            if (typeof socket !== 'undefined' && socket && socket.connected) {
                safeSocketEmit('poll_updated', { room_id: currentRoom.id, poll: result.poll });
            }
        }
    } catch (e) {
        showToast('투표에 실패했습니다.', 'error');
    }
}

/**
 * 투표 UI 업데이트
 */
function updatePollDisplay(poll) {
    var pollEl = document.querySelector('[data-poll-id="' + poll.id + '"]');
    if (!pollEl) return;

    var totalVotes = poll.options.reduce(function (sum, o) { return sum + o.vote_count; }, 0);

    poll.options.forEach(function (opt) {
        var optEl = pollEl.querySelector('[data-option-id="' + opt.id + '"]');
        if (optEl) {
            var percent = totalVotes > 0 ? Math.round((opt.vote_count / totalVotes) * 100) : 0;
            optEl.querySelector('.poll-option-progress').style.width = percent + '%';
            optEl.querySelector('.poll-option-percent').textContent = percent + '%';
            optEl.classList.toggle('selected', poll.my_votes && poll.my_votes.includes(opt.id));
        }
    });
}

/**
 * 투표 종료
 */
async function closePoll(pollId) {
    if (!currentRoom) return;
    if (!confirm('이 투표를 종료하시겠습니까?')) return;

    try {
        var result = await api('/api/polls/' + pollId + '/close', { method: 'POST' });
        if (result.success) {
            showToast('투표가 종료되었습니다.', 'success');
            loadRoomPolls();
        } else {
            showToast(result.error || '투표 종료 실패', 'error');
        }
    } catch (e) {
        showToast('투표 종료에 실패했습니다.', 'error');
    }
}

/**
 * 대화방 투표 목록 로드
 */
async function loadRoomPolls() {
    if (!currentRoom) return;
    try {
        var polls = await api('/api/rooms/' + currentRoom.id + '/polls');
        renderPollList(polls);
    } catch (e) {
        console.error('Load polls error:', e);
        if (typeof showToast === 'function') {
            showToast('투표 목록을 불러올 수 없습니다.', 'error');
        }
    }
}

/**
 * 투표 목록 렌더링
 */
function renderPollList(polls) {
    var messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;

    // 기존 투표 요소 제거
    messagesContainer.querySelectorAll('.poll-message').forEach(function (el) {
        el.remove();
    });

    if (!polls || polls.length === 0) return;

    polls.forEach(function (poll) {
        var pollEl = createPollElement(poll);
        if (pollEl) {
            // 투표를 메시지 영역 상단에 표시
            messagesContainer.insertBefore(pollEl, messagesContainer.firstChild);
        }
    });
}

/**
 * 투표 요소 생성
 * [v4.31] 마감시간 UI 추가
 */
function createPollElement(poll) {
    var div = document.createElement('div');
    div.className = 'message poll-message';
    div.dataset.pollId = poll.id;

    var totalVotes = poll.options.reduce(function (sum, o) { return sum + (o.vote_count || 0); }, 0);
    var isClosed = poll.is_closed || poll.status === 'closed';
    var isCreator = currentUser && poll.creator_id === currentUser.id;

    var statusBadge = isClosed
        ? '<span class="poll-status closed">종료됨</span>'
        : '<span class="poll-status active">진행중</span>';

    // [v4.31] 마감시간 표시
    var deadlineHtml = '';
    if (poll.ends_at && !isClosed) {
        var endsAt = new Date(poll.ends_at);
        var now = new Date();
        var diffMs = endsAt - now;

        if (diffMs > 0) {
            var diffHours = Math.floor(diffMs / (1000 * 60 * 60));
            var diffDays = Math.floor(diffHours / 24);

            var timeText;
            if (diffDays > 0) {
                timeText = diffDays + '일 후 마감';
            } else if (diffHours > 0) {
                timeText = diffHours + '시간 후 마감';
            } else {
                var diffMinutes = Math.floor(diffMs / (1000 * 60));
                timeText = diffMinutes + '분 후 마감';
            }
            deadlineHtml = '<span class="poll-deadline">⏰ ' + timeText + '</span>';
        } else {
            deadlineHtml = '<span class="poll-deadline expired">⏰ 마감됨</span>';
        }
    }

    var optionsHtml = poll.options.map(function (opt) {
        var percent = totalVotes > 0 ? Math.round((opt.vote_count || 0) / totalVotes * 100) : 0;
        var isSelected = poll.my_votes && poll.my_votes.includes(opt.id);
        var selectedClass = isSelected ? ' selected' : '';
        var clickHandler = isClosed ? '' : ' onclick="votePoll(' + poll.id + ', ' + opt.id + ')"';

        return '<div class="poll-option' + selectedClass + '" data-option-id="' + opt.id + '"' + clickHandler + '>' +
            '<div class="poll-option-text">' + escapeHtml(opt.text || opt.option_text) + '</div>' +
            '<div class="poll-option-bar">' +
            '<div class="poll-option-progress" style="width:' + percent + '%"></div>' +
            '</div>' +
            '<div class="poll-option-percent">' + percent + '% (' + (opt.vote_count || 0) + ')</div>' +
            '</div>';
    }).join('');

    var closeBtn = (!isClosed && isCreator)
        ? '<button class="btn btn-sm btn-secondary" onclick="closePoll(' + poll.id + ')">투표 종료</button>'
        : '';

    div.innerHTML =
        '<div class="message-content poll-content">' +
        '<div class="poll-header">' +
        '<span class="poll-icon">📊</span>' +
        '<span class="poll-title">' + escapeHtml(poll.question) + '</span>' +
        statusBadge +
        deadlineHtml +
        '</div>' +
        '<div class="poll-options">' + optionsHtml + '</div>' +
        '<div class="poll-footer">' +
        '<span class="poll-total">총 ' + totalVotes + '표</span>' +
        closeBtn +
        '</div>' +
        '</div>';

    return div;
}

// ============================================================================
// 파일 저장소
// ============================================================================

/**
 * 파일 모달 열기
 */
async function openFilesModal() {
    if (!currentRoom) return;
    var filesModal = $('filesModal');
    if (!filesModal) return;
    filesModal.classList.add('active');
    loadRoomFiles();
}

/**
 * 대화방 파일 목록 로드
 */
async function loadRoomFiles(fileType) {
    fileType = fileType || '';
    if (!currentRoom) return;
    try {
        var url = '/api/rooms/' + currentRoom.id + '/files';
        if (fileType) url += '?type=' + fileType;
        var files = await api(url);
        renderFileList(files);
    } catch (e) {
        console.error('Load files error:', e);
    }
}

/**
 * 파일 목록 렌더링
 */
function renderFileList(files) {
    var container = $('fileStorageList');
    if (!container) return;

    if (!files || files.length === 0) {
        container.innerHTML = '<div class="empty-files">파일이 없습니다</div>';
        return;
    }

    container.innerHTML = files.map(function (file) {
        var isImage = file.file_type && file.file_type.startsWith('image');
        var safePath = encodeURIComponent(file.file_path || '');
        var icon = isImage ? '<img src="/uploads/' + safePath + '" alt="">' : '📄';
        return '<div class="file-item" data-file-id="' + file.id + '">' +
            '<div class="file-item-icon">' + icon + '</div>' +
            '<div class="file-item-info">' +
            '<div class="file-item-name">' + escapeHtml(file.file_name) + '</div>' +
            '<div class="file-item-meta">' + escapeHtml(file.uploader_name || '알 수 없음') + ' · ' + formatDate(file.uploaded_at) + '</div>' +
            '</div>' +
            '<div class="file-item-actions">' +
            '<a href="/uploads/' + safePath + '" download class="icon-btn" title="다운로드">⬇️</a>' +
            '<button class="icon-btn" onclick="deleteFile(' + file.id + ')" title="삭제">🗑️</button>' +
            '</div>' +
            '</div>';
    }).join('');
}

/**
 * 파일 삭제
 */
async function deleteFile(fileId) {
    if (!currentRoom) return;
    if (!confirm('이 파일을 삭제하시겠습니까?')) return;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/files/' + fileId, { method: 'DELETE' });
        if (result.success) {
            showToast('파일이 삭제되었습니다.', 'success');
            loadRoomFiles();
        } else {
            showToast(result.error || '파일 삭제 실패', 'error');
        }
    } catch (e) {
        showToast('파일 삭제에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 공지사항 시스템
// ============================================================================
var currentPins = [];

/**
 * 공지사항 로드
 */
async function loadPinnedMessages() {
    if (!currentRoom) return;
    try {
        var pins = await api('/api/rooms/' + currentRoom.id + '/pins');
        currentPins = pins;
        updatePinnedBanner();
    } catch (e) {
        console.error('Load pins error:', e);
    }
}

/**
 * 공지 배너 업데이트
 */
function updatePinnedBanner() {
    var banner = $('pinnedBanner');
    var content = $('pinnedContent');
    if (!banner || !content) return;

    if (currentPins.length > 0) {
        var latestPin = currentPins[0];
        content.textContent = latestPin.content || latestPin.message_content || '공지사항';
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
    }
}

/**
 * 메시지를 공지로 고정
 */
async function pinCurrentMessage(messageId, content) {
    if (!currentRoom) return;
    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/pins', {
            method: 'POST',
            body: JSON.stringify({ message_id: messageId, content: content })
        });
        if (result.success) {
            showToast('공지로 고정되었습니다.', 'success');
            loadPinnedMessages();
            if (typeof socket !== 'undefined' && socket && socket.connected) {
                safeSocketEmit('pin_updated', { room_id: currentRoom.id });
            }
        }
    } catch (e) {
        showToast('공지 고정에 실패했습니다.', 'error');
    }
}

/**
 * 공지 삭제
 */
async function deletePin(pinId) {
    if (!currentRoom) return;
    if (!confirm('이 공지를 삭제하시겠습니까?')) return;

    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/pins/' + pinId, { method: 'DELETE' });
        if (result.success) {
            showToast('공지가 삭제되었습니다.', 'success');
            loadPinnedMessages();
            if (typeof socket !== 'undefined' && socket && socket.connected) {
                safeSocketEmit('pin_updated', { room_id: currentRoom.id });
            }
        } else {
            showToast(result.error || '공지 삭제 실패', 'error');
        }
    } catch (e) {
        showToast('공지 삭제에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 관리자 설정
// ============================================================================
var isCurrentUserAdmin = false;

/**
 * 관리자 상태 확인
 */
async function checkAdminStatus() {
    if (!currentRoom) return;
    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/admin-check');
        isCurrentUserAdmin = result.is_admin;
        updateAdminUI();
    } catch (e) {
        isCurrentUserAdmin = false;
    }
}

/**
 * 관리자 UI 업데이트
 */
function updateAdminUI() {
    var adminBtn = $('adminSettingsBtn');
    if (adminBtn) {
        adminBtn.style.display = isCurrentUserAdmin ? 'flex' : 'none';
    }
}

/**
 * 관리자 모달 열기
 */
async function openAdminModal() {
    if (!currentRoom || !isCurrentUserAdmin) return;
    $('adminModal').classList.add('active');
    await loadAdminMemberList();
}

/**
 * 관리자 멤버 목록 로드
 */
async function loadAdminMemberList() {
    try {
        var roomInfo = await api('/api/rooms/' + currentRoom.id + '/info');
        var admins = await api('/api/rooms/' + currentRoom.id + '/admins');
        var adminIds = admins.map(function (a) { return a.id; });

        var container = $('adminMemberList');
        if (!container) return;

        container.innerHTML = roomInfo.members.map(function (m) {
            var isAdmin = adminIds.includes(m.id);
            return '<div class="user-item" style="display:flex; justify-content:space-between; align-items:center; padding:12px 0;">' +
                '<div style="display:flex; align-items:center; gap:12px;">' +
                createAvatarHtml(m.nickname, m.profile_image, m.id, 'user-item-avatar') +
                '<span>' + escapeHtml(m.nickname) + '</span>' +
                (isAdmin ? '<span class="admin-badge">👑 관리자</span>' : '') +
                '</div>' +
                '<button class="btn btn-sm ' + (isAdmin ? 'btn-danger' : 'btn-secondary') + '" ' +
                'onclick="toggleAdmin(' + m.id + ', ' + !isAdmin + ')">' +
                (isAdmin ? '해제' : '지정') + '</button>' +
                '</div>';
        }).join('');
    } catch (e) {
        console.error('Admin list error:', e);
    }
}

/**
 * 관리자 권한 토글
 */
async function toggleAdmin(userId, makeAdmin) {
    try {
        var result = await api('/api/rooms/' + currentRoom.id + '/admins', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId, is_admin: makeAdmin })
        });
        if (result.success) {
            showToast(makeAdmin ? '관리자로 지정되었습니다.' : '관리자 권한이 해제되었습니다.', 'success');
            loadAdminMemberList();
            if (typeof socket !== 'undefined' && socket && socket.connected) {
                safeSocketEmit('admin_updated', { room_id: currentRoom.id });
            }
        }
    } catch (e) {
        showToast('관리자 설정에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 대화 내 검색 기능
// ============================================================================
var chatSearchMatches = [];
var chatSearchCurrentIndex = 0;

/**
 * 대화 내 검색 열기
 */
function openChatSearch() {
    var chatSearch = $('chatSearch');
    if (!chatSearch) {
        // 검색 바 동적 생성
        var container = document.querySelector('.chat-header');
        if (!container) return;

        chatSearch = document.createElement('div');
        chatSearch.id = 'chatSearch';
        chatSearch.className = 'chat-search-bar';
        chatSearch.innerHTML =
            '<input type="text" id="chatSearchInput" placeholder="대화 내 검색...">' +
            '<span id="chatSearchCount" class="chat-search-count"></span>' +
            '<button class="icon-btn" onclick="chatSearchPrev()">↑</button>' +
            '<button class="icon-btn" onclick="chatSearchNext()">↓</button>' +
            '<button class="icon-btn" onclick="closeChatSearch()">✕</button>';
        container.after(chatSearch);

        // 입력 이벤트
        var input = $('chatSearchInput');
        if (input) {
            input.oninput = debounce(doChatSearch, 300);
            input.onkeydown = function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if (e.shiftKey) chatSearchPrev();
                    else chatSearchNext();
                } else if (e.key === 'Escape') {
                    closeChatSearch();
                }
            };
        }
    }

    chatSearch.classList.add('active');
    $('chatSearchInput').focus();
}

/**
 * 대화 내 검색 닫기
 */
function closeChatSearch() {
    var chatSearch = $('chatSearch');
    if (chatSearch) chatSearch.classList.remove('active');

    // 하이라이트 제거
    document.querySelectorAll('.search-highlight').forEach(function (el) {
        el.classList.remove('search-highlight', 'search-highlight-current');
    });
    chatSearchMatches = [];
    chatSearchCurrentIndex = 0;
}

/**
 * 대화 내 검색 실행
 */
function doChatSearch() {
    var query = $('chatSearchInput').value.trim().toLowerCase();
    var countEl = $('chatSearchCount');

    // 기존 하이라이트 제거
    document.querySelectorAll('.search-highlight').forEach(function (el) {
        el.classList.remove('search-highlight', 'search-highlight-current');
    });

    chatSearchMatches = [];
    chatSearchCurrentIndex = 0;

    if (!query) {
        if (countEl) countEl.textContent = '';
        return;
    }

    // 메시지 검색
    document.querySelectorAll('.message').forEach(function (msgEl) {
        var bubble = msgEl.querySelector('.message-bubble');
        if (bubble && bubble.textContent.toLowerCase().includes(query)) {
            chatSearchMatches.push(msgEl);
            msgEl.classList.add('search-highlight');
        }
    });

    if (countEl) {
        countEl.textContent = chatSearchMatches.length > 0
            ? '1/' + chatSearchMatches.length
            : '결과 없음';
    }

    if (chatSearchMatches.length > 0) {
        highlightCurrentMatch();
    }
}

/**
 * 현재 검색 결과 하이라이트
 */
function highlightCurrentMatch() {
    // 이전 현재 하이라이트 제거
    document.querySelectorAll('.search-highlight-current').forEach(function (el) {
        el.classList.remove('search-highlight-current');
    });

    if (chatSearchMatches.length === 0) return;

    var current = chatSearchMatches[chatSearchCurrentIndex];
    current.classList.add('search-highlight-current');
    current.scrollIntoView({ behavior: 'smooth', block: 'center' });

    var countEl = $('chatSearchCount');
    if (countEl) {
        countEl.textContent = (chatSearchCurrentIndex + 1) + '/' + chatSearchMatches.length;
    }
}

/**
 * 다음 검색 결과
 */
function chatSearchNext() {
    if (chatSearchMatches.length === 0) return;
    chatSearchCurrentIndex = (chatSearchCurrentIndex + 1) % chatSearchMatches.length;
    highlightCurrentMatch();
}

/**
 * 이전 검색 결과
 */
function chatSearchPrev() {
    if (chatSearchMatches.length === 0) return;
    chatSearchCurrentIndex = (chatSearchCurrentIndex - 1 + chatSearchMatches.length) % chatSearchMatches.length;
    highlightCurrentMatch();
}

// ============================================================================
// 고급 검색
// ============================================================================

// [v4.32] 검색 페이지네이션 상태
var advSearchPage = 0;
var advSearchLimit = 20;
var advSearchHasMore = false;
var advSearchLastParams = null;

/**
 * 고급 검색 모달 열기
 */
function openAdvancedSearch() {
    var advSearchModal = $('advancedSearchModal');
    if (!advSearchModal) return;
    advSearchModal.classList.add('active');

    var advSearchQuery = $('advSearchQuery');
    var advSearchDateFrom = $('advSearchDateFrom');
    var advSearchDateTo = $('advSearchDateTo');
    var advSearchFileOnly = $('advSearchFileOnly');
    var advSearchResults = $('advancedSearchResults');

    if (advSearchQuery) advSearchQuery.value = '';
    if (advSearchDateFrom) advSearchDateFrom.value = '';
    if (advSearchDateTo) advSearchDateTo.value = '';
    if (advSearchFileOnly) advSearchFileOnly.checked = false;
    if (advSearchResults) advSearchResults.innerHTML = '';

    // [v4.32] 페이지네이션 상태 초기화
    advSearchPage = 0;
    advSearchHasMore = false;
    advSearchLastParams = null;
}

/**
 * 고급 검색 실행
 * [v4.32] 페이지네이션 지원 추가
 */
async function doAdvancedSearch(loadMore) {
    loadMore = loadMore || false;

    var advSearchQuery = $('advSearchQuery');
    var advSearchDateFrom = $('advSearchDateFrom');
    var advSearchDateTo = $('advSearchDateTo');
    var advSearchFileOnly = $('advSearchFileOnly');

    var query = advSearchQuery ? advSearchQuery.value.trim() : '';
    var dateFrom = advSearchDateFrom ? advSearchDateFrom.value : '';
    var dateTo = advSearchDateTo ? advSearchDateTo.value : '';
    var fileOnly = advSearchFileOnly ? advSearchFileOnly.checked : false;

    // [v4.32] 검색 조건 유효성 검사 (백엔드와 일치)
    if (!loadMore && !query && !dateFrom && !dateTo && !fileOnly) {
        showToast('검색어를 입력하거나 필터를 선택해주세요.', 'warning');
        return;
    }
    if (query && query.length < 2) {
        showToast('검색어는 2자 이상 입력해주세요.', 'warning');
        return;
    }

    var params = new URLSearchParams();
    if (query) params.append('q', query);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (fileOnly) params.append('file_only', '1');
    if (currentRoom) params.append('room_id', currentRoom.id);

    // [v4.32] 페이지네이션
    if (loadMore && advSearchLastParams) {
        advSearchPage++;
    } else {
        advSearchPage = 0;
        advSearchLastParams = params.toString();
    }
    params.append('offset', advSearchPage * advSearchLimit);
    params.append('limit', advSearchLimit);

    try {
        var results = await api('/api/search?' + params.toString());
        advSearchHasMore = results && results.length >= advSearchLimit;
        renderAdvancedSearchResults(results, loadMore);
    } catch (e) {
        console.error('Search error:', e);
        showToast('검색에 실패했습니다.', 'error');
    }
}

/**
 * 고급 검색 결과 렌더링
 * [v4.32] 페이지네이션 지원 및 접근성 개선
 */
function renderAdvancedSearchResults(results, append) {
    var container = $('advancedSearchResults');
    if (!container) return;

    if (!results || results.length === 0) {
        if (!append) {
            container.innerHTML = '<div class="empty-results" role="status">검색 결과가 없습니다</div>';
        }
        return;
    }

    // [v4.32] 기존 "더 보기" 버튼 제거
    var existingLoadMore = container.querySelector('.load-more-btn');
    if (existingLoadMore) existingLoadMore.remove();

    var resultsHtml = results.map(function (r) {
        return '<div class="search-result-item" role="listitem" tabindex="0" onclick="goToMessage(' + r.room_id + ', ' + r.id + ')" onkeydown="if(event.key===\'Enter\')goToMessage(' + r.room_id + ', ' + r.id + ')">' +
            '<div class="search-result-sender">' + escapeHtml(r.sender_name || '알 수 없음') + '</div>' +
            '<div class="search-result-content">' + escapeHtml(r.content) + '</div>' +
            '<div class="search-result-time">' + formatTime(r.created_at) + '</div>' +
            '</div>';
    }).join('');

    if (append) {
        container.insertAdjacentHTML('beforeend', resultsHtml);
    } else {
        container.innerHTML = resultsHtml;
        container.setAttribute('role', 'list');
        container.setAttribute('aria-label', '검색 결과');
    }

    // [v4.32] "더 보기" 버튼 추가
    if (advSearchHasMore) {
        var loadMoreBtn = document.createElement('button');
        loadMoreBtn.className = 'load-more-btn btn btn-secondary';
        loadMoreBtn.textContent = '더 보기';
        loadMoreBtn.setAttribute('aria-label', '검색 결과 더 보기');
        loadMoreBtn.onclick = function () { doAdvancedSearch(true); };
        container.appendChild(loadMoreBtn);
    }
}

/**
 * 검색 결과 메시지로 이동
 */
async function goToMessage(roomId, messageId) {
    $('advancedSearchModal').classList.remove('active');

    // 해당 방으로 이동
    if (typeof rooms !== 'undefined') {
        var room = rooms.find(function (r) { return r.id === roomId; });
        if (room && typeof openRoom === 'function') {
            await openRoom(room);
            setTimeout(function () {
                if (typeof scrollToMessage === 'function') {
                    scrollToMessage(messageId);
                }
            }, 500);
        }
    }
}

// ============================================================================
// 오프라인 상태 감지 및 배너
// ============================================================================
var offlineBanner = null;
var isOnline = navigator.onLine;

/**
 * 오프라인 배너 초기화
 */
function initOfflineBanner() {
    window.addEventListener('online', function () {
        isOnline = true;
        if (offlineBanner) {
            offlineBanner.remove();
            offlineBanner = null;
        }
        showToast('인터넷 연결이 복구되었습니다.', 'success');
    });

    window.addEventListener('offline', function () {
        isOnline = false;
        if (!offlineBanner) {
            offlineBanner = document.createElement('div');
            offlineBanner.className = 'offline-banner';
            offlineBanner.innerHTML =
                '<span>⚠️ 오프라인 상태입니다</span>' +
                '<button class="btn btn-sm" onclick="retryConnection()">다시 시도</button>';
            document.body.prepend(offlineBanner);
        }
    });
}

/**
 * 연결 재시도
 */
function retryConnection() {
    if (navigator.onLine) {
        if (offlineBanner) {
            offlineBanner.remove();
            offlineBanner = null;
        }
        if (typeof socket !== 'undefined' && socket) {
            socket.connect();
        }
    } else {
        showToast('아직 오프라인 상태입니다.', 'warning');
    }
}

// 초기화
initOfflineBanner();

/**
 * 방 진입 시 V4 기능 초기화
 */
function initRoomV4Features() {
    loadRoomPolls();
    loadPinnedMessages();
    checkAdminStatus();
}

// ============================================================================
// 전역 노출
// ============================================================================
window.initRoomV4Features = initRoomV4Features;
window.openLightbox = openLightbox;
window.closeLightbox = closeLightbox;
window.prevImage = prevImage;
window.nextImage = nextImage;

window.openPollModal = openPollModal;
window.createPoll = createPoll;
window.votePoll = votePoll;
window.loadRoomPolls = loadRoomPolls;
window.closePoll = closePoll;

window.openFilesModal = openFilesModal;
window.loadRoomFiles = loadRoomFiles;
window.deleteFile = deleteFile;

window.loadPinnedMessages = loadPinnedMessages;
window.pinCurrentMessage = pinCurrentMessage;
window.deletePin = deletePin;

window.checkAdminStatus = checkAdminStatus;
window.openAdminModal = openAdminModal;
window.toggleAdmin = toggleAdmin;

window.openChatSearch = openChatSearch;
window.closeChatSearch = closeChatSearch;
window.chatSearchNext = chatSearchNext;
window.chatSearchPrev = chatSearchPrev;

window.openAdvancedSearch = openAdvancedSearch;
window.doAdvancedSearch = doAdvancedSearch;
window.goToMessage = goToMessage;

window.retryConnection = retryConnection;

// ============================================================================
// DOM 로드 후 이벤트 바인딩
// ============================================================================
document.addEventListener('DOMContentLoaded', function () {
    // 투표 옵션 추가 버튼
    var addPollOption = document.getElementById('addPollOption');
    if (addPollOption) {
        addPollOption.addEventListener('click', function () {
            var container = document.getElementById('pollOptions');
            var count = container.querySelectorAll('input').length;
            if (count >= 10) {
                if (typeof showToast === 'function') {
                    showToast('옵션은 최대 10개까지 가능합니다.', 'warning');
                }
                return;
            }
            var div = document.createElement('div');
            div.className = 'poll-option-input';
            div.innerHTML = '<input type="text" placeholder="옵션 ' + (count + 1) + '" maxlength="100">';
            container.appendChild(div);
        });
    }

    // 투표 생성 버튼
    var createPollBtn = document.getElementById('createPollBtn');
    if (createPollBtn) {
        createPollBtn.addEventListener('click', createPoll);
    }

    // 파일 필터 탭
    document.querySelectorAll('.file-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.file-tab').forEach(function (t) {
                t.classList.remove('active');
            });
            this.classList.add('active');
            loadRoomFiles(this.dataset.type);
        });
    });

    // 고급 검색 버튼
    var doAdvSearchBtn = document.getElementById('doAdvancedSearch');
    if (doAdvSearchBtn) {
        doAdvSearchBtn.addEventListener('click', doAdvancedSearch);
    }

    // 공지 배너 닫기 버튼
    var closePinBtn = document.getElementById('closePinnedBanner');
    if (closePinBtn) {
        closePinBtn.addEventListener('click', function () {
            var banner = document.getElementById('pinnedBanner');
            if (banner) banner.classList.add('hidden');
        });
    }
});
