# -*- coding: utf-8 -*-
"""
Lightweight OIDC helpers (no hard dependency on external SDK).
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.parse
import urllib.request
from threading import Lock
from typing import Any

import jwt

_JWKS_CLIENT_CACHE: dict[str, dict[str, Any]] = {}
_JWKS_CLIENT_CACHE_LOCK = Lock()


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


def _resolve_oidc_metadata(app) -> tuple[str, str, str, str, str]:
    issuer = (app.config.get("OIDC_ISSUER_URL") or "").strip().rstrip("/")
    auth = (app.config.get("OIDC_AUTHORIZE_URL") or "").strip()
    token = (app.config.get("OIDC_TOKEN_URL") or "").strip()
    userinfo = (app.config.get("OIDC_USERINFO_URL") or "").strip()
    jwks = (app.config.get("OIDC_JWKS_URL") or "").strip()

    if issuer and (not auth or not token or not userinfo or not jwks):
        doc = _fetch_json(f"{issuer}/.well-known/openid-configuration")
        auth = auth or doc.get("authorization_endpoint", "")
        token = token or doc.get("token_endpoint", "")
        userinfo = userinfo or doc.get("userinfo_endpoint", "")
        jwks = jwks or doc.get("jwks_uri", "")

    return auth, token, userinfo, issuer, jwks


def _get_jwks_client(jwks_url: str, cache_seconds: int):
    if not jwks_url:
        raise RuntimeError("OIDC JWKS endpoint is not configured")
    now = time.time()
    with _JWKS_CLIENT_CACHE_LOCK:
        cached = _JWKS_CLIENT_CACHE.get(jwks_url)
        if cached and (now - float(cached.get("created_at", 0))) < cache_seconds:
            return cached["client"]
        client = jwt.PyJWKClient(jwks_url)
        _JWKS_CLIENT_CACHE[jwks_url] = {"client": client, "created_at": now}
        return client


def _verify_id_token(app, id_token: str, expected_nonce: str) -> dict[str, Any]:
    if not id_token:
        raise RuntimeError("OIDC id_token is missing")
    if not expected_nonce:
        raise RuntimeError("OIDC nonce is missing")

    _, _, _, issuer, jwks_url = _resolve_oidc_metadata(app)
    if not issuer:
        raise RuntimeError("OIDC issuer is not configured")

    audience = (app.config.get("OIDC_CLIENT_ID") or "").strip()
    if not audience:
        raise RuntimeError("OIDC client_id is not configured")

    cache_seconds = int(app.config.get("OIDC_JWKS_CACHE_SECONDS") or 300)
    jwks_client = _get_jwks_client(jwks_url, cache_seconds=cache_seconds)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)

    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "HS256", "HS384", "HS512"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "sub"]},
    )

    nonce = claims.get("nonce")
    if not nonce or nonce != expected_nonce:
        raise RuntimeError("OIDC nonce mismatch")

    return claims


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
    auth_url, _, _, _, _ = _resolve_oidc_metadata(app)
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


def exchange_code_for_userinfo(app, code: str, redirect_uri: str, expected_nonce: str) -> dict[str, Any]:
    _, token_url, userinfo_url, _, _ = _resolve_oidc_metadata(app)
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
    if not id_token:
        raise RuntimeError("OIDC id_token is required")

    id_claims = _verify_id_token(app, id_token=id_token, expected_nonce=expected_nonce)
    claims: dict[str, Any] = dict(id_claims)

    if access_token and userinfo_url:
        req = urllib.request.Request(
            userinfo_url,
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            userinfo_claims = json.loads(resp.read().decode("utf-8"))

        if userinfo_claims.get("sub") and claims.get("sub") and userinfo_claims.get("sub") != claims.get("sub"):
            raise RuntimeError("OIDC userinfo subject mismatch")
        claims.update({k: v for k, v in userinfo_claims.items() if v not in (None, "")})

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "preferred_username": claims.get("preferred_username") or claims.get("name"),
        "nickname": claims.get("name") or claims.get("preferred_username"),
    }
