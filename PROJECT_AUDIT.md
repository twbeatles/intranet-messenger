# Project Audit

감사 일자: 2026-10-04
감사 범위: 기능 구현·런타임 안정성 (보안 경계, 동시성, 데이터 흐름, 복구, 문서 정합성)
감사 방식: `README.md`·`CLAUDE.md`·`implementation_gap_review_2026-04-27.md`·`docs/BACKUP_RUNBOOK.md` 선독 → CodeGraph MCP 구조/호출 분석 → `Select-String`·파일 열람으로 보완 → pytest·`npm run check:js`·pyright 실행 검증
제약 준수: 코드 수정 없음, destructive 명령 없음, production 데이터 변경 없음, 미실행 테스트 기재 없음

> 참고: 루트에 2026-06-25자 `PROJECT_AUDIT.md`가 이미 존재했고, 그 문서의 개선 권고(초대 트랜잭션화, Redis 경고/`REQUIRE_REDIS_STATE`, relay rate limit, `refreshPendingMessageDecryption`, experimental race guard 등)가 현재 코드에 반영되어 있음을 확인했다. 본 문서는 그 후속 상태에 대한 새로운 원샷 감사로 기존 문서를 대체한다.

## Remediation Status (2026-10-04)

본 문서의 모든 High-Risk Issues와 확인된 Gap이 아래와 같이 조치되었다.

| 항목 | 상태 | 검증 |
|------|------|------|
| ISSUE-001 그린렛-로컬 커넥션 + BEGIN 실패 명시화 | ✅ `app/models/base.py`, `app/models/rooms.py` | `tests/test_project_audit_remediation.py` (그린렛 병렬 + BEGIN 실패 + 단일 요청 동일 버전) |
| ISSUE-002 탈퇴 첨부 정합성 + sender FK 마이그레이션 | ✅ `app/models/users.py`, `app/models/base.py` | `tests/test_user_deletion.py` (참조 정리 + 구 스키마 마이그레이션) |
| ISSUE-003 복원 WAL/서버감지/스냅샷 분리 | ✅ `scripts/restore_local.py` | `tests/test_restore_local.py` (신규) |
| ISSUE-004 rotate 실패 가시화 | ✅ `app/http/rooms.py` (경고 + `key_rotation_failed` audit) | `tests/test_kick_member.py` |
| ISSUE-005 스캔 temp 정리 + purge quarantine 포함 | ✅ `app/upload_scan.py`, `app/upload_tokens.py` | `tests/test_upload_tokens.py` |
| ISSUE-006 검색 fallback 이스케이프 | ✅ `app/models/messages.py` | `tests/test_search_limit_clamp.py` |
| OIDC 연동 계정 탈퇴 경로 | ✅ `app/models/users.py`, `app/http/auth.py` (`oidc_confirm`) | `tests/test_user_deletion.py` |
| limiter redis 폴백 경고 | ✅ `app/bootstrap/runtime.py` | 로그 경로 (단위 테스트 없음) |
| 레거시 아카이브 | ✅ `archive/legacy-models/` 이동 + spec 제외 | 전체 스위트 |
| server.py 배너 + AGENTS.md | ✅ 문구 정정 + `AGENTS.md` 신설 | — |
| 스캔 job 재시도/취소 API + 프론트 facade | ✅ `app/http/uploads.py`, `static/js/services/upload-service.js` | `tests/test_upload_scan_jobs.py`, smoke 계약 테스트 |
| 경량 E2E smoke | ✅ `tests/test_e2e_smoke.py` (소켓 클라이언트 기반) | 1 passed |

추가 발견 (감사 문서에 없던 실제 버그): 메시지가 있는 사용자는 `messages.sender_id` FK 때문에 탈퇴 자체가 실패했음. sender FK 제거 마이그레이션으로 해소.

최종 검증 (2026-10-04): `npm run check:js` pass, `pytest tests -q` **134 passed**, targeted 3종 **19 passed**, `pyright app gui` **0 errors, 0 warnings**.

## 1. Executive Summary

- 프로젝트 전체 상태: Flask + Socket.IO(gevent) 실시간 메신저. 멤버십 기반 방 키 로테이션(`messages.key_version >= room_members.joined_key_version`), 서버 권위 소켓 이벤트, 업로드 토큰 1회성 소비, 삭제 첨부 검색 제외 등 핵심 계약이 구현되어 있고 회귀 테스트로 뒷받침된다. 이번 감사 시점 전체 스위트가 녹색이다.
- 전체 위험도: **단일 프로세스 기준 Medium, gevent 동시 부하 또는 복원 절차 기준 Medium~High**
- 가장 중요한 문제 3~5개:
  1. gevent 그린렛이 `threading.local` DB 커넥션을 공유해 초대 원자성 등 트랜잭션 경계가 훼손될 수 있음 (High/Likely)
  2. 회원 탈퇴 시 첨부 파일 바이트는 삭제되지만 메시지의 `file_path`가 남아 깨진 첨부 참조가 남음 (Medium/Confirmed)
  3. `scripts/restore_local.py`가 SQLite WAL/`-shm`을 처리하지 않고 실행 중 서버도 검사하지 않음 (Medium/Confirmed)
  4. 강퇴/나가기 후 키 로테이션 실패가 경고 로그로만 끝나 구 키가 유지됨 (Medium/Likely)
  5. OIDC 전용 계정은 비밀번호를 몰라 계정 탈퇴·비밀번호 변경이 불가함 (Medium/Confirmed Gap)
- 데이터 손상/유실 가능성 여부: **있음 (조건부)** — 복원 절차의 WAL 잔류, 탈퇴자의 공유 첨부 바이트 삭제, 동시 쓰기 시 트랜잭션 interleaving이 해당 조건에서 데이터 무결성을 해칠 수 있다. 평상시 단일 사용자 순차 사용에서는 유실 경로가 확인되지 않았다.
- 가장 먼저 수정해야 할 영역: DB 쓰기 경로의 그린렛-안전성(커넥션 공유 제거 또는 쓰기 직렬화)과 탈퇴 시 첨부 정합성.

## 2. Project Understanding

- 프로젝트 목적: 사내 실시간 채팅(방/파일/핀/리액션/투표/검색/멘션), PyQt6 서버 관리 GUI, PyInstaller 단일 실행 배포, SQLite + 로컬 `uploads/` 기반 단일 서버 우선 설계. 방 키는 서버가 관리하고 멤버 범위로 keyring을 전달하는 모델(서버-블라인드 E2E가 아님).
- 주요 entrypoint: `server.py` (GUI 기본, `--cli` 서버, `--worker` 런처) → `app/__init__.py::create_app()` → `app/factory.py::build_app()`.
- 핵심 모듈:
  - `app/bootstrap/` — `runtime.py`(Flask/세션/StateStore/Redis 경고), `socketio_config.py`, `workers.py`(maintenance + AV 스캔 워커), `hooks.py`(세션 강제·teardown·보안 헤더)
  - `app/http/` — `auth.py`(가입/로그인/탈퇴), `rooms.py`(방/초대/강퇴/나가기), `messages.py`(조회/수정/삭제/검색/리액션), `uploads.py`(업로드/다운로드/파일 삭제), `collaboration.py`(핀/투표), `public.py`(OIDC)
  - `app/socket_events/` — `messages.py`(send/edit/delete/reaction), `rooms.py`·`features.py`(relay + rate limit), `presence.py`, `connection.py`, `shared.py`(세션 토큰·rate limit)
  - `app/models/` — `rooms.py`(키 로테이션·`invite_members_with_key_rotation`), `messages.py`(가시성·검색), `users.py`(인증·탈퇴), `files.py`, `base.py`(연결·init·정리)
  - `app/upload_tokens.py` + `app/state_store.py`(TTL 300초 1회성 토큰), `app/crypto_manager.py`(마스터키 기반 방 키 암호화), `app/oidc.py`
- 데이터 저장 방식: SQLite(WAL) 단일 파일 + `uploads/`(최상위 첨부, `profiles/`, `quarantine/`), Flask-Session 파일 캐시, StateStore(기본 in-memory, Redis 선택).
- 외부 의존성: Flask-SocketIO/gevent, pycryptodome, bcrypt, PyJWT(선택 OIDC), ClamAV(선택, TCP), Redis(선택, 다중 워커용).
- 핵심 실행 흐름:
  - `POST /api/upload → issue_upload_token(StateStore, TTL 300s) → socket send_message에서 consume(1회성) → create_message(+room_files) → new_message broadcast`
  - `초대/나가기/강퇴/탈퇴 → rotate_room_key → emit room_security_updated(사용자별 keyring) → 프론트 키 갱신 + pending 복호화 재시도`
  - `조회/검색/파일/핀/리액션/답장/읽음/다운로드/수정·삭제 = messages.key_version >= joined_key_version + 삭제첨부 제외 공유 조건`
  - `server.py --cli → create_app → init_db → maintenance worker → socketio.run`

## 3. Audit Coverage & Limitations

- 실제 확인한 주요 모듈: `app/http`(auth/rooms/messages/uploads), `app/models`(rooms/messages/users/files/base), `app/socket_events`(messages/features/rooms/shared), `app/upload_tokens.py`, `app/state_store.py`, `app/crypto_manager.py`, `app/oidc.py`, `app/bootstrap`(runtime/workers/hooks), `scripts/backup_local.py`·`restore_local.py`, `config.py`·`server.py`·`messenger.spec`, 프론트 소켓 런타임/초대·보안 핸들러(발췌).
- CodeGraph로 분석한 호출 관계: entrypoint→factory→bootstrap/routes/sockets, `invite_members_with_key_rotation`·`rotate_room_key`·`can_user_see_message`·`consume_upload_token`·`sync_user_room_membership`·`get_db` blast radius, 레거시 `models_monolith` 중복 정의 존재 확인.
- 실행한 테스트(모두 당일 실행, 결과 인용):
  - `python -m pytest tests -q` → **115 passed** (147.9s, gevent monkey-patch 경고 1건만 기록, 기능 영향 없음)
  - `pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py tests/test_project_audit_remediation.py -q` → **15 passed**
  - `npm run check:js` (eslint + tsc) → **pass**
  - `pyright app gui` → **0 errors, 0 warnings**
- 확인하지 못한 환경/외부 서비스: Redis 다중 워커 실제 구성, ClamAV 실연동 스캔, OIDC 실제 IdP, PyQt6 GUI 실기동(헤드리스), PyInstaller 빌드 산출물, gevent 동시 부하 재현, Windows 부팅 자동실행/방화벽 경로.
- CodeGraph 또는 분석상의 한계: `muse.search`가 `static/js`에서 무응답이라 프론트 확인은 `Select-String`으로 대체했다. 동시성 이슈(ISSUE-001)는 코드 메커니즘까지만 확정하고 런타임 재현은 하지 않아 Likely로 표기했다. `app/legacy/models_monolith.py`는 런타임 미사용으로 보고 dead-code 취급하되 risk로 과장하지 않았다.

## 4. High-Risk Issues

### [ISSUE-001] gevent 그린렛 간 `threading.local` 커넥션 공유로 트랜잭션 경계 훼손 가능

* **위치:** `app/models/base.py` — `_ConnectionLocal(threading.local)`, `get_db()` / `app/__init__.py` — `monkey.patch_all()` / `app/models/rooms.py` — `invite_members_with_key_rotation()`
* **우선순위:** High
* **신뢰도:** Likely
* **문제:** CLI(권장 운영 모드)에서는 gevent monkey patch가 적용되고, `get_db()`는 `threading.local` 커넥션을 반환한다. gevent는 한 OS 스레드에서 다수 그린렛을 돌리므로 동시 요청/소켓 이벤트가 같은 `sqlite3` 커넥션 객체를 공유할 수 있다. `check_same_thread=False` + `busy_timeout`은 잠금 대기만 완화할 뿐 같은 커넥션 위의 인터리빙은 막지 못한다. 그린렛 B가 그린렛 A의 초대 트랜잭션 도중 `get_db()`를 얻으면 A의 커넥션을 재사용해 B의 `commit()`이 A의 부분 트랜잭션을 조기 확정하거나, B의 `BEGIN IMMEDIATE`가 "cannot start a transaction within a transaction"으로 실패하는데 초대/나가기 코드는 이를 bare `except: pass`로 삼켜 경계가 깨진 채 진행한다.
* **발생 조건:** gevent 모드(CLI)에서 DB 쓰기가 겹칠 때 — 동시 초대, 초대+메시지 전송, maintenance purge와 업로드 경합 등.
* **영향:** 2026-06-25 remediation으로 확보한 초대 원자성(`BEGIN IMMEDIATE` + 단일 commit)이 무력화되어 `joined_key_version` 불일치(과거 히스토리 과다 노출) 또는 "Recursive use of cursors" 계열 메시지 저장 실패가 가능.
* **근거:** `base.py:32-38`(threading.local), `app/__init__.py:25-32`(CLI에서 patch 적용, GUI에서만 SKIP), `rooms.py:260-308`(`BEGIN IMMEDIATE` + swallow + 공유 `conn.commit()`), `hooks.py:58-60`(teardown은 요청 종료 후 정리라 동시 진행 중 공유를 막지 못함).
* **반증 확인:** `busy_timeout=30000`·WAL·teardown 정리를 확인했으나 이들은 잠금/사후 정리에만 유효하고 동일 커넥션 인터리빙은 막지 못한다. 테스트가 전부 순차 실행이라 녹색 스위트는 반증이 아니다. GUI 모드(PyQt, gevent 미적용·실스레드)에서는 `threading.local`이 정상 동작하므로 해당 모드는 영향 제외.
* **호출/영향 범위:** CodeGraph 기준 `get_db` 호출자 80+ (`rooms`·`messages`·`users`·`files`·`polls`·토큰 purge·maintenance). 쓰기 트랜잭션 전역에 영향.
* **권장 수정 방향:** 쓰기 경로 직렬화(단일 writer 락) 또는 그린렛-로컬 커넥션(gevent.local/요청별 커넥션)으로 교체. `BEGIN IMMEDIATE` 실패 swallow를 제거하고 실패 시 명시 롤백+에러 반환.
* **필요한 회귀 테스트 (구현 시 정정):** 병렬 초대 요청은 각각 직렬 rotate되므로 멤버별 버전이 다를 수 있다. 정확한 계약은 ① 단일 요청 다수 초대 → 전원 동일 버전(`test_single_invite_request_assigns_same_joined_key_version`), ② 병렬 요청 → 실패율 0 + 각 버전이 유효 범위 내(`test_concurrent_invites_via_greenlets_keep_key_versions_consistent`), ③ BEGIN 실패 → `error` 코드(`test_invite_returns_error_when_begin_fails`)이다.

### [ISSUE-002] 회원 탈퇴 시 공유 첨부의 바이트는 지워지는데 메시지 참조는 남아 깨진 첨부가 됨

* **위치:** `app/models/users.py` — `delete_user()` (451~465행)
* **우선순위:** Medium
* **신뢰도:** Confirmed
* **문제:** 탈퇴 처리에서 `DELETE FROM room_files WHERE uploaded_by` + 디스크 파일 삭제를 수행하지만, `messages` 행의 `file_path`·`file_name`은 그대로 두고 content만 익명화한다. 공유방에 남는 메시지는 존재하지 않는 파일을 계속 가리킨다.
* **발생 조건:** 파일을 올린 사용자가 탈퇴하고, 그 파일 메시지가 있는 공유방에 다른 멤버가 남아 있을 때 (항상).
* **영향:** 잔존 멤버의 공유 첨부 유실 + 깨진 첨부 UI. 다운로드는 `room_files` 조회에서 404로 우아하게 실패하므로 크래시는 없다.
* **근거:** `users.py:451-465`(room_files 삭제 후 messages는 content만 갱신), `uploads.py:198-212`(room_files 행 없으면 404).
* **반증 확인:** `delete_message`·`delete_room_file`은 messages까지 함께 정리함을 확인 — 탈퇴 경로만 불일치. 파일 서랍(`get_room_files`)은 room_files 기준이라 일관되나 채팅 메시지 렌더와 불일치한다.
* **호출/영향 범위:** `auth.py::delete_account` → `delete_user` → 잔존 멤버의 `get_room_messages`·다운로드 경로.
* **권장 수정 방향:** 탈퇴 시 해당 사용자의 파일 메시지도 `delete_message`와 동일하게 `[삭제된 메시지]` + `file_path/file_name = NULL`로 정리하거나, 정책상 보존이면 바이트 삭제를 중단하고 소유권을 방(또는 null)으로 이전.
* **필요한 회귀 테스트:** 파일 올린 사용자 탈퇴 후 잔존 멤버 조회 → 메시지 `file_path IS NULL` + 디스크 파일 부재 + 다운로드 404를 assert.

### [ISSUE-003] 복원 스크립트가 WAL/`-shm`을 처리하지 않고 실행 중 서버도 검사하지 않음

* **위치:** `scripts/restore_local.py` — `main()` (58~79행)
* **우선순위:** Medium
* **신뢰도:** Confirmed
* **문제:** `--yes` 복원이 `messenger.db` 파일만 `copy2`로 덮어쓰고 `-wal`/`-shm` 잔존 파일을 제거하지 않는다. 안전 스냅샷도 `messenger.db`만 복사한다. 서버 실행 중 복원 여부를 검사하지 않고(미확인 시 경고 문구만 출력, `--yes`면 무조건 진행), WAL 체크포인트도 수행하지 않는다.
* **발생 조건:** WAL 파일이 남아 있는 상태(루트에 `messenger.db-wal` 존재 확인됨)에서 복원하거나, 서버를 끄지 않고 `--yes` 복원할 때.
* **영향:** 오래된 WAL 프레임이 복원된 DB에 적용되거나 무결성 오류 → 복원 후 데이터 불일치·시작 실패. 백업 쪽(`backup_sqlite`)은 SQLite online backup API라 안전하고, 문제는 복원 방향에만 있다.
* **근거:** `restore_local.py:65-73`(db 파일만 복사, wal/shm 언급 없음), 루트 `messenger.db-wal` 실존, `verify_restore.py`는 사후 검사만 담당.
* **반증 확인:** `BACKUP_RUNBOOK.md`가 "서버 중지 후 복원"을 안내하나 스크립트가 강제하지 않으므로 운용자 실수 경로가 열려 있다. `shutil.copytree`의 uploads 복원은 원자적이지 않으나 DB 정합성만큼 치명적이지 않아 본 이슈의 부기로 둔다.
* **호출/영향 범위:** 수동 복원 절차 전체(DB + uploads + 스냅샷). 복원 검증을 통과해도 WAL 잔류는 `integrity_check`에서 잡히지 않을 수 있다.
* **권장 수정 방향:** 복원 전 실행 중 서버 감지(Control 포트/락 파일) 시 중단, 복원 전후 `PRAGMA wal_checkpoint(TRUNCATE)` + `-wal`/`-shm` 제거, 스냅샷을 백업 디렉토리 밖(형제 디렉토리)으로 분리.
* **필요한 회귀 테스트:** WAL이 있는 DB에 대한 복원 드라이런 → 복원 후 `-wal`/`-shm` 부재 + `integrity_check == ok` + 복원 전 스냅샷이 백업본과 동일함을 assert.

### [ISSUE-004] 강퇴/나가기 후 키 로테이션 실패가 경고 로그로만 끝나 구 키가 유지됨

* **위치:** `app/http/rooms.py` — `_rotate_and_emit_room_security()` (57~64행), `leave_room_route`·`kick_member`
* **우선순위:** Medium
* **신뢰도:** Likely
* **문제:** 멤버십 삭제 commit 이후 별도 트랜잭션으로 rotate하는데, 실패 시 `logger.warning`만 남기고 HTTP는 이미 성공 반환됐다. 재시도·관리자 알림·실패 표기가 없다.
* **발생 조건:** rotate 중 DB 오류 등 드문 실패. 또는 emit 단계 실패(소켓 미수신 — 클라이언트는 재입장 전까지 구 키).
* **영향:** 나간 멤버가 아는 구 키로 방이 계속 운영됨. 나간 멤버의 API/소켓 접근 자체는 차단되므로(멤버십 동기화·`room_access_revoked`), 새 암호문을 입수할 경로는 없어 실질 노출은 제한적이나, 보안 계약("잔존 멤버 대상 rotate") 위반 상태가 조용히 지속된다.
* **근거:** `rooms.py:57-64`(실패 시 조기 return), leave/kick은 삭제-회전 2트랜잭션 분리.
* **반증 확인:** 접근 차단은 별도 경로로 동작함을 확인해 탈퇴자 열람 가능성은 반증됨. 남은 것은 키 위생 실패의 불가시성이다.
* **호출/영향 범위:** leave·kick·(탈퇴 후 accounts 경로의 best-effort rotate 포함, `users.py:472-478` — 반환값 미검사).
* **권장 수정 방향:** rotate 실패 시 500이 아닌 "성공 + 보안 경고" 상태로 반환하거나 admin audit 로그에 기록하고, maintenance에서 `key_version` 정합성 재검사 후 경고.
* **필요한 회귀 테스트:** rotate를 강제 실패시킨 강퇴 → 응답에 경고 표기(또는 audit 로그 기록) + 이후 rotate 성공 시 복구를 assert.

### [ISSUE-005] AV 스캔 예외 경로의 quarantine 임시 파일이 영구 잔류함

* **위치:** `app/upload_scan.py` — `_process_job()` (166~171행) / `app/upload_tokens.py` — `purge_expired_upload_tokens()` (41~54행)
* **우선순위:** Low
* **신뢰도:** Confirmed
* **문제:** 스캔 결과 `not clean`이면 temp를 삭제하지만, 그 바깥 예외(`shutil.move` 실패 등) 경로에서는 temp 파일을 삭제하지 않고 job만 `error`로 둔다. purge는 최상위 파일만 `scandir`하므로 `quarantine/` 하위 temp는 영원히 정리되지 않는다.
* **발생 조건:** AV 활성화 + 스캔 워커 예외 발생 시.
* **영향:** 디스크 서서히 증가. 보안·정합성 영향 없음.
* **근거:** `upload_scan.py:150-171`(두 경로의 삭제 여부 차이), `upload_tokens.py:41`(비재귀 스캔), `uploads.py:86-89`(temp가 quarantine 하위).
* **반증 확인:** 프로필 이미지 교체(`profile.py:106-110`)는 구 파일 삭제를 확인 — 본 건은 스캔 예외 경로에만 해당.
* **호출/영향 범위:** AV 활성화 배포의 `uploads/quarantine/` 디스크 사용량.
* **권장 수정 방향:** 예외 경로에서도 temp 삭제 시도 + purge가 `quarantine/` 하위를 포함하도록 확장(단 `profiles/`는 제외 유지).
* **필요한 회귀 테스트:** `_process_job`에 강제 예외 주입 → temp 파일 부재 assert. quarantine에 오래된 temp 배치 후 purge → 삭제됨 assert.

### [ISSUE-006] 일반 검색 fallback의 LIKE 와일드카드 미이스케이프 과다 매칭

* **위치:** `app/models/messages.py` — `search_messages()` (436~466행)
* **우선순위:** Low
* **신뢰도:** Confirmed
* **문제:** FTS 미사용 fallback이 `f'%{query}%'`를 그대로 바인딩해 `%`·`_` 입력이 와일드카드로 동작한다. 같은 파일의 `advanced_search`는 `_like_escape`로 이스케이프하므로 두 경로가 불일치한다.
* **발생 조건:** FTS 테이블 부재 + `%`/`_` 포함 검색어.
* **영향:** 검색 결과 과다 노출(단 멤버십·가시성 필터 안이므로 권한 밖 노출은 없음). SQL 인젝션은 아님(파라미터 바인딩).
* **근거:** `messages.py:447`·`465` vs `495-496`의 이스케이프 유무 차이.
* **반증 확인:** 권한 경계는 유지됨을 확인 — 정확도 문제로 한정.
* **호출/영향 범위:** `/api/search` 경유 일반 검색(advanced_search는 정상).
* **권장 수정 방향:** fallback에도 `_like_escape` 적용 + `ESCAPE '\'` 절 추가.
* **필요한 회귀 테스트:** `%`·`_`·`\` 포함 검색어 → 리터럴 일치만 반환 assert.

## 5. Potential Functional Gaps

- **Confirmed Gap — OIDC 전용 계정은 탈퇴·비밀번호 변경이 불가:** `delete_account`(`auth.py:118-153`)와 `change_password`가 현재 비밀번호 검증을 요구하고, `get_or_create_oidc_user`(`users.py:294-359`)는 무작위 비밀번호 해시를 부여한다. OIDC 사용자는 비밀번호를 알 수 없어 두 API를 사용할 수 없고, 대체 경로(연동 해제·관리자 탈퇴)도 없다.
- **Confirmed Gap — 동시성 회귀 테스트 부재:** leave/kick/invite 가시성·원자성 단위 테스트는 있으나 병렬 초대·병렬 메시지 전송 시나리오는 `tests/` 어디에도 없다(디렉토리 목록 및 CodeGraph 호출자 기준). ISSUE-001의 재현 커버리지가 없는 상태다.
- **Confirmed Gap — 스캔 실패 job 재시도 API 부재:** `GET /api/upload/jobs/<id>`는 `infected`·`error` 조회만 제공하고 재시도/취소 엔드포인트가 없다. AV 오탐·clamd 일시 장애 시 사용자는 같은 파일을 처음부터 다시 업로드해야 한다.
- **Likely Gap — rate limit의 침묵 메모리 폴백:** `RATELIMIT_STORAGE_URI`가 redis 스킴인데 `redis` import 실패 시 `runtime.py:153-157`에서 경고 없이 `memory://`로 전환된다. StateStore 쪽은 경고/`REQUIRE_REDIS_STATE` fail-fast가 있으나 limiter 쪽은 없어, 다중 워커에서 로그인·업로드 제한이 워커별로 따로 적용될 수 있다.
- **추정 — 암호화 메시지 서버 검색 제외:** `search_messages`·`advanced_search`가 `m.encrypted = 0`만 검색하고 암호문은 제외한다(코드 내 note 명시). 서버가 키를 보유한 구조상 기술적으로 가능하나 현재 설계상 의도이므로 버그가 아니라 UX 제약으로 기록한다. 초대 전 히스토리가 검색에서 빠지는 것은 동일 visibility 규칙의 당연한 결과다.
- **추정 — 메시지 동시 편집 last-write-wins:** `edit_message`에 버전·충돌 감지가 없어 두 단말 동시 편집 시 조용히 덮어쓴다. 빈도·피해가 낮아 구조 개선 단계로 둔다.

## 6. Documentation Mismatches

- **`server.py:83` CLI 배너의 "E2E (종단간 암호화)" 표기 잔존 (Confirmed):** README의 E2E 표현은 remediation에서 정정됐고 `claude.md`·`gemini.md`도 "not server-blind E2E"로 명시했으나, `python server.py --cli` 시작 배너는 여전히 `암호화: E2E (종단간 암호화)`를 출력한다. 실제 모델(서버 관리형 방 키 + 평문 keyring 전달)과 배치된다. Low.
- **`AGENTS.md` 부재 (Confirmed → 해소):** 2026-10-04 조치로 `AGENTS.md`를 신설하고 `claude.md`·`gemini.md`의 문서 목록에도 반영했다. Low.
- **구 `PROJECT_AUDIT.md`(2026-06-25)의 "115개 중 3개 실패" 서술이 현재와 불일치:** 당시 결과(`test_encoding_hygiene`·OIDC 2건 실패)는 remediation으로 해소되어 본 감사에서 **115 passed**를 확인했다. 본 문서로 대체되면서 해소된다. 정보성.
- **없음이 확인된 항목:** `messenger.spec`의 hiddenimports·포장 데이터(`app.*` + `docs/BACKUP_RUNBOOK.md`)는 현행 런타임과 일치한다. BACKUP_RUNBOOK의 테이블 목록·스모크 체크 항목은 현재 스키마·계약과 일치한다.

## 7. Recommended Fix Plan

### Phase 1 — Immediate

1. ISSUE-001: 쓰기 직렬화(단일 writer 락) 또는 그린렛-로컬 커넥션 도입 + `BEGIN` 실패 swallow 제거. 병행해서 동시 초대 회귀 테스트 추가.
2. ISSUE-002: 탈퇴 시 파일 메시지 정리 정책 확정(메시지 정리 또는 바이트 보존+소유권 이전) 후 동일 변경셋에 회귀 테스트.
3. ISSUE-003: `restore_local.py`에 실행 중 서버 감지·WAL 체크포인트/`-wal`·`-shm` 제거·스냅샷 분리. 다음 릴리스 전 복원 드라이런 필수.

### Phase 2 — Stability

1. ISSUE-004: rotate 실패 가시화(audit 로그 + 응답 경고) 및 maintenance 정합성 검사.
2. ISSUE-005: 스캔 예외 경로 temp 정리 + purge의 `quarantine/` 포함.
3. ISSUE-006: 검색 fallback 이스케이프 통일.
4. OIDC 계정 탈퇴/비밀번호 경로(연동 계정용 확인 절차 또는 관리자 탈퇴) 신설.
5. limiter redis 폴백에 StateStore와 동일한 경고 로그 추가.

### Phase 3 — Structural

1. `app/legacy/models_monolith.py` 아카이브(현행 `app/models/*` 단일화, import 경로 정리) — 유지보수 혼선 제거.
2. `server.py` 배너 문구와 `AGENTS.md`(또는 소문자 문서로의 리다이렉트) 정리.
3. 스캔 job 재시도/취소 API + 프론트 복구 UX.
4. Playwright 등 경량 E2E smoke(방 전환·키 로테이션·핀-파일 삭제 동기화) — JS 핵심 계약이 eslint/tsc에만 의존 중.

## 8. Test Recommendations

- **Unit:** `rotate_room_key(conn=...)` 공유-트랜잭션 단위 테스트(외부 conn 주입 시 commit/rollback을 호출자가 전담함을 assert). `can_user_see_message` 파라미터화(초대 전/후, 삭제 첨부, 탈퇴자). `_like_escape` 포함 검색 동등성(FTS vs fallback).
- **Integration:** 동시 초대 N건 → 단일 `key_version` 증가 + `joined_key_version` 일치. 탈퇴→잔존 멤버 메시지·다운로드 정합성. WAL 존재 상태에서 복원 스크립트 실행(임시 디렉토리). rotate 강제 실패 주입 강퇴 → 경고/audit 기록. quarantine temp 예외 주입 → 잔류 없음.
- **End-to-End:** 초대→신규 멤버의 초대 전 히스토리 비가시→신규 메시지 가시 전구간. 파일 업로드→토큰 재사용 거부→메시지 실패 시 orphan 정리. 핀-파일 삭제 시 `message_deleted` + `pin_updated` 동시 수신.
- **Concurrency:** gevent 그린렛 8~16 병렬 초대·전송 100회 → 실패율 0 + 버전 단조성. maintenance purge와 업로드 경합.
- **Regression:** 기존 `test_project_audit_remediation.py`·`test_upload_tokens.py`·`test_implementation_gap_remediation.py` 유지. `test_user_deletion.py`에 첨부 케이스 추가.
- **Platform-specific:** Windows(GUI, gevent 미적용) vs Linux(CLI, gevent) 동일 시나리오 비교 — ISSUE-001이 gevent 경로에만 있는지 확인. 한글 파일명·보안솔트 경로(`runtime_paths`)의 OS별 동작.

## 9. Final Assessment

| 영역 | 평가 | 근거 |
|------|------|------|
| Functional Correctness | Acceptable | 핵심 계약(가시성·토큰·서버 권위 이벤트) 구현+회귀 테스트. 탈퇴 첨부·OIDC 탈퇴 등 조건부 결함 잔존 |
| Runtime Stability | Needs Work | gevent+threading.local 공유(ISSUE-001)가 동시 부하에서 트랜잭션을 위협. 순차 사용은 안정 |
| Data Integrity | Needs Work | 복원 WAL(ISSUE-003)·탈퇴 첨부(ISSUE-002)가 조건부 무결성 위험. 백업 방향은 안전 |
| Error Resilience | Acceptable | 소켓·HTTP 예외 처리·rate limit·세션 무효화가 전반적으로 갖춰짐. rotate 실패 불가시성(ISSUE-004)이 감점 |
| Cross-platform Robustness | Acceptable | Windows GUI/CLI 분기·UTF-8 표준출력·경로 헬퍼 존재. GUI 실기동·빌드 산출물은 미검증 |
| Test Confidence | Good | 115 passed + targeted 15 passed + eslint/tsc + pyright 무오류. 동시성·복원 스크립트 커버리지만 부족 |

**실제로 먼저 수정할 문제 3개:**

1. **[ISSUE-001] gevent 커넥션 공유** — 유일한 High. remediation 원자성을 무력화할 수 있는 구조 문제라 최우선.
2. **[ISSUE-002] 탈퇴 시 첨부 정합성** — 확정적 데이터 유실(공유 첨부)이라 조건 명확·수정 범위 작음.
3. **[ISSUE-003] 복원 스크립트 WAL 처리** — 복원은 드물지만 실패 시 복구 자체가 깨지는 경로라 릴리스 전 필수.
