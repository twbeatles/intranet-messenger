# -*- coding: utf-8 -*-
"""
관리자 보호 테스트 - 마지막 관리자 해제 방지, 자동 위임, 공지 삭제 권한
"""
import pytest


def test_cannot_remove_last_admin(client):
    """마지막 관리자 해제 시 400 에러 반환 확인"""
    # 사용자 등록
    client.post('/api/register', json={
        'username': 'last_admin_user',
        'password': 'password123',
        'nickname': 'Last Admin'
    })
    
    # 로그인
    client.post('/api/login', json={
        'username': 'last_admin_user',
        'password': 'password123'
    })
    
    # 방 생성 (생성자는 자동 관리자)
    response = client.post('/api/rooms', json={
        'name': 'Last Admin Test Room',
        'members': []
    })
    room_id = response.json['room_id']
    
    # 자신의 관리자 권한 해제 시도 (마지막 관리자이므로 실패해야 함)
    response = client.post(f'/api/rooms/{room_id}/admins', json={
        'user_id': 1,
        'is_admin': False
    })
    assert response.status_code == 400
    assert '최소 한 명' in response.json.get('error', '')


def test_creator_is_auto_admin(client):
    """방 생성자가 자동으로 관리자로 설정되는지 확인"""
    # 사용자 등록
    client.post('/api/register', json={
        'username': 'auto_admin_user',
        'password': 'password123',
        'nickname': 'Auto Admin'
    })
    
    # 로그인
    client.post('/api/login', json={
        'username': 'auto_admin_user',
        'password': 'password123'
    })
    
    # 방 생성
    response = client.post('/api/rooms', json={
        'name': 'Auto Admin Test Room',
        'members': []
    })
    room_id = response.json['room_id']
    
    # 관리자 여부 확인
    response = client.get(f'/api/rooms/{room_id}/admin-check')
    assert response.status_code == 200
    assert response.json['is_admin'] is True


def test_member_can_delete_pin(client):
    """[v4.20] 모든 멤버가 공지 삭제 가능한지 확인 (정책 변경)"""
    # 두 사용자 등록
    client.post('/api/register', json={
        'username': 'pin_admin',
        'password': 'password123',
        'nickname': 'Pin Admin'
    })
    client.post('/api/register', json={
        'username': 'pin_member',
        'password': 'password123',
        'nickname': 'Pin Member'
    })
    
    # 관리자로 로그인 후 방 생성
    client.post('/api/login', json={
        'username': 'pin_admin',
        'password': 'password123'
    })
    
    response = client.post('/api/rooms', json={
        'name': 'Pin Delete Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 공지 생성
    response = client.post(f'/api/rooms/{room_id}/pins', json={
        'content': '테스트 공지'
    })
    assert response.status_code == 200
    pin_id = response.json['pin_id']
    
    # 일반 멤버로 로그인
    client.post('/api/logout')
    client.post('/api/login', json={
        'username': 'pin_member',
        'password': 'password123'
    })
    
    # [v4.20] 공지 삭제 시도 - 성공해야 함 (모든 멤버가 삭제 가능)
    response = client.delete(f'/api/rooms/{room_id}/pins/{pin_id}')
    assert response.status_code == 200


def test_admin_can_remove_another_admin_if_not_last(client):
    """마지막 관리자가 아닐 때 관리자 권한 해제 가능"""
    # 두 사용자 등록
    client.post('/api/register', json={
        'username': 'multi_admin1',
        'password': 'password123',
        'nickname': 'Admin 1'
    })
    client.post('/api/register', json={
        'username': 'multi_admin2',
        'password': 'password123',
        'nickname': 'Admin 2'
    })
    
    # 첫 번째 사용자로 로그인 후 방 생성
    client.post('/api/login', json={
        'username': 'multi_admin1',
        'password': 'password123'
    })
    
    response = client.post('/api/rooms', json={
        'name': 'Multi Admin Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 두 번째 사용자를 관리자로 승격
    response = client.post(f'/api/rooms/{room_id}/admins', json={
        'user_id': 2,
        'is_admin': True
    })
    assert response.status_code == 200
    
    # 첫 번째 사용자의 관리자 권한 해제 (두 번째 관리자가 있으므로 성공해야 함)
    response = client.post(f'/api/rooms/{room_id}/admins', json={
        'user_id': 1,
        'is_admin': False
    })
    assert response.status_code == 200
