# -*- coding: utf-8 -*-
"""
Pins, polls, and advanced search HTTP endpoints.
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request, session

from app.extensions import limiter
from app.http.common import json_error, parse_int_from_json, parse_json_payload, require_login
from app.http.route_deps import get_routes_shim
from app.models import (
    close_poll,
    create_poll,
    get_pinned_messages,
    get_poll,
    get_room_polls,
    get_user_votes,
    is_room_admin,
    is_room_member,
    pin_message,
    unpin_message,
    vote_poll,
)
from app.services.socket_broadcasts import emit_pin_system_message, emit_pin_updated
from app.utils import sanitize_input

collaboration_bp = Blueprint("collaboration", __name__)


@collaboration_bp.get("/api/rooms/<int:room_id>/pins")
def get_room_pins(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    return jsonify(get_pinned_messages(room_id))


@collaboration_bp.post("/api/rooms/<int:room_id>/pins")
def create_pin(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    message_id = data.get("message_id")
    content = sanitize_input(data.get("content", ""), max_length=500)
    if not message_id and not content:
        return jsonify({"error": "고정할 메시지 또는 내용을 입력해 주세요."}), 400

    pin_id = pin_message(room_id, session["user_id"], message_id, content)
    if not pin_id:
        return jsonify({"error": "공지 고정에 실패했습니다."}), 500

    nickname = session.get("nickname", "User")
    emit_pin_system_message(room_id, session["user_id"], f"{nickname} pinned a message.")
    emit_pin_updated(room_id)
    return jsonify({"success": True, "pin_id": pin_id})


@collaboration_bp.delete("/api/rooms/<int:room_id>/pins/<int:pin_id>")
def delete_pin(room_id: int, pin_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    success, error = unpin_message(pin_id, session["user_id"], room_id)
    if success:
        nickname = session.get("nickname", "User")
        emit_pin_system_message(room_id, session["user_id"], f"{nickname} removed a pinned message.")
        emit_pin_updated(room_id)
        return jsonify({"success": True})
    if error and "찾을 수 없습니다" in error:
        return jsonify({"error": error}), 404
    if error and "일치하지 않습니다" in error:
        return jsonify({"error": error}), 403
    return jsonify({"error": error or "공지 해제에 실패했습니다."}), 400


@collaboration_bp.get("/api/rooms/<int:room_id>/polls")
def get_polls(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    polls = get_room_polls(room_id)
    for poll in polls:
        poll["my_votes"] = get_user_votes(poll["id"], session["user_id"])
    return jsonify(polls)


@collaboration_bp.post("/api/rooms/<int:room_id>/polls")
def create_poll_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    question = sanitize_input(data.get("question", ""), max_length=200)
    options = data.get("options", [])
    multiple_choice = data.get("multiple_choice", False)
    anonymous = data.get("anonymous", False)
    ends_at = data.get("ends_at")
    if not question:
        return jsonify({"error": "질문을 입력해 주세요."}), 400
    if len(options) < 2:
        return jsonify({"error": "최소 2개의 옵션이 필요합니다."}), 400

    if ends_at:
        try:
            ends_at_dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
            if ends_at_dt < datetime.now(ends_at_dt.tzinfo) if ends_at_dt.tzinfo else ends_at_dt < datetime.now():
                return jsonify({"error": "마감 시간은 현재 시간 이후여야 합니다."}), 400
            ends_at = ends_at_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({"error": "올바른 날짜/시간 형식이 아닙니다. (ISO 8601)"}), 400

    options = [sanitize_input(opt, max_length=100) for opt in options[:10]]
    poll_id = create_poll(room_id, session["user_id"], question, options, multiple_choice, anonymous, ends_at)
    if not poll_id:
        return jsonify({"error": "투표 생성에 실패했습니다."}), 500

    poll = get_poll(poll_id)
    if poll:
        return jsonify({"success": True, "poll": poll})
    return jsonify({"error": "투표 생성 후 조회에 실패했습니다."}), 500


@collaboration_bp.post("/api/polls/<int:poll_id>/vote")
def vote_poll_route(poll_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    poll = get_poll(poll_id)
    if not poll:
        return jsonify({"error": "투표를 찾을 수 없습니다."}), 404
    if not is_room_member(poll["room_id"], session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    option_id = data.get("option_id")
    if not option_id:
        return json_error("옵션을 선택해 주세요.", 400, "missing_option_id")

    success, error = vote_poll(poll_id, option_id, session["user_id"])
    if not success:
        return json_error(error or "투표 실패", 400, "invalid_poll_option")

    poll = get_poll(poll_id)
    if not poll:
        return json_error("Poll reload failed.", 500, "poll_reload_failed")
    poll["my_votes"] = get_user_votes(poll_id, session["user_id"])
    return jsonify({"success": True, "poll": poll})


@collaboration_bp.post("/api/polls/<int:poll_id>/close")
def close_poll_route(poll_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    poll = get_poll(poll_id)
    if not poll:
        return jsonify({"error": "투표를 찾을 수 없습니다."}), 404
    if not is_room_member(poll["room_id"], session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    success, error = close_poll(poll_id, session["user_id"], is_admin=is_room_admin(poll["room_id"], session["user_id"]))
    if success:
        return jsonify({"success": True})
    return jsonify({"error": error or "투표 마감에 실패했습니다."}), 403


@collaboration_bp.post("/api/search/advanced")
@limiter.limit("30 per minute")
def advanced_search_route():
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    limit, error_response = parse_int_from_json(data, "limit", 50, minimum=1, maximum=200)
    if error_response:
        return error_response
    offset, error_response = parse_int_from_json(data, "offset", 0, minimum=0)
    if error_response:
        return error_response

    routes_shim = get_routes_shim()
    results = routes_shim.advanced_search(
        user_id=session["user_id"],
        query=data.get("query"),
        room_id=data.get("room_id"),
        sender_id=data.get("sender_id"),
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        file_only=data.get("file_only", False),
        limit=limit,
        offset=offset,
    )
    return jsonify(results)
