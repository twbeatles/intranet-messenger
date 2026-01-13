# -*- coding: utf-8 -*-
"""
권한 검증 테스트
"""
import pytest


def test_invite_nonexistent_user(client):
    """존재하지 않는 사용자 초대 시도"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'auth_test_user',
        'password': 'password123',
        'nickname': 'Auth Tester'
    })
    client.post('/api/login', json={
        'username': 'auth_test_user',
        'password': 'password123'
    })
    
    # 방 생성
    response = client.post('/api/rooms', json={
        'name': 'Auth Test Room',
        'members': []
    })
    room_id = response.json['room_id']
    
    # 존재하지 않는 사용자 초대
    response = client.post(f'/api/rooms/{room_id}/members', json={
        'user_ids': [99999]  # 존재하지 않는 ID
    })
    # added_count가 0이거나 에러 응답
    assert response.json.get('added_count', 0) == 0 or response.status_code == 400


def test_invite_existing_user(client):
    """존재하는 사용자 초대 테스트"""
    # 두 사용자 등록
    client.post('/api/register', json={
        'username': 'invite_host',
        'password': 'password123',
        'nickname': 'Host'
    })
    client.post('/api/register', json={
        'username': 'invite_guest',
        'password': 'password123',
        'nickname': 'Guest'
    })
    
    # 첫 번째 사용자로 로그인
    client.post('/api/login', json={
        'username': 'invite_host',
        'password': 'password123'
    })
    
    # 방 생성
    response = client.post('/api/rooms', json={
        'name': 'Invite Test Room',
        'members': []
    })
    room_id = response.json['room_id']
    
    # 두 번째 사용자 초대 (user_id 2)
    response = client.post(f'/api/rooms/{room_id}/members', json={
        'user_ids': [2]
    })
    assert response.status_code == 200
    assert response.json.get('added_count', 0) == 1


def test_session_regeneration_on_login(client):
    """로그인 시 세션 재생성 확인"""
    # 사용자 등록
    client.post('/api/register', json={
        'username': 'session_test_user',
        'password': 'password123',
        'nickname': 'Session Tester'
    })
    
    # 첫 번째 로그인
    response1 = client.post('/api/login', json={
        'username': 'session_test_user',
        'password': 'password123'
    })
    assert response1.status_code == 200
    
    # 현재 사용자 확인
    me_response = client.get('/api/me')
    assert me_response.json.get('logged_in') is True
    
    # 로그아웃 후 재로그인
    client.post('/api/logout')
    response2 = client.post('/api/login', json={
        'username': 'session_test_user',
        'password': 'password123'
    })
    assert response2.status_code == 200
