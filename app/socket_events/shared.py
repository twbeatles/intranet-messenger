# -*- coding: utf-8 -*-
"""
Shared Socket.IO helper functions.
"""

from __future__ import annotations

import logging

from flask import current_app, request, session
from flask_socketio import disconnect, emit

from app.services.text_hygiene import sanitize_client_message
from app.services.session_tokens import is_session_token_valid
from app.state_store import state_store

logger = logging.getLogger(__name__)


def emit_error(message: str, fallback: str = "요청 처리 중 오류가 발생했습니다."):
    emit("error", {"message": sanitize_client_message(message, fallback)})


def ensure_session_token(event_name: str):
    if is_session_token_valid():
        return True
    logger.warning(f"Socket session invalidated during event: {event_name}")
    emit_error("세션이 만료되었거나 다른 세션에서 무효화되었습니다.")
    try:
        disconnect()
    except Exception:
        pass
    return False


def check_send_message_rate_limit(user_id: int) -> bool:
    per_minute = int(current_app.config.get("SOCKET_SEND_MESSAGE_PER_MINUTE", 100))
    key = f"socket:send_message:{user_id}"
    count = state_store.incr(key, ttl_seconds=60)
    return count <= per_minute


def parse_positive_int(data, key: str):
    try:
        value = int(data.get(key))
        if value <= 0:
            return None
        return value
    except (AttributeError, TypeError, ValueError):
        return None


def check_event_rate_limit(event: str, user_id: int, per_minute: int) -> bool:
    key = f"socket:{event}:{user_id}"
    count = state_store.incr(key, ttl_seconds=60)
    return count <= max(int(per_minute), 1)


def request_sid() -> str:
    return getattr(request, "sid")
