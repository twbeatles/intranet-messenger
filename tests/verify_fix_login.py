import requests
import re
import random
import string

base_url = 'http://127.0.0.1:5001'
s = requests.Session()

def get_csrf_token(text):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', text)
    return match.group(1) if match else None

def verify_fix():
    # 1. Initial Page Load
    print("1. Loading index page...")
    res = s.get(base_url + '/')
    initial_csrf = get_csrf_token(res.text)
    print(f"Initial CSRF: {initial_csrf}")
    
    if not initial_csrf:
        print("FAIL: No CSRF token on index page")
        return

    # 2. Register User
    username = f"newuser_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    password = "password123"
    print(f"2. Registering {username}...")
    res = s.post(base_url + '/api/register', json={
        'username': username, 
        'password': password,
        'nickname': username
    }, headers={'X-CSRFToken': initial_csrf})
    
    # 3. Login
    print("3. Logging in...")
    res = s.post(base_url + '/api/login', json={
        'username': username,
        'password': password
    }, headers={'X-CSRFToken': initial_csrf})
    
    if res.status_code != 200:
        print(f"FAIL: Login failed {res.status_code} {res.text}")
        return
        
    data = res.json()
    new_csrf = data.get('csrf_token')
    print(f"Login Response CSRF: {new_csrf}")
    
    if not new_csrf:
        print("FAIL: No CSRF token returned in login response")
        return
        
    if new_csrf == initial_csrf:
        print("WARNING: CSRF token did not change (session might not have been cleared/regenerated?)")
    else:
        print("PASS: CSRF token rotated successfully")

    # 4. Perform Action with NEW Token (simulate app.js behavior)
    print("4. Attempting action with NEW CSRF token...")
    # Create a room
    room_payload = {'name': 'Test Room', 'members': []}
    res = s.post(base_url + '/api/rooms', json=room_payload, headers={'X-CSRFToken': new_csrf})
    
    if res.status_code == 200:
        print("PASS: POST action successful with new token")
    else:
        print(f"FAIL: POST action failed {res.status_code} {res.text}")

    # 5. Verify Session Persistence
    print("5. Verifying session persistence...")
    res = s.get(base_url + '/api/me')
    if res.json().get('logged_in'):
        print("PASS: Session valid")
    else:
        print("FAIL: Session lost")

if __name__ == "__main__":
    verify_fix()
