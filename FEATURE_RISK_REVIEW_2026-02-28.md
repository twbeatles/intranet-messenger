# FEATURE_RISK_REVIEW_2026-02-28

- 기준일: 2026-02-28
- 상태: 구현 반영 완료
- 검증: `pytest -q` -> `84 passed`

## 1) 구현 범위

- 설정/의존성/패키징
  - `PyJWT` 의존성 추가
  - `SOCKET_PIN_UPDATED_PER_MINUTE`, `OIDC_JWKS_URL`, `OIDC_JWKS_CACHE_SECONDS` 설정 추가
  - PyInstaller `.spec`의 `jwt` 관련 hidden import 보강
- HTTP 하드닝
  - `/api/search/advanced`의 `limit`, `offset` 타입 오류를 `400 + code`로 표준화
  - `/uploads/<path>` 경로 검증을 `os.path.commonpath` 기반으로 강화
  - `/api/rooms/<room_id>/leave` idempotent 응답(`left`, `already_left`) 추가
  - invite/kick/leave 성공 시 서버 emit(`room_members_updated`) 추가
- 소켓 authoritative 전환
  - `room_members_updated`, `profile_updated`, `reaction_updated`, `poll_created`, `poll_updated`, `pin_updated`를 서버 검증/정규화 중심으로 전환
  - `pin_updated`에서 시스템 메시지 생성 로직 제거 + rate limit 적용
- 프론트 정합
  - poll emit payload를 `poll_id` 중심으로 전환
  - pin create/delete 후 클라이언트의 `pin_updated` emit 제거
  - `leaveRoom` 성공 후 `leave_room` emit 사용
  - 컨텍스트 메뉴 동작에서 전역 `currentRoom` 덮어쓰기 제거
  - `togglePinRoom`, `toggleMuteRoom`, `leaveRoom` 대상 room 인자 지원
  - `startOnlineUsersPolling` 중복 interval 가드 추가
- OIDC 보안 강화
  - `id_token` 필수, JWKS 서명 검증 + `iss/aud/exp/nonce` 검증
  - callback에서 `state`, `nonce` one-time pop 처리

## 2) 반영 파일

- 백엔드
  - `app/__init__.py`
  - `app/routes.py`
  - `app/sockets.py`
  - `app/oidc.py`
  - `config.py`
- 프론트
  - `static/js/features.js`
  - `static/js/rooms.js`
- 패키징/의존성
  - `requirements.txt`
  - `messenger.spec`
- 문서
  - `README.md`
  - `claude.md`
  - `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md`
- 테스트
  - `tests/test_feature_risk_review_plan.py`

## 3) API/계약 변경 요약

- `POST /api/search/advanced`
  - 비정상 `limit`/`offset` 입력: `400` + `code` (`invalid_limit`, `invalid_offset`)
- `POST /api/rooms/<room_id>/leave`
  - 공통 `success: true`
  - `left`, `already_left`로 idempotent 상태 반환
- Socket emit 계약
  - `poll_created`, `poll_updated`: `poll_id` 중심
  - `reaction_updated`, `profile_updated`: 클라이언트 위조 payload 무시
  - `pin_updated`: room 갱신 신호만 처리

## 4) 테스트 결과

- 신규 테스트: `tests/test_feature_risk_review_plan.py`
  - 고급검색 입력 검증
  - leave idempotent 응답 검증
  - 소켓 권한/무결성 검증
  - pin API 서버 emit 검증
  - 업로드 경로 검증
  - OIDC strict 검증
- 전체 결과: `pytest -q` -> `84 passed`

## 5) 메모

- 현재 워킹트리는 문서/코드 동기화 상태이며, 본 문서 기준으로 README/claude/분석 문서와 구현 내용 정합을 맞춤.
