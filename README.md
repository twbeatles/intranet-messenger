# 🔒 사내 웹메신저 v4.3

Flask + Socket.IO + PyQt6 기반 **종단간 암호화(E2E)** 사내 메신저

## ✨ v4.3 업데이트

### ⚡ 성능 최적화
- **backdrop-filter 최적화** - blur 값 감소 (GPU 부하 ↓)
- **JavaScript throttle/캐싱** - loadRooms 2초, 스크롤 100ms throttle
- **멘션 자동완성 캐싱** - 동일 방에서 API 중복 호출 방지
- **설정창 레이아웃 수정** - 스크롤 개선 (max-height 85vh)

### 🐛 버그 수정
- **DB 연결 누수** - models.py에 try-finally 블록 추가
- **닉네임 캐시** - 세션 미존재 시 DB 폴백 추가
- **전역 함수 참조** - window.openRoom/rooms 전역 노출

### 🆕 새 기능
- **읽음 표시 UI** - ✓✓ 모두읽음 / ✓ N명 안읽음
- **검색 하이라이트** - 펄스 애니메이션 효과
- **파일 드래그 앤 드롭** - 채팅 영역에 파일 드래그

---

## 📌 주요 기능

| 기능 | 설명 |
|------|------|
| 🔐 E2E 암호화 | AES-256 종단간 암호화 |
| 👑 관리자 권한 | 권한 부여/이양 기능 |
| 📋 투표/설문 | 그룹 의사결정 지원 |
| 📁 파일 공유 | 드래그앤드롭 업로드 |
| 🔍 고급 검색 | 날짜/작성자/파일 필터 |
| 🔔 읽음 확인 | 실시간 Read Receipt |
| ✓✓ 읽음 표시 | 메시지별 읽음 상태 |

---

## 🔒 사내망 호환
- ✅ **완전 독립 실행**: 외부 CDN/API 의존성 없음
- ✅ **로컬 라이브러리**: Socket.IO, Crypto-JS 내장
- ✅ **경량 DB**: SQLite (별도 서버 불필요)

---

## 📦 설치

```powershell
pip install -r requirements.txt
```

---

## 🚀 실행

```powershell
# GUI 모드 (일반 사용자용)
python server.py

# CLI 모드 (서버/대규모 접속용)
python server.py --cli
```

---

## 📦 PyInstaller 빌드

```powershell
# 빌드 실행
pyinstaller messenger.spec --clean

# 결과물 위치
dist/사내메신저v4.3/사내메신저v4.3.exe
```

### 빌드 최적화
- **UPX 압축** 적용
- **불필요 모듈 제외** (matplotlib, numpy, tkinter 등)
- **PyQt6 경량화** (미사용 Qt 모듈 제외)
- **DLL 압축 제외** (호환성 보장)

---

## 🗂️ 프로젝트 구조

```
사내메신저/
├── server.py            # 메인 실행 파일
├── config.py            # 환경 설정
├── messenger.spec       # PyInstaller 빌드 설정
├── app/                 # 백엔드 (Flask + Socket.IO)
│   ├── routes.py        # HTTP API 라우트
│   ├── sockets.py       # WebSocket 이벤트
│   └── models.py        # DB 모델/CRUD
├── gui/                 # 데스크탑 UI (PyQt6)
├── static/              # 프론트엔드 (JS/CSS)
└── templates/           # HTML 템플릿
```

---

## ⚠️ 기술 참고사항

| 항목 | 설명 |
|------|------|
| 암호화 | AES-256 (pycryptodome) |
| GUI 모드 | gevent 패칭 비활성화 |
| CLI 모드 | gevent 비동기 완전 활용 |
| DB | SQLite + WAL 모드 |
| 성능 | throttle/캐싱 최적화 |
