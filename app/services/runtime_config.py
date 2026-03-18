# -*- coding: utf-8 -*-
"""
Runtime configuration payload helpers shared by HTTP handlers.
"""

from __future__ import annotations


def get_max_upload_size(app, default_max_size: int) -> int:
    return int(app.config.get("MAX_CONTENT_LENGTH") or default_max_size or 16 * 1024 * 1024)


def build_public_config(app, *, default_max_size: int, default_socket_send_per_minute: int) -> dict:
    return {
        "upload": {
            "max_size_bytes": get_max_upload_size(app, default_max_size),
        },
        "rate_limits": {
            "login": "10/min",
            "register": "5/min",
            "upload": "10/min",
            "search_advanced": "30/min",
            "socket_send_message": f"{int(app.config.get('SOCKET_SEND_MESSAGE_PER_MINUTE', default_socket_send_per_minute))}/min",
            "socket_pin_updated": f"{int(app.config.get('SOCKET_PIN_UPDATED_PER_MINUTE', 30))}/min",
        },
        "features": {
            "oidc": bool(app.config.get("FEATURE_OIDC_ENABLED")),
            "av": bool(app.config.get("FEATURE_AV_SCAN_ENABLED")),
            "redis": bool(app.config.get("FEATURE_REDIS_ENABLED")),
        },
    }

