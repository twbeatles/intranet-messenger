# -*- coding: utf-8 -*-
"""
Flask runtime app construction and configuration.
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from flask import Flask
from flask_session import Session

from app.state_store import state_store

try:
    from cachelib.file import FileSystemCache
except Exception:
    FileSystemCache = None

try:
    from config import (
        APP_NAME,
        ASYNC_MODE,
        AV_CLAMD_HOST,
        AV_CLAMD_PORT,
        AV_SCAN_TIMEOUT_SECONDS,
        AV_SCANNER,
        BASE_DIR,
        FEATURE_AV_SCAN_ENABLED,
        FEATURE_OIDC_ENABLED,
        FEATURE_REDIS_ENABLED,
        MAINTENANCE_INTERVAL_SECONDS,
        MAX_CONTENT_LENGTH,
        MESSAGE_QUEUE,
        OIDC_AUTHORIZE_URL,
        OIDC_CLIENT_ID,
        OIDC_CLIENT_SECRET,
        OIDC_ISSUER_URL,
        OIDC_JWKS_CACHE_SECONDS,
        OIDC_JWKS_URL,
        OIDC_PROVIDER_NAME,
        OIDC_REDIRECT_URI,
        OIDC_SCOPE,
        OIDC_TOKEN_URL,
        OIDC_USERINFO_URL,
        PING_INTERVAL,
        PING_TIMEOUT,
        RATE_LIMIT_STORAGE_URI,
        RETENTION_DAYS,
        SESSION_TIMEOUT_HOURS,
        SOCKETIO_CORS_ALLOWED_ORIGINS,
        SOCKET_PIN_UPDATED_PER_MINUTE,
        SOCKET_SEND_MESSAGE_PER_MINUTE,
        STATE_STORE_REDIS_URL,
        STATIC_FOLDER,
        TEMPLATE_FOLDER,
        UPLOAD_FOLDER,
        UPLOAD_QUARANTINE_FOLDER,
        USE_HTTPS,
    )
except ImportError:
    from config import *  # type: ignore  # noqa: F403,F401


def _load_or_create_secret(file_path: str, byte_length: int) -> str:
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    value = secrets.token_hex(byte_length)
    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write(value)
    return value


def build_flask_app():
    static_folder = STATIC_FOLDER
    template_folder = TEMPLATE_FOLDER

    if not os.path.exists(static_folder):
        os.makedirs(static_folder, exist_ok=True)
    if not os.path.exists(template_folder):
        os.makedirs(template_folder, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, "profiles"), exist_ok=True)
    os.makedirs(UPLOAD_QUARANTINE_FOLDER, exist_ok=True)

    app = Flask(__name__, static_folder=static_folder, static_url_path="/static", template_folder=template_folder)

    app.config["SECRET_KEY"] = _load_or_create_secret(os.path.join(BASE_DIR, ".secret_key"), 32)
    app.config["PASSWORD_SALT"] = _load_or_create_secret(os.path.join(BASE_DIR, ".security_salt"), 16)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_SECURE"] = USE_HTTPS
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=SESSION_TIMEOUT_HOURS)
    app.config["RATELIMIT_STORAGE_URI"] = RATE_LIMIT_STORAGE_URI
    app.config["STATE_STORE_REDIS_URL"] = STATE_STORE_REDIS_URL
    app.config["RETENTION_DAYS"] = RETENTION_DAYS
    app.config["MAINTENANCE_INTERVAL_SECONDS"] = MAINTENANCE_INTERVAL_SECONDS
    app.config["FEATURE_OIDC_ENABLED"] = FEATURE_OIDC_ENABLED
    app.config["FEATURE_AV_SCAN_ENABLED"] = FEATURE_AV_SCAN_ENABLED
    app.config["FEATURE_REDIS_ENABLED"] = FEATURE_REDIS_ENABLED
    app.config["OIDC_PROVIDER_NAME"] = OIDC_PROVIDER_NAME
    app.config["OIDC_ISSUER_URL"] = OIDC_ISSUER_URL
    app.config["OIDC_AUTHORIZE_URL"] = OIDC_AUTHORIZE_URL
    app.config["OIDC_TOKEN_URL"] = OIDC_TOKEN_URL
    app.config["OIDC_USERINFO_URL"] = OIDC_USERINFO_URL
    app.config["OIDC_CLIENT_ID"] = OIDC_CLIENT_ID
    app.config["OIDC_CLIENT_SECRET"] = OIDC_CLIENT_SECRET
    app.config["OIDC_SCOPE"] = OIDC_SCOPE
    app.config["OIDC_REDIRECT_URI"] = OIDC_REDIRECT_URI
    app.config["OIDC_JWKS_URL"] = OIDC_JWKS_URL
    app.config["OIDC_JWKS_CACHE_SECONDS"] = OIDC_JWKS_CACHE_SECONDS
    app.config["AV_SCANNER"] = AV_SCANNER
    app.config["AV_CLAMD_HOST"] = AV_CLAMD_HOST
    app.config["AV_CLAMD_PORT"] = AV_CLAMD_PORT
    app.config["AV_SCAN_TIMEOUT_SECONDS"] = AV_SCAN_TIMEOUT_SECONDS
    app.config["UPLOAD_QUARANTINE_FOLDER"] = UPLOAD_QUARANTINE_FOLDER
    app.config["SOCKET_SEND_MESSAGE_PER_MINUTE"] = SOCKET_SEND_MESSAGE_PER_MINUTE
    app.config["SOCKET_PIN_UPDATED_PER_MINUTE"] = SOCKET_PIN_UPDATED_PER_MINUTE
    app.config["APP_NAME"] = APP_NAME
    app.config["ASYNC_MODE"] = ASYNC_MODE
    app.config["PING_TIMEOUT"] = PING_TIMEOUT
    app.config["PING_INTERVAL"] = PING_INTERVAL
    app.config["MESSAGE_QUEUE"] = MESSAGE_QUEUE
    app.config["SOCKETIO_CORS_ALLOWED_ORIGINS"] = SOCKETIO_CORS_ALLOWED_ORIGINS

    if str(app.config.get("RATELIMIT_STORAGE_URI", "")).startswith("redis"):
        try:
            import redis  # type: ignore # noqa: F401
        except Exception:
            app.config["RATELIMIT_STORAGE_URI"] = "memory://"

    session_dir = os.path.join(BASE_DIR, "flask_session")
    os.makedirs(session_dir, exist_ok=True)
    app.config["SESSION_PERMANENT"] = True
    if FileSystemCache is not None:
        app.config["SESSION_TYPE"] = "cachelib"
        app.config["SESSION_CACHELIB"] = FileSystemCache(cache_dir=session_dir, threshold=1000, mode=0o600)
    else:
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = session_dir
    Session(app)

    state_store.init_app(redis_url=app.config.get("STATE_STORE_REDIS_URL") or None)
    return app

