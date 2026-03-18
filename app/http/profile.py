# -*- coding: utf-8 -*-
"""
Profile HTTP endpoints.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session

from app.http.common import parse_json_payload, require_login
from app.models import get_user_by_id, safe_file_delete, update_user_profile
from app.utils import sanitize_input, validate_file_header

try:
    from config import UPLOAD_FOLDER
except ImportError:
    UPLOAD_FOLDER = "uploads"

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)


@profile_bp.get("/api/profile")
def get_profile():
    login_error = require_login()
    if login_error:
        return login_error
    user = get_user_by_id(session["user_id"])
    if user:
        return jsonify(user)
    return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404


@profile_bp.put("/api/profile")
def update_profile():
    login_error = require_login()
    if login_error:
        return login_error

    data, error_response = parse_json_payload()
    if error_response:
        return error_response

    nickname = sanitize_input(data.get("nickname", ""), max_length=20)
    status_message = sanitize_input(data.get("status_message", ""), max_length=100)
    if nickname and len(nickname) < 2:
        return jsonify({"error": "닉네임은 2자 이상이어야 합니다."}), 400

    success = update_user_profile(
        session["user_id"],
        nickname=nickname if nickname else None,
        status_message=status_message if status_message else None,
    )
    if not success:
        return jsonify({"error": "프로필 업데이트에 실패했습니다."}), 500

    if nickname:
        session["nickname"] = nickname
    return jsonify({"success": True})


@profile_bp.post("/api/profile/image")
def upload_profile_image():
    login_error = require_login()
    if login_error:
        return login_error

    upload_folder = current_app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER)
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    original_filename = file.filename or ""
    if original_filename == "":
        return jsonify({"error": "파일을 선택하지 않았습니다."}), 400

    allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext not in allowed_extensions:
        return jsonify({"error": "이미지 파일만 업로드 가능합니다."}), 400
    if not validate_file_header(file):
        return jsonify({"error": "유효하지 않은 이미지 파일입니다."}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        return jsonify({"error": "파일 크기는 5MB 이하여야 합니다."}), 400

    profile_folder = os.path.join(upload_folder, "profiles")
    os.makedirs(profile_folder, exist_ok=True)

    user = get_user_by_id(session["user_id"])
    if user and user.get("profile_image"):
        try:
            old_image_path = os.path.join(upload_folder, user["profile_image"])
            if safe_file_delete(old_image_path):
                logger.debug(f"Old profile image deleted: {user['profile_image']}")
        except Exception as exc:
            logger.warning(f"Old profile image deletion failed: {exc}")

    filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(profile_folder, filename)
    file.save(file_path)

    try:
        profile_image = f"profiles/{filename}"
        success = update_user_profile(session["user_id"], profile_image=profile_image)
        if success:
            return jsonify({"success": True, "profile_image": profile_image})
        return jsonify({"error": "프로필 이미지 데이터베이스 업데이트 실패"}), 500
    except Exception as exc:
        logger.error(f"Profile update error: {exc}")
        return jsonify({"error": f"프로필 처리 중 오류가 발생했습니다: {str(exc)}"}), 500


@profile_bp.delete("/api/profile/image")
def delete_profile_image():
    login_error = require_login()
    if login_error:
        return login_error

    user = get_user_by_id(session["user_id"])
    upload_folder = current_app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER)
    if user and user.get("profile_image"):
        try:
            old_image_path = os.path.join(upload_folder, user["profile_image"])
            safe_file_delete(old_image_path)
        except Exception as exc:
            logger.warning(f"Profile image file deletion failed: {exc}")

    success = update_user_profile(session["user_id"], profile_image="")
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "프로필 이미지 삭제에 실패했습니다."}), 500

