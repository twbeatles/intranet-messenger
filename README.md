# 🔒 사내 웹메신저 v4.1

Flask + Socket.IO + PyQt6 기반 **종단간 암호화(E2E)** 사내 메신저

## ✨ v4.1 신규 기능

### 🔒 계정 보안
- 비밀번호 변경 (프로필 설정 > 계정 보안 탭)
- 회원 탈퇴 기능

### 📢 시스템 메시지
- 방 이름 변경, 공지 등록 시 채팅창에 알림 표시

### 🎨 UI 개선
- 프로필 모달 탭 구조 개편
- 글래스모피즘 효과, 커스텀 스크롤바

---

## 📌 v4.0 핵심 기능
- 📌 공지사항 고정 | 📋 투표/설문 | 📁 파일 저장소 | 👑 관리자 권한
- 👍 이모지 리액션 | 🔔 알림 세분화 | 🔍 고급 검색 | 💾 드래프트 저장

---

## 🔒 사내망 호환
- ✅ 외부 CDN/API 없음 (완전 독립)
- ✅ Socket.IO, CryptoJS 로컬 포함
- ✅ SQLite 데이터베이스

---

## 📦 설치

```powershell
pip install -r requirements.txt
```

또는 개별 설치:
```powershell
pip install flask flask-socketio simple-websocket pycryptodome pyqt6 cryptography gevent gevent-websocket
```

---

## 🚀 실행

```powershell
# GUI 모드 (권장)
python server.py

# CLI 모드 (고성능)
python server.py --cli
```

---

## 📦 PyInstaller 빌드

```powershell
pyinstaller messenger.spec --clean
```

결과물: `dist/사내메신저v4.1/`

---

## 🗂️ 구조

```
사내 메신저/
├── server.py            # 진입점
├── config.py            # 설정
├── messenger.spec       # PyInstaller
├── requirements.txt     # 의존성
├── app/                 # Flask 앱
├── gui/                 # PyQt6 GUI
├── static/              # CSS, JS
├── templates/           # HTML
└── certs/               # SSL 인증서
```

---

## ⚠️ 참고
- GUI 모드: PyQt6 충돌 방지를 위해 gevent 자동 비활성화
- CLI 모드: gevent 활성화로 수백 명 동시 접속 지원
