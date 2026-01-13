# -*- coding: utf-8 -*-
"""
유지보수 함수 테스트
"""
import pytest
from datetime import datetime, timedelta


def test_close_expired_polls(app):
    """만료된 투표 자동 마감 테스트"""
    with app.app_context():
        from app.models import get_db, create_poll, get_poll, close_expired_polls
        
        # 테스트 데이터 준비: 만료된 투표 생성
        conn = get_db()
        cursor = conn.cursor()
        
        # 테스트 사용자 생성
        cursor.execute("INSERT INTO users (username, password_hash, nickname) VALUES (?, ?, ?)",
                      ('expired_poll_user', 'hash', 'Test User'))
        user_id = cursor.lastrowid
        
        # 테스트 방 생성
        cursor.execute("INSERT INTO rooms (name, type, created_by) VALUES (?, ?, ?)",
                      ('Test Room', 'group', user_id))
        room_id = cursor.lastrowid
        
        # 만료된 투표 생성 (어제 만료)
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO polls (room_id, created_by, question, ends_at, closed)
            VALUES (?, ?, ?, ?, 0)
        ''', (room_id, user_id, '만료된 투표', yesterday))
        expired_poll_id = cursor.lastrowid
        
        # 유효한 투표 생성 (내일 만료)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO polls (room_id, created_by, question, ends_at, closed)
            VALUES (?, ?, ?, ?, 0)
        ''', (room_id, user_id, '유효한 투표', tomorrow))
        valid_poll_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        # 만료 투표 정리 실행
        count = close_expired_polls()
        
        # 검증: 만료된 투표만 closed=1로 변경되어야 함
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT closed FROM polls WHERE id = ?', (expired_poll_id,))
        assert cursor.fetchone()['closed'] == 1, "만료된 투표가 마감되지 않음"
        
        cursor.execute('SELECT closed FROM polls WHERE id = ?', (valid_poll_id,))
        assert cursor.fetchone()['closed'] == 0, "유효한 투표가 잘못 마감됨"
        
        conn.close()


def test_cleanup_old_access_logs(app):
    """오래된 접속 로그 정리 테스트"""
    with app.app_context():
        from app.models import get_db, cleanup_old_access_logs
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 테스트 사용자 생성
        cursor.execute("INSERT INTO users (username, password_hash, nickname) VALUES (?, ?, ?)",
                      ('log_test_user', 'hash', 'Log Tester'))
        user_id = cursor.lastrowid
        
        # 오래된 로그 생성 (100일 전)
        old_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO access_logs (user_id, action, ip_address, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, 'login', '127.0.0.1', old_date))
        
        # 최근 로그 생성
        cursor.execute('''
            INSERT INTO access_logs (user_id, action, ip_address)
            VALUES (?, ?, ?)
        ''', (user_id, 'login', '127.0.0.1'))
        
        conn.commit()
        
        # 정리 전 로그 수 확인
        cursor.execute('SELECT COUNT(*) FROM access_logs WHERE user_id = ?', (user_id,))
        count_before = cursor.fetchone()[0]
        conn.close()
        
        # 90일 이전 로그 정리
        cleanup_old_access_logs(days_to_keep=90)
        
        # 정리 후 확인
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM access_logs WHERE user_id = ?', (user_id,))
        count_after = cursor.fetchone()[0]
        conn.close()
        
        # 오래된 로그 1개가 삭제되었어야 함
        assert count_after == count_before - 1, "오래된 로그가 정리되지 않음"
