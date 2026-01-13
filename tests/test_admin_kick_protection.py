# -*- coding: utf-8 -*-
"""
관리자 강퇴 보호 테스트
[v4.10] 관리자가 다른 관리자를 강퇴할 수 없음을 확인
"""
import pytest


def test_kick_admin_by_admin(client):
    """관리자가 다른 관리자를 강퇴하려고 할 때 - 실패해야 함"""
    # 두 사용자 등록
    client.post('/api/register', json={
        'username': 'admin_kicker',
        'password': 'password123',
        'nickname': 'Admin Kicker'
    })
    client.post('/api/register', json={
        'username': 'admin_target',
        'password': 'password123',
        'nickname': 'Admin Target'
    })
    
    # 첫 번째 사용자(관리자)로 로그인
    client.post('/api/login', json={
        'username': 'admin_kicker',
        'password': 'password123'
    })
    
    # 방 생성 (방 생성자는 자동 관리자)
    response = client.post('/api/rooms', json={
        'name': 'Admin Protection Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 두 번째 사용자를 관리자로 설정
    response = client.post(f'/api/rooms/{room_id}/admins', json={
        'user_id': 2,
        'is_admin': True
    })
    assert response.status_code == 200
    
    # 관리자가 다른 관리자를 강퇴 시도 - 403 에러 반환해야 함
    response = client.delete(f'/api/rooms/{room_id}/members/2')
    assert response.status_code == 403
    assert '관리자' in response.json.get('error', '')


def test_kick_regular_member_by_admin(client):
    """관리자가 일반 멤버를 강퇴 - 성공해야 함"""
    # 세 사용자 등록
    client.post('/api/register', json={
        'username': 'room_admin',
        'password': 'password123',
        'nickname': 'Room Admin'
    })
    client.post('/api/register', json={
        'username': 'regular_member',
        'password': 'password123',
        'nickname': 'Regular'
    })
    
    # 관리자로 로그인
    client.post('/api/login', json={
        'username': 'room_admin',
        'password': 'password123'
    })
    
    # 방 생성
    response = client.post('/api/rooms', json={
        'name': 'Regular Kick Test',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 일반 멤버 강퇴 - 성공해야 함
    response = client.delete(f'/api/rooms/{room_id}/members/2')
    assert response.status_code == 200
    assert response.json['success'] is True
