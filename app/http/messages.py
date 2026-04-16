# -*- coding: utf-8 -*-
"""
Message and search HTTP endpoints.
"""

from __future__ import annotations

import logging
from bisect import bisect_left

from flask import Blueprint, jsonify, request, session

from app.extensions import limiter
from app.http.common import parse_json_payload, require_login
from app.http.route_deps import get_routes_shim
from app.models import (
    advanced_search,
    delete_message,
    edit_message,
    get_message_reactions,
    get_message_room_id,
    get_room_last_reads,
    get_room_members,
    get_room_messages,
    get_room_security_bundle,
    is_room_member,
    toggle_reaction,
)

logger = logging.getLogger(__name__)

messages_bp = Blueprint("messages", __name__)


@messages_bp.get("/api/rooms/<int:room_id>/messages")
def get_messages(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "방 접근 권한이 없습니다."}), 403

    try:
        before_id = request.args.get("before_id", type=int)
        limit = request.args.get("limit", type=int) or 50
        limit = max(1, min(limit, 200))
        include_meta = str(request.args.get("include_meta", "1")).lower() in ("1", "true", "yes")

        messages = get_room_messages(room_id, viewer_user_id=session["user_id"], before_id=before_id, limit=limit)
        members = get_room_members(room_id) if include_meta else None
        security = get_room_security_bundle(room_id, session["user_id"]) if include_meta else None

        if messages:
            if include_meta and members:
                for message in messages:
                    message_version = int(message.get("key_version") or 1)
                    unread = 0
                    for member in members:
                        if int(member.get("joined_key_version") or 1) > message_version:
                            continue
                        if member.get("id") == message["sender_id"]:
                            continue
                        if (member.get("last_read_message_id") or 0) < message["id"]:
                            unread += 1
                    message["unread_count"] = unread
            else:
                user_last_read = {}
                last_read_ids = []
                for last_read, uid in get_room_last_reads(room_id):
                    value = last_read or 0
                    user_last_read[uid] = value
                    last_read_ids.append(value)

                last_read_ids.sort()
                for message in messages:
                    sender_id = message["sender_id"]
                    message_id = message["id"]
                    unread = bisect_left(last_read_ids, message_id)
                    sender_last_read = user_last_read.get(sender_id, 0)
                    if sender_last_read < message_id:
                        unread -= 1
                    message["unread_count"] = max(unread, 0)

        response: dict[str, object] = {"messages": messages}
        if include_meta:
            response["members"] = members
            response["encryption_key"] = security.get("encryption_key") if security else None
            response["encryption_keys"] = security.get("encryption_keys") if security else {}
            response["key_version"] = security.get("key_version") if security else 1
            response["member_key_version"] = security.get("member_key_version") if security else 1
        return jsonify(response)
    except Exception as exc:
        logger.error(f"메시지 로드 오류: {exc}")
        return jsonify({"error": "메시지 로드 실패"}), 500


@messages_bp.delete("/api/messages/<int:message_id>")
def delete_message_route(message_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    success, result = delete_message(message_id, session["user_id"])
    if success:
        return jsonify({"success": True, "room_id": result})
    return jsonify({"error": result}), 403


@messages_bp.put("/api/messages/<int:message_id>")
def edit_message_route(message_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    new_content = data.get("content", "")
    if not new_content:
        return jsonify({"error": "메시지 내용을 입력해 주세요."}), 400

    success, error, room_id, key_version = edit_message(message_id, session["user_id"], new_content)
    if success:
        return jsonify({"success": True, "room_id": room_id, "key_version": key_version})
    return jsonify({"error": error}), 403


@messages_bp.get("/api/search")
@limiter.limit("30 per minute")
def search():
    login_error = require_login()
    if login_error:
        return login_error

    query = request.args.get("q")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    file_only = str(request.args.get("file_only", "")).lower() in ("1", "true", "yes")
    room_id = request.args.get("room_id", type=int)
    offset = request.args.get("offset", type=int)
    limit = request.args.get("limit", type=int)
    offset = max(offset if offset is not None else 0, 0)
    limit = min(max(limit if limit is not None else 50, 1), 200)

    if (not query or not query.strip()) and not date_from and not date_to and not file_only:
        return jsonify([])

    q = (query or "").strip()
    if q and len(q) < 2:
        return jsonify([])

    routes_shim = get_routes_shim()
    results = routes_shim.advanced_search(
        user_id=session["user_id"],
        query=(q or None),
        room_id=room_id,
        date_from=(date_from or None),
        date_to=(date_to or None),
        file_only=file_only,
        limit=limit,
        offset=offset,
    )
    return jsonify(results.get("messages", []))


@messages_bp.get("/api/messages/<int:message_id>/reactions")
def get_reactions(message_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    room_id = get_message_room_id(message_id)
    if room_id is None or not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "방 접근 권한이 없습니다."}), 403
    return jsonify(get_message_reactions(message_id))


@messages_bp.post("/api/messages/<int:message_id>/reactions")
def add_reaction_route(message_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    room_id = get_message_room_id(message_id)
    if room_id is None or not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "방 접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    emoji = data.get("emoji", "")
    if not emoji or len(emoji) > 10:
        return jsonify({"error": "유효하지 않은 이모지입니다."}), 400

    success, action = toggle_reaction(message_id, session["user_id"], emoji)
    if not success:
        return jsonify({"error": "리액션 추가에 실패했습니다."}), 500
    return jsonify({"success": True, "action": action, "reactions": get_message_reactions(message_id)})
