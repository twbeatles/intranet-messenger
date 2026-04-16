# BACKUP_RUNBOOK

Created: 2026-02-25
Last updated: 2026-04-16
Scope: local backup, restore, and post-restore verification

## Purpose

- Back up `messenger.db` and `uploads/` together before risky changes or release work.
- Verify both database integrity and the presence of required application tables after a restore.
- Confirm that current room-security and upload-cleanup behaviors still work after recovery.

## Backup

```bash
python scripts/backup_local.py --label before_release
```

Useful options:

- `--output-root backup/manual`
- `--db-path <sqlite_path>`
- `--uploads-dir <uploads_path>`
- `--label <custom_label>`

Expected output:

- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/db/messenger.db`
- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/uploads/...`
- `backup/manual/backup_<UTC_TIMESTAMP>_<label>/manifest.json`

## Restore

Preview:

```bash
python scripts/restore_local.py backup/manual/backup_20260225T120000Z_before_release
```

Apply:

```bash
python scripts/restore_local.py backup/manual/backup_20260225T120000Z_before_release --yes
```

Restore behavior:

- The current database and uploads directory are snapshotted as `pre_restore_snapshot_<UTC_TIMESTAMP>`.
- The selected backup content is copied back into the configured runtime paths.

## Database Verification

```bash
python scripts/verify_restore.py
```

Verify at least:

- SQLite `integrity_check == ok`
- Required tables exist:
  - `users`
  - `rooms`
  - `room_members`
  - `room_keys`
  - `messages`
  - `polls`
  - `poll_options`
  - `poll_votes`
  - `room_files`
  - `sso_identities`
  - `upload_scan_jobs`
  - `admin_audit_logs`

## Post-Restore Smoke Checks

### Runtime startup

```bash
python server.py --cli
```

### Python regression checks

```bash
pytest tests -q
pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q
```

### Frontend regression checks

```bash
npm install
npm run check:js
```

### Manual contract checks

- Confirm `GET /api/rooms/<room_id>/messages` still returns `encryption_key`, `encryption_keys`, `key_version`, and `member_key_version`.
- Confirm an invited user cannot read pre-invite messages.
- Confirm deleting a pinned file emits both `message_deleted` and `pin_updated`.
- Confirm expired orphan upload files can still be cleaned without touching referenced uploads.

## Recovery Notes

1. If backup creation fails, verify disk space, database path, uploads path, and filesystem permissions.
2. If restore fails, stop the running server first and verify locks or permission issues on the target paths.
3. If database verification fails:
   - roll back to the latest `pre_restore_snapshot_*`
   - inspect whether the chosen backup is incomplete or stale
4. If room history visibility or upload cleanup behaves differently after restore, compare the restored schema against the current application baseline before accepting the restore.
