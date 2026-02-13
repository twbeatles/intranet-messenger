# -*- coding: utf-8 -*-
"""
대화방 관리 모듈
"""

import sqlite3
import logging

from app.models.base import get_db
from app.utils import E2ECrypto

logger = logging.getLogger(__name__)


def create_room(name, room_type, created_by, member_ids):
    """대화방 생성"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1:1 대화방인 경우 기존 대화방 확인
        if room_type == 'direct' and len(member_ids) == 2:
            cursor.execute('''
                SELECT r.id FROM rooms r
                JOIN room_members rm1 ON r.id = rm1.room_id
                JOIN room_members rm2 ON r.id = rm2.room_id
                WHERE r.type = 'direct' AND rm1.user_id = ? AND rm2.user_id = ?
            ''', (member_ids[0], member_ids[1]))
            existing = cursor.fetchone()
            if existing:
                return existing[0]
        
        # 대화방별 암호화 키 생성
        raw_key = E2ECrypto.generate_room_key()
        try:
            from app.crypto_manager import CryptoManager
            encryption_key = CryptoManager.encrypt_room_key(raw_key)
        except Exception as e:
            logger.warning(f"Key encryption failed, storing raw: {e}")
            encryption_key = raw_key
        
        cursor.execute(
            'INSERT INTO rooms (name, type, created_by, encryption_key) VALUES (?, ?, ?, ?)',
            (name, room_type, created_by, encryption_key)
        )
        room_id = cursor.lastrowid
        
        for user_id in member_ids:
            role = 'admin' if user_id == created_by else 'member'
            cursor.execute(
                'INSERT INTO room_members (room_id, user_id, role) VALUES (?, ?, ?)',
                (room_id, user_id, role)
            )
        
        conn.commit()
        return room_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Create room error: {e}")
        raise


def get_room_key(room_id):
    """대화방 암호화 키 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT encryption_key FROM rooms WHERE id = ?', (room_id,))
        result = cursor.fetchone()
        if not result:
            return None
        
        encrypted_key = result['encryption_key']
        try:
            from app.crypto_manager import CryptoManager
            return CryptoManager.decrypt_room_key(encrypted_key)
        except Exception as e:
            logger.debug(f"Key decryption failed, returning as-is: {e}")
            return encrypted_key
    except Exception as e:
        logger.error(f"Get room key error: {e}")
        return None


def get_user_rooms(user_id, include_members=False):
    """사용자의 대화방 목록 (성능 최적화 버전)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            WITH my_rooms AS (
                SELECT r.*, rm.last_read_message_id, rm.pinned, rm.muted
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
                JOIN room_members rm ON rm.room_id = m.room_id AND rm.user_id = ?
                WHERE m.id > COALESCE(rm.last_read_message_id, 0) AND m.sender_id != ?
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
        ''' , (user_id, user_id, user_id))
        rooms = [dict(r) for r in cursor.fetchall()]

        if not rooms:
            return []

        # UI? last_message_preview ?? + ???(content) ?? ??
        for room in rooms:
            last_type = room.get('last_message_type') or 'text'
            last_message = room.get('last_message')
            last_encrypted = bool(room.get('last_message_encrypted'))
            file_name = room.get('last_message_file_name')

            preview = '\uc0c8 \ub300\ud654'
            if last_type == 'image':
                preview = '[\uc0ac\uc9c4]'
            elif last_type == 'file':
                preview = file_name or '[\ud30c\uc77c]'
            elif last_type == 'system':
                if last_message:
                    preview = last_message[:25] + ('...' if len(last_message) > 25 else '')
            else:
                if last_message:
                    if last_encrypted:
                        preview = '[\uc554\ud638\ud654\ub41c \uba54\uc2dc\uc9c0]'
                        room['last_message'] = None
                    else:
                        preview = last_message[:25] + ('...' if len(last_message) > 25 else '')

            room['last_message_preview'] = preview

        # direct ?? partner ?? + (??) group ?? ??
        direct_room_ids = [r['id'] for r in rooms if r.get('type') == 'direct']
        group_room_ids = [r['id'] for r in rooms if r.get('type') != 'direct']

        member_room_ids = list(direct_room_ids)
        if include_members:
            member_room_ids.extend(group_room_ids)

        members_by_room = {}
        if member_room_ids:
            placeholders = ','.join('?' * len(member_room_ids))
            cursor.execute(f'''
                SELECT rm.room_id, u.id, u.nickname, u.profile_image, u.status
                FROM users u
                JOIN room_members rm ON u.id = rm.user_id
                WHERE rm.room_id IN ({placeholders})
            ''', member_room_ids)
            for m in cursor.fetchall():
                rid = m['room_id']
                members_by_room.setdefault(rid, []).append(dict(m))

        result = []
        for room in rooms:
            rid = room['id']
            room_members = members_by_room.get(rid, [])

            if room.get('type') == 'direct':
                partner = next((m for m in room_members if m['id'] != user_id), None)
                if partner:
                    room['partner'] = partner
                    room['name'] = partner.get('nickname') or room.get('name')
            else:
                if include_members:
                    room['members'] = room_members

            result.append(room)

        return result
    except Exception as e:
        logger.error(f"Get user rooms error: {e}")
        return []
def get_room_members(room_id):
    """대화방 멤버 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.id, u.nickname, u.profile_image, u.status, rm.last_read_message_id, rm.pinned, rm.muted
            FROM users u
            JOIN room_members rm ON u.id = rm.user_id
            WHERE rm.room_id = ?
        ''', (room_id,))
        members = cursor.fetchall()
        return [dict(m) for m in members]
    except Exception as e:
        logger.error(f"Get room members error: {e}")
        return []


def is_room_member(room_id, user_id):
    """대화방 멤버 확인"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ?',
            (room_id, user_id)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Check room membership error: {e}")
        return False


def add_room_member(room_id, user_id):
    """대화방 멤버 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO room_members (room_id, user_id) VALUES (?, ?)', (room_id, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def leave_room_db(room_id, user_id):
    """대화방 나가기"""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
    except Exception:
        pass
        
    cursor = conn.cursor()
    try:
        if is_room_admin(room_id, user_id):
            cursor.execute('''
                SELECT u.id FROM users u
                JOIN room_members rm ON u.id = rm.user_id
                WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
            ''', (room_id, room_id))
            admin_ids = [row['id'] for row in cursor.fetchall()]
            
            if len(admin_ids) == 1 and admin_ids[0] == user_id:
                members = get_room_members(room_id)
                for member in members:
                    if member['id'] != user_id:
                        cursor.execute('UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?',
                                       ('admin', room_id, member['id']))
                        logger.info(f"Admin auto-delegated: room {room_id}")
                        break
        
        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Leave room error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass


def update_room_name(room_id, new_name):
    """대화방 이름 변경"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE rooms SET name = ? WHERE id = ?', (new_name, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Update room name error: {e}")
        return False


def get_room_by_id(room_id):
    """대화방 정보 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        return dict(room) if room else None
    except Exception as e:
        logger.error(f"Get room error: {e}")
        return None


def pin_room(user_id, room_id, pinned):
    """대화방 상단 고정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE room_members SET pinned = ? WHERE user_id = ? AND room_id = ?', 
                      (1 if pinned else 0, user_id, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Pin room error: {e}")
        return False


def mute_room(user_id, room_id, muted):
    """대화방 알림 끄기"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE room_members SET muted = ? WHERE user_id = ? AND room_id = ?', 
                      (1 if muted else 0, user_id, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Mute room error: {e}")
        return False


def kick_member(room_id, target_user_id):
    """멤버 강제 퇴장"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', 
                      (room_id, target_user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Kick member error: {e}")
        return False


# 관리자 관련 함수
def set_room_admin(room_id: int, user_id: int, is_admin: bool = True):
    """관리자 권한 설정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        role = 'admin' if is_admin else 'member'
        cursor.execute('UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?', 
                      (role, room_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Set room admin error: {e}")
        return False


def is_room_admin(room_id: int, user_id: int):
    """관리자 여부 확인"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT created_by FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        if room and room['created_by'] == user_id:
            return True
        
        cursor.execute('SELECT role FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        member = cursor.fetchone()
        return member and member['role'] == 'admin'
    except Exception as e:
        logger.error(f"Check room admin error: {e}")
        return False


def get_room_admins(room_id: int):
    """대화방 관리자 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.id, u.nickname, u.profile_image, rm.role
            FROM users u
            JOIN room_members rm ON u.id = rm.user_id
            WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
        ''', (room_id, room_id))
        return [dict(a) for a in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get room admins error: {e}")
        return []
