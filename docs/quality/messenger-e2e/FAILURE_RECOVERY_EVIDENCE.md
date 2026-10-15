# Failure and recovery evidence (real runs, 2026-10-15)

## MSG-05 — live WAL backup (`test_msg05_live_wal_backup_integrity`, PASS)
- Enabled `PRAGMA journal_mode=WAL` on the real test DB, inserted a row without
  checkpoint, ran `scripts/backup_local.py --label msg05` against the live
  file + live uploads dir.
- Observed: exit 0, `PRAGMA integrity_check=ok` on the backup, backup message
  count == live count, attachment SHA-256 match, `manifest.json` with
  `db_size_bytes > 0`.

## MSG-06 — backup → mutate → restore round-trip (`test_msg06_…`, PASS)
- Baseline (message count N, attachment SHA) → `backup_local.py` → added 1
  message + 1 file (count N+1) → `close_thread_db()` (see Windows note) →
  `restore_local.py --yes --force`.
- Observed: exit 0, count back to N, extra row absent, `integrity_check=ok`,
  baseline attachment SHA restored, extra file gone, no `-wal`/`-shm` residue,
  exactly one NEW `pre_restore_snapshot_*` sibling dir holding the mutated
  pre-restore DB (extra row present), backup dir unpolluted.
- Windows note: the app's thread-local SQLite handle locks the `-wal` file, so
  restore must run with the connection released — the same precondition as the
  runbook ("stop the server"). First full-suite run caught a stale-snapshot
  counting flake; the test now diffs pre/post snapshot sets.

## MSG-07 — uploads copy failure is never silent (`test_msg07_…`, PASS)
- Injected `OSError("disk-full")` into `shutil.copytree` for the uploads step.
- Observed: `restore.main()` raises (does NOT return 0 or print `[OK]`),
  safety snapshot with `messenger.db.before_restore` still written.
- Known non-atomicity (documented, product unchanged): the DB file is already
  replaced before the uploads copy, so a mid-restore uploads failure leaves
  DB-new/uploads-incomplete — recovery is via the safety snapshot.

## MSG-03/04 — duplicates and interleaving (`test_message_interleaving.py`, PASS)
- Duplicate `send_message` over a real socket client records 2 rows with
  distinct ids: the server is at-least-once; exactly-once must not be claimed
  without an ACK/idempotency key. The test pins this so a future dedup is explicit.
- Phased traffic (concurrent invites + 30 socket sends, confirmed kick, 5 more
  sends): 35/35 rows with unique ids, post-kick visibility 0 for all 5,
  kicked session HTTP 403, no 500s. Within-phase concurrency only; order across
  phases is fixed, so no flaky timing.

## Live loopback findings (2026-10-15, `tests/test_browser_e2e.py`)
- Isolated gevent subprocess on 127.0.0.1 (`tests/live_server.py`, BASE_DIR
  redirect) boots and serves; HTTP + live Socket.IO invite/visibility flow
  passed 2x on a clean channel (M1 hidden / M2 shown to B; B's live send
  persisted and visible to the owner).
- This box intermittently RSTs/hangs loopback (WinError 10054, AdGuard
  content-script injection into Chromium document stream observed). Harness
  answer: stability gate (5 clean round-trips) + single connection-level
  retry; gate trips become BLOCKED skips, never passes. Default suite runs
  these tests as skips; CI sets `RUN_LIVE_E2E=1`.
- Chromium DOM assertions could not go green locally (document `load` never
  fires under the filter); they run in CI without the filter.

## AUTH-06 — owner deletion with remaining member (`test_auth06_…`, PASS)
- Owner + viewer room with a real attachment; `delete_user(owner)`.
- Observed: owner message file refs NULL, `room_files` rows for owner 0, bytes
  deleted, zero dangling `room_files` (every remaining `file_path` exists on
  disk), viewer room list intact, deleted file message hidden from history.
