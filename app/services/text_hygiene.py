# -*- coding: utf-8 -*-
"""
Shared text hygiene helpers for mojibake detection and sanitization.
"""

from __future__ import annotations

import re

_MOJIBAKE_LATIN_RE = re.compile(r"[Ã-ÿ]{2,}")


def looks_like_mojibake(text: str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if "\ufffd" in text:
        return True
    if _MOJIBAKE_LATIN_RE.search(text):
        return True
    if text.count("?") >= 2 and any(ord(ch) > 127 for ch in text):
        return True
    return False


def sanitize_client_message(message: str, fallback: str = "요청 처리 중 오류가 발생했습니다.") -> str:
    return fallback if looks_like_mojibake(message) else message
