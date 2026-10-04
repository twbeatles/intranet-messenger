# -*- coding: utf-8 -*-
"""
Asynchronous upload AV scan queue (optional, clamd-based).
"""

from __future__ import annotations

import logging
import os
import queue
import shutil
import socket
import struct
import threading
import uuid
from datetime import datetime

from app.models.base import get_db, close_thread_db, safe_file_delete
from app.services.uploads import resolve_stored_path
from app.upload_tokens import issue_upload_token

logger = logging.getLogger(__name__)

_scan_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()
_app_ref = None


def is_scan_enabled(app) -> bool:
    return bool(app.config.get("FEATURE_AV_SCAN_ENABLED"))


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_scan_job(
    user_id: int,
    room_id: int,
    temp_path: str,
    final_path: str,
    file_name: str,
    file_type: str,
    file_size: int,
) -> str:
    job_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO upload_scan_jobs (
            job_id, user_id, room_id, temp_path, final_path,
            file_name, file_type, file_size, status, result, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, ?)
        """,
        (
            job_id,
            user_id,
            room_id,
            temp_path,
            final_path,
            file_name,
            file_type,
            file_size,
            _now_str(),
            _now_str(),
        ),
    )
    conn.commit()
    _scan_queue.put(job_id)
    return job_id


def get_scan_job(job_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM upload_scan_jobs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def _update_scan_job(job_id: str, status: str, result: str = "", token: str | None = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE upload_scan_jobs
        SET status = ?, result = ?, token = COALESCE(?, token), updated_at = ?
        WHERE job_id = ?
        """,
        (status, result, token, _now_str(), job_id),
    )
    conn.commit()


def _update_scan_job_if_pending(
    job_id: str, status: str, result: str = "", token: str | None = None
) -> bool:
    """워커 처리 결과가 사용자 취소와 경합해도 취소가 풀리지 않게 한다."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE upload_scan_jobs
        SET status = ?, result = ?, token = COALESCE(?, token), updated_at = ?
        WHERE job_id = ? AND status = 'pending'
        """,
        (status, result, token, _now_str(), job_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def retry_scan_job(job_id: str, user_id: int) -> tuple[bool, str]:
    """실패(error)한 스캔 job을 다시 pending으로 되돌려 큐에 넣는다."""
    job = get_scan_job(job_id)
    if not job:
        return False, "스캔 작업을 찾을 수 없습니다."
    if int(job.get("user_id") or 0) != int(user_id):
        return False, "접근 권한이 없습니다."
    if (job.get("status") or "").lower() != "error":
        return False, "실패한 작업만 다시 시도할 수 있습니다."
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE upload_scan_jobs SET status = 'pending', result = '', updated_at = ? "
        "WHERE job_id = ? AND status = 'error'",
        (_now_str(), job_id),
    )
    conn.commit()
    if cursor.rowcount < 1:
        return False, "작업 상태가 변경되었습니다."
    _scan_queue.put(job_id)
    return True, ""


def cancel_scan_job(job_id: str, user_id: int) -> tuple[bool, str]:
    """스캔 job을 취소하고 temp 파일을 정리한다."""
    job = get_scan_job(job_id)
    if not job:
        return False, "스캔 작업을 찾을 수 없습니다."
    if int(job.get("user_id") or 0) != int(user_id):
        return False, "접근 권한이 없습니다."
    status = (job.get("status") or "").lower()
    if status in ("clean", "cancelled"):
        return False, "이미 처리된 작업은 취소할 수 없습니다."
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE upload_scan_jobs SET status = 'cancelled', updated_at = ? "
        "WHERE job_id = ? AND status NOT IN ('clean', 'cancelled')",
        (_now_str(), job_id),
    )
    conn.commit()
    if cursor.rowcount < 1:
        return False, "작업 상태가 변경되었습니다."
    try:
        from app.services.runtime_paths import get_upload_folder

        abs_temp = resolve_stored_path(get_upload_folder(), job.get("temp_path") or "")
        if abs_temp:
            safe_file_delete(abs_temp)
    except Exception as exc:
        logger.warning(f"Cancelled scan temp cleanup failed: {exc}")
    return True, ""


def _scan_with_clamav(abs_path: str, host: str, port: int, timeout_seconds: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
            sock.sendall(b"zINSTREAM\0")
            with open(abs_path, "rb") as fh:
                while True:
                    chunk = fh.read(8192)
                    if not chunk:
                        break
                    sock.sendall(struct.pack(">I", len(chunk)))
                    sock.sendall(chunk)
            sock.sendall(struct.pack(">I", 0))
            response = sock.recv(4096).decode("utf-8", errors="replace")
        if "FOUND" in response:
            return False, response.strip()
        if "OK" in response:
            return True, "clean"
        return False, f"unexpected scanner response: {response.strip()}"
    except Exception as e:
        return False, f"clamav scan failed: {e}"


def _process_job(job_id: str):
    global _app_ref
    app = _app_ref
    if app is None:
        return

    with app.app_context():
        abs_temp_for_cleanup = None
        try:
            job = get_scan_job(job_id)
            if not job:
                return
            if job.get("status") != "pending":
                return

            upload_root = app.config.get("UPLOAD_FOLDER")
            abs_temp = resolve_stored_path(upload_root, job["temp_path"])
            abs_temp_for_cleanup = abs_temp
            abs_final = resolve_stored_path(upload_root, job["final_path"])
            os.makedirs(os.path.dirname(abs_final), exist_ok=True)

            scanner = (app.config.get("AV_SCANNER") or "clamav").lower()
            if scanner != "clamav":
                # ISSUE-005: 지원하지 않는 스캐너여도 temp 파일을 남기지 않는다.
                safe_file_delete(abs_temp)
                _update_scan_job_if_pending(job_id, "error", f"unsupported scanner: {scanner}")
                return

            clean, result = _scan_with_clamav(
                abs_temp,
                host=app.config.get("AV_CLAMD_HOST", "127.0.0.1"),
                port=int(app.config.get("AV_CLAMD_PORT", 3310)),
                timeout_seconds=int(app.config.get("AV_SCAN_TIMEOUT_SECONDS", 15)),
            )

            if not clean:
                safe_file_delete(abs_temp)
                status = "infected" if "FOUND" in result else "error"
                _update_scan_job_if_pending(job_id, status, result)
                return

            shutil.move(abs_temp, abs_final)
            token = issue_upload_token(
                user_id=job["user_id"],
                room_id=job["room_id"],
                file_path=job["final_path"],
                file_name=job["file_name"],
                file_type=job["file_type"],
                file_size=job.get("file_size") or 0,
            )
            _update_scan_job_if_pending(job_id, "clean", "clean", token=token)
        except Exception as e:
            logger.error(f"Upload scan worker job error({job_id}): {e}")
            # ISSUE-005: 예외 경로에서도 temp 파일을 정리한다.
            # (abs_temp 초기화 전 실패면 삭제할 파일이 없다.)
            if abs_temp_for_cleanup:
                safe_file_delete(abs_temp_for_cleanup)
            try:
                _update_scan_job(job_id, "error", str(e))
            except Exception:
                pass
        finally:
            close_thread_db()


def _scan_worker_loop():
    while True:
        job_id = _scan_queue.get()
        try:
            _process_job(job_id)
        finally:
            _scan_queue.task_done()


def init_upload_scan_worker(app):
    global _worker_started, _app_ref
    _app_ref = app
    if not is_scan_enabled(app):
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_scan_worker_loop, daemon=True, name="upload-scan-worker")
        thread.start()
        _worker_started = True
        logger.info("Upload AV scan worker started")

