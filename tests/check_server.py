import requests
try:
    resp = requests.get('http://127.0.0.1:5001/')
    print(f"Status: {resp.status_code}")
    print(f"Content: {resp.text[:100]}")
except Exception as e:
    print(f"Error: {e}")
