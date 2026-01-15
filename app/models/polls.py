# -*- coding: utf-8 -*-
"""
투표 관리 모듈
"""

import logging
from app.models.base import get_db

logger = logging.getLogger(__name__)


def create_poll(room_id: int, created_by: int, question: str, options: list,
                multiple_choice: bool = False, anonymous: bool = False, ends_at: str = None):
    """투표 생성"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO polls (room_id, created_by, question, multiple_choice, anonymous, ends_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (room_id, created_by, question, 1 if multiple_choice else 0, 1 if anonymous else 0, ends_at))
        poll_id = cursor.lastrowid
        
        for option_text in options:
            cursor.execute('INSERT INTO poll_options (poll_id, option_text) VALUES (?, ?)', (poll_id, option_text))
        
        conn.commit()
        return get_poll(poll_id)
    except Exception as e:
        conn.rollback()
        logger.error(f"Create poll error: {e}")
        return None


def get_poll(poll_id: int):
    """투표 정보 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return None
        
        poll_dict = dict(poll)
        
        # 옵션 조회
        cursor.execute('''
            SELECT po.id, po.option_text, COUNT(pv.id) as vote_count
            FROM poll_options po
            LEFT JOIN poll_votes pv ON po.id = pv.option_id
            WHERE po.poll_id = ?
            GROUP BY po.id
        ''', (poll_id,))
        poll_dict['options'] = [dict(o) for o in cursor.fetchall()]
        
        # 총 투표 수
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id = ?', (poll_id,))
        poll_dict['total_voters'] = cursor.fetchone()[0]
        
        return poll_dict
    except Exception as e:
        logger.error(f"Get poll error: {e}")
        return None


def get_room_polls(room_id: int):
    """대화방의 투표 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT p.*, u.nickname as creator_name
            FROM polls p
            JOIN users u ON p.created_by = u.id
            WHERE p.room_id = ?
            ORDER BY p.created_at DESC
        ''', (room_id,))
        polls = [dict(p) for p in cursor.fetchall()]
        
        for poll in polls:
            cursor.execute('''
                SELECT po.id, po.option_text, COUNT(pv.id) as vote_count
                FROM poll_options po
                LEFT JOIN poll_votes pv ON po.id = pv.option_id
                WHERE po.poll_id = ?
                GROUP BY po.id
            ''', (poll['id'],))
            poll['options'] = [dict(o) for o in cursor.fetchall()]
            
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id = ?', (poll['id'],))
            poll['total_voters'] = cursor.fetchone()[0]
        
        return polls
    except Exception as e:
        logger.error(f"Get room polls error: {e}")
        return []


def vote_poll(poll_id: int, option_id: int, user_id: int):
    """투표 참여"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 투표 마감 여부 확인
        cursor.execute('SELECT closed, multiple_choice FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return False, "투표를 찾을 수 없습니다."
        if poll['closed']:
            return False, "마감된 투표입니다."
        
        # 복수 선택 불가 시 기존 투표 삭제
        if not poll['multiple_choice']:
            cursor.execute('DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?', (poll_id, user_id))
        else:
            # 중복 투표 확인
            cursor.execute('SELECT 1 FROM poll_votes WHERE poll_id = ? AND option_id = ? AND user_id = ?',
                          (poll_id, option_id, user_id))
            if cursor.fetchone():
                return False, "이미 투표한 옵션입니다."
        
        cursor.execute('INSERT INTO poll_votes (poll_id, option_id, user_id) VALUES (?, ?, ?)',
                      (poll_id, option_id, user_id))
        conn.commit()
        return True, None
    except Exception as e:
        logger.error(f"Vote poll error: {e}")
        return False, "투표 중 오류가 발생했습니다."


def get_user_votes(poll_id: int, user_id: int):
    """사용자의 투표 내역"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?', (poll_id, user_id))
        return [row['option_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get user votes error: {e}")
        return []


def close_poll(poll_id: int, user_id: int, is_admin: bool = False):
    """투표 마감 - 생성자 또는 관리자만 가능"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT created_by, closed FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return False, "투표를 찾을 수 없습니다."
        if poll['closed']:
            return False, "이미 마감된 투표입니다."
        # [v4.21] 생성자 또는 관리자만 마감 가능
        if poll['created_by'] != user_id and not is_admin:
            return False, "투표 생성자 또는 관리자만 마감할 수 있습니다."
        
        cursor.execute('UPDATE polls SET closed = 1 WHERE id = ?', (poll_id,))
        conn.commit()
        return True, None
    except Exception as e:
        logger.error(f"Close poll error: {e}")
        return False, "마감 중 오류가 발생했습니다."
