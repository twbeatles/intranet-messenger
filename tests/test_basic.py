def test_home_page(client):
    """Test that the home page loads successfully."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Safe Messenger" in response.data or "사내 메신저".encode('utf-8') in response.data

def test_register_login(client):
    """Test user registration and login."""
    # Register - [v4.22] 비밀번호 강도 검사 통과용 강한 비밀번호 사용
    response = client.post('/api/register', json={
        'username': 'testuser',
        'password': 'Password123!',
        'nickname': 'Tester'
    })
    assert response.status_code == 200
    assert response.json['success'] is True

    # Login
    response = client.post('/api/login', json={
        'username': 'testuser',
        'password': 'Password123!'
    })
    assert response.status_code == 200
    assert response.json['success'] is True

def test_login_fail(client):
    """Test login with wrong password."""
    # Register first
    client.post('/api/register', json={
        'username': 'testuser2',
        'password': 'Password123!',
        'nickname': 'Tester2'
    })

    # Fail Login
    response = client.post('/api/login', json={
        'username': 'testuser2',
        'password': 'wrongpassword'
    })
    assert response.status_code == 401


# ============================================================================
# [v4.32] 추가 테스트: 대화방 및 API 엔드포인트
# ============================================================================

def test_get_users_unauthorized(client):
    """Test that users endpoint requires login."""
    response = client.get('/api/users')
    assert response.status_code == 401

def test_get_rooms_unauthorized(client):
    """Test that rooms endpoint requires login."""
    response = client.get('/api/rooms')
    assert response.status_code == 401

def test_create_room_and_get_rooms(client):
    """Test room creation and listing."""
    # Register two users
    client.post('/api/register', json={
        'username': 'roomtest1',
        'password': 'Password123!',
        'nickname': 'RoomTester1'
    })
    client.post('/api/register', json={
        'username': 'roomtest2',
        'password': 'Password123!',
        'nickname': 'RoomTester2'
    })
    
    # Login as user 1
    client.post('/api/login', json={
        'username': 'roomtest1',
        'password': 'Password123!'
    })
    
    # Get users to find user 2's ID
    users_response = client.get('/api/users')
    assert users_response.status_code == 200
    users = users_response.json
    user2 = next((u for u in users if u['username'] == 'roomtest2'), None)
    assert user2 is not None
    
    # Create room
    create_response = client.post('/api/rooms', json={
        'members': [user2['id']]
    })
    assert create_response.status_code == 200
    assert create_response.json['success'] is True
    
    # Get rooms
    rooms_response = client.get('/api/rooms')
    assert rooms_response.status_code == 200
    assert len(rooms_response.json) >= 1

def test_logout(client):
    """Test logout functionality."""
    # Register and login
    client.post('/api/register', json={
        'username': 'logouttest',
        'password': 'Password123!',
        'nickname': 'LogoutTester'
    })
    client.post('/api/login', json={
        'username': 'logouttest',
        'password': 'Password123!'
    })
    
    # Logout
    response = client.post('/api/logout')
    assert response.status_code == 200
    
    # Verify logged out - rooms endpoint should fail
    rooms_response = client.get('/api/rooms')
    assert rooms_response.status_code == 401

def test_profile_unauthorized(client):
    """Test that profile endpoint requires login."""
    response = client.get('/api/profile')
    assert response.status_code == 401

def test_profile_get_and_update(client):
    """Test profile get and update."""
    # Register and login
    client.post('/api/register', json={
        'username': 'profiletest',
        'password': 'Password123!',
        'nickname': 'ProfileTester'
    })
    client.post('/api/login', json={
        'username': 'profiletest',
        'password': 'Password123!'
    })
    
    # Get profile
    response = client.get('/api/profile')
    assert response.status_code == 200
    assert response.json['nickname'] == 'ProfileTester'
    
    # Update profile
    update_response = client.put('/api/profile', json={
        'nickname': 'UpdatedTester'
    })
    assert update_response.status_code == 200
    
    # Verify update
    response = client.get('/api/profile')
    assert response.json['nickname'] == 'UpdatedTester'
