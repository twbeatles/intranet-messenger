# -*- coding: utf-8 -*-
"""
사내 메신저 앱 패키지
Flask 앱 팩토리 패턴
"""

from __future__ import annotations

import logging
import os

_SKIP_GEVENT = os.environ.get("SKIP_GEVENT_PATCH", "0") == "1"
_GEVENT_AVAILABLE = False
_GEVENT_ALREADY_PATCHED = False

try:
    from gevent import monkey

    _GEVENT_ALREADY_PATCHED = monkey.is_module_patched("socket")
    if _GEVENT_ALREADY_PATCHED:
        _GEVENT_AVAILABLE = True
except ImportError:
    pass

if not _SKIP_GEVENT and not _GEVENT_ALREADY_PATCHED:
    try:
        from gevent import monkey

        monkey.patch_all()
        _GEVENT_AVAILABLE = True
    except ImportError:
        _GEVENT_AVAILABLE = False

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        os.path.join(BASE_DIR, "server.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )
except (PermissionError, OSError):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

logger = logging.getLogger(__name__)
socketio = None


def create_app():
    global socketio

    from app.factory import build_app

    app, socketio_instance = build_app(gevent_available=_GEVENT_AVAILABLE, logger=logger)
    socketio = socketio_instance
    return app, socketio_instance


__all__ = ["create_app", "socketio"]
