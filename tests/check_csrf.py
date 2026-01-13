import requests
import re
import random
import string

base_url = 'http://127.0.0.1:5000'
s = requests.Session()

def get_csrf_token():
    res = s.get(base_url + '/')
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', res.text)
    return match.group(1) if match else None

def check_csrf_after_login():
    # 1. Get initial CSRF
    initial_token = get_csrf_token()
    print(f"Initial CSRF: {initial_token}")
    
    # 2. Login
    username = f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    password = "password123"
    # Register first
    s.post(base_url + '/api/register', json={'username': username, 'password': password, 'nickname': username}, headers={'X-CSRFToken': initial_token})
    # Login
    res = s.post(base_url + '/api/login', json={'username': username, 'password': password}, headers={'X-CSRFToken': initial_token})
    print(f"Login Status: {res.status_code}")
    
    # 3. Try POST action with OLD token
    print("Attempting POST with INITIAL token...")
    res = s.post(base_url + '/api/rooms', json={'name': 'test_room', 'members': []}, headers={'X-CSRFToken': initial_token})
    
    print(f"POST Status: {res.status_code}")
    if res.status_code == 200:
        print("PASS: Old CSRF token works.")
    else:
        print(f"FAIL: Old CSRF token rejected. Body: {res.text}")

if __name__ == "__main__":
    check_csrf_after_login()
