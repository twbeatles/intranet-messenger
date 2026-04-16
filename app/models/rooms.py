# -*- coding: utf-8 -*-
"""
Room management models.
"""

from __future__ import annotations

import logging
import sqlite3

from app.models.base import get_db
from app.utils import E2ECrypto

logger = logging.getLogger(__name__)

_HIDDEN_DELETED_ATTACHMENT_WHERE = "NOT (m.message_type IN ('file', 'image') AND m.file_path IS NULL AND m.content = '[삭제된 메시지]')"


def _encrypt_room_key(raw_key: str) -> str:
    try:
        from app.crypto_manager import CryptoManager

        return CryptoManager.encrypt_room_key(raw_key)
    except Exception as exc:
        logger.warning(f"Key encryption failed, storing raw: {exc}")
        return raw_key


def _decrypt_room_key(encrypted_key: str | None) -> str | None:
    if not encrypted_key:
        return None
    try:
        from app.crypto_manager import CryptoManager

        return CryptoManager.decrypt_room_key(encrypted_key)
    except Exception as exc:
        logger.debug(f"Key decryption failed, returning as-is: {exc}")
        return encrypted_key


def _generate_room_key() -> tuple[str, str]:
    raw_key = E2ECrypto.generate_room_key()
    return raw_key, _encrypt_room_key(raw_key)


def _get_room_key_version(cursor, room_id: int) -> int:
    cursor.execute('SELECT COALESCE(key_version, 1) AS key_version FROM rooms WHERE id = ?', (room_id,))
    row = cursor.fetchone()
    return int((row['key_version'] if row else 1) or 1)


def create_room(name, room_type, created_by, member_ids):
    """Create a room and seed key version 1."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        if room_type == 'direct' and len(member_ids) == 2:
            cursor.execute(
                '''
                    SELECT r.id
                    FROM rooms r
                    JOIN room_members rm1 ON r.id = rm1.room_id
                    JOIN room_members rm2 ON r.id = rm2.room_id
                    WHERE r.type = 'direct' AND rm1.user_id = ? AND rm2.user_id = ?
                ''',
                (member_ids[0], member_ids[1]),
            )
            existing = cursor.fetchone()
            if existing:
                return existing[0]

        _, encryption_key = _generate_room_key()
        cursor.execute(
            'INSERT INTO rooms (name, type, created_by, encryption_key, key_version) VALUES (?, ?, ?, ?, 1)',
            (name, room_type, created_by, encryption_key),
        )
        room_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO room_keys (room_id, version, encryption_key) VALUES (?, 1, ?)',
            (room_id, encryption_key),
        )

        for user_id in member_ids:
            role = 'admin' if user_id == created_by else 'member'
            cursor.execute(
                'INSERT INTO room_members (room_id, user_id, role, joined_key_version) VALUES (?, ?, ?, 1)',
                (room_id, user_id, role),
            )

        conn.commit()
        return room_id
    except Exception as exc:
        conn.rollback()
        logger.error(f"Create room error: {exc}")
        raise


def get_room_key(room_id):
    """Return the latest room key in plaintext."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT encryption_key FROM rooms WHERE id = ?', (room_id,))
        result = cursor.fetchone()
        if not result:
            return None
        return _decrypt_room_key(result['encryption_key'])
    except Exception as exc:
        logger.error(f"Get room key error: {exc}")
        return None


def get_room_member_key_version(room_id: int, user_id: int) -> int | None:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                SELECT COALESCE(joined_key_version, 1) AS joined_key_version
                FROM room_members
                WHERE room_id = ? AND user_id = ?
            ''',
            (room_id, user_id),
        )
        row = cursor.fetchone()
        return int(row['joined_key_version']) if row else None
    except Exception as exc:
        logger.error(f"Get room member key version error: {exc}")
        return None


def get_room_keyring(room_id: int, user_id: int | None = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        min_version = 1
        if user_id is not None:
            member_version = get_room_member_key_version(room_id, user_id)
            if member_version is None:
                return {}
            min_version = max(1, member_version)

        cursor.execute(
            '''
                SELECT version, encryption_key
                FROM room_keys
                WHERE room_id = ? AND version >= ?
                ORDER BY version ASC
            ''',
            (room_id, min_version),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                'SELECT COALESCE(key_version, 1) AS version, encryption_key FROM rooms WHERE id = ?',
                (room_id,),
            )
            row = cursor.fetchone()
            if not row or not row['encryption_key']:
                return {}
            rows = [row]

        keyring = {}
        for row in rows:
            raw_key = _decrypt_room_key(row['encryption_key'])
            if raw_key:
                keyring[str(int(row['version']))] = raw_key
        return keyring
    except Exception as exc:
        logger.error(f"Get room keyring error: {exc}")
        return {}


def get_room_security_bundle(room_id: int, user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COALESCE(key_version, 1) AS key_version FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        if not room:
            return None

        keyring = get_room_keyring(room_id, user_id=user_id)
        current_version = int(room['key_version'] or 1)
        current_key = keyring.get(str(current_version))
        if not current_key:
            current_key = get_room_key(room_id)
            if current_key:
                keyring[str(current_version)] = current_key

        member_key_version = get_room_member_key_version(room_id, user_id)
        return {
            'room_id': room_id,
            'key_version': current_version,
            'member_key_version': member_key_version or current_version,
            'encryption_key': current_key,
            'encryption_keys': keyring,
        }
    except Exception as exc:
        logger.error(f"Get room security bundle error: {exc}")
        return None


def rotate_room_key(room_id: int, conn=None):
    own_conn = conn is None
    conn = conn or get_db()
    cursor = conn.cursor()
    try:
        current_version = _get_room_key_version(cursor, room_id)
        raw_key, encrypted_key = _generate_room_key()
        next_version = current_version + 1
        cursor.execute(
            'UPDATE rooms SET encryption_key = ?, key_version = ? WHERE id = ?',
            (encrypted_key, next_version, room_id),
        )
        if cursor.rowcount < 1:
            if own_conn:
                conn.rollback()
            return None
        cursor.execute(
            'INSERT OR REPLACE INTO room_keys (room_id, version, encryption_key) VALUES (?, ?, ?)',
            (room_id, next_version, encrypted_key),
        )
        if own_conn:
            conn.commit()
        return {'room_id': room_id, 'key_version': next_version, 'encryption_key': raw_key}
    except Exception as exc:
        if own_conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error(f"Rotate room key error: {exc}")
        return None


def get_user_rooms(user_id, include_members=False):
    """Return the user's rooms with only currently visible messages."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            WITH my_rooms AS (
                SELECT r.*, rm.last_read_message_id, rm.pinned, rm.muted,
                       COALESCE(rm.joined_key_version, 1) AS joined_key_version
                FROM rooms r
                JOIN room_members rm ON r.id = rm.room_id
                WHERE rm.user_id = ?
            ),
            member_counts AS (
                SELECT rm.room_id, COUNT(*) AS member_count
                FROM room_members rm
                JOIN my_rooms mr ON mr.id = rm.room_id
                GROUP BY rm.room_id
            ),
            last_msg AS (
                SELECT m.room_id, MAX(m.id) AS last_message_id
                FROM messages m
                JOIN my_rooms mr ON mr.id = m.room_id
                WHERE COALESCE(m.key_version, 1) >= mr.joined_key_version
                  AND ''' + _HIDDEN_DELETED_ATTACHMENT_WHERE + '''
                GROUP BY m.room_id
            ),
            last_msg_data AS (
                SELECT m.room_id,
                       m.content AS last_message,
                       m.message_type AS last_message_type,
                       m.created_at AS last_message_time,
                       COALESCE(m.encrypted, 0) AS last_message_encrypted,
                       m.file_name AS last_message_file_name
                FROM messages m
                JOIN last_msg lm ON lm.room_id = m.room_id AND lm.last_message_id = m.id
            ),
            unread_counts AS (
                SELECT m.room_id, COUNT(*) AS unread_count
                FROM messages m
                JOIN my_rooms mr ON mr.id = m.room_id
                WHERE m.id > COALESCE(mr.last_read_message_id, 0)
                  AND m.sender_id != ?
                  AND COALESCE(m.key_version, 1) >= mr.joined_key_version
                  AND ''' + _HIDDEN_DELETED_ATTACHMENT_WHERE + '''
                GROUP BY m.room_id
            )
            SELECT mr.*,
                   COALESCE(mc.member_count, 0) AS member_count,
                   lmd.last_message,
                   lmd.last_message_type,
                   lmd.last_message_time,
                   lmd.last_message_encrypted,
                   lmd.last_message_file_name,
                   COALESCE(uc.unread_count, 0) AS unread_count
            FROM my_rooms mr
            LEFT JOIN member_counts mc ON mc.room_id = mr.id
            LEFT JOIN last_msg_data lmd ON lmd.room_id = mr.id
            LEFT JOIN unread_counts uc ON uc.room_id = mr.id
            ORDER BY mr.pinned DESC,
                     (lmd.last_message_time IS NULL) ASC,
                     lmd.last_message_time DESC
            ''',
            (user_id, user_id),
        )
        rooms = [dict(r) for r in cursor.fetchall()]
        if not rooms:
            return []

        for room in rooms:
            last_type = room.get('last_message_type') or 'text'
            last_message = room.get('last_message')
            last_encrypted = bool(room.get('last_message_encrypted'))
            file_name = room.get('last_message_file_name')

            preview = '새 대화'
            if last_type == 'image':
                preview = '[사진]'
            elif last_type == 'file':
                preview = file_name or '[파일]'
            elif last_type == 'system':
                if last_message:
                    preview = last_message[:25] + ('...' if len(last_message) > 25 else '')
            elif last_message:
                if last_encrypted:
                    preview = '[암호화된 메시지]'
                    room['last_message'] = None
                else:
                    preview = last_message[:25] + ('...' if len(last_message) > 25 else '')

            room['last_message_preview'] = preview

        direct_room_ids = [r['id'] for r in rooms if r.get('type') == 'direct']
        group_room_ids = [r['id'] for r in rooms if r.get('type') != 'direct']
        member_room_ids = list(direct_room_ids)
        if include_members:
            member_room_ids.extend(group_room_ids)

        members_by_room = {}
        if member_room_ids:
            placeholders = ','.join('?' * len(member_room_ids))
            cursor.execute(
                f'''
                    SELECT rm.room_id, u.id, u.nickname, u.profile_image, u.status,
                           COALESCE(rm.joined_key_version, 1) AS joined_key_version,
                           COALESCE(rm.role, 'member') AS role
                    FROM users u
                    JOIN room_members rm ON u.id = rm.user_id
                    WHERE rm.room_id IN ({placeholders})
                ''',
                member_room_ids,
            )
            for member in cursor.fetchall():
                members_by_room.setdefault(member['room_id'], []).append(dict(member))

        result = []
        for room in rooms:
            rid = room['id']
            room_members = members_by_room.get(rid, [])
            if room.get('type') == 'direct':
                partner = next((m for m in room_members if m['id'] != user_id), None)
                if partner:
                    room['partner'] = partner
                    room['name'] = partner.get('nickname') or room.get('name')
            elif include_members:
                room['members'] = room_members
            result.append(room)
        return result
    except Exception as exc:
        logger.error(f"Get user rooms error: {exc}")
        return []


def get_room_members(room_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                SELECT u.id, u.nickname, u.profile_image, u.status,
                       rm.last_read_message_id, rm.pinned, rm.muted,
                       COALESCE(rm.joined_key_version, 1) AS joined_key_version,
                       COALESCE(rm.role, 'member') AS role
                FROM users u
                JOIN room_members rm ON u.id = rm.user_id
                WHERE rm.room_id = ?
            ''',
            (room_id,),
        )
        return [dict(member) for member in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"Get room members error: {exc}")
        return []


def is_room_member(room_id, user_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        return cursor.fetchone() is not None
    except Exception as exc:
        logger.error(f"Check room membership error: {exc}")
        return False


def add_room_member(room_id, user_id, joined_key_version: int | None = None, conn=None):
    own_conn = conn is None
    conn = conn or get_db()
    cursor = conn.cursor()
    try:
        version = joined_key_version or _get_room_key_version(cursor, room_id)
        cursor.execute(
            'INSERT INTO room_members (room_id, user_id, joined_key_version) VALUES (?, ?, ?)',
            (room_id, user_id, version),
        )
        if own_conn:
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        if own_conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    except Exception as exc:
        if own_conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error(f"Add room member error: {exc}")
        return False


def leave_room_db(room_id, user_id):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
    except Exception:
        pass

    cursor = conn.cursor()
    try:
        if is_room_admin(room_id, user_id):
            cursor.execute(
                '''
                    SELECT u.id
                    FROM users u
                    JOIN room_members rm ON u.id = rm.user_id
                    WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
                ''',
                (room_id, room_id),
            )
            admin_ids = [row['id'] for row in cursor.fetchall()]
            if len(admin_ids) == 1 and admin_ids[0] == user_id:
                cursor.execute(
                    '''
                        SELECT user_id
                        FROM room_members
                        WHERE room_id = ? AND user_id != ?
                        ORDER BY CASE WHEN COALESCE(role, 'member') = 'admin' THEN 0 ELSE 1 END, user_id ASC
                        LIMIT 1
                    ''',
                    (room_id, user_id),
                )
                replacement = cursor.fetchone()
                if replacement:
                    cursor.execute(
                        'UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?',
                        ('admin', room_id, replacement['user_id']),
                    )
                    logger.info(f"Admin auto-delegated: room {room_id}")

        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        logger.error(f"Leave room error: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def update_room_name(room_id, new_name):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE rooms SET name = ? WHERE id = ?', (new_name, room_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        logger.error(f"Update room name error: {exc}")
        return False


def get_room_by_id(room_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        return dict(room) if room else None
    except Exception as exc:
        logger.error(f"Get room error: {exc}")
        return None


def pin_room(user_id, room_id, pinned):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE room_members SET pinned = ? WHERE user_id = ? AND room_id = ?',
            (1 if pinned else 0, user_id, room_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.error(f"Pin room error: {exc}")
        return False


def mute_room(user_id, room_id, muted):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE room_members SET muted = ? WHERE user_id = ? AND room_id = ?',
            (1 if muted else 0, user_id, room_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.error(f"Mute room error: {exc}")
        return False


def kick_member(room_id, target_user_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, target_user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        logger.error(f"Kick member error: {exc}")
        return False


def set_room_admin(room_id: int, user_id: int, is_admin: bool = True):
    conn = get_db()
    cursor = conn.cursor()
    try:
        role = 'admin' if is_admin else 'member'
        cursor.execute(
            'UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?',
            (role, room_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        logger.error(f"Set room admin error: {exc}")
        return False


def is_room_admin(room_id: int, user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT created_by FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        if room and room['created_by'] == user_id:
            return True

        cursor.execute('SELECT role FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        member = cursor.fetchone()
        return bool(member and member['role'] == 'admin')
    except Exception as exc:
        logger.error(f"Check room admin error: {exc}")
        return False


def get_room_admins(room_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                SELECT u.id, u.nickname, u.profile_image, rm.role
                FROM users u
                JOIN room_members rm ON u.id = rm.user_id
                WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
            ''',
            (room_id, room_id),
        )
        return [dict(admin) for admin in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"Get room admins error: {exc}")
        return []
