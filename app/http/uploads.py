# -*- coding: utf-8 -*-
"""
Upload, scan-job, file-storage, and download HTTP endpoints.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_from_directory, session
from werkzeug.utils import secure_filename

from app.extensions import limiter
from app.http.common import require_login
from app.http.route_deps import get_routes_shim
from app.models import (
    delete_room_file,
    get_db,
    get_message_room_id,
    get_room_files,
    is_room_admin,
    is_room_member,
    log_admin_action,
    safe_file_delete,
)
from app.services.runtime_config import get_max_upload_size
from app.services.socket_broadcasts import emit_message_deleted
from app.services.uploads import normalize_stored_path
from app.upload_scan import get_scan_job
from app.upload_tokens import issue_upload_token
from app.utils import allowed_file, validate_file_header

try:
    from config import MAX_CONTENT_LENGTH, UPLOAD_FOLDER
except ImportError:
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_FOLDER = "uploads"

logger = logging.getLogger(__name__)

uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.post("/api/upload")
@limiter.limit("10 per minute")
def upload_file():
    login_error = require_login()
    if login_error:
        return login_error

    upload_folder = current_app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER)
    room_id = request.form.get("room_id", type=int)
    if not room_id:
        return jsonify({"error": "room_id가 필요합니다."}), 400
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "대화방 접근 권한이 없습니다."}), 403

    max_size = get_max_upload_size(current_app, MAX_CONTENT_LENGTH)
    if request.content_length and request.content_length > max_size:
        return jsonify({"error": f"파일 크기는 {max_size} bytes 이하여야 합니다."}), 413

    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    original_filename = file.filename or ""
    if original_filename == "":
        return jsonify({"error": "파일을 선택하지 않았습니다."}), 400
    if not (file and allowed_file(original_filename)):
        return jsonify({"error": "허용되지 않는 파일 형식입니다."}), 400
    if not validate_file_header(file):
        logger.warning(f"File signature mismatch: {file.filename}")
        return jsonify({"error": "파일 내용이 확장자와 일치하지 않습니다."}), 400

    filename = secure_filename(original_filename)
    unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{filename}"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_type = "image" if ext in {"png", "jpg", "jpeg", "gif", "webp", "bmp", "ico"} else "file"

    routes_shim = get_routes_shim()
    av_enabled = bool(routes_shim.is_scan_enabled(current_app))
    if av_enabled:
        quarantine_folder = current_app.config.get("UPLOAD_QUARANTINE_FOLDER") or os.path.join(upload_folder, "quarantine")
        os.makedirs(quarantine_folder, exist_ok=True)

        temp_abs_path = os.path.join(quarantine_folder, unique_filename)
        file.save(temp_abs_path)
        file_size = os.path.getsize(temp_abs_path)

        temp_rel_path = normalize_stored_path(upload_folder, temp_abs_path)
        final_rel_path = unique_filename.replace("\\", "/")
        try:
            job_id = routes_shim.create_scan_job(
                user_id=session["user_id"],
                room_id=room_id,
                temp_path=temp_rel_path,
                final_path=final_rel_path,
                file_name=filename,
                file_type=file_type,
                file_size=file_size,
            )
        except Exception as exc:
            logger.error(f"Create upload scan job failed: {exc}")
            try:
                safe_file_delete(temp_abs_path)
            except Exception:
                pass
            return jsonify({"error": "업로드 준비에 실패했습니다."}), 500

        return jsonify({"success": True, "scan_status": "pending", "job_id": job_id})

    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    file_size = os.path.getsize(file_path)
    upload_token = issue_upload_token(
        user_id=session["user_id"],
        room_id=room_id,
        file_path=unique_filename,
        file_name=filename,
        file_type=file_type,
        file_size=file_size,
    )
    return jsonify(
        {
            "success": True,
            "scan_status": "clean",
            "file_path": unique_filename,
            "file_name": filename,
            "upload_token": upload_token,
        }
    )


@uploads_bp.get("/api/upload/jobs/<job_id>")
def get_upload_job_status(job_id: str):
    login_error = require_login()
    if login_error:
        return login_error

    job = get_scan_job(job_id)
    if not job:
        return jsonify({"error": "스캔 작업을 찾을 수 없습니다."}), 404
    if int(job.get("user_id") or 0) != int(session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    status = (job.get("status") or "pending").lower()
    payload = {"job_id": job_id, "scan_status": status}
    if status == "clean":
        payload.update(
            {
                "upload_token": job.get("token"),
                "file_path": job.get("final_path"),
                "file_name": job.get("file_name"),
            }
        )
    elif status in ("infected", "error"):
        payload.update({"error": job.get("result") or "스캔 실패"})
    return jsonify(payload)


@uploads_bp.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    login_error = require_login()
    if login_error:
        return login_error

    upload_folder = current_app.config.get("UPLOAD_FOLDER", UPLOAD_FOLDER)
    safe_filename = secure_filename(os.path.basename(filename))

    is_profile = False
    if "/" in filename:
        subdir = os.path.dirname(filename)
        allowed_subdirs = ["profiles"]
        if subdir not in allowed_subdirs:
            return jsonify({"error": "접근 권한이 없습니다."}), 403
        safe_path = os.path.join(subdir, safe_filename)
        is_profile = subdir == "profiles"
    else:
        safe_path = safe_filename

    upload_root = os.path.realpath(upload_folder)
    full_path = os.path.realpath(os.path.join(upload_folder, safe_path))
    try:
        within_root = os.path.commonpath([full_path, upload_root]) == upload_root
    except ValueError:
        within_root = False
    if not within_root:
        logger.warning(f"Path traversal attempt: {filename}")
        return jsonify({"error": "잘못된 요청입니다."}), 400
    if not os.path.isfile(full_path):
        return jsonify({"error": "파일을 찾을 수 없습니다."}), 404

    download_name = safe_filename
    if not is_profile:
        try:
            conn = get_db()
            cursor = conn.cursor()
            lookup_path = safe_path.replace("\\", "/")
            cursor.execute(
                "SELECT room_id, file_name FROM room_files WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (lookup_path,),
            )
            row = cursor.fetchone()
        except Exception as exc:
            logger.warning(f"Upload auth lookup failed: {exc}")
            row = None

        if not row:
            return jsonify({"error": "파일을 찾을 수 없습니다."}), 404
        room_id = row["room_id"]
        download_name = row["file_name"] or download_name
        if not is_room_member(room_id, session["user_id"]):
            return jsonify({"error": "접근 권한이 없습니다."}), 403

    ext = os.path.splitext(safe_filename)[1].lower().lstrip(".")
    inline_exts = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "ico"}
    as_attachment = (not is_profile) and (ext not in inline_exts)
    response = send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        as_attachment=as_attachment,
        download_name=download_name if as_attachment else None,
    )
    response.headers["Cache-Control"] = "private, max-age=3600" if is_profile else "private, no-store"
    response.headers["Vary"] = "Accept-Encoding"
    if not as_attachment and ext in inline_exts:
        response.headers["Content-Disposition"] = "inline"
    return response


@uploads_bp.get("/api/rooms/<int:room_id>/files")
def get_files(room_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    return jsonify(get_room_files(room_id, request.args.get("type")))


@uploads_bp.delete("/api/rooms/<int:room_id>/files/<int:file_id>")
def delete_file_route(room_id: int, file_id: int):
    login_error = require_login()
    if login_error:
        return login_error
    if not is_room_member(room_id, session["user_id"]):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    is_admin = is_room_admin(room_id, session["user_id"])
    success, deleted_info = delete_room_file(file_id, session["user_id"], room_id=room_id, is_admin=is_admin)
    if not success:
        return jsonify({"error": "파일 삭제 권한이 없습니다."}), 403
    if not isinstance(deleted_info, dict):
        deleted_info = {"file_path": None, "message_id": None}

    if is_admin:
        log_admin_action(
            room_id=room_id,
            actor_user_id=session["user_id"],
            action="delete_file",
            metadata={"file_id": file_id, "file_path": deleted_info.get("file_path")},
        )
    message_id = deleted_info.get("message_id")
    if isinstance(message_id, int) and message_id > 0:
        emit_message_deleted(room_id, message_id)
    return jsonify({"success": True})
