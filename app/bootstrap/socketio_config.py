# -*- coding: utf-8 -*-
"""
Socket.IO configuration.
"""

from __future__ import annotations

from importlib import import_module

from flask_socketio import SocketIO

try:
    from config import ASYNC_MODE, MAX_HTTP_BUFFER_SIZE, MESSAGE_QUEUE, PING_INTERVAL, PING_TIMEOUT, SOCKETIO_CORS_ALLOWED_ORIGINS
except ImportError:
    from config import *  # type: ignore  # noqa: F403,F401


def create_socketio(app, *, gevent_available: bool, logger):
    async_mode = None
    if gevent_available:
        try:
            import gevent  # noqa: F401
            from gevent import pywsgi  # noqa: F401

            async_mode = "gevent"
            logger.info("gevent 비동기 모드 활성화 (고성능 동시 접속 지원)")
        except ImportError:
            logger.warning("gevent를 찾을 수 없습니다. 다른 모드로 대체합니다.")

    if async_mode is None and ASYNC_MODE == "eventlet":
        try:
            eventlet = import_module("eventlet")
            eventlet.monkey_patch()
            async_mode = "eventlet"
            logger.info("eventlet 비동기 모드 활성화")
        except ImportError:
            logger.warning("eventlet을 찾을 수 없습니다. 다른 모드로 대체합니다.")

    if async_mode is None:
        try:
            import simple_websocket  # noqa: F401
            import engineio.async_drivers.threading  # noqa: F401

            async_mode = "threading"
            logger.info("threading 비동기 모드 활성화 (동시 접속 제한적)")
        except ImportError:
            async_mode = None

    kwargs = {
        "ping_timeout": PING_TIMEOUT,
        "ping_interval": PING_INTERVAL,
        "max_http_buffer_size": MAX_HTTP_BUFFER_SIZE,
        "async_mode": async_mode,
        "logger": False,
        "engineio_logger": False,
    }
    if SOCKETIO_CORS_ALLOWED_ORIGINS is not None:
        kwargs["cors_allowed_origins"] = SOCKETIO_CORS_ALLOWED_ORIGINS
    if MESSAGE_QUEUE:
        kwargs["message_queue"] = MESSAGE_QUEUE
        logger.info(f"메시지 큐 활성화: {MESSAGE_QUEUE}")

    try:
        socketio = SocketIO(app, **kwargs)
        logger.info(f"Socket.IO 초기화 완료 (모드: {async_mode or 'default'})")
    except ValueError as exc:
        logger.warning(f"Socket.IO 초기화 경고: {exc}, 기본 모드로 재시도")
        socketio = SocketIO(app, logger=False, engineio_logger=False)
    return socketio

