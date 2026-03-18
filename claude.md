# CLAUDE.md

프로젝트: `intranet-messenger-main`  
최종 업데이트: 2026-03-18

## 1) 목적

Claude 세션에서 프로젝트의 현재 기준선, 핵심 계약, 검증 루틴을 빠르게 파악하기 위한 운영 문서다.

## 2) 세션 시작 전 필수 확인

1. `README.md`
2. `pyrightconfig.json`
3. `docs/BACKUP_RUNBOOK.md`
4. 최근 변경 파일
   - `app/factory.py`
   - `app/bootstrap/`
   - `app/http/`
   - `app/socket_events/`
   - `app/services/`
   - `app/routes.py`
   - `app/sockets.py`
   - `gui/window/main_window.py`
   - `gui/server_window.py`
   - `templates/partials/`
   - `static/js/core/`
   - `static/js/features/`
   - `static/js/services/`
   - `tests/test_route_map_smoke.py`
   - `tests/test_template_assets_smoke.py`
   - `tests/test_gui_import_smoke.py`
   - `tests/test_encoding_hygiene.py`

## 3) 현재 기준선

- 버전 메모: 런타임 `config.VERSION == 4.36`, PyInstaller 산출물 이름은 `v4.36.3` 호환 유지
- 타입 기준선
  - `pyright app gui` => `0 errors, 0 warnings`
- 테스트 기준선
  - `pytest tests -q` => `89 passed`
  - `pytest --maxfail=1` => `89 passed`
- `pytest.ini`
  - `testpaths = tests`
  - `norecursedirs = backup dist build`
- 구조 기준선
  - `app/routes.py`, `app/sockets.py`, `gui/server_window.py`는 compatibility shim
  - 실제 구현은 `app/http/*`, `app/socket_events/*`, `gui/window/main_window.py`에 위치

## 4) 핵심 API/보안 계약

### 4.1 방 생성 API

- 엔드포인트: `POST /api/rooms`
- 주 입력 키: `members`
- 호환 입력 키: `member_ids`
- 둘 다 들어오면 `members`를 우선 사용하고 `member_ids`는 무시한다. 경고 로그는 남긴다.
- 멤버 정규화 규칙
  - 정수 변환
  - 중복 제거
  - 자기 자신 자동 포함

### 4.2 업로드/파일 메시지 보안

- 업로드: `POST /api/upload`
  - `room_id` 필수
  - 성공 응답에는 `upload_token` 포함
- 파일 메시지 전송: `send_message`
  - `type in ('file', 'image')`이면 `upload_token` 필수
  - 클라이언트가 `file_path`나 `file_name`을 임의 전달하지 않는다
  - 토큰은 user/room/type/만료/1회성까지 검증한다
- 토큰 저장소: `app/upload_tokens.py`
  - 기본 TTL 5분
  - thread-safe lock
  - one-time consume

### 4.3 파일 다운로드 캐시 정책

- 엔드포인트: `GET /uploads/<path>`
- 일반 파일: `Cache-Control: private, no-store`
- 프로필 이미지: `Cache-Control: private, max-age=3600`

### 4.4 검색 API 정책

- 엔드포인트: `GET /api/search`
- `limit` clamp 범위: `1..200`
- `offset`은 음수 방지(`>= 0`)

### 4.5 Poll/Pin 계약

- Poll 생성 모델 계약
  - `create_poll(...) -> poll_id | None`
- Poll 생성 라우트
  - `poll_id` 생성 후 `get_poll(poll_id)`로 다시 조회해 응답한다
- Pin 해제
  - `success, error = unpin_message(...)` 형태를 사용한다
  - tuple 자체의 truthy 판단은 금지한다
- Pin 시스템 메시지
  - `pin_updated` 소켓 이벤트 경로에서는 만들지 않는다
  - `/api/rooms/<room_id>/pins`의 생성/삭제 성공 경로에서만 만든다

### 4.6 탈퇴와 무결성

- `polls.created_by = NULL` 업데이트 금지 (`NOT NULL` 제약)
- 탈퇴 사용자가 만든 poll 처리 규칙
  - 같은 방의 다른 멤버에게 소유권을 넘긴다 (관리자 우선)
  - 넘길 수 없으면 poll을 삭제한다

### 4.7 Socket authoritative 계약

- 소켓 브로드캐스트 payload는 서버 DB 조회 결과를 기준으로 한다
- `profile_updated`, `reaction_updated`, `poll_updated`, `poll_created`는 클라이언트 payload를 신뢰하지 않는다
- `room_members_updated` emit 전에는 room 멤버 검증이 필수다

## 5) 작업 원칙

1. `app/models.py` 단일 모듈보다 `app/models/*` 경로를 우선 사용한다.
2. `app/routes.py`, `app/sockets.py`, `gui/server_window.py`에 신규 로직을 누적하지 않는다. 실제 구현은 분리 패키지에 둔다.
3. API 계약을 바꾸면 라우트, 프런트엔드, 테스트, README를 함께 갱신한다.
4. 파일 전송 경로에서는 클라이언트 입력 경로를 그대로 신뢰하지 않는다.
5. 보안 로직을 추가하면 테스트도 반드시 함께 추가한다.
6. README, 사용자 흐름, API 설명과 실제 구현이 일치하는지 확인한다.
7. 타입/인코딩 관련 변경 시 `pyrightconfig.json`과 `tests/test_encoding_hygiene.py`도 함께 점검한다.

## 6) 변경 검증 루틴

1. `pytest tests -q`
2. `pytest --maxfail=1`
3. `pyright app gui`
4. 필요 시 수동 점검
   - `/api/upload` 응답에 `upload_token`이 있는지
   - 토큰 없이 파일 메시지 전송 시 에러가 발생하는지
   - `/api/search?limit=9999&offset=-1`가 clamp 되는지
   - `/uploads` 캐시 헤더가 경로별로 다르게 나가는지
   - `pin_updated` 연속 호출 시 rate limit이 동작하는지
   - OIDC callback에서 nonce/state one-time pop과 검증 실패 로그가 남는지
   - tracked text files에 BOM이나 mojibake가 없는지
   - `/` 렌더링 시 `templates/partials/*`와 분리된 static asset이 모두 resolve되는지

## 7) PR/커밋 체크리스트

- [ ] 계약 변경이 README와 문서에 반영되었는가
- [ ] 테스트가 추가 또는 수정되었는가
- [ ] 기존 테스트 전체 통과를 확인했는가
- [ ] 보안 우회 케이스(토큰 우회, 권한 우회)를 검증했는가
- [ ] shim 파일 계약(`app/routes.py`, `app/sockets.py`, `gui/server_window.py`)을 유지했는가

## 8) Claude 세션 프롬프트 템플릿

아래 문장을 세션 첫 메시지로 사용할 수 있다.

```text
Read `claude.md`, `README.md`, `pyrightconfig.json`, and `docs/BACKUP_RUNBOOK.md` first.
Then summarize:
1) current baseline (tests/contracts),
2) risks if we change this area,
3) exact files to edit,
and execute changes with verification (`pyright`, `pytest tests -q`, `pytest --maxfail=1`).
```

## 9) 2026-02-25 기준 업데이트 (Full Remediation)

- 코드 기준선
  - 리스크 매핑 R-01~R-11 반영 완료
  - 추가 기능: OIDC, AV 스캔, Redis state_store, 관리자 감사 로그, 보조 정책, 백업/복구
- 주요 변경 파일
  - `app/state_store.py`
  - `app/upload_scan.py`
  - `app/oidc.py`
  - `app/models/admin_audit.py`
  - `app/legacy/models_monolith.py`
  - `scripts/backup_local.py`
  - `scripts/restore_local.py`
  - `scripts/verify_restore.py`
  - `docs/BACKUP_RUNBOOK.md`
- 공개 API 기준선
  - `GET /api/config`
  - `GET /api/upload/jobs/<job_id>`
  - `GET /api/auth/providers`
  - `GET /auth/oidc/login`
  - `GET /auth/oidc/callback`
  - `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`
- 테스트 기준선
  - `pytest -q` => `84 passed`
- 작업 시 주의사항
  - 세션 무효화는 HTTP(`before_request`)와 Socket(`connect`/주요 이벤트)에서 모두 적용한다
  - 파일 메시지의 `upload_token` 검증 경로를 우회할 수 없게 유지한다
  - `state_store`는 Redis 장애 시 메모리 경로로 안전하게 폴백해야 한다

## 10) 2026-02-25 통합 문서 메모

- README, API 계약, 구조 분석 문서 간 기준선 동기화 완료
- 테스트 기준선: `pytest -q` => `84 passed`
- `.spec` 반영 항목
  - `app.state_store`
  - `app.upload_scan`
  - `app.oidc`
  - `app.models.admin_audit`
  - `redis`, `redis.asyncio`
  - `docs/BACKUP_RUNBOOK.md` 데이터 포함

## 11) 2026-02-27 구조 리스크 개선 반영

- `messenger_server.py`는 deprecated shim으로 유지하고 신규 로직은 추가하지 않는다
- 프런트엔드 업로드 책임은 `static/js/message-upload.js`로 분리한다
- 세션 저장소는 `cachelib` 백엔드를 기준으로 유지한다
- 인코딩 안정성을 위해 서버 진입점의 UTF-8 stdio 설정을 유지한다

### API 계약 고정값

- `GET /api/config`
- `POST /api/upload` + `GET /api/upload/jobs/<job_id>`
- `POST /api/polls/<poll_id>/vote` (`error`, `code`)
- `GET /api/auth/providers`
- `GET /auth/oidc/login`
- `GET /auth/oidc/callback`
- `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`

## 12) 2026-02-28 Feature Risk Review Sync

- Socket authoritative policy는 `room_members_updated`, `profile_updated`, `reaction_updated`, `poll_created`, `poll_updated`, `pin_updated`에 적용된다
- `pin_updated` 소켓 이벤트는 더 이상 시스템 메시지를 생성하지 않는다
- 시스템 메시지는 HTTP pin 생성/삭제 성공 경로에서만 생성된다
- OIDC callback은 one-time `state`/`nonce` pop을 사용하며, `id_token` 또는 nonce 검증 실패 시 로그인을 거부한다
- OIDC `id_token` 검증은 JWKS 서명 검증과 `iss`, `aud`, `exp`, `nonce` 체크를 포함한다
- API 계약 업데이트
  - `POST /api/search/advanced`: 잘못된 `limit`/`offset`은 `400`과 `invalid_limit`/`invalid_offset`을 반환한다
  - `POST /api/rooms/<room_id>/leave`: `left`, `already_left` 플래그를 포함한 idempotent success를 반환한다
- 테스트 기준선: `pytest -q` => `84 passed` (2026-02-28)

## 13) 2026-03-15 Pylance/인코딩 정합성 반영

- `pyrightconfig.json` 추가로 로컬 타입체크 기준선을 고정했다
- `pyright` 기준 `0 errors, 0 warnings`
- `pytest -q` 기준 `86 passed`
- UTF-8 BOM 제거와 깨진 한글 복구를 반영했다
- `tests/test_encoding_hygiene.py`를 추가해 BOM/mojibake 회귀를 자동 검증한다
- 의도적 detector token은 `app/__init__.py`, `app/sockets.py`만 allowlist로 유지한다

## 14) 2026-03-18 구조 분할 리팩토링 동기화

- Python runtime 구조
  - `app/factory.py`
  - `app/bootstrap/*`
  - `app/http/*`
  - `app/socket_events/*`
  - `app/services/*`
- Web/GUI 구조
  - `templates/index.html` + `templates/partials/*`
  - `static/js/core/*`, `static/js/services/*`, `static/js/features/*`, `static/js/bootstrap/*`
  - `static/css/style.css` + `static/css/{tokens,base,layout,components,features,responsive,themes}.css`
  - `gui/services/*`, `gui/widgets/*`, `gui/styles/*`, `gui/window/main_window.py`
- 호환 shim 유지
  - `app/routes.py`
  - `app/sockets.py`
  - `gui/server_window.py`
- 회귀 방지 테스트 추가
  - `tests/test_route_map_smoke.py`
  - `tests/test_template_assets_smoke.py`
  - `tests/test_gui_import_smoke.py`
- 최신 기준선
  - `pytest -q` => `89 passed`
  - `pyright app gui` => `0 errors, 0 warnings`
