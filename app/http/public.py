# -*- coding: utf-8 -*-
"""
Public and bootstrap HTTP endpoints.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from app.http.common import require_login
from app.models import get_or_create_oidc_user, get_user_by_id, log_access
from app.oidc import (
    build_authorize_redirect,
    exchange_code_for_userinfo,
    get_provider_metadata,
    oidc_enabled,
)
from app.services.runtime_config import build_public_config

try:
    from config import MAX_CONTENT_LENGTH, SOCKET_SEND_MESSAGE_PER_MINUTE
except ImportError:
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SOCKET_SEND_MESSAGE_PER_MINUTE = 100

logger = logging.getLogger(__name__)

public_bp = Blueprint("public", __name__)


@public_bp.get("/")
def index():
    return render_template("index.html")


@public_bp.get("/api/me")
def get_current_user():
    if "user_id" in session:
        user = get_user_by_id(session["user_id"])
        if user:
            return jsonify({"logged_in": True, "user": user})
    return jsonify({"logged_in": False})


@public_bp.get("/api/config")
def get_runtime_config():
    return jsonify(
        build_public_config(
            current_app,
            default_max_size=MAX_CONTENT_LENGTH,
            default_socket_send_per_minute=SOCKET_SEND_MESSAGE_PER_MINUTE,
        )
    )


@public_bp.get("/api/auth/providers")
def auth_providers():
    providers = []
    if oidc_enabled(current_app):
        meta = get_provider_metadata(current_app)
        providers.append(
            {
                "type": "oidc",
                "provider": meta.get("provider", "oidc"),
                "login_url": "/auth/oidc/login",
            }
        )
    return jsonify({"providers": providers})


@public_bp.get("/auth/oidc/login")
def oidc_login():
    if not oidc_enabled(current_app):
        return redirect("/")
    redirect_uri = current_app.config.get("OIDC_REDIRECT_URI") or url_for("public.oidc_callback", _external=True)
    try:
        return redirect(build_authorize_redirect(current_app, redirect_uri=redirect_uri))
    except Exception as exc:
        logger.error(f"OIDC login redirect build failed: {exc}")
        return redirect("/")


@public_bp.get("/auth/oidc/callback")
def oidc_callback():
    if not oidc_enabled(current_app):
        return redirect("/")

    expected_state = session.pop("oidc_state", None)
    expected_nonce = session.pop("oidc_nonce", None)
    state = request.args.get("state")
    code = request.args.get("code")
    if not code or not state or state != expected_state:
        return redirect("/")

    redirect_uri = current_app.config.get("OIDC_REDIRECT_URI") or url_for("public.oidc_callback", _external=True)
    try:
        claims = exchange_code_for_userinfo(
            current_app,
            code=code,
            redirect_uri=redirect_uri,
            expected_nonce=expected_nonce,
        )
        provider = current_app.config.get("OIDC_PROVIDER_NAME") or "oidc"
        subject = (claims or {}).get("sub")
        if not subject:
            return redirect("/")

        user = get_or_create_oidc_user(
            provider=provider,
            subject=subject,
            email=(claims or {}).get("email"),
            preferred_username=(claims or {}).get("preferred_username"),
            nickname=(claims or {}).get("nickname"),
        )
        if not user:
            return redirect("/")

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["nickname"] = user.get("nickname", user["username"])
        session["session_token"] = user.get("session_token")
        log_access(user["id"], "oidc_login", request.remote_addr, request.user_agent.string)
        return redirect("/")
    except Exception as exc:
        logger.error(f"OIDC callback failed: {exc}")
        return redirect("/")

