# -*- coding: utf-8 -*-
"""
Room and admin Socket.IO events.
"""

from __future__ import annotations

import logging

from flask import session
from flask_socketio import emit

from app.models import create_message, is_room_admin, is_room_member
from app.socket_events.shared import emit_error, ensure_session_token, parse_positive_int

logger = logging.getLogger(__name__)


def register_room_events(socketio):
    @socketio.on("room_name_updated")
    def handle_room_name_updated(data):
        try:
            if not ensure_session_token("room_name_updated"):
                return
            room_id = data.get("room_id")
            new_name = data.get("name")
            if room_id and new_name and "user_id" in session:
                if not is_room_admin(room_id, session["user_id"]):
                    emit_error("관리자만 방 이름을 변경할 수 있습니다.")
                    return
                nickname = session.get("nickname", "사용자")
                content = f"{nickname}님이 방 이름을 '{new_name}'(으)로 변경했습니다."
                sys_msg = create_message(room_id, session["user_id"], content, "system")
                if sys_msg:
                    emit("new_message", sys_msg, to=f"room_{room_id}")
                emit("room_name_updated", {"room_id": room_id, "name": new_name}, to=f"room_{room_id}")
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
            room_id = data.get("room_id")
            target_user_id = data.get("user_id")
            is_admin_flag = data.get("is_admin")
            if room_id and target_user_id is not None and "user_id" in session:
                if not is_room_admin(room_id, session["user_id"]):
                    emit_error("관리자만 권한을 변경할 수 있습니다.")
                    return
                emit("admin_updated", {"room_id": room_id, "user_id": target_user_id, "is_admin": is_admin_flag}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Admin update broadcast error: {exc}")

