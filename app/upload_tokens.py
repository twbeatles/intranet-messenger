# -*- coding: utf-8 -*-
"""
업로드 토큰 저장소 (in-memory)
"""

import secrets
import threading
import time

TOKEN_TTL_SECONDS = 300  # 5 minutes

_upload_tokens: dict[str, dict] = {}
_upload_tokens_lock = threading.Lock()


def purge_expired_upload_tokens():
    """만료된 업로드 토큰 정리"""
    now = time.time()
    removed = 0
    with _upload_tokens_lock:
        expired = [token for token, data in _upload_tokens.items() if data.get('expires_at', 0) <= now]
        for token in expired:
            _upload_tokens.pop(token, None)
            removed += 1
    return removed


def issue_upload_token(
    user_id: int,
    room_id: int,
    file_path: str,
    file_name: str,
    file_type: str,
    file_size: int,
) -> str:
    """업로드 토큰 발급"""
    purge_expired_upload_tokens()
    token = secrets.token_urlsafe(32)
    with _upload_tokens_lock:
        _upload_tokens[token] = {
            'user_id': user_id,
            'room_id': room_id,
            'file_path': file_path,
            'file_name': file_name,
            'file_type': file_type,
            'file_size': file_size,
            'expires_at': time.time() + TOKEN_TTL_SECONDS,
        }
    return token


def get_upload_token_failure_reason(
    token: str,
    user_id: int,
    room_id: int,
    expected_type: str = None,
) -> str:
    """업로드 토큰 검증 실패 사유 조회 (소비하지 않음)"""
    if not token or not isinstance(token, str):
        return '업로드 토큰이 필요합니다.'

    now = time.time()
    with _upload_tokens_lock:
        token_data = _upload_tokens.get(token)
        if not token_data:
            return '업로드 토큰이 유효하지 않습니다.'
        if token_data.get('expires_at', 0) <= now:
            _upload_tokens.pop(token, None)
            return '업로드 토큰이 만료되었습니다.'
        if token_data.get('user_id') != user_id:
            return '업로드 토큰 사용자 정보가 일치하지 않습니다.'
        if token_data.get('room_id') != room_id:
            return '업로드 토큰의 대화방 정보가 일치하지 않습니다.'
        if expected_type and token_data.get('file_type') not in (None, expected_type):
            return '업로드 토큰 파일 유형이 일치하지 않습니다.'
    return ''


def consume_upload_token(
    token: str,
    user_id: int,
    room_id: int,
    expected_type: str = None,
):
    """업로드 토큰 1회 소비"""
    if get_upload_token_failure_reason(token, user_id, room_id, expected_type):
        return None

    with _upload_tokens_lock:
        token_data = _upload_tokens.pop(token, None)
        if not token_data:
            return None

    return {
        'user_id': token_data['user_id'],
        'room_id': token_data['room_id'],
        'file_path': token_data['file_path'],
        'file_name': token_data['file_name'],
        'file_type': token_data['file_type'],
        'file_size': token_data['file_size'],
    }
