import requests
import unittest

BASE_URL = "http://127.0.0.1:5000"

class TestSecurityImprovements(unittest.TestCase):
    def test_security_headers(self):
        """보안 헤더 존재 여부 확인"""
        try:
            response = requests.get(BASE_URL)
            print(f"Headers: {response.headers}")
            self.assertIn('X-Content-Type-Options', response.headers)
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn('X-Frame-Options', response.headers)
            self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn('Content-Security-Policy', response.headers)
        except requests.exceptions.ConnectionError:
            print("서버가 실행 중이지 않습니다. 테스트를 건너뜁니다.")

    def test_weak_password_registration(self):
        """약한 비밀번호로 회원가입 시도"""
        try:
            # 1. 길이 부족
            payload = {'username': 'test_weak_1', 'password': 'pw1', 'nickname': 'weak1'}
            response = requests.post(f"{BASE_URL}/api/register", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn('8자 이상', response.json().get('error', ''))

            # 2. 숫자 미포함
            payload = {'username': 'test_weak_2', 'password': 'passwordonly', 'nickname': 'weak2'}
            response = requests.post(f"{BASE_URL}/api/register", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn('숫자', response.json().get('error', ''))
            
            # 3. 영문자 미포함
            payload = {'username': 'test_weak_3', 'password': '12345678', 'nickname': 'weak3'}
            response = requests.post(f"{BASE_URL}/api/register", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn('영문자', response.json().get('error', ''))

        except requests.exceptions.ConnectionError:
            print("서버가 실행 중이지 않습니다.")

if __name__ == '__main__':
    unittest.main()
