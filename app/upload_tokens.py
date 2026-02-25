# -*- coding: utf-8 -*-
"""
업로드 토큰 저장소
"""

import secrets
import time
from app.state_store import state_store

TOKEN_TTL_SECONDS = 300  # 5 minutes

_TOKEN_PREFIX = "upload_token"


def _token_key(token: str) -> str:
    return f"{_TOKEN_PREFIX}:{token}"


def purge_expired_upload_tokens():
    """Redis backend에서는 TTL 기반 자동 정리를 사용한다."""
    return 0


def issue_upload_token(
    user_id: int,
    room_id: int,
    file_path: str,
    file_name: str,
    file_type: str,
    file_size: int,
) -> str:
    """업로드 토큰 발급"""
    token = secrets.token_urlsafe(32)
    state_store.set_json(
        _token_key(token),
        {
            "user_id": user_id,
            "room_id": room_id,
            "file_path": file_path,
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "expires_at": time.time() + TOKEN_TTL_SECONDS,
        },
        ttl_seconds=TOKEN_TTL_SECONDS,
    )
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
    token_data = state_store.get_json(_token_key(token))
    if not token_data:
        return '업로드 토큰이 유효하지 않습니다.'
    if token_data.get('expires_at', 0) <= now:
        state_store.delete(_token_key(token))
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

    token_data = state_store.getdel_json(_token_key(token))
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
