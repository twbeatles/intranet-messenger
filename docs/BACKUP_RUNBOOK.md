# BACKUP_RUNBOOK

작성일: 2026-02-25
범위: 로컬 환경 수동 백업/복구/검증

## 1. 목적
- 운영 중 장애/실수에 대비해 `messenger.db`와 `uploads/`를 일관성 있게 백업한다.
- 복구 후 무결성(`sqlite integrity_check`)과 핵심 테이블 존재 여부를 자동 확인한다.

## 2. 전제
- 이 문서는 로컬 대상만 다룬다.
- 백업/복구는 **수동 실행** 기준이다.
- 복구 전에는 앱/서버 프로세스를 중지해야 한다.

## 3. 백업 실행
명령:
```bash
python scripts/backup_local.py --label before_release
```

옵션:
- `--output-root backup/manual` (기본값)
- `--db-path <sqlite_path>`
- `--uploads-dir <uploads_path>`
- `--label <임의태그>`

산출물:
- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/db/messenger.db`
- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/uploads/...`
- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/manifest.json`

## 4. 복구 실행
복구는 실제 데이터 덮어쓰기이므로 서버 중지 상태에서 수행한다.

미리보기(실행 안 함):
```bash
python scripts/restore_local.py backup/manual/backup_20260225T120000Z_before_release
```

실행:
```bash
python scripts/restore_local.py backup/manual/backup_20260225T120000Z_before_release --yes
```

복구 동작:
- 현재 DB/업로드를 `pre_restore_snapshot_<UTC_TIMESTAMP>`로 안전 복사
- 백업본 DB/업로드를 대상 경로로 복원

## 5. 복구 검증
명령:
```bash
python scripts/verify_restore.py
```

검증 항목:
- SQLite `integrity_check == ok`
- 필수 테이블 존재 여부
  - `users`, `rooms`, `room_members`, `messages`, `polls`, `poll_options`, `poll_votes`, `room_files`
  - `sso_identities`, `upload_scan_jobs`, `admin_audit_logs`
- 기본 개수 통계 출력(사용자/방/메시지/업로드 파일)

## 6. 장애 대응
1. 백업 실패: 디스크 여유 공간 확인, DB/업로드 경로 확인, 권한 확인
2. 복구 실패: 앱 완전 중지 여부 확인, 경로 잠금/권한 확인
3. 검증 실패:
   - `integrity_check` 실패 시 즉시 이전 `pre_restore_snapshot_*`로 롤백
   - 필수 테이블 누락 시 잘못된 백업본 사용 여부 점검

## 7. 권장 운영 절차
1. 배포 전: `backup_local.py`
2. 배포 후: 스모크 테스트
3. 장애 시: `restore_local.py --yes`
4. 복구 직후: `verify_restore.py`
5. 검증 성공 후 서비스 재기동
