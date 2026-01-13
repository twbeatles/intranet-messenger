
import requests
import os
import re

# Create a dummy image file
with open('test_profile.jpg', 'wb') as f:
    f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00')

def get_csrf_token(session, url):
    response = session.get(url)
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    if match:
        return match.group(1)
    return None

def test_upload():
    session = requests.Session()
    base_url = 'http://127.0.0.1:5000'
    
    # 0. Get CSRF Token from login page
    print("Fetching CSRF token...")
    response = session.get(base_url + '/')
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    if match:
        csrf_token = match.group(1)
    else:
        csrf_token = None

    if not csrf_token:
        print("Failed to find CSRF token")
        return
    print(f"CSRF Token: {csrf_token}")
    print(f"Response Cookies: {response.cookies.get_dict()}")
    print(f"Response Headers: {response.headers}")

    
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': base_url + '/'
    }

    # 1. Register
    reg_data = {
        'username': 'debug_user_123',
        'password': 'password123',
        'nickname': 'Debug User'
    }
    import random
    suffix = random.randint(1000,9999)
    reg_data['username'] = f'debug_{suffix}'
    
    print(f"Registering user: {reg_data['username']}")
    res = session.post(base_url + '/api/register', json=reg_data, headers=headers)
    if res.status_code != 200:
        print(f"Registration failed: {res.status_code} {res.text}")
        # Even if registration fails (e.g. user exists), try to login
    
    # 2. Login
    login_data = {
        'username': reg_data['username'],
        'password': reg_data['password']
    }
    print("Logging in...")
    res = session.post(base_url + '/api/login', json=login_data, headers=headers)
    if res.status_code != 200:
       print(f"Login failed: {res.status_code} {res.text}")
       return
    print("Logged in.")

    # 3. Upload Profile Image
    print("Uploading profile image...")
    # NOTE: Fetching the CSRF token again might be safer if it rotates, but usually it sticks to session
    # Let's try sending it with the multipart request
    
    files = {'file': ('test_profile.jpg', open('test_profile.jpg', 'rb'), 'image/jpeg')}
    
    # Requests automatically sets Content-Type to multipart/form-data with boundary when 'files' is passed
    # We just need to add the CSRF header
    res = session.post(base_url + '/api/profile/image', files=files, headers=headers)
    
    print(f"Upload Status: {res.status_code}")
    print(f"Upload Response: {res.text}")

if __name__ == "__main__":
    try:
        test_upload()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists('test_profile.jpg'):
            os.remove('test_profile.jpg')
