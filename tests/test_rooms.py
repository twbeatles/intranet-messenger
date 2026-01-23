# -*- coding: utf-8 -*-
"""
대화방 API 테스트
"""
import pytest


def test_create_room(client):
    """대화방 생성 테스트"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'room_user1',
        'password': 'password123',
        'nickname': 'User1'
    })
    client.post('/api/register', json={
        'username': 'room_user2',
        'password': 'password123',
        'nickname': 'User2'
    })
    client.post('/api/login', json={
        'username': 'room_user1',
        'password': 'password123'
    })
    
    # 대화방 생성
    response = client.post('/api/rooms', json={
        'name': 'Test Room',
        'members': [1, 2]
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    assert 'room_id' in response.json


def test_leave_room(client):
    """대화방 나가기 테스트"""
    # Setup
    client.post('/api/register', json={
        'username': 'leave_user1',
        'password': 'password123',
        'nickname': 'LeaveUser1'
    })
    client.post('/api/register', json={
        'username': 'leave_user2',
        'password': 'password123',
        'nickname': 'LeaveUser2'
    })
    client.post('/api/login', json={
        'username': 'leave_user1',
        'password': 'password123'
    })
    
    # 대화방 생성
    response = client.post('/api/rooms', json={
        'name': 'Leave Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 대화방 나가기
    response = client.post(f'/api/rooms/{room_id}/leave')
    assert response.status_code == 200
    assert response.json['success'] is True


def test_room_access_denied(client):
    """비멤버의 대화방 접근 차단 테스트"""
    # 사용자1 등록 및 로그인
    client.post('/api/register', json={
        'username': 'access_user1',
        'password': 'password123',
        'nickname': 'AccessUser1'
    })
    client.post('/api/register', json={
        'username': 'access_user2',
        'password': 'password123',
        'nickname': 'AccessUser2'
    })
    client.post('/api/register', json={
        'username': 'access_user3',
        'password': 'password123',
        'nickname': 'AccessUser3'
    })
    
    # 사용자1로 로그인하여 대화방 생성 (1, 2만 멤버)
    client.post('/api/login', json={
        'username': 'access_user1',
        'password': 'password123'
    })
    response = client.post('/api/rooms', json={
        'name': 'Private Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 사용자3으로 로그인 (비멤버)
    client.post('/api/logout')
    client.post('/api/login', json={
        'username': 'access_user3',
        'password': 'password123'
    })
    
    # 비멤버가 메시지 조회 시도 -> 403 예상
    response = client.get(f'/api/rooms/{room_id}/messages')
    assert response.status_code == 403


def test_invite_member(client):
    """멤버 초대 테스트"""
    # Setup
    client.post('/api/register', json={
        'username': 'invite_user1',
        'password': 'password123',
        'nickname': 'InviteUser1'
    })
    client.post('/api/register', json={
        'username': 'invite_user2',
        'password': 'password123',
        'nickname': 'InviteUser2'
    })
    client.post('/api/register', json={
        'username': 'invite_user3',
        'password': 'password123',
        'nickname': 'InviteUser3'
    })
    client.post('/api/login', json={
        'username': 'invite_user1',
        'password': 'password123'
    })
    
    # 대화방 생성 (1, 2만 멤버)
    response = client.post('/api/rooms', json={
        'name': 'Invite Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 사용자3 초대
    response = client.post(f'/api/rooms/{room_id}/members', json={
        'user_id': 3
    })
    assert response.status_code == 200
    assert response.json['success'] is True
