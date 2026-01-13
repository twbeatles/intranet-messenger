import requests
import sys

BASE_URL = 'http://127.0.0.1:5001'

def register(username, password, nickname):
    try:
        data = {'username': username, 'password': password, 'nickname': nickname}
        resp = requests.post(f'{BASE_URL}/api/register', json=data)
        if resp.status_code == 201 or resp.json().get('success'):
            print(f"Registered {username}")
        else:
            print(f"Failed to register {username}: {resp.text}")
    except Exception as e:
        print(f"Error registering {username}: {e}")

if __name__ == '__main__':
    register('user1', 'password123', 'User One')
    register('user2', 'password123', 'User Two')
