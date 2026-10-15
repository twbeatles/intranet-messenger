# Test verification report — CORE VERIFIED + BLOCKED (2026-10-15)

Verdict: **CORE VERIFIED + BLOCKED**. Real-server permission, message/file
integrity and SQLite recovery paths pass with independent oracles and 8 killed
mutants. Unverified infra (Redis/OIDC/ClamAV/real browser/Windows EXE) is
listed as BLOCKED, not passed.

## Results by harness
- Flask `test_client` + `socketio.test_client` + real isolated SQLite/uploads:
  154 passed, 2 skipped (opt-in live), 0 failed (141 pre-existing + 13 new).
  `test_e2e_smoke.py` is empty → NOT RUN.
- New: `tests/test_room_auth_boundaries.py` (7: AUTH-01/02/04/05/07/08/10, MSG-01),
  `tests/test_recovery_integrity.py` (4: MSG-05/06/07, AUTH-06),
  `tests/test_message_interleaving.py` (2: MSG-03/04),
  `tests/test_browser_e2e.py` (2 live: HTTP+socket oracle, Chromium DOM oracle).
- Mutation: 8 killed / 0 survived (see MUTATION_EVIDENCE.md); M5/M9 + live
  OIDC/ClamAV not run (BLOCKED).
- Gates: `npm run check:js` PASS, pyright 0 errors, PyInstaller build OK
  (windowed EXE launches only interactively — VM run stays BLOCKED).
- `SKIP` contributes nothing: the 2 skips are opt-in live tests, uncounted.

## Unauthorized-exposure summary
A/B/C separate sessions verified: pre-invite history 0, post-kick reads 403,
outsider file/search/reaction 403 + empty search, cross-room 403, socket
intrusion → `error` + 0 DB rows, single-use token replay rejected, deleted
owner bytes gone with 0 dangling links. No unauthorized exposure observed.

## Deltas vs the plan worth knowing
- `/api/users` excludes the caller and `/api/me` returns 200 + `logged_in:false`
  after logout (tests assert the real behavior, not 401/inclusion).
- Socket sends from non-members fail; the DB delta assertion counts only rows.
- Restore on Windows requires the app DB handle released (runbook: stop server).
- M7 is caught by the pre-existing WAL unit test, not the new round-trip test.
- Restore is not atomic across DB+uploads on mid-copy failure (snapshot is the
  recovery path) — documented in FAILURE_RECOVERY_EVIDENCE.md.

## Follow-ups needing approval/infra
Real Redis broker, OIDC IdP, ClamAV service, Playwright browser pass,
Windows VM EXE validation, and multi-worker/gevent stress (MSG-10/11/12,
Phase 3 GUI) remain BLOCKED.
