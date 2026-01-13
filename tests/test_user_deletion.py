# -*- coding: utf-8 -*-
"""
사용자 삭제 및 데이터 정리 테스트
"""
import pytest
import os
import tempfile


def test_user_deletion_cleanup(client, app):
    """사용자 삭제 시 관련 데이터 정리 테스트"""
    # 사용자 등록
    response = client.post('/api/register', json={
        'username': 'delete_test_user',
        'password': 'password123',
        'nickname': 'Delete Tester'
    })
    assert response.status_code == 200
    
    # 로그인
    client.post('/api/login', json={
        'username': 'delete_test_user',
        'password': 'password123'
    })
    
    # 계정 삭제
    response = client.delete('/api/me', json={
        'password': 'password123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    
    # 삭제 후 로그인 실패 확인
    response = client.post('/api/login', json={
        'username': 'delete_test_user',
        'password': 'password123'
    })
    assert response.status_code == 401


def test_user_deletion_wrong_password(client):
    """잘못된 비밀번호로 삭제 시도"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'nodelete_user',
        'password': 'password123',
        'nickname': 'No Delete'
    })
    client.post('/api/login', json={
        'username': 'nodelete_user',
        'password': 'password123'
    })
    
    # 잘못된 비밀번호로 삭제 시도
    response = client.delete('/api/me', json={
        'password': 'wrongpassword'
    })
    assert response.status_code == 400
    assert '비밀번호' in response.json.get('error', '')


def test_change_password(client):
    """비밀번호 변경 테스트"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'pwchange_user',
        'password': 'oldpassword123',
        'nickname': 'PW Changer'
    })
    client.post('/api/login', json={
        'username': 'pwchange_user',
        'password': 'oldpassword123'
    })
    
    # 비밀번호 변경
    response = client.put('/api/me/password', json={
        'current_password': 'oldpassword123',
        'new_password': 'newpassword123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    
    # 로그아웃 후 새 비밀번호로 로그인
    client.post('/api/logout')
    response = client.post('/api/login', json={
        'username': 'pwchange_user',
        'password': 'newpassword123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
