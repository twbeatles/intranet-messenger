# -*- coding: utf-8 -*-
"""
Room and admin Socket.IO events.
"""

from __future__ import annotations

import logging

from flask import session
from flask_socketio import emit

from app.models import is_room_admin, is_room_member, set_room_admin, update_room_name
from app.services.socket_broadcasts import emit_admin_updated, emit_room_name_updated
from app.socket_events.shared import emit_error, ensure_session_token, parse_positive_int

logger = logging.getLogger(__name__)


def register_room_events(socketio):
    @socketio.on("room_name_updated")
    def handle_room_name_updated(data):
        try:
            if not ensure_session_token("room_name_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            new_name = (data or {}).get("name")
            if not room_id or not isinstance(new_name, str) or not new_name.strip():
                emit_error("Invalid request.")
                return
            if not is_room_admin(room_id, session["user_id"]):
                emit_error("관리자만 방 이름을 변경할 수 있습니다.")
                return
            if update_room_name(room_id, new_name.strip()):
                emit_room_name_updated(room_id, new_name.strip())
        except Exception as exc:
            logger.error(f"Room name update broadcast error: {exc}")

    @socketio.on("room_members_updated")
    def handle_room_members_updated(data):
        try:
            if not ensure_session_token("room_members_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            if not room_id:
                emit_error("Invalid request.")
                return
            if not is_room_member(room_id, session["user_id"]):
                emit_error("Room access denied.")
                return
            emit("room_members_updated", {"room_id": room_id}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Room members update broadcast error: {exc}")

    @socketio.on("admin_updated")
    def handle_admin_updated(data):
        try:
            if not ensure_session_token("admin_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            target_user_id = parse_positive_int(data or {}, "user_id")
            is_admin_flag = bool((data or {}).get("is_admin"))
            if not room_id or not target_user_id:
                emit_error("Invalid request.")
                return
            if not is_room_admin(room_id, session["user_id"]):
                emit_error("관리자만 권한을 변경할 수 있습니다.")
                return
            if set_room_admin(room_id, target_user_id, is_admin_flag):
                emit_admin_updated(room_id, target_user_id, is_admin_flag)
        except Exception as exc:
            logger.error(f"Admin update broadcast error: {exc}")
