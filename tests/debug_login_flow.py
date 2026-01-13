import requests

def test_login_flow():
    s = requests.Session()
    base_url = 'http://127.0.0.1:5000'
    
    # 1. Login
    print("1. Logging in...")
    # Basic login (assuming user exists from previous tests or I register one)
    # I'll try to register a new one to be sure
    import random
    u = f'testuser_{random.randint(1000,9999)}'
    p = 'password123'
    
    # Register
    res = s.post(base_url + '/api/register', json={'username': u, 'password': p, 'nickname': u})
    # Ignore error if exists, proceed to login
    
    # Need CSRF token?
    # Fetch / first
    res = s.get(base_url + '/')
    import re
    m = re.search(r'<meta name="csrf-token" content="([^"]+)">', res.text)
    token = m.group(1) if m else None
    
    headers = {'X-CSRFToken': token}
    if not token:
        print("FAIL: No CSRF Token")
        return

    # Login
    res = s.post(base_url + '/api/login', json={'username': u, 'password': p}, headers=headers)
    print(f"Login Status: {res.status_code}")
    if res.status_code != 200:
        print(f"Login Failed: {res.text}")
        return
        
    print(f"Cookies after login: {s.cookies.get_dict()}")
    
    # 2. Check Session (/api/me) simulating reload
    print("2. Checking Session (/api/me)...")
    res = s.get(base_url + '/api/me')
    print(f"Session Check Status: {res.status_code}")
    print(f"Session Check Body: {res.text}")
    
    if res.json().get('logged_in'):
        print("SUCCESS: Session Persisted.")
    else:
        print("FAIL: Session NOT Persisted.")

if __name__ == '__main__':
    try:
        test_login_flow()
    except Exception as e:
        print(f"Error: {e}")
