import requests
import re
import random
import string
import json

base_url = 'http://127.0.0.1:5000'
s = requests.Session()

def get_csrf_token():
    try:
        res = s.get(base_url + '/')
        match = re.search(r'<meta name="csrf-token" content="([^"]+)">', res.text)
        if match:
            return match.group(1)
        print("Warning: No CSRF token found in index page")
        return None
    except Exception as e:
        print(f"Error fetching CSRF token: {e}")
        return None

def register_and_login():
    # 1. Get CSRF
    csrf_token = get_csrf_token()
    headers = {'X-CSRFToken': csrf_token} if csrf_token else {}
    
    # 2. Register
    username = f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    password = "password123"
    nickname = "TestUser"
    
    print(f"Attempting to register: {username}")
    res = s.post(base_url + '/api/register', json={
        'username': username,
        'password': password,
        'nickname': nickname
    }, headers=headers)
    
    if res.status_code != 200:
        print(f"Register failed: {res.status_code} {res.text}")
        # Try login directly if already exists (unlikely with random)
    
    # 3. Login
    print("Attempting to login...")
    res = s.post(base_url + '/api/login', json={
        'username': username,
        'password': password
    }, headers=headers)
    
    if res.status_code != 200:
        print(f"Login failed: {res.status_code} {res.text}")
        return
        
    print(f"Login successful. Cookies: {s.cookies.get_dict()}")
    
    # 4. Check Session
    print("Checking /api/me...")
    res = s.get(base_url + '/api/me')
    data = res.json()
    print(f"Session check result: {data}")
    
    if data.get('logged_in'):
        print("PASS: Backend session works.")
    else:
        print("FAIL: Backend session lost.")

if __name__ == "__main__":
    register_and_login()
