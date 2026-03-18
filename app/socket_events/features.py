# -*- coding: utf-8 -*-
"""
Pin and poll Socket.IO events.
"""

from __future__ import annotations

import logging

from flask import current_app, session
from flask_socketio import emit

from app.models import get_poll, is_room_member
from app.socket_events.shared import check_event_rate_limit, emit_error, ensure_session_token, parse_positive_int

logger = logging.getLogger(__name__)


def register_feature_events(socketio):
    @socketio.on("poll_updated")
    def handle_poll_updated(data):
        try:
            if not ensure_session_token("poll_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            poll_id = parse_positive_int(data or {}, "poll_id")
            if not poll_id:
                poll_payload = (data or {}).get("poll") if isinstance(data, dict) else None
                if isinstance(poll_payload, dict):
                    poll_id = parse_positive_int(poll_payload, "id")
            if not room_id or not poll_id:
                emit_error("Invalid request.")
                return
            if not is_room_member(room_id, session["user_id"]):
                emit_error("Room access denied.")
                return
            poll = get_poll(poll_id)
            if not poll or int(poll.get("room_id", 0)) != room_id:
                emit_error("Invalid request.")
                return
            emit("poll_updated", {"room_id": room_id, "poll": poll}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Poll update broadcast error: {exc}")

    @socketio.on("poll_created")
    def handle_poll_created(data):
        try:
            if not ensure_session_token("poll_created"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            poll_id = parse_positive_int(data or {}, "poll_id")
            if not poll_id:
                poll_payload = (data or {}).get("poll") if isinstance(data, dict) else None
                if isinstance(poll_payload, dict):
                    poll_id = parse_positive_int(poll_payload, "id")
            if not room_id or not poll_id:
                emit_error("Invalid request.")
                return
            if not is_room_member(room_id, session["user_id"]):
                emit_error("Room access denied.")
                return
            poll = get_poll(poll_id)
            if not poll or int(poll.get("room_id", 0)) != room_id:
                emit_error("Invalid request.")
                return
            emit("poll_created", {"room_id": room_id, "poll": poll}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Poll created broadcast error: {exc}")

    @socketio.on("pin_updated")
    def handle_pin_updated(data):
        try:
            if not ensure_session_token("pin_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            if not room_id:
                emit_error("Invalid request.")
                return
            if not is_room_member(room_id, session["user_id"]):
                emit_error("Room access denied.")
                return
            per_minute = int(current_app.config.get("SOCKET_PIN_UPDATED_PER_MINUTE", 30))
            if not check_event_rate_limit("pin_updated", session["user_id"], per_minute):
                emit_error("Too many requests.")
                return
            emit("pin_updated", {"room_id": room_id}, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Pin update broadcast error: {exc}")

