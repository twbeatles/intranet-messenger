# -*- coding: utf-8 -*-
"""
Connection and room-subscription Socket.IO events.
"""

from __future__ import annotations

import logging

from flask import session
from flask_socketio import emit, join_room, leave_room

from app.models import is_room_member, server_stats, update_user_status
from app.socket_events.shared import ensure_session_token, request_sid
from app.socket_events.state import (
    cleanup_old_cache,
    get_user_room_ids,
    invalidate_user_cache,
    online_users,
    online_users_lock,
    stats_lock,
    typing_last_emit,
    typing_rate_lock,
    user_cache,
    user_sids,
)
from app.state_store import state_store

logger = logging.getLogger(__name__)


def register_connection_events(socketio):
    @socketio.on("connect")
    def handle_connect():
        if not ensure_session_token("connect"):
            return False

        user_id = session.get("user_id")
        if not user_id:
            return False

        sid = request_sid()
        with online_users_lock:
            online_users[sid] = user_id
            user_sids.setdefault(user_id, []).append(sid)
        was_offline = state_store.incr(f"presence:user:{user_id}") == 1

        try:
            join_room(f"user_{user_id}")
        except Exception:
            pass

        room_ids = get_user_room_ids(user_id)
        for room_id in room_ids:
            try:
                join_room(f"room_{room_id}")
            except Exception:
                pass

        if was_offline:
            update_user_status(user_id, "online")
            for room_id in room_ids:
                emit("user_status", {"user_id": user_id, "status": "online"}, to=f"room_{room_id}")

        with stats_lock:
            server_stats["total_connections"] += 1
            server_stats["active_connections"] += 1
            should_cleanup = server_stats["total_connections"] % 100 == 0
        if should_cleanup:
            cleanup_old_cache()

    @socketio.on("disconnect")
    def handle_disconnect():
        user_id = None
        still_online = False
        sid = request_sid()
        room_ids = []

        with online_users_lock:
            user_id = online_users.pop(sid, None)
            if user_id and user_id in user_sids:
                if sid in user_sids[user_id]:
                    user_sids[user_id].remove(sid)
                local_still_online = len(user_sids[user_id]) > 0
                if not local_still_online:
                    del user_sids[user_id]
                    if user_id in user_cache:
                        room_ids = user_cache[user_id].get("rooms", []).copy()
        if user_id:
            still_online = state_store.decr(f"presence:user:{user_id}") > 0

        if user_id and not still_online:
            update_user_status(user_id, "offline")
            if not room_ids:
                room_ids = get_user_room_ids(user_id)
            try:
                for room_id in room_ids:
                    emit("user_status", {"user_id": user_id, "status": "offline"}, to=f"room_{room_id}")
            except Exception as exc:
                logger.error(f"Disconnect broadcast error: {exc}")

            with typing_rate_lock:
                keys_to_remove = [key for key in typing_last_emit if key[0] == user_id]
                for key in keys_to_remove:
                    del typing_last_emit[key]

        with stats_lock:
            server_stats["active_connections"] = max(0, server_stats["active_connections"] - 1)

    @socketio.on("subscribe_rooms")
    def handle_subscribe_rooms(data):
        try:
            if not ensure_session_token("subscribe_rooms"):
                return
            room_ids = data.get("room_ids") if isinstance(data, dict) else None
            if not isinstance(room_ids, list):
                return
            room_ids = [rid for rid in room_ids if isinstance(rid, int) and rid > 0]
            if not room_ids:
                return

            user_id = session["user_id"]
            allowed = set(get_user_room_ids(user_id))
            for room_id in room_ids:
                if room_id in allowed:
                    join_room(f"room_{room_id}")
                    continue
                if is_room_member(room_id, user_id):
                    invalidate_user_cache(user_id)
                    join_room(f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Subscribe rooms error: {exc}")

    @socketio.on("join_room")
    def handle_join_room(data):
        try:
            if not ensure_session_token("join_room"):
                return
            room_id = data.get("room_id")
            if room_id and "user_id" in session:
                user_rooms = get_user_room_ids(session["user_id"])
                if room_id in user_rooms:
                    join_room(f"room_{room_id}")
                    emit("joined_room", {"room_id": room_id})
                elif is_room_member(room_id, session["user_id"]):
                    invalidate_user_cache(session["user_id"])
                    join_room(f"room_{room_id}")
                    emit("joined_room", {"room_id": room_id})
                else:
                    from app.socket_events.shared import emit_error

                    emit_error("대화방 접근 권한이 없습니다.")
        except Exception as exc:
            logger.error(f"Join room error: {exc}")

    @socketio.on("leave_room")
    def handle_leave_room(data):
        try:
            if not ensure_session_token("leave_room"):
                return
            room_id = data.get("room_id")
            if room_id:
                leave_room(f"room_{room_id}")
                if "user_id" in session:
                    invalidate_user_cache(session["user_id"])
        except Exception as exc:
            logger.error(f"Leave room error: {exc}")
