# Intranet Messenger 프로젝트 구조 정밀 분석 및 기능 확장 가이드

- 작성일: 2026-02-27
- 대상 경로: `C:\twbeatles-repos\intranet-messenger`
- 목적: 현재 구조를 기준으로 기능 확장 시 수정 지점, 리스크, 우선순위를 명확히 정의

## 1. 참조 문서

- `README.md`
- `claude.md`
- `gemini.md`
- `docs/BACKUP_RUNBOOK.md`

## 2. 현재 기준선

- 테스트 기준선: `pytest -q` -> `71 passed` (2026-02-27)
- 실행 진입점: `server.py`
- 레거시 호환 진입점: `messenger_server.py` (deprecated shim)

## 3. 프로젝트 최상위 구조

- `server.py`: CLI/GUI 실행 진입
- `config.py`: 런타임 설정 및 기능 플래그
- `app/`: 백엔드 핵심(앱 팩토리, routes, sockets, models)
- `static/`, `templates/`: 프론트엔드 리소스 및 단일 페이지 템플릿
- `tests/`: 회귀 테스트
- `scripts/`: 백업/복구/검증 스크립트
- `docs/`: 운영 문서
- `messenger.spec`: PyInstaller 빌드 명세

## 4. 주요 실행/구성 흐름

1. `server.py` 실행
2. `app.create_app()`에서 확장 초기화(Session/Socket/RateLimit 등)
3. `app/routes.py` HTTP 라우트 등록
4. `app/sockets.py` 소켓 이벤트 등록
5. `app/models/base.py` 기반 DB 초기화/유지보수

## 5. 구조 리스크/기술부채

### 5.1 코드 경로 이중화

- 과거에는 `messenger_server.py`와 `app/*`가 병행되어 기준 경로 혼선 위험이 존재
- 현재는 `server.py` 기준으로 단일화하고 `messenger_server.py`는 shim으로 축소

### 5.2 프론트엔드 결합도

- `messages.js`/`rooms.js`의 책임 집중이 크고 변경 영향 범위가 넓음
- 업로드 로직은 `static/js/message-upload.js`로 1차 분리 완료

### 5.3 문자열/인코딩 흔들림

- 콘솔/로그 인코딩 환경에 따라 깨짐 가능성이 존재
- 서버 진입점에 UTF-8 stdio 설정을 적용해 완화

### 5.4 테스트 경고 누적

- Flask-Session deprecation 경고가 누적될 여지가 있었음
- `cachelib` 백엔드 전환으로 경고 리스크를 완화

## 6. 2026-02-27 개선 반영 요약

- `messenger_server.py` deprecated shim 전환
- `static/js/message-upload.js` 추가 및 `messages.js` 위임 구조 적용
- `server.py`, `app/server_launcher.py`, `app/run_server.py` UTF-8 stdio 고정
- `app/sockets.py` 오류 메시지 모지바케 정규화 경로 추가
- `app/__init__.py` 세션 저장소 `cachelib` 전환
- `requirements.txt`에 `cachelib>=0.13.0` 추가

## 7. 기능 확장 우선순위 제안

- P1: 알림 센터(미읽음/멘션), 메시지 수정 이력, 보존 정책 UI
- P2: 스레드 답글, 예약 메시지, 관리자 대시보드
- P3: 고급 검색 확장, 파일 DLP 라벨, 프론트 모듈 전환

## 8. 작업 원칙

1. API 계약 변경 시 `routes + static/js + tests + README`를 같은 변경 세트로 갱신
2. 파일 메시지는 항상 `upload_token` 검증 경로 유지
3. 세션 무효화 검증은 HTTP/Socket 모두 유지
4. 변경 후 최소 `pytest -q` 실행 결과를 기록

