# -*- coding: utf-8 -*-
"""
Upload token helpers.
"""

from __future__ import annotations

import os
import secrets
import time

from app.models.base import get_db, safe_file_delete
from app.services.runtime_paths import get_upload_folder
from app.state_store import state_store

TOKEN_TTL_SECONDS = 300

_TOKEN_PREFIX = "upload_token"

_QUARANTINE_SUBDIR = "quarantine"


def _token_key(token: str) -> str:
    return f"{_TOKEN_PREFIX}:{token}"


def _iter_purge_candidates(upload_root: str):
    """만료 정리 대상 파일 경로를 yield한다.

    최상위 파일 + quarantine 하위 파일만 스캔한다. profiles 등 다른 하위
    디렉토리는 정리 대상이 아니다 (ISSUE-005).
    """
    try:
        top_entries = list(os.scandir(upload_root))
    except FileNotFoundError:
        return
    for entry in top_entries:
        if entry.is_file():
            yield entry.path
    try:
        quarantine_entries = list(os.scandir(os.path.join(upload_root, _QUARANTINE_SUBDIR)))
    except FileNotFoundError:
        return
    for entry in quarantine_entries:
        if entry.is_file():
            yield entry.path


def purge_expired_upload_tokens(upload_folder: str | None = None, now: float | None = None):
    """Delete expired, unreferenced uploads that never became room files."""
    cutoff = float(now if now is not None else time.time()) - TOKEN_TTL_SECONDS
    upload_root = upload_folder or get_upload_folder()
    if not os.path.isdir(upload_root):
        return 0

    conn = get_db()
    cursor = conn.cursor()
    deleted = 0
    try:
        cursor.execute("SELECT file_path FROM room_files")
        referenced = {str(row["file_path"]).replace("\\", "/") for row in cursor.fetchall() if row["file_path"]}
    except Exception:
        referenced = set()

    for file_path in _iter_purge_candidates(upload_root):
        try:
            if os.path.getmtime(file_path) > cutoff:
                continue
        except FileNotFoundError:
            continue

        rel_path = os.path.relpath(file_path, upload_root).replace("\\", "/")
        if rel_path in referenced:
            continue
        if safe_file_delete(file_path):
            deleted += 1
    return deleted


def issue_upload_token(
    user_id: int,
    room_id: int,
    file_path: str,
    file_name: str,
    file_type: str,
    file_size: int,
) -> str:
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
    expected_type: str | None = None,
) -> str:
    if not token or not isinstance(token, str):
        return "업로드 토큰이 필요합니다."

    now = time.time()
    token_data = state_store.get_json(_token_key(token))
    if not token_data:
        return "업로드 토큰이 유효하지 않습니다."
    if token_data.get("expires_at", 0) <= now:
        state_store.delete(_token_key(token))
        return "업로드 토큰이 만료되었습니다."
    if token_data.get("user_id") != user_id:
        return "업로드 토큰 사용자 정보가 일치하지 않습니다."
    if token_data.get("room_id") != room_id:
        return "업로드 토큰 대화방 정보가 일치하지 않습니다."
    if expected_type and token_data.get("file_type") not in (None, expected_type):
        return "업로드 토큰 파일 유형이 일치하지 않습니다."
    return ""


def consume_upload_token(
    token: str,
    user_id: int,
    room_id: int,
    expected_type: str | None = None,
):
    if get_upload_token_failure_reason(token, user_id, room_id, expected_type):
        return None

    token_data = state_store.getdel_json(_token_key(token))
    if not token_data:
        return None

    return {
        "user_id": token_data["user_id"],
        "room_id": token_data["room_id"],
        "file_path": token_data["file_path"],
        "file_name": token_data["file_name"],
        "file_type": token_data["file_type"],
        "file_size": token_data["file_size"],
    }
