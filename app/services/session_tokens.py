# -*- coding: utf-8 -*-
"""
Session token validation shared by HTTP and Socket.IO flows.
"""

from __future__ import annotations

from flask import jsonify, redirect, request, session

from app.models import get_user_session_token


PUBLIC_SESSION_EXEMPT_PATHS = {
    "/api/login",
    "/api/register",
    "/api/logout",
    "/api/config",
    "/api/auth/providers",
    "/auth/oidc/login",
    "/auth/oidc/callback",
}


def is_session_token_valid() -> bool:
    user_id = session.get("user_id")
    if not user_id:
        return False

    db_token = get_user_session_token(user_id)
    sess_token = session.get("session_token")
    return bool(db_token and sess_token and db_token == sess_token)


def enforce_http_session_token():
    if "user_id" not in session:
        return None

    path = request.path or ""
    if path.startswith("/control/") or path.startswith("/static/"):
        return None
    if path in PUBLIC_SESSION_EXEMPT_PATHS:
        return None

    if is_session_token_valid():
        return None

    session.clear()
    if path.startswith("/api") or path.startswith("/uploads"):
        return jsonify({"error": "세션이 만료되었거나 다른 세션에서 무효화되었습니다."}), 401
    return redirect("/")

