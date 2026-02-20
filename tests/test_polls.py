# -*- coding: utf-8 -*-
"""
투표 기능 테스트
"""
import pytest


def test_create_poll(client):
    """투표 생성 테스트"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'poll_user',
        'password': 'password123',
        'nickname': 'Poll Tester'
    })
    client.post('/api/login', json={
        'username': 'poll_user',
        'password': 'password123'
    })
    
    # 다른 사용자 등록
    client.post('/api/register', json={
        'username': 'poll_user2',
        'password': 'password123',
        'nickname': 'Poll Tester 2'
    })
    
    # 대화방 생성
    response = client.post('/api/rooms', json={
        'name': 'Test Room',
        'members': [1, 2]
    })
    assert response.status_code == 200
    room_id = response.json['room_id']
    
    # 투표 생성
    response = client.post(f'/api/rooms/{room_id}/polls', json={
        'question': '점심 메뉴 뭐 먹을까요?',
        'options': ['김치찌개', '된장찌개', '삼겹살'],
        'multiple_choice': False,
        'anonymous': False
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    assert 'poll' in response.json
    assert response.json['poll'] is not None
    assert isinstance(response.json['poll'].get('id'), int)


def test_vote_poll(client):
    """투표 참여 테스트"""
    # Setup: 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'voter',
        'password': 'password123',
        'nickname': 'Voter'
    })
    client.post('/api/register', json={
        'username': 'voter2',
        'password': 'password123',
        'nickname': 'Voter2'
    })
    client.post('/api/login', json={
        'username': 'voter',
        'password': 'password123'
    })
    
    # 대화방 생성
    response = client.post('/api/rooms', json={
        'name': 'Vote Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    # 투표 생성
    response = client.post(f'/api/rooms/{room_id}/polls', json={
        'question': '테스트 질문',
        'options': ['옵션1', '옵션2'],
        'multiple_choice': False
    })
    poll = response.json['poll']
    poll_id = poll['id']
    option_id = poll['options'][0]['id']
    
    # 투표 참여
    response = client.post(f'/api/polls/{poll_id}/vote', json={
        'option_id': option_id
    })
    assert response.status_code == 200
    assert response.json['success'] is True


def test_close_poll(client):
    """투표 마감 테스트"""
    # Setup
    client.post('/api/register', json={
        'username': 'poll_creator',
        'password': 'password123',
        'nickname': 'Creator'
    })
    client.post('/api/register', json={
        'username': 'poll_member',
        'password': 'password123',
        'nickname': 'Member'
    })
    client.post('/api/login', json={
        'username': 'poll_creator',
        'password': 'password123'
    })
    
    # 대화방 및 투표 생성
    response = client.post('/api/rooms', json={
        'name': 'Close Test Room',
        'members': [1, 2]
    })
    room_id = response.json['room_id']
    
    response = client.post(f'/api/rooms/{room_id}/polls', json={
        'question': '마감 테스트',
        'options': ['A', 'B']
    })
    poll_id = response.json['poll']['id']
    
    # 투표 마감
    response = client.post(f'/api/polls/{poll_id}/close')
    assert response.status_code == 200
    assert response.json['success'] is True
