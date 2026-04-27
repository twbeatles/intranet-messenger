# -*- coding: utf-8 -*-
"""
Room Socket.IO refresh events.
"""

from __future__ import annotations

import logging

from flask import session
from flask_socketio import emit

from app.models import is_room_member
from app.socket_events.shared import emit_error, ensure_session_token, parse_positive_int

logger = logging.getLogger(__name__)


def register_room_events(socketio):
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
