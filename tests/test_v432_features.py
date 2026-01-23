# -*- coding: utf-8 -*-
"""
v4.32 기능 테스트
검색 페이지네이션, 파일 업로드, 리액션 관련 테스트
"""

import pytest


def test_search_api_with_pagination(client):
    """Test search API supports pagination parameters."""
    # Register and login first
    client.post('/api/register', json={
        'username': 'searchuser',
        'password': 'Password123!',
        'nickname': 'SearchTester'
    })
    client.post('/api/login', json={
        'username': 'searchuser',
        'password': 'Password123!'
    })
    
    # Test search with pagination params
    response = client.get('/api/search?q=test&offset=0&limit=20')
    assert response.status_code == 200
    # Should return a list (possibly empty)
    assert isinstance(response.json, list)


def test_search_api_with_date_filters(client):
    """Test search API supports date filtering."""
    client.post('/api/register', json={
        'username': 'dateuser',
        'password': 'Password123!',
        'nickname': 'DateTester'
    })
    client.post('/api/login', json={
        'username': 'dateuser',
        'password': 'Password123!'
    })
    
    # Test search with date filters
    response = client.get('/api/search?q=test&date_from=2025-01-01&date_to=2025-12-31')
    assert response.status_code == 200


def test_file_upload_needs_auth(client):
    """Test file upload requires authentication."""
    response = client.post('/api/upload')
    # Should fail without login
    assert response.status_code in [401, 302]  # 401 or redirect


def test_reaction_api(client):
    """Test reaction API endpoint exists."""
    # Register and login
    client.post('/api/register', json={
        'username': 'reactuser',
        'password': 'Password123!',
        'nickname': 'Reactor'
    })
    client.post('/api/login', json={
        'username': 'reactuser',
        'password': 'Password123!'
    })
    
    # Try getting reactions for non-existent message
    response = client.get('/api/messages/999999/reactions')
    # Should return either empty list or 404
    assert response.status_code in [200, 404]


def test_poll_api(client):
    """Test poll-related endpoints exist."""
    client.post('/api/register', json={
        'username': 'polluser',
        'password': 'Password123!',
        'nickname': 'PollTester'
    })
    client.post('/api/login', json={
        'username': 'polluser',
        'password': 'Password123!'
    })
    
    # First create a room
    room_response = client.post('/api/rooms', json={
        'name': 'Poll Test Room',
        'member_ids': []
    })
    
    if room_response.status_code == 200 and room_response.json.get('room'):
        room_id = room_response.json['room']['id']
        
        # Get polls for the room
        response = client.get(f'/api/rooms/{room_id}/polls')
        assert response.status_code == 200


def test_pins_api(client):
    """Test pins-related endpoints."""
    client.post('/api/register', json={
        'username': 'pinuser',
        'password': 'Password123!',
        'nickname': 'PinTester'
    })
    client.post('/api/login', json={
        'username': 'pinuser',
        'password': 'Password123!'
    })
    
    # Create a room
    room_response = client.post('/api/rooms', json={
        'name': 'Pin Test Room',
        'member_ids': []
    })
    
    if room_response.status_code == 200 and room_response.json.get('room'):
        room_id = room_response.json['room']['id']
        
        # Get pins for the room
        response = client.get(f'/api/rooms/{room_id}/pins')
        assert response.status_code == 200


def test_room_files_api(client):
    """Test room files endpoint."""
    client.post('/api/register', json={
        'username': 'fileuser',
        'password': 'Password123!',
        'nickname': 'FileTester'
    })
    client.post('/api/login', json={
        'username': 'fileuser',
        'password': 'Password123!'
    })
    
    # Create a room
    room_response = client.post('/api/rooms', json={
        'name': 'File Test Room',
        'member_ids': []
    })
    
    if room_response.status_code == 200 and room_response.json.get('room'):
        room_id = room_response.json['room']['id']
        
        # Get files for the room
        response = client.get(f'/api/rooms/{room_id}/files')
        assert response.status_code == 200


def test_profile_api(client):
    """Test profile get/update endpoints."""
    client.post('/api/register', json={
        'username': 'profileuser',
        'password': 'Password123!',
        'nickname': 'ProfileTester'
    })
    client.post('/api/login', json={
        'username': 'profileuser',
        'password': 'Password123!'
    })
    
    # Get profile
    response = client.get('/api/profile')
    assert response.status_code == 200
    
    # Update profile
    response = client.put('/api/profile', json={
        'nickname': 'UpdatedNickname',
        'status_message': 'Hello!'
    })
    assert response.status_code == 200
