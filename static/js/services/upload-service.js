/**
 * Upload subsystem extracted from messages.js
 * - keeps upload/scan/message-send flow in one place
 * - exposes a small global facade for legacy pages
 */
(function (global) {
    'use strict';

    function getReplyToId() {
        return (typeof global.replyingTo !== 'undefined' && global.replyingTo)
            ? global.replyingTo.id
            : null;
    }

    function getUploadMaxSizeBytes() {
        return (global.serverConfig &&
            global.serverConfig.upload &&
            Number(global.serverConfig.upload.max_size_bytes)) || (16 * 1024 * 1024);
    }

    function inferMessageType(file) {
        var ext = (file.name.split('.').pop() || '').toLowerCase();
        var imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'];
        return imageExts.includes(ext) || (file.type || '').startsWith('image/') ? 'image' : 'file';
    }

    function emitUploadedFileMessage(file, result, replyToId) {
        if (!global.socket || !global.socket.connected) {
            if (typeof global.showToast === 'function') {
                global.showToast('서버 연결이 끊어졌습니다. 파일은 업로드되었지만 메시지 전송에 실패했습니다.', 'warning');
            }
            return false;
        }

        if (!result.upload_token) {
            if (typeof global.showToast === 'function') {
                global.showToast('업로드 토큰 발급에 실패했습니다. 다시 업로드해주세요.', 'error');
            }
            return false;
        }

        global.safeSocketEmit('send_message', {
            room_id: global.currentRoom.id,
            content: file.name || '',
            type: inferMessageType(file),
            upload_token: result.upload_token,
            file_path: result.file_path,
            file_name: result.file_name || file.name,
            encrypted: false,
            reply_to: replyToId || null
        });
        if (typeof global.clearReply === 'function') global.clearReply();
        if (typeof global.showToast === 'function') global.showToast('파일이 전송되었습니다.', 'success');
        return true;
    }

    function pollUploadScanJob(jobId, file, replyToId, onDone) {
        var maxAttempts = 40;
        var intervalMs = 1500;
        var attempts = 0;

        function finish() {
            if (typeof onDone === 'function') onDone();
        }

        function tick() {
            attempts += 1;
            fetch('/api/upload/jobs/' + encodeURIComponent(jobId), { credentials: 'same-origin' })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    var status = (data && data.scan_status) || 'pending';
                    if (status === 'pending') {
                        if (attempts >= maxAttempts) {
                            if (typeof global.showToast === 'function') global.showToast('파일 검사 시간이 초과되었습니다.', 'error');
                            finish();
                            return;
                        }
                        setTimeout(tick, intervalMs);
                        return;
                    }

                    if (status === 'clean') {
                        emitUploadedFileMessage(file, data, replyToId);
                        finish();
                        return;
                    }

                    if (typeof global.showToast === 'function') {
                        global.showToast((data && data.error) || '파일 검사에 실패했습니다.', 'error');
                    }
                    finish();
                })
                .catch(function () {
                    if (attempts >= maxAttempts) {
                        if (typeof global.showToast === 'function') global.showToast('파일 검사 상태 조회에 실패했습니다.', 'error');
                        finish();
                        return;
                    }
                    setTimeout(tick, intervalMs);
                });
        }

        tick();
    }

    function handleUploadApiResult(file, result, replyToId, onDone) {
        if (!result || !result.success) {
            if (typeof global.showToast === 'function') {
                global.showToast((result && result.error) || '파일 업로드 실패', 'error');
            }
            if (typeof onDone === 'function') onDone();
            return;
        }

        var status = result.scan_status || (result.upload_token ? 'clean' : 'pending');
        if (status === 'pending') {
            if (typeof global.showToast === 'function') global.showToast('파일 보안 검사를 진행 중입니다.', 'info');
            pollUploadScanJob(result.job_id, file, replyToId, onDone);
            return;
        }

        emitUploadedFileMessage(file, result, replyToId);
        if (typeof onDone === 'function') onDone();
    }

    function handleFileUploadEvent(e) {
        var file = e.target.files[0];
        if (!file || !global.currentRoom) return;

        var formData = new FormData();
        formData.append('file', file);
        formData.append('room_id', global.currentRoom.id);

        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var xhr = new XMLHttpRequest();
        var progressToastId = null;

        xhr.upload.onprogress = function (event) {
            if (!event.lengthComputable || typeof global.showToast !== 'function') return;
            var percent = Math.round((event.loaded / event.total) * 100);
            if (percent >= 25 && !progressToastId) {
                progressToastId = 25;
                global.showToast('📤 파일 업로드 시작... 25%', 'info');
            } else if (percent >= 50 && progressToastId < 50) {
                progressToastId = 50;
                global.showToast('📤 파일 업로드 중... 50%', 'info');
            } else if (percent >= 75 && progressToastId < 75) {
                progressToastId = 75;
                global.showToast('📤 거의 완료... 75%', 'info');
            }
        };

        xhr.onload = function () {
            try {
                var result = JSON.parse(xhr.responseText);
                handleUploadApiResult(file, result, getReplyToId(), function () { e.target.value = ''; });
                return;
            } catch (err) {
                console.error('파일 업로드 응답 파싱 실패:', err);
                if (typeof global.showToast === 'function') global.showToast('파일 업로드 응답 처리 실패', 'error');
            }
            e.target.value = '';
        };

        xhr.onerror = function () {
            console.error('파일 업로드 실패');
            if (typeof global.showToast === 'function') global.showToast('파일 업로드에 실패했습니다.', 'error');
            e.target.value = '';
        };

        xhr.timeout = 120000;
        xhr.ontimeout = function () {
            console.error('파일 업로드 타임아웃');
            if (typeof global.showToast === 'function') {
                global.showToast('파일 업로드 시간이 초과되었습니다. 더 작은 파일을 시도하거나 네트워크 연결을 확인하세요.', 'error');
            }
            e.target.value = '';
        };

        xhr.open('POST', '/api/upload');
        if (csrfToken) {
            xhr.setRequestHeader('X-CSRFToken', csrfToken.getAttribute('content'));
        }
        xhr.send(formData);
    }

    function uploadFile(file) {
        if (!global.currentRoom) return;
        var formData = new FormData();
        formData.append('file', file);
        formData.append('room_id', global.currentRoom.id);

        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var xhr = new XMLHttpRequest();

        xhr.onload = function () {
            try {
                var result = JSON.parse(xhr.responseText);
                handleUploadApiResult(file, result, getReplyToId());
            } catch (err) {
                console.error('파일 업로드 응답 파싱 실패:', err);
                if (typeof global.showToast === 'function') global.showToast('파일 업로드에 실패했습니다.', 'error');
            }
        };

        xhr.onerror = function () {
            console.error('파일 업로드 실패');
            if (typeof global.showToast === 'function') global.showToast('파일 업로드에 실패했습니다.', 'error');
        };

        xhr.timeout = 120000;
        xhr.ontimeout = function () {
            console.error('파일 업로드 타임아웃');
            if (typeof global.showToast === 'function') {
                global.showToast('파일 업로드 시간이 초과되었습니다.', 'error');
            }
        };

        xhr.open('POST', '/api/upload');
        if (csrfToken) {
            xhr.setRequestHeader('X-CSRFToken', csrfToken.getAttribute('content'));
        }
        xhr.send(formData);
    }

    function handleDroppedFiles(files) {
        if (!global.currentRoom) {
            if (typeof global.showToast === 'function') global.showToast('먼저 대화방을 선택해주세요.', 'warning');
            return;
        }
        for (var i = 0; i < files.length; i++) {
            var file = files[i];
            if (file.size > getUploadMaxSizeBytes()) {
                if (typeof global.showToast === 'function') global.showToast('파일 크기 제한을 초과했습니다.', 'warning');
                continue;
            }
            uploadFile(file);
        }
    }

    global.MessengerUpload = {
        getUploadMaxSizeBytes: getUploadMaxSizeBytes,
        inferMessageType: inferMessageType,
        emitUploadedFileMessage: emitUploadedFileMessage,
        pollUploadScanJob: pollUploadScanJob,
        handleUploadApiResult: handleUploadApiResult,
        handleFileUploadEvent: handleFileUploadEvent,
        handleDroppedFiles: handleDroppedFiles,
        uploadFile: uploadFile
    };
})(window);
