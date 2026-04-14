# -*- coding: utf-8 -*-
"""
Presence and profile Socket.IO events.
"""

from __future__ import annotations

import logging
import time

from flask import session
from flask_socketio import emit

from app.models import get_message_room_id, get_user_by_id, is_room_member, update_last_read
from app.socket_events.shared import ensure_session_token
from app.socket_events.state import TYPING_RATE_LIMIT, typing_last_emit, typing_rate_lock

logger = logging.getLogger(__name__)


def register_presence_events(socketio):
    @socketio.on("message_read")
    def handle_message_read(data):
        try:
            if not ensure_session_token("message_read"):
                return
            room_id = data.get("room_id")
            message_id = data.get("message_id")
            if room_id and message_id:
                if not is_room_member(room_id, session["user_id"]):
                    return
                if get_message_room_id(message_id) != room_id:
                    return
                update_last_read(room_id, session["user_id"], message_id)
                emit("read_updated", {"room_id": room_id, "user_id": session["user_id"], "message_id": message_id}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Message read error: {exc}")

    @socketio.on("typing")
    def handle_typing(data):
        try:
            if not ensure_session_token("typing"):
                return
            room_id = data.get("room_id")
            if not room_id:
                return

            user_id = session["user_id"]
            if not is_room_member(room_id, user_id):
                return

            current_time = time.time()
            rate_key = (user_id, room_id)
            with typing_rate_lock:
                last_emit = typing_last_emit.get(rate_key, 0)
                if current_time - last_emit < TYPING_RATE_LIMIT:
                    return
                typing_last_emit[rate_key] = current_time
                if len(typing_last_emit) > 1000:
                    expired = [key for key, value in typing_last_emit.items() if current_time - value > 300]
                    for key in expired:
                        del typing_last_emit[key]

            nickname = session.get("nickname", "")
            if not nickname:
                user = get_user_by_id(user_id)
                nickname = user.get("nickname", "사용자") if user else "사용자"

            emit(
                "user_typing",
                {"room_id": room_id, "user_id": user_id, "nickname": nickname, "is_typing": data.get("is_typing", False)},
                to=f"room_{room_id}",
                include_self=False,
            )
        except Exception as exc:
            logger.error(f"Typing event error: {exc}")

    @socketio.on("profile_updated")
    def handle_profile_updated(data):
        try:
            if not ensure_session_token("profile_updated"):
                return
            user_id = session.get("user_id")
            if not user_id:
                return
            user = get_user_by_id(user_id)
            if not user:
                return

            emit(
                "user_profile_updated",
                {
                    "user_id": user_id,
                    "nickname": user.get("nickname"),
                    "profile_image": user.get("profile_image"),
                    "status_message": user.get("status_message"),
                },
                broadcast=True,
                include_self=False,
            )
            logger.info(f"Profile updated broadcast: user_id={user_id}")
        except Exception as exc:
            logger.error(f"Profile update broadcast error: {exc}")
