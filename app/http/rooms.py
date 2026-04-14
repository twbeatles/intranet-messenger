# -*- coding: utf-8 -*-
"""
Room, membership, and admin HTTP endpoints.
"""

from __future__ import annotations

import csv
import io
import logging

from flask import Blueprint, jsonify, make_response, request, session

from app.http.common import parse_json_payload, require_login, truthy_param
from app.models import (
    add_room_member,
    get_admin_audit_logs,
    get_all_users,
    get_online_users,
    get_room_admins,
    get_room_by_id,
    get_room_key,
    get_room_members,
    get_room_messages,
    get_room_last_reads,
    get_unread_count,
    get_user_by_id,
    get_user_rooms,
    is_room_admin,
    is_room_member,
    kick_member as kick_member_db,
    leave_room_db,
    log_admin_action,
    mute_room,
    pin_room,
    set_room_admin,
    update_room_name,
    create_room,
)
from app.services.socket_broadcasts import (
    emit_room_access_revoked,
    emit_room_list_updated,
    emit_room_members_updated,
    sync_user_room_membership,
)
from app.utils import sanitize_input

logger = logging.getLogger(__name__)

rooms_bp = Blueprint("rooms", __name__)


def _room_member_ids(room_id: int) -> list[int]:
    return [member["id"] for member in get_room_members(room_id)]


@rooms_bp.get("/api/users")
def get_users():
    login_error = require_login()
    if login_error:
        return login_error
    users = get_all_users()
    return jsonify([u for u in users if u["id"] != session["user_id"]])


@rooms_bp.get("/api/rooms")
def get_rooms():
    login_error = require_login()
    if login_error:
        return login_error
    include_members = truthy_param(request.args.get("include_members"))
    rooms = get_user_rooms(session["user_id"], include_members=include_members)
    return jsonify(rooms)


@rooms_bp.post("/api/rooms")
def create_room_route():
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    has_members = "members" in data
    has_member_ids = "member_ids" in data
    if has_members:
        raw_members = data.get("members")
        if has_member_ids:
            logger.warning("Both members and member_ids were provided; members will be used.")
    else:
        raw_members = data.get("member_ids", [])

    if raw_members is None:
        raw_members = []
    if not isinstance(raw_members, list):
        return jsonify({"error": "members 또는 member_ids는 배열이어야 합니다."}), 400

    normalized_members = []
    seen = set()
    for value in raw_members:
        try:
            member_id = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "멤버 ID는 정수여야 합니다."}), 400
        if member_id <= 0 or member_id in seen:
            continue
        seen.add(member_id)
        normalized_members.append(member_id)

    if session["user_id"] not in seen:
        normalized_members.append(session["user_id"])
        seen.add(session["user_id"])

    member_ids = [uid for uid in normalized_members if get_user_by_id(uid)]
    if session["user_id"] not in member_ids:
        member_ids.append(session["user_id"])

    room_type = "direct" if len(member_ids) == 2 else "group"
    name = data.get("name", "")

    try:
        created_room_id = create_room(name, room_type, session["user_id"], member_ids)
        if not created_room_id:
            raise RuntimeError("room_id missing after create_room")
        room_id = int(created_room_id)
        for member_id in member_ids:
            sync_user_room_membership(room_id, member_id, joined=True)
        emit_room_list_updated([session["user_id"]], "room_created")
        invited_user_ids = [member_id for member_id in member_ids if member_id != session["user_id"]]
        if invited_user_ids:
            emit_room_list_updated(invited_user_ids, "room_invited")
        return jsonify({"success": True, "room_id": room_id})
    except Exception as exc:
        logger.error(f"Room creation failed: {exc}")
        return jsonify({"error": "대화방 생성에 실패했습니다."}), 500


@rooms_bp.post("/api/rooms/<int:room_id>/members")
def invite_member(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    user_ids = data.get("user_ids", [])
    user_id = data.get("user_id")
    if user_id:
        user_ids = [user_id]

    valid_user_ids = [uid for uid in user_ids if get_user_by_id(uid)]
    added = 0
    added_user_ids: list[int] = []
    for uid in valid_user_ids:
        if add_room_member(room_id, uid):
            added += 1
            added_user_ids.append(uid)

    if added > 0:
        for user_id_to_join in added_user_ids:
            sync_user_room_membership(room_id, user_id_to_join, joined=True)
        emit_room_members_updated(room_id)
        emit_room_list_updated(added_user_ids, "room_invited")
        remaining_user_ids = [user_id for user_id in _room_member_ids(room_id) if user_id not in added_user_ids]
        if remaining_user_ids:
            emit_room_list_updated(remaining_user_ids, "membership_changed")
        return jsonify({"success": True, "added_count": added})
    return jsonify({"error": "이미 참여 중인 사용자입니다."}), 400


@rooms_bp.post("/api/rooms/<int:room_id>/leave")
def leave_room_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error

    user_id = session["user_id"]
    if not is_room_member(room_id, user_id):
        return jsonify({"success": True, "left": False, "already_left": True})

    leave_room_db(room_id, user_id)
    sync_user_room_membership(room_id, user_id, joined=False)
    emit_room_access_revoked(user_id, room_id, "left")
    emit_room_list_updated([user_id], "room_left")
    emit_room_members_updated(room_id)
    remaining_user_ids = _room_member_ids(room_id)
    if remaining_user_ids:
        emit_room_list_updated(remaining_user_ids, "membership_changed")
    return jsonify({"success": True, "left": True, "already_left": False})


@rooms_bp.delete("/api/rooms/<int:room_id>/members/<int:target_user_id>")
def kick_member(room_id: int, target_user_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_admin(room_id, session["user_id"]):
        return jsonify({"error": "관리자만 멤버를 강퇴할 수 있습니다."}), 403
    if target_user_id == session["user_id"]:
        return jsonify({"error": "자신은 강퇴할 수 없습니다."}), 400
    if is_room_admin(room_id, target_user_id):
        return jsonify({"error": "관리자는 강퇴할 수 없습니다."}), 403
    if not is_room_member(room_id, target_user_id):
        return jsonify({"error": "해당 사용자는 대화방 멤버가 아닙니다."}), 400

    kick_member_db(room_id, target_user_id)
    sync_user_room_membership(room_id, target_user_id, joined=False)
    emit_room_access_revoked(target_user_id, room_id, "kicked")
    emit_room_list_updated([target_user_id], "room_kicked")
    emit_room_members_updated(room_id)
    remaining_user_ids = _room_member_ids(room_id)
    if remaining_user_ids:
        emit_room_list_updated(remaining_user_ids, "membership_changed")
    log_admin_action(
        room_id=room_id,
        actor_user_id=session["user_id"],
        target_user_id=target_user_id,
        action="kick_member",
        metadata={"source": "api"},
    )
    return jsonify({"success": True})


@rooms_bp.put("/api/rooms/<int:room_id>/name")
def update_room_name_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403
    if not is_room_admin(room_id, session["user_id"]):
        return jsonify({"error": "관리자만 대화방 이름을 변경할 수 있습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    new_name = sanitize_input(data.get("name", ""), max_length=50)
    if not new_name:
        return jsonify({"error": "대화방 이름을 입력해 주세요."}), 400

    update_room_name(room_id, new_name)
    return jsonify({"success": True})


@rooms_bp.post("/api/rooms/<int:room_id>/pin-room")
@rooms_bp.post("/api/rooms/<int:room_id>/pin")
def pin_room_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    pinned = data.get("pinned", True)
    if pin_room(session["user_id"], room_id, pinned):
        return jsonify({"success": True})
    return jsonify({"error": "설정 변경에 실패했습니다."}), 400


@rooms_bp.post("/api/rooms/<int:room_id>/mute")
def mute_room_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response
    muted = data.get("muted", True)
    if mute_room(session["user_id"], room_id, muted):
        return jsonify({"success": True})
    return jsonify({"error": "설정 변경에 실패했습니다."}), 400


@rooms_bp.get("/api/users/online")
def get_online_users_route():
    login_error = require_login()
    if login_error:
        return login_error
    users = get_online_users()
    return jsonify([u for u in users if u["id"] != session["user_id"]])


@rooms_bp.get("/api/rooms/<int:room_id>/info")
def get_room_info(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403

    room = get_room_by_id(room_id)
    if not room:
        return jsonify({"error": "대화방을 찾을 수 없습니다."}), 404

    members = get_room_members(room_id)
    room["members"] = members
    room.pop("encryption_key", None)
    return jsonify(room)


@rooms_bp.get("/api/rooms/<int:room_id>/admins")
def get_admins(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    return jsonify(get_room_admins(room_id))


@rooms_bp.post("/api/rooms/<int:room_id>/admins")
def set_admin_route(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_admin(room_id, session["user_id"]):
        return jsonify({"error": "관리자 권한이 필요합니다."}), 403

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    target_user_id = data.get("user_id")
    is_admin = data.get("is_admin", True)
    if not target_user_id:
        return jsonify({"error": "사용자를 선택해 주세요."}), 400

    if not is_admin and len(get_room_admins(room_id)) <= 1:
        return jsonify({"error": "최소 한 명의 관리자가 필요합니다."}), 400

    if set_room_admin(room_id, target_user_id, is_admin):
        log_admin_action(
            room_id=room_id,
            actor_user_id=session["user_id"],
            target_user_id=target_user_id,
            action="set_admin" if is_admin else "unset_admin",
            metadata={"source": "api"},
        )
        return jsonify({"success": True})
    return jsonify({"error": "관리자 설정에 실패했습니다."}), 500


@rooms_bp.get("/api/rooms/<int:room_id>/admin-check")
def check_admin(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    return jsonify({"is_admin": is_room_admin(room_id, session["user_id"])})


@rooms_bp.get("/api/rooms/<int:room_id>/admin-audit-logs")
def room_admin_audit_logs(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_admin(room_id, session["user_id"]):
        return jsonify({"error": "관리자 권한이 필요합니다."}), 403

    output_format = (request.args.get("format") or "json").lower()
    limit = request.args.get("limit", type=int) or 200
    offset = request.args.get("offset", type=int) or 0
    logs = get_admin_audit_logs(room_id=room_id, limit=limit, offset=offset)
    if output_format != "csv":
        return jsonify({"logs": logs, "limit": limit, "offset": offset})

    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "room_id", "actor_user_id", "actor_nickname", "target_user_id", "target_nickname", "action", "metadata", "created_at"])
    for row in logs:
        writer.writerow(
            [
                row.get("id"),
                row.get("room_id"),
                row.get("actor_user_id"),
                row.get("actor_nickname"),
                row.get("target_user_id"),
                row.get("target_nickname"),
                row.get("action"),
                row.get("metadata"),
                row.get("created_at"),
            ]
        )
    response = make_response(stream.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename=room_{room_id}_admin_audit_logs.csv"
    return response
