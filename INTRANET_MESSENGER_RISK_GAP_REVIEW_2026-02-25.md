# 사내 메신저 기능 리스크/추가기능 정밀점검 보고서 (2026-02-25)

- 작성일: 2026-02-25
- 대상 경로: `C:\twbeatles-repos\intranet-messenger`
- 기준 문서: `claude.md`, `README.md`, `IMPLEMENTATION_AUDIT.md`
- 작업 범위: 코드 수정 없이 리스크/갭 분석 문서화

## 목적
본 문서는 사내 메신저 프로그램으로서 현재 코드베이스의 잠재 리스크와 추가 구현 필요 사항을 정밀 점검해, 바로 구현 가능한 실행 스펙으로 정리하기 위한 산출물이다.

기준선 정리:
- `claude.md` 기준 계약: `v4.36.3 (2026-02-20)`, 핵심 API/보안 계약 및 테스트 기준(`pytest tests -q`, `pytest --maxfail=1`) 명시.
- `README.md` 기준 주장: 보안 기능, 폐쇄망 호환성, Rate Limiting 정책, 업로드 정책, 버전 이력 명시.
- `IMPLEMENTATION_AUDIT.md`는 과거 감사 결과를 담고 있으나, 현재 저장소 상태와 일부 메타 정보가 불일치하는 지점 존재.

## 점검 범위/근거
점검 대상(정적 코드 근거 수집):
- 백엔드: `app/__init__.py`, `app/routes.py`, `app/sockets.py`, `app/upload_tokens.py`
- 모델: `app/models/base.py`, `app/models/users.py`, `app/models/polls.py`, `app/models/messages.py`, `app/models/files.py`, `app/models/rooms.py`
- 프론트: `templates/index.html`, `static/js/messages.js`, `static/js/auth.js`, `static/js/app.js`, `static/js/modules/api.js`
- 설정/배포: `config.py`, `requirements.txt`, `messenger.spec`
- 문서/감사: `README.md`, `claude.md`, `IMPLEMENTATION_AUDIT.md`

검증 근거 수집 방식:
- 코드 라인 단위 정적 점검
- 로컬 테스트/환경 확인
- 실행 로그 확인(의존성 누락으로 인한 테스트 제약 포함)

## 확정 리스크(Critical/High/Medium)

### R-01
- 심각도: Critical
- 증상: 파일 첨부 UI 경로에서 `/api/upload` 요청에 `room_id`가 포함되지 않아 서버 계약과 불일치한다.
- 근거 파일·라인:
  - `static/js/messages.js:928-930` (`FormData`에 `file`만 추가)
  - `app/routes.py:475-477` (`room_id` 필수, 누락 시 400)
- 영향:
  - 첨부 버튼 경로에서 업로드 실패가 발생할 수 있다.
  - 같은 파일 업로드라도 진입 경로(첨부 버튼 vs 드래그앤드롭)에 따라 동작이 달라져 기능 신뢰도가 저하된다.
- 권장 조치:
  - 프론트의 모든 업로드 경로에서 `room_id`를 강제 주입한다.
  - 업로드 API 계약 테스트를 경로별(E2E)로 분리해 회귀를 방지한다.
- 재현·검증 방법:
  - 첨부 버튼으로 파일 선택 후 전송.
  - 네트워크 요청 바디에 `room_id` 존재 여부 확인.
  - 누락 시 `/api/upload`가 400(`room_id가 필요합니다.`)을 반환하는지 확인.

### R-02
- 심각도: Critical
- 증상: “비밀번호 변경 시 타 세션 무효화” 로직이 토큰 저장까지만 구현되고, 요청/소켓 검증 훅이 없어 실질 무효화가 동작하지 않는다.
- 근거 파일·라인:
  - `app/routes.py:1036-1041` (`session_token`을 현재 세션에만 저장)
  - `app/models/users.py:222-253` (DB에 `session_token` 생성/조회)
  - `app` 전역 검색 기준: `before_request` 또는 소켓 connect에서 `session_token` 검증 로직 부재
- 영향:
  - 비밀번호 변경 이후 기존 기기 세션이 계속 유효할 수 있다.
  - 계정 보안 요구사항(다중 세션 강제 로그아웃)을 충족하지 못한다.
- 권장 조치:
  - 공통 인증 미들웨어(`before_request`)에서 세션의 `session_token`과 DB 최신 토큰을 비교 검증한다.
  - 소켓 connect/이벤트 처리에도 동일 검증을 적용한다.
- 재현·검증 방법:
  - 동일 계정으로 두 개 세션(A/B) 로그인.
  - 세션 A에서 비밀번호 변경.
  - 세션 B에서 보호 API 호출 시 401/강제 로그아웃 발생 여부 확인.

### R-03
- 심각도: High
- 증상: 투표 시 `option_id`가 해당 `poll_id` 소속인지 검증하지 않아 데이터 무결성 훼손 가능성이 있다.
- 근거 파일·라인:
  - `app/models/polls.py:106-124` (`poll_votes` 삽입 전 `option_id` 소속 검증 부재)
- 영향:
  - 다른 투표 옵션 ID를 사용해 비정상 투표 데이터가 생성될 수 있다.
  - 투표 집계 신뢰도가 저하된다.
- 권장 조치:
  - `option_id`가 해당 `poll_id`의 `poll_options`에 속하는지 선검증 후 삽입한다.
  - 불일치 시 400 표준 오류를 반환한다.
- 재현·검증 방법:
  - Poll A 생성 후 Poll B의 `option_id`로 `/api/polls/<A>/vote` 요청.
  - 현재는 삽입 가능 여부 확인, 개선 후 400 응답 및 DB 오염 없음 확인.

### R-04
- 심각도: High
- 증상: README의 Rate Limit 정책과 실제 구현이 일치하지 않는다.
- 근거 파일·라인:
  - `README.md:519-523` (로그인/회원가입/메시지 전송/파일 업로드 정책 주장)
  - `app/routes.py:66,96,434,470,998` (`register`, `login`, `search`만 limiter 적용, `upload`/`search/advanced` 미적용)
  - `app/sockets.py:243` (`send_message` 이벤트 레이트리밋 미적용)
- 영향:
  - 운영자가 문서 기준으로 방어 수준을 오판할 수 있다.
  - 메시지 전송/업로드 경로에서 과도 요청 방어가 약해질 수 있다.
- 권장 조치:
  - README 정책과 실제 제한치를 일치시킨다.
  - `/api/upload`, `/api/search/advanced`, 소켓 `send_message`에 명시적 제한을 추가한다.
- 재현·검증 방법:
  - 각 엔드포인트/소켓 이벤트에 단시간 다량 요청을 보내고 차단 여부 확인.
  - 문서 정책값과 런타임 동작이 일치하는지 대조.

### R-05
- 심각도: High
- 증상: `requirements.txt`에 `flask-session`이 누락되어 신규 환경에서 앱 기동/테스트 실패 가능성이 있다.
- 근거 파일·라인:
  - `requirements.txt:7-18` (`flask-session` 명시 없음)
  - `app/__init__.py:40` (`from flask_session import Session`)
- 영향:
  - 신규 환경에서 설치 직후 ImportError가 발생할 수 있다.
  - CI/개발자 로컬 재현성이 낮아진다.
- 권장 조치:
  - `requirements.txt`에 `flask-session`을 명시적으로 추가한다.
  - 최소 부팅 테스트를 CI에 포함해 의존성 누락을 조기 검출한다.
- 재현·검증 방법:
  - 깨끗한 가상환경에서 `pip install -r requirements.txt`.
  - `python server.py --cli` 또는 `pytest` 초기 import 단계 성공 여부 확인.

### R-06
- 심각도: High
- 증상: 업로드 토큰/레이트리밋 저장소가 메모리 기반이라 멀티 프로세스/재시작 시 일관성이 깨진다.
- 근거 파일·라인:
  - `app/upload_tokens.py:12-14` (in-memory dict)
  - `app/extensions.py:8` (`Limiter(..., storage_uri="memory://")`)
  - `config.py:73-75` (`MESSAGE_QUEUE = None`, 단일 서버 기본)
- 영향:
  - 워커 간 토큰 검증 불일치 발생 가능.
  - 재시작 시 제한 상태/토큰이 초기화되어 정책 편차 발생.
- 권장 조치:
  - Redis 등 외부 공유 저장소로 토큰/레이트리밋 상태를 이전한다.
  - 멀티 워커 배포 시나리오를 표준 운영 가이드로 고정한다.
- 재현·검증 방법:
  - 워커 A에서 발급한 토큰으로 워커 B의 소켓 이벤트 전송 테스트.
  - 프로세스 재시작 전후 제한 상태 지속성 확인.

### R-07
- 심각도: Medium
- 증상: 여러 라우트에서 `request.json` None 케이스 방어가 약해 malformed 요청 시 500 가능성이 있다.
- 근거 파일·라인:
  - `app/routes.py` 전반의 `data = request.json` 사용 구간
  - 예시: `app/routes.py:68,98,278,341,360,375,405,624,750,802,850,936,967,1002,1022,1055`
- 영향:
  - 클라이언트 실수 또는 악성 입력에서 안정성이 떨어진다.
  - 에러 응답 일관성이 깨져 디버깅/운영 비용이 증가한다.
- 권장 조치:
  - `request.get_json(silent=True) or {}` 패턴을 공통 적용한다.
  - 필수 필드 검증 실패 시 400으로 표준화한다.
- 재현·검증 방법:
  - `Content-Type` 누락/잘못된 JSON 바디로 각 엔드포인트 호출.
  - 500이 아닌 400 계열로 일관 응답하는지 확인.

### R-08
- 심각도: Medium
- 증상: 회원 탈퇴 시 `rooms.created_by = NULL` 처리 후 관리자 재할당 로직이 없어 무관리자 방이 남을 수 있다.
- 근거 파일·라인:
  - `app/models/users.py:291` (`rooms.created_by = NULL`)
  - `app/models/users.py:331-332` (탈퇴 사용자 room_members 삭제 + users 삭제)
  - `app/models/rooms.py:380-393` (`created_by` 또는 role 기반으로 관리자 판정)
- 영향:
  - 관리자 권한이 필요한 방 관리 기능이 막힐 수 있다.
  - 운영 중 방 거버넌스가 붕괴될 수 있다.
- 권장 조치:
  - 탈퇴 시 방별 관리자 최소 1명 보장 로직(관리자 승계)을 추가한다.
  - 승계 불가 시 정책에 따라 방 폐쇄 또는 운영자 개입 절차를 정의한다.
- 재현·검증 방법:
  - 단독 관리자 방 생성 후 관리자가 탈퇴.
  - 남은 멤버의 관리자 기능 접근 가능 여부 확인.

### R-09
- 심각도: Medium
- 증상: 만료 투표 자동 마감이 서버 시작 시점 중심이며, 투표 로직에서 `ends_at`를 직접 검증하지 않아 장기 가동 중 만료 드리프트가 발생할 수 있다.
- 근거 파일·라인:
  - `app/models/base.py:424-426` (서버 시작 시 유지보수 호출)
  - `app/models/polls.py:106-111` (`vote_poll`은 `closed`만 검사)
- 영향:
  - 실제로는 만료된 투표가 열려 있는 것처럼 동작할 가능성이 있다.
  - 비즈니스 규칙(마감 시각 준수) 위반 위험이 있다.
- 권장 조치:
  - `vote_poll`에서 `ends_at` 실시간 검증을 추가한다.
  - 주기적 배치/스케줄러로 `close_expired_polls`를 정기 실행한다.
- 재현·검증 방법:
  - 가까운 만료시각의 투표 생성 후 서버 재시작 없이 만료 이후 투표 시도.
  - 개선 전/후 응답 차이(허용 vs 차단) 확인.

### R-10
- 심각도: Medium
- 증상: 기존 감사 문서의 일부 메타 정보가 현재 저장소 상태와 불일치한다.
- 근거 파일·라인:
  - `IMPLEMENTATION_AUDIT.md:4-7` (대상 경로/`claude.md` 부재 판단 등 stale)
- 영향:
  - 후속 점검/개발 세션에서 잘못된 기준선을 참조할 수 있다.
  - 문서 신뢰도 저하.
- 권장 조치:
  - 감사 문서 메타(경로/기준 문서/최종 검증 시점)를 현재 저장소 기준으로 갱신한다.
  - 과거 이력은 별도 섹션으로 보존하고 최신 기준선 섹션을 분리한다.
- 재현·검증 방법:
  - 문서에 기재된 경로/파일 존재 여부를 현재 저장소와 대조.

### R-11
- 심각도: Medium
- 증상: `app/models.py`(모놀리식)와 `app/models/*`(모듈식)가 동시에 존재하여 유지보수 드리프트 위험이 있다.
- 근거 파일·라인:
  - `app/models.py` (모놀리식 구현 존재)
  - `app/models/__init__.py` (모듈식 re-export)
- 영향:
  - 어느 경로가 기준인지 혼동되어 수정 누락/중복 수정이 발생할 수 있다.
  - 마이그레이션/인덱스/유지보수 로직 불일치 위험이 증가한다.
- 권장 조치:
  - 단일 소스 오브 트루스 경로를 명시하고 구 경로를 단계적으로 제거한다.
  - import lint 규칙으로 금지 경로(`app/models.py`) 사용을 차단한다.
- 재현·검증 방법:
  - 코드 검색으로 모놀리식/모듈식 참조 지점을 분류.
  - 한쪽만 수정 시 동작 편차가 발생하는지 회귀 점검.

## 추가 기능 제안
다음 항목은 사내 메신저의 보안·운영·확장성·계약 일관성 수준을 높이기 위한 우선 제안이다.

1. 사내 인증 연동: LDAP/AD SSO 또는 SAML/OIDC 연동.
2. 분산 일관성: 업로드 토큰/레이트리밋/presence 상태의 Redis 백엔드 전환.
3. 첨부파일 보안: 업로드 후 AV 스캔 파이프라인과 격리 큐.
4. 운영 준수: 메시지 보존기간/자동삭제 정책과 감사 추적.
5. 관리자 감사로그: 권한 변경·강퇴·삭제 작업의 구조화 로그/내보내기.
6. 가용성: 정기 백업/복구 검증(runbook 포함) 자동화.
7. UX-서버 계약 단일화: 업로드 제한값을 서버 설정 단일 소스로 주입(`GET /api/config` 등).

추가 기능 로드맵 트랙:
- 보안 트랙: 인증 연동, 세션 무효화 완성, 첨부파일 AV 스캔.
- 운영/컴플라이언스 트랙: 보존 정책, 감사로그, 백업·복구 자동화.
- 확장성 트랙: Redis 기반 분산 상태 관리, 멀티 워커 안정화.
- UX 계약 정합 트랙: 서버 설정 단일 소스 제공 및 프론트 하드코딩 제거.

## 공개 API/인터페이스 변경안
1. `POST /api/upload`
   - 변경 목적: `room_id` 계약 위반 방지.
   - 변경안: 프론트 전 경로에서 `room_id` 필수 주입, 누락 시 명확한 400 에러 스키마 표준화.

2. `POST /api/polls/<poll_id>/vote`
   - 변경 목적: `option_id`-`poll_id` 무결성 보장.
   - 변경안: `option_id` 소속 검증 추가, 불일치 시 400(`invalid_option`) 표준 응답.

3. 인증 미들웨어
   - 변경 목적: 비밀번호 변경 이후 타 세션 강제 무효화.
   - 변경안: `before_request` + 소켓 connect에서 DB `session_token` 검증 훅 추가.

4. 레이트리밋 정책 정합
   - 변경 목적: 문서 정책과 구현 동기화.
   - 변경안: `/api/upload`, `/api/search/advanced`, 소켓 `send_message`에 제한 정책 적용 및 문서 업데이트.

5. 구성 조회 인터페이스
   - 변경 목적: 프론트 하드코딩 제거.
   - 변경안: `GET /api/config`(예: `max_upload_size`, 정책 플래그) 제공 후 프론트 동적 반영.

## 테스트 시나리오
아래 시나리오는 리스크 항목과 1:1로 연결되는 회귀 검증 세트다.

1. 첨부 버튼 업로드 E2E
   - 절차: 파일 선택 → `/api/upload` 요청 바디 확인 → 소켓 `send_message` 확인.
   - 기대 결과: `room_id` 포함, 업로드 성공, 메시지 저장 성공.

2. 투표 무결성
   - 절차: Poll A/B 생성 후 Poll A에 Poll B의 `option_id`로 투표.
   - 기대 결과: 400 반환, `poll_votes` 오염 없음.

3. 세션 무효화
   - 절차: 다중 세션 로그인 후 한 세션에서 비밀번호 변경.
   - 기대 결과: 나머지 세션이 401/재로그인 상태가 됨.

4. 레이트리밋 정합
   - 절차: 로그인/업로드/메시지 전송에 정책 초과 요청 주입.
   - 기대 결과: 문서 정책값대로 차단됨.

5. 멀티워커 토큰 일관성
   - 절차: 워커 A 업로드 토큰 발급 후 워커 B 소켓 전송 검증.
   - 기대 결과: 공유 저장소 기반에서 일관되게 성공/실패 판정.

6. malformed JSON 회귀
   - 절차: JSON 누락/비정상 타입 요청 반복.
   - 기대 결과: 500 없이 400 계열로 일관 응답.

7. 탈퇴 후 관리자 무결성
   - 절차: 생성자 탈퇴 후 방 관리 기능(관리자 전용 API) 점검.
   - 기대 결과: 방당 최소 1명 관리자 보장.

8. 환경 재현성
   - 절차: `pip install -r requirements.txt` 후 최소 부팅/테스트 진입.
   - 기대 결과: import 실패 없이 앱/테스트 초기화 성공.

## 우선순위 로드맵
즉시(0~2일):
- R-01, R-02, R-03 조치.
- 계약 위반/무결성/세션 보안 이슈 우선 차단.

단기(3~7일):
- R-04, R-05, R-06, R-07 조치.
- 정책 정합, 의존성 재현성, 분산 일관성 기반 정비.

중기(1~2주):
- R-08, R-09, R-10, R-11 조치.
- 관리자 무결성, 만료 처리 체계, 문서 최신화, 모델 구조 단일화.

지속 과제:
- 추가 기능 7개 항목을 보안/운영/확장성/UX 트랙으로 분할하여 단계 적용.

## 부록(환경 제약)
로컬 점검 환경(2026-02-25) 확인 결과:
- Python 버전: `3.13.12`
- 테스트 실행 제약:
  - `pytest tests -q` 실행 시 `ModuleNotFoundError: flask_socketio`로 대량 실패.
  - `pip show` 기준 미설치 패키지 확인: `flask-socketio`, `flask-session`, `Flask-Limiter`, `Flask-WTF`.
- 해석:
  - 본 보고서의 기능 리스크는 코드 정적 점검 근거 중심으로 작성했다.
  - 런타임 회귀 결과는 의존성 충족 후 재검증이 필요하다.

---

작성 원칙:
- 기존 `IMPLEMENTATION_AUDIT.md`는 보존.
- 이번 산출물은 코드 수정 없이 “점검 결과 문서화”에 집중.
- 심각도는 보안/무결성/가용성/운영성 영향을 우선 기준으로 분류.

---

## 구현 반영 결과 업데이트 (2026-02-25)

본 섹션은 문서 작성 당시의 리스크 점검 결과에 대해, 실제 코드 반영 후 상태를 기록한 것이다.

### 1) R-01 ~ R-11 처리 상태

- R-01: 완료 (`/api/upload` 전 경로 `room_id` 강제)
- R-02: 완료 (비밀번호 변경 시 `session_token` 갱신 + HTTP/Socket 검증)
- R-03: 완료 (`option_id`-`poll_id` 소속 검증)
- R-04: 완료 (레이트리밋 정책 정합화)
- R-05: 완료 (`Flask-Session` 요구사항 반영)
- R-06: 완료 (`state_store` 추상화 + Redis 장애 시 메모리 강등)
- R-07: 완료 (공통 JSON 파서 기반 malformed `400`)
- R-08: 완료 (탈퇴 시 `rooms.created_by` 재할당 및 관리자 무결성 보강)
- R-09: 완료 (만료 투표 정리: 주기 작업 + 조회/투표 시점 보정)
- R-10: 완료 (감사 문서 최신 기준선 섹션 반영)
- R-11: 완료 (`app/models/*` 단일 소스화, 모놀리식은 `app/legacy`로 분리)

### 2) 추가 기능 7개 반영 상태

- OIDC SSO(옵션): 완료 (`/api/auth/providers`, `/auth/oidc/login`, `/auth/oidc/callback`)
- 분산 일관성(옵션): 완료 (`state_store`, Redis/메모리 강등)
- AV 격리 스캔(옵션): 완료 (`upload_scan_jobs`, `/api/upload/jobs/<job_id>`)
- 보존 정책(옵션): 완료 (`RETENTION_DAYS` 기반 정리)
- 관리자 감사로그: 완료 (JSON/CSV 조회)
- 백업/복구(로컬 수동): 완료 (`scripts/*`, `docs/BACKUP_RUNBOOK.md`)
- 서버 설정 단일화: 완료 (`GET /api/config`)

### 3) `.spec` 점검/반영

`messenger.spec` 보강 반영:

- 신규 모듈 hidden import 추가
  - `app.state_store`, `app.upload_scan`, `app.oidc`, `app.models.admin_audit`
- Redis 동적 import 누락 방지
  - `redis`, `redis.asyncio`
- 런북 데이터 포함
  - `docs/BACKUP_RUNBOOK.md`

### 4) 검증 결과

- 전체 테스트: `pytest -q` -> **71 passed**
- 문법 검사: 핵심 수정 파일 `py_compile` 통과
