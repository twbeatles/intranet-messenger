# -*- coding: utf-8 -*-
"""
Message models.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from app.models.base import get_db, safe_file_delete
from app.services.runtime_paths import get_upload_folder

logger = logging.getLogger(__name__)

_HIDDEN_DELETED_ATTACHMENT_WHERE = "NOT (m.message_type IN ('file', 'image') AND m.file_path IS NULL AND m.content = '[삭제된 메시지]')"
_VISIBLE_FOR_MEMBER_WHERE = "COALESCE(m.key_version, 1) >= COALESCE(rm.joined_key_version, 1)"

server_stats = {
    'start_time': None,
    'total_messages': 0,
    'total_connections': 0,
    'active_connections': 0,
}
_stats_lock = threading.Lock()


def _get_room_key_version(cursor, room_id: int) -> int:
    cursor.execute('SELECT COALESCE(key_version, 1) AS key_version FROM rooms WHERE id = ?', (room_id,))
    row = cursor.fetchone()
    return int((row['key_version'] if row else 1) or 1)


def update_server_stats(key, value=1, increment=True):
    with _stats_lock:
        if increment:
            server_stats[key] += value
        else:
            server_stats[key] = value


def get_server_stats():
    with _stats_lock:
        return server_stats.copy()


def create_message(
    room_id,
    sender_id,
    content,
    message_type='text',
    file_path=None,
    file_name=None,
    reply_to=None,
    encrypted=True,
    file_size=None,
):
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cursor = conn.cursor()
    try:
        if reply_to is not None:
            cursor.execute('SELECT room_id FROM messages WHERE id = ?', (reply_to,))
            reply_row = cursor.fetchone()
            if not reply_row or reply_row['room_id'] != room_id:
                conn.rollback()
                return None

        key_version = _get_room_key_version(cursor, room_id)
        cursor.execute(
            '''
                INSERT INTO messages (
                    room_id, sender_id, content, encrypted, message_type,
                    file_path, file_name, reply_to, key_version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                room_id,
                sender_id,
                content,
                1 if encrypted else 0,
                message_type,
                file_path,
                file_name,
                reply_to,
                key_version,
                now_kst,
            ),
        )
        message_id = cursor.lastrowid

        if message_type in ('file', 'image') and file_path and file_name:
            cursor.execute(
                '''
                    INSERT INTO room_files (
                        room_id, uploaded_by, file_path, file_name, file_size, file_type, message_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (room_id, sender_id, file_path, file_name, file_size, message_type, message_id),
            )
        conn.commit()

        cursor.execute(
            '''
                SELECT m.*, u.nickname AS sender_name, u.profile_image AS sender_image,
                       rm.content AS reply_content, ru.nickname AS reply_sender,
                       COALESCE(rm.key_version, 1) AS reply_key_version
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                LEFT JOIN messages rm ON m.reply_to = rm.id
                LEFT JOIN users ru ON rm.sender_id = ru.id
                WHERE m.id = ?
            ''',
            (message_id,),
        )
        message = cursor.fetchone()

        update_server_stats('total_messages')
        return dict(message) if message else None
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error(f"Create message error: {exc}")
        return None


def get_room_messages(room_id, viewer_user_id=None, limit=50, before_id=None, include_reactions=True):
    from app.models.reactions import get_messages_reactions

    conn = get_db()
    cursor = conn.cursor()
    try:
        join_params: list[object] = []
        where_params: list[object] = [room_id]
        joins = [
            'JOIN users u ON m.sender_id = u.id',
            'LEFT JOIN messages rm ON m.reply_to = rm.id',
            'LEFT JOIN users ru ON rm.sender_id = ru.id',
        ]
        conditions = ['m.room_id = ?']
        reply_content_expr = 'rm.content AS reply_content'
        reply_sender_expr = 'ru.nickname AS reply_sender'
        reply_key_version_expr = 'COALESCE(rm.key_version, 1) AS reply_key_version'
        if viewer_user_id is not None:
            joins.append('JOIN room_members vm ON vm.room_id = m.room_id AND vm.user_id = ?')
            join_params.append(viewer_user_id)
            conditions.append('COALESCE(m.key_version, 1) >= COALESCE(vm.joined_key_version, 1)')
            reply_content_expr = (
                "CASE WHEN COALESCE(rm.key_version, 1) >= COALESCE(vm.joined_key_version, 1) "
                "THEN rm.content ELSE NULL END AS reply_content"
            )
            reply_sender_expr = (
                "CASE WHEN COALESCE(rm.key_version, 1) >= COALESCE(vm.joined_key_version, 1) "
                "THEN ru.nickname ELSE NULL END AS reply_sender"
            )
            reply_key_version_expr = (
                "CASE WHEN COALESCE(rm.key_version, 1) >= COALESCE(vm.joined_key_version, 1) "
                "THEN COALESCE(rm.key_version, 1) ELSE NULL END AS reply_key_version"
            )
        if before_id:
            conditions.append('m.id < ?')
            where_params.append(before_id)
        conditions.append(_HIDDEN_DELETED_ATTACHMENT_WHERE)

        cursor.execute(
            f'''
                SELECT m.*, u.nickname AS sender_name, u.profile_image AS sender_image,
                       {reply_content_expr}, {reply_sender_expr},
                       {reply_key_version_expr}
                FROM messages m
                {' '.join(joins)}
                WHERE {' AND '.join(conditions)}
                ORDER BY m.id DESC
                LIMIT ?
            ''',
            join_params + where_params + [limit],
        )
        messages = cursor.fetchall()
        message_list = [dict(row) for row in reversed(messages)]

        if include_reactions and message_list:
            message_ids = [message['id'] for message in message_list]
            reactions_map = get_messages_reactions(message_ids)
            for message in message_list:
                message['reactions'] = reactions_map.get(message['id'], [])

        return message_list
    except Exception as exc:
        logger.error(f"Get room messages error: {exc}")
        return []


def update_last_read(room_id, user_id, message_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                UPDATE room_members SET last_read_message_id = ?
                WHERE room_id = ? AND user_id = ? AND last_read_message_id < ?
            ''',
            (message_id, room_id, user_id, message_id),
        )
        conn.commit()
    except Exception as exc:
        logger.error(f"Update last read error: {exc}")


def get_unread_count(room_id, message_id, sender_id=None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if sender_id:
            cursor.execute(
                '''
                    SELECT COUNT(*) FROM room_members
                    WHERE room_id = ? AND last_read_message_id < ? AND user_id != ?
                ''',
                (room_id, message_id, sender_id),
            )
        else:
            cursor.execute(
                '''
                    SELECT COUNT(*) FROM room_members
                    WHERE room_id = ? AND last_read_message_id < ?
                ''',
                (room_id, message_id),
            )
        return cursor.fetchone()[0]
    except Exception as exc:
        logger.error(f"Get unread count error: {exc}")
        return 0


def get_room_last_reads(room_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT last_read_message_id, user_id FROM room_members WHERE room_id = ?', (room_id,))
        return [(row[0] or 0, row[1]) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"Get room last reads error: {exc}")
        return []


def get_message_room_id(message_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT room_id FROM messages WHERE id = ?', (message_id,))
        result = cursor.fetchone()
        return result['room_id'] if result else None
    except Exception as exc:
        logger.error(f"Get message room_id error: {exc}")
        return None


def delete_message(message_id, user_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT sender_id, room_id, file_path FROM messages WHERE id = ?', (message_id,))
        msg = cursor.fetchone()
        if not msg or msg['sender_id'] != user_id:
            return False, "삭제 권한이 없습니다."

        cursor.execute(
            "UPDATE messages SET content = '[삭제된 메시지]', encrypted = 0, file_path = NULL, file_name = NULL WHERE id = ?",
            (message_id,),
        )
        if msg['file_path']:
            cursor.execute('DELETE FROM room_files WHERE file_path = ?', (msg['file_path'],))

        conn.commit()

        if msg['file_path']:
            full_path = os.path.join(get_upload_folder(), msg['file_path'])
            safe_file_delete(full_path)

        return True, msg['room_id']
    except Exception as exc:
        logger.error(f"Delete message error: {exc}")
        return False, "메시지 삭제 중 오류가 발생했습니다."


def edit_message(message_id, user_id, new_content, encrypted=None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT sender_id, room_id, COALESCE(encrypted, 0) AS encrypted, COALESCE(key_version, 1) AS key_version FROM messages WHERE id = ?',
            (message_id,),
        )
        msg = cursor.fetchone()
        if not msg or msg['sender_id'] != user_id:
            return False, "수정 권한이 없습니다.", None, None

        encrypted_flag = bool(msg['encrypted']) if encrypted is None else bool(encrypted)
        key_version = int(msg['key_version'] or 1)
        if encrypted_flag:
            key_version = _get_room_key_version(cursor, msg['room_id'])

        cursor.execute(
            'UPDATE messages SET content = ?, encrypted = ?, key_version = ? WHERE id = ?',
            (new_content, 1 if encrypted_flag else 0, key_version, message_id),
        )
        conn.commit()
        return True, "", msg['room_id'], key_version
    except Exception as exc:
        logger.error(f"Edit message error: {exc}")
        return False, "메시지 수정 중 오류가 발생했습니다.", None, None


def search_messages(user_id, query, offset=0, limit=50):
    conn = get_db()
    cursor = conn.cursor()
    try:
        q = (query or '').strip()
        if not q:
            return {'messages': [], 'total': 0, 'offset': offset, 'limit': limit, 'has_more': False}

        def _fts5_available():
            try:
                cursor.execute("SELECT 1 FROM messages_fts LIMIT 1")
                cursor.fetchone()
                return True
            except Exception:
                return False

        def _fts5_build_query(text: str):
            text = (text or '').strip()
            if not text:
                return None
            parts = [part for part in re.split(r'\s+', text) if part]
            parts = [part.replace('"', '""') for part in parts]
            return ' AND '.join([f'"{part}"' for part in parts]) if parts else None

        fts_query = _fts5_build_query(q)
        if fts_query and _fts5_available():
            cursor.execute(
                '''
                    WITH hits AS (
                        SELECT rowid AS id
                        FROM messages_fts
                        WHERE content MATCH ?
                    )
                    SELECT COUNT(DISTINCT m.id)
                    FROM hits h
                    JOIN messages m ON m.id = h.id
                    JOIN room_members rm ON rm.room_id = m.room_id
                    WHERE rm.user_id = ? AND m.encrypted = 0 AND ''' + _VISIBLE_FOR_MEMBER_WHERE + '''
                ''',
                (fts_query, user_id),
            )
            total_count = cursor.fetchone()[0]

            cursor.execute(
                '''
                    WITH hits AS (
                        SELECT rowid AS id, bm25(messages_fts) AS rank
                        FROM messages_fts
                        WHERE content MATCH ?
                    )
                    SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                    FROM hits h
                    JOIN messages m ON m.id = h.id
                    JOIN rooms r ON m.room_id = r.id
                    JOIN room_members rm ON r.id = rm.room_id AND rm.user_id = ?
                    JOIN users u ON m.sender_id = u.id
                    WHERE m.encrypted = 0 AND ''' + _VISIBLE_FOR_MEMBER_WHERE + '''
                    ORDER BY h.rank ASC, m.created_at DESC
                    LIMIT ? OFFSET ?
                ''',
                (fts_query, user_id, limit, offset),
            )
            messages = [dict(message) for message in cursor.fetchall()]
            return {
                'messages': messages,
                'total': total_count,
                'offset': offset,
                'limit': limit,
                'has_more': offset + len(messages) < total_count,
                'note': '암호화된 메시지는 서버 검색에서 제외됩니다.',
            }

        cursor.execute(
            '''
                SELECT COUNT(DISTINCT m.id)
                FROM messages m
                JOIN rooms r ON m.room_id = r.id
                JOIN room_members rm ON r.id = rm.room_id
                WHERE rm.user_id = ? AND m.encrypted = 0
                  AND ''' + _VISIBLE_FOR_MEMBER_WHERE + '''
                  AND ''' + _HIDDEN_DELETED_ATTACHMENT_WHERE + '''
                  AND m.content LIKE ?
            ''',
            (user_id, f'%{query}%'),
        )
        total_count = cursor.fetchone()[0]

        cursor.execute(
            '''
                SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                FROM messages m
                JOIN rooms r ON m.room_id = r.id
                JOIN room_members rm ON r.id = rm.room_id
                JOIN users u ON m.sender_id = u.id
                WHERE rm.user_id = ? AND m.encrypted = 0
                  AND ''' + _VISIBLE_FOR_MEMBER_WHERE + '''
                  AND ''' + _HIDDEN_DELETED_ATTACHMENT_WHERE + '''
                  AND m.content LIKE ?
                ORDER BY m.created_at DESC
                LIMIT ? OFFSET ?
            ''',
            (user_id, f'%{query}%', limit, offset),
        )
        messages = [dict(message) for message in cursor.fetchall()]
        return {
            'messages': messages,
            'total': total_count,
            'offset': offset,
            'limit': limit,
            'has_more': offset + len(messages) < total_count,
            'note': '암호화된 메시지는 서버 검색에서 제외됩니다.',
        }
    except Exception as exc:
        logger.error(f"Search messages error: {exc}")
        return {'messages': [], 'total': 0, 'offset': 0, 'limit': limit, 'has_more': False}


def advanced_search(
    user_id: int,
    query: str | None = None,
    room_id: int | None = None,
    sender_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    file_only: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    conn = get_db()
    cursor = conn.cursor()
    try:
        def _like_escape(text: str) -> str:
            return (text or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

        def _fts5_available():
            try:
                cursor.execute("SELECT 1 FROM messages_fts LIMIT 1")
                cursor.fetchone()
                return True
            except Exception:
                return False

        def _fts5_build_query(text: str):
            text = (text or '').strip()
            if not text:
                return None
            parts = [part for part in re.split(r'\s+', text) if part]
            parts = [part.replace('"', '""') for part in parts]
            return ' AND '.join([f'"{part}"' for part in parts]) if parts else None

        conditions = ['rm.user_id = ?', _VISIBLE_FOR_MEMBER_WHERE, _HIDDEN_DELETED_ATTACHMENT_WHERE]
        params: list[object] = [user_id]

        if room_id:
            conditions.append('m.room_id = ?')
            params.append(room_id)
        if sender_id:
            conditions.append('m.sender_id = ?')
            params.append(sender_id)
        if date_from:
            conditions.append('m.created_at >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('m.created_at <= ?')
            params.append(date_to)

        if file_only:
            conditions.append("m.message_type IN ('file', 'image')")
            if query:
                q = _like_escape(query.strip())
                if q:
                    where_base = ' AND '.join(conditions)
                    prefix = f'{q}%'
                    contains = f'%{q}%'
                    count_params = params.copy() + [prefix] + params.copy() + [contains, prefix]
                    cursor.execute(
                        f'''
                            SELECT COUNT(DISTINCT id) FROM (
                                SELECT m.id AS id
                                FROM messages m
                                JOIN rooms r ON m.room_id = r.id
                                JOIN room_members rm ON r.id = rm.room_id
                                WHERE {where_base}
                                  AND m.file_name LIKE ? ESCAPE '\\'
                                UNION ALL
                                SELECT m.id AS id
                                FROM messages m
                                JOIN rooms r ON m.room_id = r.id
                                JOIN room_members rm ON r.id = rm.room_id
                                WHERE {where_base}
                                  AND m.file_name LIKE ? ESCAPE '\\'
                                  AND m.file_name NOT LIKE ? ESCAPE '\\'
                            ) t
                        ''',
                        count_params,
                    )
                    total_count = cursor.fetchone()[0]

                    list_params = params.copy() + [prefix] + params.copy() + [contains, prefix, limit, offset]
                    cursor.execute(
                        f'''
                            SELECT * FROM (
                                SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                                FROM messages m
                                JOIN rooms r ON m.room_id = r.id
                                JOIN room_members rm ON r.id = rm.room_id
                                JOIN users u ON m.sender_id = u.id
                                WHERE {where_base}
                                  AND m.file_name LIKE ? ESCAPE '\\'
                                UNION ALL
                                SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                                FROM messages m
                                JOIN rooms r ON m.room_id = r.id
                                JOIN room_members rm ON r.id = rm.room_id
                                JOIN users u ON m.sender_id = u.id
                                WHERE {where_base}
                                  AND m.file_name LIKE ? ESCAPE '\\'
                                  AND m.file_name NOT LIKE ? ESCAPE '\\'
                            )
                            ORDER BY created_at DESC
                            LIMIT ? OFFSET ?
                        ''',
                        list_params,
                    )
                    messages = [dict(row) for row in cursor.fetchall()]
                    return {
                        'messages': messages,
                        'total': total_count,
                        'offset': offset,
                        'limit': limit,
                        'has_more': offset + len(messages) < total_count,
                    }
        elif query:
            conditions.append('m.encrypted = 0')
            fts_query = _fts5_build_query(query)
            if fts_query and _fts5_available():
                where_clause = ' AND '.join(conditions)
                count_params = [fts_query] + params.copy()
                cursor.execute(
                    f'''
                        WITH hits AS (
                            SELECT rowid AS id, bm25(messages_fts) AS rank
                            FROM messages_fts
                            WHERE content MATCH ?
                        )
                        SELECT COUNT(DISTINCT m.id)
                        FROM hits h
                        JOIN messages m ON m.id = h.id
                        JOIN rooms r ON m.room_id = r.id
                        JOIN room_members rm ON r.id = rm.room_id
                        WHERE {where_clause}
                    ''',
                    count_params,
                )
                total_count = cursor.fetchone()[0]

                list_params = [fts_query] + params + [limit, offset]
                cursor.execute(
                    f'''
                        WITH hits AS (
                            SELECT rowid AS id, bm25(messages_fts) AS rank
                            FROM messages_fts
                            WHERE content MATCH ?
                        )
                        SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                        FROM hits h
                        JOIN messages m ON m.id = h.id
                        JOIN rooms r ON m.room_id = r.id
                        JOIN room_members rm ON r.id = rm.room_id
                        JOIN users u ON m.sender_id = u.id
                        WHERE {where_clause}
                        ORDER BY h.rank ASC, m.created_at DESC
                        LIMIT ? OFFSET ?
                    ''',
                    list_params,
                )
                messages = [dict(row) for row in cursor.fetchall()]
                return {
                    'messages': messages,
                    'total': total_count,
                    'offset': offset,
                    'limit': limit,
                    'has_more': offset + len(messages) < total_count,
                    'note': '암호화된 메시지는 서버 검색에서 제외됩니다.',
                }
            conditions.append('m.content LIKE ?')
            params.append(f'%{query}%')

        where_clause = ' AND '.join(conditions)
        count_params = params.copy()
        cursor.execute(
            f'''
                SELECT COUNT(DISTINCT m.id)
                FROM messages m
                JOIN rooms r ON m.room_id = r.id
                JOIN room_members rm ON r.id = rm.room_id
                WHERE {where_clause}
            ''',
            count_params,
        )
        total_count = cursor.fetchone()[0]

        list_params = params + [limit, offset]
        cursor.execute(
            f'''
                SELECT m.*, r.name AS room_name, u.nickname AS sender_name
                FROM messages m
                JOIN rooms r ON m.room_id = r.id
                JOIN room_members rm ON r.id = rm.room_id
                JOIN users u ON m.sender_id = u.id
                WHERE {where_clause}
                ORDER BY m.created_at DESC
                LIMIT ? OFFSET ?
            ''',
            list_params,
        )
        messages = [dict(row) for row in cursor.fetchall()]
        out = {
            'messages': messages,
            'total': total_count,
            'offset': offset,
            'limit': limit,
            'has_more': offset + len(messages) < total_count,
        }
        if query and not file_only:
            out['note'] = '암호화된 메시지는 서버 검색에서 제외됩니다.'
        return out
    except Exception as exc:
        logger.error(f"Advanced search error: {exc}")
        return {'messages': [], 'total': 0, 'offset': 0, 'limit': limit, 'has_more': False}


def pin_message(
    room_id: int,
    pinned_by: int,
    message_id: int | None = None,
    content: str | None = None,
):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if message_id is not None and get_message_room_id(message_id) != room_id:
            return None
        cursor.execute(
            '''
                INSERT INTO pinned_messages (room_id, message_id, content, pinned_by)
                VALUES (?, ?, ?, ?)
            ''',
            (room_id, message_id, content, pinned_by),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as exc:
        logger.error(f"Pin message error: {exc}")
        return None


def unpin_message(pin_id: int, user_id: int, room_id: int | None = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT pinned_by, room_id FROM pinned_messages WHERE id = ?', (pin_id,))
        pin = cursor.fetchone()
        if not pin:
            return False, "공지를 찾을 수 없습니다."
        if room_id is not None and pin['room_id'] != room_id:
            return False, "요청한 방과 공지의 방이 일치하지 않습니다."

        cursor.execute('DELETE FROM pinned_messages WHERE id = ?', (pin_id,))
        if cursor.rowcount < 1:
            conn.rollback()
            return False, "공지를 해제하지 못했습니다."
        conn.commit()
        return True, None
    except Exception as exc:
        logger.error(f"Unpin message error: {exc}")
        return False, "공지 해제 중 오류가 발생했습니다."


def get_pinned_messages(room_id: int):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                SELECT pm.*, u.nickname AS pinned_by_name,
                       m.content AS message_content, m.sender_id AS message_sender_id
                FROM pinned_messages pm
                JOIN users u ON pm.pinned_by = u.id
                LEFT JOIN messages m ON pm.message_id = m.id
                WHERE pm.room_id = ?
                ORDER BY pm.pinned_at DESC
            ''',
            (room_id,),
        )
        return [dict(pin) for pin in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"Get pinned messages error: {exc}")
        return []
