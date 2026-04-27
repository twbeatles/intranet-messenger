# -*- coding: utf-8 -*-
"""
Message, edit/delete, and reaction Socket.IO events.
"""

from __future__ import annotations

import logging
import os
import traceback

from flask import session
from flask_socketio import emit

from app.models import (
    can_user_see_message,
    create_message,
    delete_message,
    edit_message,
    get_message_reactions,
    get_message_room_id,
    get_unread_count,
    is_room_member,
    safe_file_delete,
)
from app.services.runtime_paths import get_upload_folder
from app.socket_events.shared import check_send_message_rate_limit, emit_error, ensure_session_token, parse_positive_int
from app.socket_events.state import get_user_room_ids
from app.upload_tokens import consume_upload_token, get_upload_token_failure_reason

logger = logging.getLogger(__name__)


def register_message_events(socketio):
    @socketio.on("send_message")
    def handle_send_message(data):
        try:
            if not ensure_session_token("send_message"):
                return

            user_id = session["user_id"]
            if not check_send_message_rate_limit(user_id):
                emit_error("메시지 전송 속도 제한을 초과했습니다.")
                return

            room_id = data.get("room_id")
            if not isinstance(room_id, int) or room_id <= 0:
                emit_error("잘못된 방 ID입니다.")
                return

            content = data.get("content", "")
            content = content.strip()[:10000] if isinstance(content, str) else ""
            message_type = data.get("type", "text")
            if message_type == "system":
                emit_error("시스템 메시지는 클라이언트에서 전송할 수 없습니다.")
                return
            if message_type not in {"text", "file", "image"}:
                message_type = "text"

            file_path = None
            file_name = None
            file_size = None
            reply_to = data.get("reply_to")
            if reply_to is not None and not isinstance(reply_to, int):
                reply_to = None
            encrypted = bool(data.get("encrypted", True))

            user_rooms = get_user_room_ids(user_id)
            if room_id not in user_rooms and not is_room_member(room_id, user_id):
                emit_error("방 접근 권한이 없습니다.")
                return
            if reply_to is not None and (
                get_message_room_id(reply_to) != room_id or not can_user_see_message(room_id, user_id, reply_to)
            ):
                emit_error("답장 대상 메시지가 현재 방에 없습니다.")
                return

            if message_type in ("file", "image"):
                token = data.get("upload_token")
                reason = get_upload_token_failure_reason(
                    token=token,
                    user_id=user_id,
                    room_id=room_id,
                    expected_type=message_type,
                )
                if reason:
                    emit_error(reason)
                    return

                token_data = consume_upload_token(
                    token=token,
                    user_id=user_id,
                    room_id=room_id,
                    expected_type=message_type,
                )
                if not token_data:
                    emit_error("업로드 토큰이 이미 사용되었거나 만료되었습니다.")
                    return

                file_path_value = token_data.get("file_path")
                file_name_value = token_data.get("file_name")
                if not isinstance(file_path_value, str) or not isinstance(file_name_value, str) or not file_name_value:
                    emit_error("업로드 파일 정보가 손상되었습니다.")
                    return

                file_path = file_path_value
                file_name = file_name_value
                raw_file_size = token_data.get("file_size")
                file_size = int(raw_file_size) if isinstance(raw_file_size, int) else None
                encrypted = False
                content = file_name or content

            if not content and not file_path:
                return

            message = create_message(
                room_id,
                user_id,
                content,
                message_type,
                file_path,
                file_name,
                reply_to,
                encrypted,
                file_size=file_size,
            )
            if not message:
                if message_type in ("file", "image") and file_path:
                    logger.warning(
                        "Potential orphan upload file after message failure: room=%s, user=%s, path=%s",
                        room_id,
                        user_id,
                        file_path,
                    )
                    safe_file_delete(os.path.join(get_upload_folder(), file_path))
                emit_error("메시지 저장에 실패했습니다.")
                return

            message["unread_count"] = get_unread_count(room_id, message["id"], user_id)
            emit("new_message", message, to=f"room_{room_id}")
        except Exception as exc:
            logger.error(f"Send message error: {exc}\n{traceback.format_exc()}")
            emit_error("메시지 전송에 실패했습니다.")

    @socketio.on("edit_message")
    def handle_edit_message(data):
        try:
            if not ensure_session_token("edit_message"):
                return
            message_id = data.get("message_id")
            content = data.get("content", "").strip()[:10000]
            encrypted = data.get("encrypted", True)
            if not message_id or not content:
                emit_error("잘못된 요청입니다.")
                return

            success, error_msg, room_id, key_version = edit_message(message_id, session["user_id"], content, encrypted)
            if success:
                emit(
                    "message_edited",
                    {"message_id": message_id, "content": content, "encrypted": encrypted, "key_version": key_version},
                    to=f"room_{room_id}",
                )
            else:
                emit_error(error_msg)
        except Exception as exc:
            logger.error(f"Edit message error: {exc}")
            emit_error("메시지 수정에 실패했습니다.")

    @socketio.on("delete_message")
    def handle_delete_message(data):
        try:
            if not ensure_session_token("delete_message"):
                return
            message_id = data.get("message_id")
            if not message_id:
                emit_error("잘못된 요청입니다.")
                return
            success, result = delete_message(message_id, session["user_id"])
            if success:
                emit("message_deleted", {"message_id": message_id}, to=f"room_{result}")
            else:
                emit_error(result)
        except Exception as exc:
            logger.error(f"Delete message error: {exc}")
            emit_error("메시지 삭제에 실패했습니다.")

    @socketio.on("reaction_updated")
    def handle_reaction_updated(data):
        try:
            if not ensure_session_token("reaction_updated"):
                return
            room_id = parse_positive_int(data or {}, "room_id")
            message_id = parse_positive_int(data or {}, "message_id")
            if not room_id or not message_id:
                emit_error("Invalid request.")
                return
            if not is_room_member(room_id, session["user_id"]):
                emit_error("Room access denied.")
                return
            if get_message_room_id(message_id) != room_id or not can_user_see_message(room_id, session["user_id"], message_id):
                emit_error("Invalid request.")
                return
            emit(
                "reaction_updated",
                {"room_id": room_id, "message_id": message_id, "reactions": get_message_reactions(message_id)},
                to=f"room_{room_id}",
            )
        except Exception as exc:
            logger.error(f"Reaction update broadcast error: {exc}")
