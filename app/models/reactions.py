# -*- coding: utf-8 -*-
"""
리액션 관리 모듈
"""

import logging
from app.models.base import get_db

logger = logging.getLogger(__name__)


def add_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO message_reactions (message_id, user_id, emoji)
            VALUES (?, ?, ?)
        ''', (message_id, user_id, emoji))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Add reaction error: {e}")
        return False


def remove_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 제거"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?
        ''', (message_id, user_id, emoji))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Remove reaction error: {e}")
        return False


def toggle_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 토글"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?
        ''', (message_id, user_id, emoji))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute('DELETE FROM message_reactions WHERE id = ?', (exists['id'],))
            action = 'removed'
        else:
            cursor.execute('''
                INSERT INTO message_reactions (message_id, user_id, emoji) VALUES (?, ?, ?)
            ''', (message_id, user_id, emoji))
            action = 'added'
        
        conn.commit()
        return True, action
    except Exception as e:
        logger.error(f"Toggle reaction error: {e}")
        return False, None


def get_message_reactions(message_id: int):
    """메시지의 리액션 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT emoji, COUNT(*) as count, GROUP_CONCAT(user_id) as user_ids
            FROM message_reactions
            WHERE message_id = ?
            GROUP BY emoji
        ''', (message_id,))
        reactions = []
        for r in cursor.fetchall():
            reactions.append({
                'emoji': r['emoji'],
                'count': r['count'],
                'user_ids': [int(uid) for uid in r['user_ids'].split(',')]
            })
        return reactions
    except Exception as e:
        logger.error(f"Get message reactions error: {e}")
        return []


def get_messages_reactions(message_ids: list):
    """여러 메시지의 리액션 일괄 조회"""
    if not message_ids:
        return {}
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        placeholders = ','.join('?' * len(message_ids))
        cursor.execute(f'''
            SELECT message_id, emoji, COUNT(*) as count, GROUP_CONCAT(user_id) as user_ids
            FROM message_reactions
            WHERE message_id IN ({placeholders})
            GROUP BY message_id, emoji
        ''', message_ids)
        
        result = {}
        for r in cursor.fetchall():
            mid = r['message_id']
            if mid not in result:
                result[mid] = []
            result[mid].append({
                'emoji': r['emoji'],
                'count': r['count'],
                'user_ids': [int(uid) for uid in r['user_ids'].split(',')]
            })
        return result
    except Exception as e:
        logger.error(f"Get messages reactions error: {e}")
        return {}
