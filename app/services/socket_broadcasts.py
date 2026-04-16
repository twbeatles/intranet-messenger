# -*- coding: utf-8 -*-
"""
Socket.IO emission helpers used by HTTP routes.
"""

from __future__ import annotations

import logging

from app.models import create_message, get_room_security_bundle
from app.socket_events.state import get_active_user_sids, invalidate_user_cache

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


def _emit_to_user_rooms(event: str, user_ids: list[int] | tuple[int, ...] | set[int], payload: dict) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    for user_id in {int(uid) for uid in user_ids if isinstance(uid, int) and uid > 0}:
        try:
            invalidate_user_cache(user_id)
            socketio_instance.emit(event, payload, to=f"user_{user_id}")
        except Exception as exc:
            logger.warning(f"{event} emit failed: user_id={user_id}, error={exc}")


def emit_room_list_updated(
    user_ids: list[int] | tuple[int, ...] | set[int],
    reason: str = "membership_changed",
) -> None:
    _emit_to_user_rooms("room_list_updated", user_ids, {"reason": reason})


def emit_room_access_revoked(user_id: int, room_id: int, reason: str) -> None:
    _emit_to_user_rooms("room_access_revoked", [user_id], {"room_id": room_id, "reason": reason})


def emit_room_security_updated(room_id: int, user_ids: list[int] | tuple[int, ...] | set[int]) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    for user_id in {int(uid) for uid in user_ids if isinstance(uid, int) and uid > 0}:
        try:
            payload = get_room_security_bundle(room_id, user_id)
            if not payload:
                continue
            invalidate_user_cache(user_id)
            socketio_instance.emit("room_security_updated", payload, to=f"user_{user_id}")
        except Exception as exc:
            logger.warning(f"room_security_updated emit failed: room_id={room_id}, user_id={user_id}, error={exc}")


def emit_room_name_updated(room_id: int, name: str) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    try:
        socketio_instance.emit("room_name_updated", {"room_id": room_id, "name": name}, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"room_name_updated emit failed: room_id={room_id}, error={exc}")


def emit_admin_updated(room_id: int, user_id: int, is_admin: bool) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    try:
        socketio_instance.emit(
            "admin_updated",
            {"room_id": room_id, "user_id": user_id, "is_admin": bool(is_admin)},
            to=f"room_{room_id}",
        )
    except Exception as exc:
        logger.warning(f"admin_updated emit failed: room_id={room_id}, user_id={user_id}, error={exc}")


def sync_user_room_membership(room_id: int, user_id: int, *, joined: bool) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    room_name = f"room_{room_id}"
    server = getattr(socketio_instance, "server", None)
    if server is None:
        return
    action = server.enter_room if joined else server.leave_room
    for sid in get_active_user_sids(user_id):
        try:
            action(sid, room_name, namespace="/")
        except Exception as exc:
            logger.warning(
                "room membership sync failed: room_id=%s, user_id=%s, joined=%s, error=%s",
                room_id,
                user_id,
                joined,
                exc,
            )


def emit_message_deleted(room_id: int, message_id: int) -> None:
    socketio_instance = get_socketio()
    if not socketio_instance:
        return
    try:
        socketio_instance.emit("message_deleted", {"message_id": message_id}, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"message_deleted emit failed: room_id={room_id}, message_id={message_id}, error={exc}")


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
        sys_msg = create_message(room_id, actor_user_id, content, "system", encrypted=False)
        if sys_msg and socketio_instance:
            socketio_instance.emit("new_message", sys_msg, to=f"room_{room_id}")
    except Exception as exc:
        logger.warning(f"pin system message emit failed: room_id={room_id}, error={exc}")
