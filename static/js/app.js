/**
 * 사내 메신저 v4.7 메인 애플리케이션 진입점
 * 모든 모듈이 로드된 후 초기화 및 이벤트 바인딩을 담당합니다.
 */

// DOM 요소 캐싱
const elements = {};

// DOMContentLoaded가 이미 발생했을 수 있으므로 readyState 체크
(function initOnLoad() {
    function doInit() {
        cacheElements();
        setupEventListeners();

        // 테마 초기화
        if (typeof initTheme === 'function') initTheme();

        // 세션 체크 (자동 로그인)
        if (typeof checkSession === 'function') checkSession();

        // 오프라인 배너 초기화 (features.js)
        if (typeof initOfflineBanner === 'function') initOfflineBanner();
    }

    if (document.readyState === 'loading') {
        // 아직 로딩 중이면 이벤트 대기
        document.addEventListener('DOMContentLoaded', doInit);
    } else {
        // 이미 로드 완료된 경우 즉시 실행
        doInit();
    }
})();

/**
 * 주요 DOM 요소 캐싱
 */
function cacheElements() {
    elements.messageInput = document.getElementById('messageInput');
    elements.sendBtn = document.getElementById('sendBtn');
    elements.emojiBtn = document.getElementById('emojiBtn');
    elements.emojiPicker = document.getElementById('emojiPicker');
    elements.messagesContainer = document.getElementById('messagesContainer');
    elements.roomList = document.getElementById('roomList');
    elements.searchInput = document.getElementById('searchInput');
    elements.profileModal = document.getElementById('profileModal');
    elements.inviteModal = document.getElementById('inviteModal');
    elements.newChatModal = document.getElementById('newChatModal');
    elements.createRoomBtn = document.getElementById('createRoomBtn');
    elements.adminModal = document.getElementById('adminModal');
    elements.pollModal = document.getElementById('pollModal');
    elements.filesModal = document.getElementById('filesModal');
    elements.fileInput = document.getElementById('fileInput');
    elements.logoutBtn = document.getElementById('logoutBtn');
}

/**
 * 이벤트 리스너 설정
 */
function setupEventListeners() {
    // =========================================================================
    // 인증 관련 이벤트 바인딩
    // =========================================================================
    var loginBtn = document.getElementById('loginBtn');
    var registerBtn = document.getElementById('registerBtn');
    var showRegister = document.getElementById('showRegister');
    var showLogin = document.getElementById('showLogin');
    var loginPassword = document.getElementById('loginPassword');
    var regNickname = document.getElementById('regNickname');
    var regPassword = document.getElementById('regPassword');

    // 로그인/회원가입 버튼
    if (loginBtn && typeof doLogin === 'function') {
        loginBtn.addEventListener('click', doLogin);
    }
    if (registerBtn && typeof doRegister === 'function') {
        registerBtn.addEventListener('click', doRegister);
    }

    // 폼 전환 링크
    if (showRegister && typeof showRegisterForm === 'function') {
        showRegister.addEventListener('click', showRegisterForm);
    }
    if (showLogin && typeof showLoginForm === 'function') {
        showLogin.addEventListener('click', showLoginForm);
    }

    // Enter 키로 로그인/회원가입
    if (loginPassword) {
        loginPassword.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && typeof doLogin === 'function') {
                doLogin();
            }
        });
    }
    if (regNickname) {
        regNickname.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && typeof doRegister === 'function') {
                doRegister();
            }
        });
    }
    if (regPassword) {
        regPassword.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && typeof doRegister === 'function') {
                doRegister();
            }
        });
    }

    // =========================================================================
    // 메시지 전송
    if (elements.sendBtn) {
        elements.sendBtn.addEventListener('click', function () {
            if (typeof sendMessage === 'function') sendMessage();
        });
    }

    if (elements.messageInput) {
        elements.messageInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (typeof sendMessage === 'function') sendMessage();
            }
        });

        // 타이핑 감지 및 리사이징 (messages.js)
        if (typeof handleTyping === 'function') {
            elements.messageInput.addEventListener('input', handleTyping);
        }
    }

    // 파일 업로드
    if (elements.fileInput && typeof handleFileUpload === 'function') {
        elements.fileInput.addEventListener('change', handleFileUpload);
    }

    // 이모지 피커 토글
    if (elements.emojiBtn && elements.emojiPicker) {
        elements.emojiBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            elements.emojiPicker.classList.toggle('hidden');
            if (typeof initEmojiPicker === 'function' && !elements.emojiPicker.classList.contains('hidden')) {
                initEmojiPicker();
            }
        });

        // 피커 닫기
        document.addEventListener('click', function (e) {
            if (!elements.emojiPicker.contains(e.target) && e.target !== elements.emojiBtn) {
                elements.emojiPicker.classList.add('hidden');
            }
        });
    }

    // 검색
    if (elements.searchInput && typeof handleSearch === 'function') {
        elements.searchInput.addEventListener('input', throttle(handleSearch, 300));
    }

    // 새 채팅방 모달 (모달 내부 버튼)
    if (elements.createRoomBtn && typeof createRoom === 'function') {
        elements.createRoomBtn.addEventListener('click', createRoom);
    }

    // =========================================================================
    // 사이드바 버튼들
    // =========================================================================

    // 새 채팅 버튼 (사이드바)
    var newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn && typeof openNewChatModal === 'function') {
        newChatBtn.addEventListener('click', openNewChatModal);
    }

    // 프로필 버튼 (사이드바)
    var profileBtn = document.getElementById('profileBtn');
    if (profileBtn && typeof openProfileModal === 'function') {
        profileBtn.addEventListener('click', openProfileModal);
    }

    // 사용자 아바타/이름 클릭 시 프로필 열기
    var userAvatar = document.getElementById('userAvatar');
    var userInfoClick = document.getElementById('userInfoClick');
    if (userAvatar && typeof openProfileModal === 'function') {
        userAvatar.addEventListener('click', openProfileModal);
    }
    if (userInfoClick && typeof openProfileModal === 'function') {
        userInfoClick.addEventListener('click', openProfileModal);
    }

    // 설정 버튼 (사이드바)
    var settingsBtn = document.getElementById('settingsBtn');
    var settingsModal = document.getElementById('settingsModal');
    if (settingsBtn && settingsModal) {
        settingsBtn.addEventListener('click', function () {
            settingsModal.classList.add('active');
        });
    }

    // 도움말 버튼 (사이드바)
    var helpBtn = document.getElementById('helpBtn');
    var helpModal = document.getElementById('helpModal');
    if (helpBtn && helpModal) {
        helpBtn.addEventListener('click', function () {
            helpModal.classList.add('active');
        });
    }

    // 로그아웃 버튼
    if (elements.logoutBtn && typeof logout === 'function') {
        elements.logoutBtn.addEventListener('click', logout);
    }

    // =========================================================================
    // 모달 닫기 버튼들
    // =========================================================================
    var modalCloseBindings = [
        { btn: 'closeNewChatModal', modal: 'newChatModal' },
        { btn: 'closeInviteModal', modal: 'inviteModal' },
        { btn: 'closeMembersModal', modal: 'membersModal' },
        { btn: 'closeMembersBtn', modal: 'membersModal' },
        { btn: 'closeProfileModal', modal: 'profileModal' },
        { btn: 'closeSettingsModal', modal: 'settingsModal' },
        { btn: 'closeSettingsBtn', modal: 'settingsModal' },
        { btn: 'closeHelpModal', modal: 'helpModal' },
        { btn: 'closeHelpBtn', modal: 'helpModal' },
        { btn: 'closePollModal', modal: 'pollModal' },
        { btn: 'closeFilesModal', modal: 'filesModal' },
        { btn: 'closeAdminModal', modal: 'adminModal' },
        { btn: 'closeAdvancedSearchModal', modal: 'advancedSearchModal' },
        { btn: 'closeNotificationSettingsModal', modal: 'notificationSettingsModal' }
    ];

    modalCloseBindings.forEach(function (binding) {
        var btn = document.getElementById(binding.btn);
        var modal = document.getElementById(binding.modal);
        if (btn && modal) {
            btn.addEventListener('click', function () {
                modal.classList.remove('active');
            });
        }
    });

    // =========================================================================
    // 채팅 헤더 버튼들
    // =========================================================================

    // 설정 드롭다운
    var roomSettingsBtn = document.getElementById('roomSettingsBtn');
    var roomSettingsMenu = document.getElementById('roomSettingsMenu');
    if (roomSettingsBtn && roomSettingsMenu) {
        roomSettingsBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            roomSettingsMenu.classList.toggle('active');
        });
        document.addEventListener('click', function (e) {
            if (!roomSettingsMenu.contains(e.target) && e.target !== roomSettingsBtn) {
                roomSettingsMenu.classList.remove('active');
            }
        });
    }

    // 드롭다운 메뉴 항목들
    var dropdownBindings = [
        { id: 'editRoomNameBtn', fn: 'editRoomName' },
        { id: 'pinRoomBtn', fn: 'togglePinRoom' },
        { id: 'muteRoomBtn', fn: 'toggleMuteRoom' },
        { id: 'viewMembersBtn', fn: 'viewMembers' },
        { id: 'createPollBtn2', fn: 'openPollModal' },
        { id: 'viewFilesBtn', fn: 'openFilesModal' },
        { id: 'viewPinsBtn', fn: 'loadPinnedMessages' },
        { id: 'adminSettingsBtn', fn: 'openAdminModal' }
    ];

    dropdownBindings.forEach(function (binding) {
        var el = document.getElementById(binding.id);
        if (el && typeof window[binding.fn] === 'function') {
            el.addEventListener('click', function () {
                window[binding.fn]();
            });
        }
    });

    // 초대 버튼
    var inviteBtn = document.getElementById('inviteBtn');
    if (inviteBtn && typeof openInviteModal === 'function') {
        inviteBtn.addEventListener('click', openInviteModal);
    }

    // 나가기 버튼
    var leaveRoomBtn = document.getElementById('leaveRoomBtn');
    if (leaveRoomBtn && typeof leaveRoom === 'function') {
        leaveRoomBtn.addEventListener('click', leaveRoom);
    }

    // 멤버 모달에서 나가기 버튼
    var leaveFromMembersBtn = document.getElementById('leaveFromMembersBtn');
    if (leaveFromMembersBtn && typeof leaveRoom === 'function') {
        leaveFromMembersBtn.addEventListener('click', function () {
            document.getElementById('membersModal').classList.remove('active');
            leaveRoom();
        });
    }

    // 초대 확인 버튼
    var confirmInviteBtn = document.getElementById('confirmInviteBtn');
    if (confirmInviteBtn && typeof confirmInvite === 'function') {
        confirmInviteBtn.addEventListener('click', confirmInvite);
    }

    // 첨부 버튼
    var attachBtn = document.getElementById('attachBtn');
    if (attachBtn && elements.fileInput) {
        attachBtn.addEventListener('click', function () {
            elements.fileInput.click();
        });
    }

    // 모바일 메뉴 버튼
    var mobileMenuBtn = document.getElementById('mobileMenuBtn');
    var sidebar = document.getElementById('sidebar');
    if (mobileMenuBtn && sidebar) {
        mobileMenuBtn.addEventListener('click', function () {
            sidebar.classList.toggle('active');
        });
    }

    // =========================================================================
    // 글로벌 단축키
    // =========================================================================
    document.addEventListener('keydown', function (e) {
        // ESC 키: 모달 닫기
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(function (m) {
                m.classList.remove('active');
            });
            if (typeof closeLightbox === 'function') closeLightbox();
            if (typeof closeChatSearch === 'function') closeChatSearch();
        }

        // Ctrl+K: 대화 검색
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            var searchInput = document.getElementById('searchInput');
            if (searchInput) searchInput.focus();
        }

        // Ctrl+N: 새 대화
        if (e.ctrlKey && e.key === 'n') {
            e.preventDefault();
            if (typeof openNewChatModal === 'function') openNewChatModal();
        }

        // Ctrl+F: 대화 내 검색
        if (e.ctrlKey && e.key === 'f' && currentRoom) {
            e.preventDefault();
            if (typeof openChatSearch === 'function') openChatSearch();
        }
    });

    // 드래그 앤 드롭 방지 (기본 브라우저 동작)
    window.addEventListener('dragover', function (e) { e.preventDefault(); }, false);
    window.addEventListener('drop', function (e) { e.preventDefault(); }, false);
}

/**
 * 애플리케이션 초기화 (로그인 후 호출됨)
 */
function initApp() {
    // UI 표시 전환
    document.getElementById('authContainer').classList.add('hidden');
    document.getElementById('appContainer').classList.add('active');

    if (typeof currentUser !== 'undefined' && currentUser) {
        if (typeof showToast === 'function') {
            showToast(currentUser.nickname + '님 환영합니다!');
        }

        // 사이드바 프로필 정보 업데이트
        var userName = document.getElementById('userName');
        var userAvatar = document.getElementById('userAvatar');

        if (userName) userName.textContent = currentUser.nickname;

        if (userAvatar) {
            if (currentUser.profile_image) {
                // [v4.22] XSS 방지: safeImagePath 사용
                var safePath = typeof safeImagePath === 'function' ? safeImagePath(currentUser.profile_image) : currentUser.profile_image;
                if (safePath) {
                    userAvatar.innerHTML = '<img src="/uploads/' + safePath + '" alt="프로필">';
                    userAvatar.classList.add('has-image');
                }
            } else {
                var initial = currentUser.nickname ? currentUser.nickname[0].toUpperCase() : '?';
                userAvatar.textContent = initial;
                userAvatar.classList.remove('has-image');
                if (typeof getUserColor === 'function') {
                    userAvatar.style.background = getUserColor(currentUser.id);
                }
            }
        }
    }

    // Socket.IO 연결 (socket-handlers.js)
    if (typeof initSocket === 'function') initSocket();

    // 데이터 로드 (rooms.js)
    if (typeof loadRooms === 'function') loadRooms();

    // 온라인 유저 폴링 시작 (rooms.js)
    if (typeof startOnlineUsersPolling === 'function') {
        startOnlineUsersPolling();
    } else if (typeof loadOnlineUsers === 'function') {
        loadOnlineUsers();
    }

    // [v4.30] 대화방 목록 이벤트 위임 초기화 (성능 최적화)
    if (typeof initRoomListEvents === 'function') initRoomListEvents();

    // 멘션 기능 초기화 (messages.js)
    if (typeof setupMention === 'function') setupMention();

    // 드래그 앤 드롭 초기화 (messages.js)
    if (typeof setupDragDrop === 'function') setupDragDrop();

    // 이모지 피커 초기화 (messages.js)
    if (typeof initEmojiPicker === 'function') initEmojiPicker();

    // [v4.35] 메시지 컨텍스트 메뉴 초기화 (messages.js)
    if (typeof initMessageContextMenu === 'function') initMessageContextMenu();

    // 스크롤 버튼 설정
    setupScrollToBottom();
}

/**
 * 스크롤 하단 바로가기 버튼 설정
 */
function setupScrollToBottom() {
    var scrollBtn = document.getElementById('scrollToBottomBtn');
    var messagesContainer = document.getElementById('messagesContainer');

    if (!scrollBtn || !messagesContainer) return;

    // 스크롤 위치에 따라 버튼 표시/숨김
    messagesContainer.addEventListener('scroll', function () {
        var isNearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 200;
        scrollBtn.classList.toggle('hidden', isNearBottom);
    });

    // 버튼 클릭 시 하단으로 스크롤
    scrollBtn.addEventListener('click', function () {
        messagesContainer.scrollTo({
            top: messagesContainer.scrollHeight,
            behavior: 'smooth'
        });
    });
}

// 전역 노출
window.initApp = initApp;
window.elements = elements;
window.setupScrollToBottom = setupScrollToBottom;
