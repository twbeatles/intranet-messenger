# Feature Implementation Risk Review

- 작성일: 2026-04-14
- 기준 문서: `README.md`, `claude.md`, `gemini.md`
- 구현 상태: 반영 완료 후 코드베이스 정합성 재점검

## 완료 항목

- 테스트/런타임 기준선 복구
  - 경로 의존 초기화를 동적 해석으로 변경
  - 테스트 temp 경로를 workspace-local `.pytest_tmp/`로 고정
  - mojibake 탐지 로직을 공용 helper로 정리
- 방 멤버십 실시간 정합성 강화
  - `user_<id>` 전용 room 사용
  - `room_list_updated`, `room_access_revoked` 이벤트 추가
  - 초대/나가기/강퇴/탈퇴 시 서버측 room join/leave 동기화
- room-bound / authoritative 정책 마감
  - `send_message`의 클라이언트 허용 타입을 `text|file|image`로 제한
  - `reply_to`, pin `message_id`, `message_read.message_id`에 room 검증 추가
  - 파일 메시지 생성과 `room_files` 저장을 하나의 transaction으로 정리
- 웹/GUI 계약 정리
  - poll UI를 `closed`, `created_by` 기준으로 수정
  - `status_message` 저장/조회/clear/socket round-trip 완료
  - 파일 저장소 삭제 시 linked attachment message를 `message_deleted` 흐름으로 정리
  - GUI 포트 충돌 시 메신저 서버로 식별될 때만 자동 종료

## 검증 결과

- `pytest -q` => `97 passed`
- `pytest tests/test_control_api_auth.py tests/test_encoding_hygiene.py -q` => `3 passed`
- `pytest tests/test_feature_risk_review_regressions.py -q` => `8 passed`
- `pyright app gui`
  - 현재 작업 환경에서는 Flask/PyQt/PyCryptodome 계열 import/type 정보 미설치로 import resolution 실패
  - 이번 변경으로 생긴 추가 타입 오류는 별도 보정 완료

## 문서/배포 정합성 메모

- `README.md`, `claude.md`, `gemini.md`에 새 소켓 이벤트와 `status_message`, `invalid_pin_message` 계약을 반영했다.
- `messenger.spec`에는 신규 서비스 모듈 `app.services.runtime_paths`, `app.services.text_hygiene` hidden import를 추가했다.
- `.gitignore`에는 테스트 임시 산출물 `.pytest_tmp/`를 추가했다.

## 잔여 메모

- `pyright` 기준선은 의존 패키지와 타입 정보가 설치된 개발 환경에서 다시 확인하는 것이 맞다.
- 현재 코드/문서/빌드 명세 간 정합성은 이번 반영 범위 기준으로 맞춰져 있다.
