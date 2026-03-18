# -*- coding: utf-8 -*-
"""
Socket.IO emission helpers used by HTTP routes.
"""

from __future__ import annotations

import logging

from app.models import create_message

logger = logging.getLogger(__name__)


def get_socketio():
    try:
        from app import socketio as socketio_instance

        return socketio_instance
    except Exception:
        return None


def emit_room_members_updated(room_id: int) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    try:
        socketio_instance.emit("room_members_updated", {"room_id": room_id}, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"room_members_updated emit failed: room_id={room_id}, error={exc}")


def emit_pin_updated(room_id: int) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    try:
        socketio_instance.emit("pin_updated", {"room_id": room_id}, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"pin_updated emit failed: room_id={room_id}, error={exc}")


def emit_pin_system_message(room_id: int, actor_user_id: int, content: str) -> None:
    socketio_instance = get_socketio()
    try:
        sys_msg = create_message(room_id, actor_user_id, content, "system")
        if sys_msg and socketio_instance:
            socketio_instance.emit("new_message", sys_msg, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"pin system message emit failed: room_id={room_id}, error={exc}")
