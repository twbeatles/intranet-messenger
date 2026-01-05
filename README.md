# 🔒 사내 웹메신저 v4.2

Flask + Socket.IO + PyQt6 기반 **종단간 암호화(E2E)** 사내 메신저

## ✨ v4.2 업데이트

### 🎨 UI/UX 대규모 개선
- **Inter 폰트** 적용으로 현대적 타이포그래피
- **글래스모피즘** 효과 (모달, 사이드바, 채팅 영역)
- **그라데이션** 버튼 및 메시지 버블
- **마이크로 애니메이션** 강화 (호버, 클릭 효과)

### 🐛 버그 수정
- 회원 탈퇴 API 엔드포인트 수정
- 프로필 미리보기 null 안전성 개선
- Socket 캐시 메모리 누수 방지

### ⚡ 성능 최적화
- DB 인덱스 5개 추가 (메시지, 멤버 조회 속도 향상)
- 캐시 크기 제한 및 자동 정리

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
dist/사내메신저v4.2/사내메신저v4.2.exe
```

### 빌드 최적화
- **UPX 압축** 적용
- **불필요 모듈 제외** (matplotlib, numpy, tkinter 등)
- **PyQt6 경량화** (미사용 Qt 모듈 제외)

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
