def test_home_page(client):
    """Test that the home page loads successfully."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Safe Messenger" in response.data or "사내 메신저".encode('utf-8') in response.data

def test_register_login(client):
    """Test user registration and login."""
    # Register
    response = client.post('/api/register', json={
        'username': 'testuser',
        'password': 'password123',
        'nickname': 'Tester'
    })
    assert response.status_code == 200
    assert response.json['success'] is True

    # Login
    response = client.post('/api/login', json={
        'username': 'testuser',
        'password': 'password123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True

def test_login_fail(client):
    """Test login with wrong password."""
    # Register first
    client.post('/api/register', json={
        'username': 'testuser2',
        'password': 'password123',
        'nickname': 'Tester2'
    })

    # Fail Login
    response = client.post('/api/login', json={
        'username': 'testuser2',
        'password': 'wrongpassword'
    })
    assert response.status_code == 401
