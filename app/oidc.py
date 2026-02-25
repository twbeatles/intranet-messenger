# -*- coding: utf-8 -*-
"""
Lightweight OIDC helpers (no hard dependency on external SDK).
"""

from __future__ import annotations

import base64
import json
import secrets
import urllib.parse
import urllib.request
from typing import Any


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _post_form(url: str, data: dict[str, str], timeout: int = 10) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _decode_jwt_payload(id_token: str) -> dict[str, Any]:
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return {}


def _resolve_oidc_endpoints(app) -> tuple[str, str, str]:
    issuer = (app.config.get("OIDC_ISSUER_URL") or "").strip().rstrip("/")
    auth = (app.config.get("OIDC_AUTHORIZE_URL") or "").strip()
    token = (app.config.get("OIDC_TOKEN_URL") or "").strip()
    userinfo = (app.config.get("OIDC_USERINFO_URL") or "").strip()

    if issuer and (not auth or not token or not userinfo):
        doc = _fetch_json(f"{issuer}/.well-known/openid-configuration")
        auth = auth or doc.get("authorization_endpoint", "")
        token = token or doc.get("token_endpoint", "")
        userinfo = userinfo or doc.get("userinfo_endpoint", "")

    return auth, token, userinfo


def oidc_enabled(app) -> bool:
    if not app.config.get("FEATURE_OIDC_ENABLED"):
        return False
    if not app.config.get("OIDC_CLIENT_ID"):
        return False
    if not app.config.get("OIDC_CLIENT_SECRET"):
        return False
    return bool(app.config.get("OIDC_ISSUER_URL") or app.config.get("OIDC_AUTHORIZE_URL"))


def get_provider_metadata(app) -> dict[str, Any]:
    enabled = oidc_enabled(app)
    return {
        "oidc_enabled": enabled,
        "provider": app.config.get("OIDC_PROVIDER_NAME", "oidc"),
    }


def build_authorize_redirect(app, redirect_uri: str) -> str:
    auth_url, _, _ = _resolve_oidc_endpoints(app)
    if not auth_url:
        raise RuntimeError("OIDC authorization endpoint is not configured")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    from flask import session

    session["oidc_state"] = state
    session["oidc_nonce"] = nonce

    query = {
        "response_type": "code",
        "client_id": app.config.get("OIDC_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "scope": app.config.get("OIDC_SCOPE", "openid profile email"),
        "state": state,
        "nonce": nonce,
    }
    return f"{auth_url}?{urllib.parse.urlencode(query)}"


def exchange_code_for_userinfo(app, code: str, redirect_uri: str) -> dict[str, Any]:
    _, token_url, userinfo_url = _resolve_oidc_endpoints(app)
    if not token_url:
        raise RuntimeError("OIDC token endpoint is not configured")

    token_resp = _post_form(
        token_url,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": app.config.get("OIDC_CLIENT_ID"),
            "client_secret": app.config.get("OIDC_CLIENT_SECRET"),
        },
    )

    access_token = token_resp.get("access_token")
    id_token = token_resp.get("id_token")
    claims: dict[str, Any] = {}

    if access_token and userinfo_url:
        req = urllib.request.Request(
            userinfo_url,
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            claims = json.loads(resp.read().decode("utf-8"))
    elif id_token:
        claims = _decode_jwt_payload(id_token)

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "preferred_username": claims.get("preferred_username") or claims.get("name"),
        "nickname": claims.get("name") or claims.get("preferred_username"),
    }

