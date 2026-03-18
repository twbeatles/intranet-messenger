# -*- coding: utf-8 -*-
"""
Application factory orchestration.
"""

from __future__ import annotations

from app.bootstrap.hooks import register_hooks
from app.bootstrap.runtime import build_flask_app
from app.bootstrap.socketio_config import create_socketio
from app.bootstrap.workers import initialize_runtime
from app.extensions import compress, csrf, limiter
from app.routes import register_routes
from app.sockets import register_socket_events

try:
    from config import APP_NAME, VERSION
except ImportError:
    APP_NAME = "Intranet Messenger"
    VERSION = "dev"


def build_app(*, gevent_available: bool, logger):
    app = build_flask_app()
    socketio = create_socketio(app, gevent_available=gevent_available, logger=logger)

    register_routes(app)
    limiter.init_app(app)
    csrf.init_app(app)
    compress.init_app(app)
    register_socket_events(socketio)
    register_hooks(app)
    initialize_runtime(app, socketio, logger)

    logger.info(f"{APP_NAME} v{VERSION} 앱 초기화 완료")
    return app, socketio
