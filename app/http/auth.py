# -*- coding: utf-8 -*-
"""
Authentication and account management HTTP endpoints.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session
from flask_wtf.csrf import generate_csrf

from app.extensions import csrf, limiter
from app.http.common import parse_json_payload, require_login
from app.models import authenticate_user, change_password, create_user, delete_user, get_db, get_room_members, log_access
from app.services.socket_broadcasts import emit_room_access_revoked, emit_room_list_updated, emit_room_members_updated, sync_user_room_membership

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/api/register")
@csrf.exempt
@limiter.limit("5 per minute")
def register():
    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    username = data.get("username", "").strip()
    password = data.get("password", "")
    nickname = data.get("nickname", "").strip() or username
    if not username or not password:
        return jsonify({"error": "아이디와 비밀번호를 입력해 주세요."}), 400

    from app.utils import validate_password, validate_username

    if not validate_username(username):
        return jsonify({"error": "아이디는 3-20자의 영문, 숫자, 밑줄만 사용할 수 있습니다."}), 400

    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    user_id = create_user(username, password, nickname)
    if user_id:
        log_access(user_id, "register", request.remote_addr, request.user_agent.string)
        return jsonify({"success": True, "user_id": user_id})
    return jsonify({"error": "이미 존재하는 아이디입니다."}), 400


@auth_bp.post("/api/login")
@csrf.exempt
@limiter.limit("10 per minute")
def login():
    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    user = authenticate_user(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["nickname"] = user.get("nickname", user["username"])
    session["session_token"] = user.get("session_token")
    log_access(user["id"], "login", request.remote_addr, request.user_agent.string)
    new_csrf_token = generate_csrf()
    return jsonify({"success": True, "user": user, "csrf_token": new_csrf_token})


@auth_bp.post("/api/logout")
@csrf.exempt
def logout():
    if "user_id" in session:
        log_access(session["user_id"], "logout", request.remote_addr, request.user_agent.string)
    session.clear()
    return jsonify({"success": True})


@auth_bp.put("/api/me/password")
def update_password():
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if not current_password or not new_password:
        return jsonify({"error": "입력값이 부족합니다."}), 400

    from app.utils import validate_password

    is_valid, error_msg = validate_password(new_password)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    success, error, new_session_token = change_password(session["user_id"], current_password, new_password)
    if not success:
        return jsonify({"error": error}), 400

    if new_session_token:
        session["session_token"] = new_session_token
    log_access(session["user_id"], "change_password", request.remote_addr, request.user_agent.string)
    return jsonify({"success": True, "message": "비밀번호가 변경되었습니다. 다른 기기에서는 세션이 로그아웃됩니다."})


@auth_bp.delete("/api/me")
def delete_account():
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    password = data.get("password")
    if not password:
        return jsonify({"error": "비밀번호를 입력해 주세요."}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT room_id FROM room_members WHERE user_id = ?", (session["user_id"],))
    affected_room_ids = [row["room_id"] for row in cursor.fetchall()]

    success, error = delete_user(session["user_id"], password)
    if not success:
        return jsonify({"error": error}), 400

    deleted_user_id = session["user_id"]
    for room_id in affected_room_ids:
        sync_user_room_membership(room_id, deleted_user_id, joined=False)
        emit_room_access_revoked(deleted_user_id, room_id, "deleted")
        emit_room_members_updated(room_id)
        remaining_user_ids = [member["id"] for member in get_room_members(room_id)]
        if remaining_user_ids:
            emit_room_list_updated(remaining_user_ids, "membership_changed")

    log_access(session["user_id"], "delete_account", request.remote_addr, request.user_agent.string)
    session.clear()
    return jsonify({"success": True})
