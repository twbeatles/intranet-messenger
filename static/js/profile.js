/**
 * 프로필 관리 모듈
 * 사용자 프로필 조회/수정, 프로필 이미지 업로드/삭제
 */

// ============================================================================
// 프로필 모달
// ============================================================================

/**
 * 프로필 모달 열기
 */
function openProfileModal() {
    var profileModal = $('profileModal');
    if (!profileModal) return;
    profileModal.classList.add('active');

    // 현재 사용자 정보로 폼 채우기
    var profileNickname = $('profileNickname');
    var profileStatusMessage = $('profileStatusMessage');
    if (profileNickname) profileNickname.value = (currentUser && currentUser.nickname) || '';
    if (profileStatusMessage) profileStatusMessage.value = (currentUser && currentUser.status_message) || '';

    // 프로필 이미지 미리보기
    updateProfilePreview();
}

/**
 * 프로필 모달 닫기
 */
function closeProfileModal() {
    var profileModal = $('profileModal');
    if (profileModal) profileModal.classList.remove('active');
}


/**
 * 프로필 이미지 미리보기 업데이트
 */
function updateProfilePreview() {
    var preview = $('profileImagePreview');
    if (!preview) return;

    if (currentUser && currentUser.profile_image) {
        // [v4.21] XSS 방지: safeImagePath 사용
        var safePath = typeof safeImagePath === 'function' ? safeImagePath(currentUser.profile_image) : currentUser.profile_image;
        if (safePath) {
            preview.innerHTML = '<img src="/uploads/' + safePath + '" alt="프로필">';
            preview.classList.add('has-image');
        }
    } else {
        var displayName = (currentUser && currentUser.nickname) ? currentUser.nickname : '?';
        preview.innerHTML = '<span id="profileInitial">' + escapeHtml(displayName[0].toUpperCase()) + '</span>';
        preview.classList.remove('has-image');
        preview.style.background = getUserColor(currentUser ? currentUser.id : 0);
    }
}

// ============================================================================
// 프로필 저장
// ============================================================================

/**
 * 프로필 저장
 */
async function saveProfile() {
    var nicknameEl = $('profileNickname');
    var statusMessageEl = $('profileStatusMessage');

    if (!nicknameEl) return;

    var nickname = nicknameEl.value.trim();
    var statusMessage = statusMessageEl ? statusMessageEl.value.trim() : '';

    if (nickname && nickname.length < 2) {
        showToast('닉네임은 2자 이상이어야 합니다.', 'error');
        return;
    }

    try {
        var result = await api('/api/profile', {
            method: 'PUT',
            body: JSON.stringify({
                nickname: nickname || null,
                status_message: statusMessage || null
            })
        });

        if (result.success) {
            // 로컬 상태 업데이트
            if (nickname) {
                currentUser.nickname = nickname;
                var userNameEl = document.getElementById('userName');
                var userAvatarEl = document.getElementById('userAvatar');
                if (userNameEl) userNameEl.textContent = nickname;
                if (userAvatarEl && !currentUser.profile_image) {
                    userAvatarEl.textContent = nickname[0].toUpperCase();
                }
            }

            // [v4.21] 소켓으로 프로필 변경 알림 (safeSocketEmit 사용)
            if (typeof safeSocketEmit === 'function') {
                safeSocketEmit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: currentUser.profile_image
                });
            }

            showToast('프로필이 저장되었습니다.', 'success');
            closeProfileModal();

            // 대화방 목록 새로고침
            if (typeof throttledLoadRooms === 'function') {
                throttledLoadRooms();
            } else if (typeof loadRooms === 'function') {
                loadRooms();
            }
        } else {
            showToast(result.error || '저장 실패', 'error');
        }
    } catch (err) {
        console.error('프로필 저장 오류:', err);
        showToast('프로필 저장에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 프로필 이미지
// ============================================================================

/**
 * 프로필 이미지 업로드 처리
 * @param {Event} e - 파일 입력 이벤트
 */
async function handleProfileImageUpload(e) {
    var file = e.target.files[0];
    if (!file) return;

    // [v4.32] 이미지 파일 타입 검사
    var validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!validTypes.includes(file.type)) {
        showToast('JPG, PNG, GIF, WEBP 이미지만 업로드 가능합니다.', 'error');
        e.target.value = '';
        return;
    }

    // 파일 크기 체크 (5MB)
    if (file.size > 5 * 1024 * 1024) {
        showToast('이미지 크기는 5MB 이하여야 합니다.', 'error');
        return;
    }

    var formData = new FormData();
    formData.append('file', file);

    // CSRF 토큰 추가
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const headers = {};
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
    }

    try {
        var response = await fetch('/api/profile/image', {
            method: 'POST',
            headers: headers,
            body: formData
        });
        var result = await response.json();

        if (result.success) {
            currentUser.profile_image = result.profile_image;
            updateProfilePreview();

            // 사이드바 아바타도 업데이트
            var userAvatarEl = document.getElementById('userAvatar');
            if (userAvatarEl) {
                // [v4.21] XSS 방지: safeImagePath 사용
                var safePath = typeof safeImagePath === 'function' ? safeImagePath(result.profile_image) : result.profile_image;
                if (safePath) {
                    userAvatarEl.innerHTML = '<img src="/uploads/' + safePath + '" alt="프로필">';
                    userAvatarEl.classList.add('has-image');
                }
            }

            // [v4.21] 소켓으로 프로필 변경 알림 (safeSocketEmit 사용)
            if (typeof safeSocketEmit === 'function') {
                safeSocketEmit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: currentUser.profile_image
                });
            }

            showToast('프로필 사진이 업로드되었습니다.', 'success');
        } else {
            showToast(result.error || '업로드 실패', 'error');
        }
    } catch (err) {
        console.error('프로필 이미지 업로드 오류:', err);
        showToast('이미지 업로드에 실패했습니다.', 'error');
    }

    // 파일 입력 초기화
    e.target.value = '';
}

/**
 * 프로필 이미지 삭제
 */
async function deleteProfileImage() {
    if (!currentUser.profile_image) {
        showToast('삭제할 프로필 사진이 없습니다.', 'info');
        return;
    }

    if (!confirm('프로필 사진을 삭제하시겠습니까?')) return;

    try {
        var result = await api('/api/profile/image', { method: 'DELETE' });

        if (result.success) {
            currentUser.profile_image = null;
            updateProfilePreview();

            // 사이드바 아바타도 업데이트
            var userAvatarEl = document.getElementById('userAvatar');
            if (userAvatarEl) {
                userAvatarEl.innerHTML = (currentUser.nickname && currentUser.nickname.length > 0)
                    ? currentUser.nickname[0].toUpperCase()
                    : '?';
                userAvatarEl.classList.remove('has-image');
            }

            // [v4.21] 소켓으로 프로필 변경 알림 (safeSocketEmit 사용)
            if (typeof safeSocketEmit === 'function') {
                safeSocketEmit('profile_updated', {
                    nickname: currentUser.nickname,
                    profile_image: null
                });
            }

            showToast('프로필 사진이 삭제되었습니다.', 'success');
        } else {
            showToast(result.error || '삭제 실패', 'error');
        }
    } catch (err) {
        console.error('프로필 이미지 삭제 오류:', err);
        showToast('삭제에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 비밀번호 변경
// ============================================================================

/**
 * 비밀번호 변경
 */
async function changePassword() {
    var currentPwEl = $('currentPassword');
    var newPwEl = $('newPassword');
    var confirmPwEl = $('newPasswordConfirm');

    if (!currentPwEl || !newPwEl || !confirmPwEl) return;

    var currentPw = currentPwEl.value;
    var newPw = newPwEl.value;
    var confirmPw = confirmPwEl.value;

    if (!currentPw || !newPw || !confirmPw) {
        showToast('모든 필드를 입력해주세요.', 'warning');
        return;
    }

    if (newPw !== confirmPw) {
        showToast('새 비밀번호가 일치하지 않습니다.', 'error');
        return;
    }

    if (newPw.length < 8) {
        showToast('비밀번호는 8자 이상이어야 합니다.', 'error');
        return;
    }

    // [v4.32] 비밀번호 복잡도 검증 추가 (auth.js doRegister와 일치)
    if (!/[A-Za-z]/.test(newPw) || !/[0-9]/.test(newPw)) {
        showToast('비밀번호는 영문자와 숫자를 포함해야 합니다.', 'error');
        return;
    }

    try {
        var result = await api('/api/me/password', {
            method: 'PUT',
            body: JSON.stringify({
                current_password: currentPw,
                new_password: newPw
            })
        });

        if (result.success) {
            showToast('비밀번호가 변경되었습니다.', 'success');
            $('currentPassword').value = '';
            $('newPassword').value = '';
            $('newPasswordConfirm').value = '';
        } else {
            showToast(result.error || '비밀번호 변경 실패', 'error');
        }
    } catch (err) {
        console.error('비밀번호 변경 오류:', err);
        showToast('비밀번호 변경에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 회원 탈퇴
// ============================================================================

/**
 * 회원 탈퇴
 */
async function deleteAccount() {
    if (!confirm('정말 탈퇴하시겠습니까?\n\n⚠️ 이 작업은 되돌릴 수 없습니다.')) return;

    var password = prompt('탈퇴를 진행하려면 현재 비밀번호를 입력해주세요:');
    if (!password) {
        showToast('비밀번호를 입력해야 합니다.', 'warning');
        return;
    }

    try {
        var result = await api('/api/me', {
            method: 'DELETE',
            body: JSON.stringify({ password: password })
        });

        if (result.success) {
            showToast('회원 탈퇴가 완료되었습니다.', 'info');
            setTimeout(function () {
                window.location.reload();
            }, 1500);
        } else {
            showToast(result.error || '탈퇴 실패', 'error');
        }
    } catch (err) {
        console.error('회원 탈퇴 오류:', err);
        showToast('회원 탈퇴에 실패했습니다.', 'error');
    }
}

// ============================================================================
// 전역 노출
// ============================================================================
window.openProfileModal = openProfileModal;
window.closeProfileModal = closeProfileModal;
window.updateProfilePreview = updateProfilePreview;
window.saveProfile = saveProfile;
window.handleProfileImageUpload = handleProfileImageUpload;
window.deleteProfileImage = deleteProfileImage;
window.changePassword = changePassword;
window.deleteAccount = deleteAccount;

// ============================================================================
// DOM 로드 후 이벤트 바인딩
// ============================================================================
document.addEventListener('DOMContentLoaded', function () {
    // 프로필 이미지 변경 버튼
    var changeBtn = document.getElementById('changeProfileImageBtn');
    var inputFile = document.getElementById('profileImageInput');
    if (changeBtn && inputFile) {
        changeBtn.addEventListener('click', function () {
            inputFile.click();
        });
        inputFile.addEventListener('change', handleProfileImageUpload);
    }

    // 프로필 이미지 삭제 버튼
    var deleteBtn = document.getElementById('deleteProfileImageBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', deleteProfileImage);
    }

    // 프로필 저장 버튼
    var saveBtn = document.getElementById('saveProfileBtn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveProfile);
    }

    // 비밀번호 변경 버튼
    var changePwBtn = document.getElementById('changePasswordBtn');
    if (changePwBtn) {
        changePwBtn.addEventListener('click', changePassword);
    }

    // 회원 탈퇴 버튼
    var deleteAccBtn = document.getElementById('deleteAccountBtn');
    if (deleteAccBtn) {
        deleteAccBtn.addEventListener('click', deleteAccount);
    }

    // 탭 전환
    document.querySelectorAll('.modal-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            var tabId = this.dataset.tab;
            document.querySelectorAll('.modal-tab').forEach(function (t) {
                t.classList.remove('active');
            });
            document.querySelectorAll('.tab-content').forEach(function (c) {
                c.classList.remove('active');
            });
            this.classList.add('active');
            var targetTab = document.getElementById('tab-' + tabId);
            if (targetTab) targetTab.classList.add('active');
        });
    });
});
