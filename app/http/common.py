# -*- coding: utf-8 -*-
"""
Common HTTP helpers shared across blueprints.
"""

from __future__ import annotations

from typing import Any, cast

from flask import jsonify, request, session


def json_error(message: str, status: int = 400, code: str | None = None):
    payload = {"error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status


def parse_json_payload(required: bool = True) -> tuple[dict[str, Any], Any | None]:
    data = request.get_json(silent=True)
    if data is None:
        if required:
            return {}, json_error("JSON body is required.", 400, "invalid_json")
        return {}, None
    if not isinstance(data, dict):
        return {}, json_error("JSON object payload is required.", 400, "invalid_json")
    return cast(dict[str, Any], data), None


def parse_int_from_json(
    data: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> tuple[int, Any | None]:
    value = data.get(key, default)
    if value in (None, ""):
        value = default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default, json_error(f"Invalid integer for '{key}'.", 400, f"invalid_{key}")
    if minimum is not None:
        parsed = max(parsed, minimum)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed, None


def require_login():
    if "user_id" not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401
    return None


def truthy_param(value) -> bool:
    return str(value or "").lower() in ("1", "true", "yes")
