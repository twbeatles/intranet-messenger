# -*- coding: utf-8 -*-
"""
Request, teardown, and response hooks.
"""

from __future__ import annotations

import json
import re

from flask import request

from app.models import close_thread_db
from app.services.session_tokens import enforce_http_session_token

_MOJIBAKE_HINT_TOKENS = (
    "濡쒓렇", "꾩슂", "뺤옣", "먯꽌", "룞", "몄씠", "⑸땲", "뒿", "媛뺥",
    "앹꽦", "怨듭", "뚯씪", "紐낆쓽", "쒖냼", "먮룞", "쒕쾭", "곗씠",
)
_MOJIBAKE_LATIN_RE = re.compile(r"[Ã-ÿ]{2,}")


def _looks_like_mojibake(text: str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if any(token in text for token in _MOJIBAKE_HINT_TOKENS):
        return True
    if _MOJIBAKE_LATIN_RE.search(text):
        return True
    if text.count("?") >= 2 and any(ord(ch) > 127 for ch in text):
        return True
    return False


def _fallback_message_for_status(status_code: int) -> str:
    if status_code == 400:
        return "요청 값이 올바르지 않습니다."
    if status_code == 401:
        return "로그인이 필요합니다."
    if status_code == 403:
        return "접근 권한이 없습니다."
    if status_code == 404:
        return "요청한 리소스를 찾을 수 없습니다."
    if status_code == 429:
        return "요청 한도를 초과했습니다."
    if status_code >= 500:
        return "서버 내부 오류가 발생했습니다."
    return "요청 처리 중 오류가 발생했습니다."


def _normalize_json_response_messages(payload, status_code: int):
    changed = False

    def walk(node, key_name=None):
        nonlocal changed
        if isinstance(node, dict):
            return {key: walk(value, key_name=key) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(item, key_name=key_name) for item in node]
        if isinstance(node, str) and key_name in ("error", "message", "detail"):
            if _looks_like_mojibake(node):
                changed = True
                return _fallback_message_for_status(status_code)
            return node
        return node

    normalized = walk(payload)
    return normalized, changed


def register_hooks(app):
    @app.before_request
    def enforce_session_token():
        return enforce_http_session_token()

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        close_thread_db()

    @app.after_request
    def add_security_headers(response):
        if (request.path or "").startswith("/api") and response.mimetype == "application/json":
            payload = response.get_json(silent=True)
            if payload is not None:
                normalized_payload, changed = _normalize_json_response_messages(payload, response.status_code)
                if changed:
                    response.set_data(json.dumps(normalized_payload, ensure_ascii=False).encode("utf-8"))
                    response.headers["Content-Type"] = "application/json; charset=utf-8"

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

