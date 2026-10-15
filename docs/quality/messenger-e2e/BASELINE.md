# Baseline (2026-10-15)

- HEAD SHA (start/end): `d85f978f07a080ba41918d0b4a8bdcce9a20d6b4` (no product-code changes; only test/docs/CI files added)
- OS/Python/SQLite: Windows / Python 3.15.0 / SQLite 3.53.4
- Pre-existing suite: 141 tests (all passing; `test_e2e_smoke.py` is empty — 0 collected, recorded as NOT RUN, not a pass)
- New tests added: 13 in-process (7 in `tests/test_room_auth_boundaries.py`,
  4 in `tests/test_recovery_integrity.py`, 2 in `tests/test_message_interleaving.py`)
  + 2 opt-in live tests (`tests/test_browser_e2e.py`, `RUN_LIVE_E2E=1`; default: skip)
- Full suite after change: 154 passed, 2 skipped, 0 failed
  (`python -m pytest tests -q -p no:cacheprovider`, ~2 min)
- Gates: `npm run check:js` PASS, `python -m pyright app gui` 0 errors,
  PyInstaller `messenger.spec` build OK (dist, 78 MB v4.36.4 EXE)
- Test isolation: each test gets a fresh SQLite file + uploads dir via `tests/conftest.py`
  (tmp base/upload/quarantine/db, `TESTING=True`, CSRF off); no production DB/uploads touched
- CI status: no `.github` directory existed, so no prior Actions history to compare;
  added `.github/workflows/quality.yml` (unit + P0 network-permission smoke on every PR)
- Environment notes: Redis/OIDC/ClamAV/Windows-EXE infra absent — corresponding scopes are
  BLOCKED (see TEST_VERIFICATION_REPORT.md), not reported as passed
