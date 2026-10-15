# Mutation evidence (2026-10-15, one mutant at a time, reverted after each)

Working tree after the campaign is clean (`git status` shows only the new
test/docs/CI files). Each mutant below was applied, the cited test run RED,
then reverted and the same test run GREEN.

| Mutant | Temporary fault | Killing test(s) | Result |
|---|---|---|---|
| M1 | `_VISIBLE_FOR_MEMBER_WHERE = "1 = 1"` (`app/models/messages.py`) — version check skipped | `test_auth01_invitee_sees_zero_preinvite_messages` (search oracle leaks M1: `[1] == []`) | KILLED (new test; note: `can_user_see_message` uses its own inline SQL and stayed green — layered coverage matters) |
| M2 | `is_room_member` always `True` (`app/models/rooms.py`) — non-member endpoints open | `test_auth07_10_outsider_and_crossroom_isolation` (200 vs 403), `test_msg01_…` (no error event) | KILLED (new tests, HTTP + socket) |
| M3 | `add_failed` branch commits instead of `rollback` (`invite_members_with_key_rotation`) | `test_invite_rotate_rolls_back_when_member_insert_fails` (version 2 vs 1) | KILLED (existing test) |
| M4 | `consume_upload_token` uses `get_json` (no delete) — token reusable | `test_auth08_…`, `test_issue_and_consume_upload_token_once`, `test_upload_token_single_use_under_thread_race` (4/4 consumed) | KILLED (new + existing) |
| M6 | `delete_user` skips `safe_file_delete(full_path)` — metadata cleaned, bytes kept | `test_auth06_…`, `test_user_deletion_clears_file_message_references` (file still on disk) | KILLED (new + existing) |
| M7 | `_checkpoint_and_clear_wal` returns `True` immediately — WAL cleanup skipped | `test_restore_clears_wal_and_separates_snapshot` (`-wal` residue) | KILLED (existing test; the new `test_msg06` did NOT catch it — its scenario had no residual WAL, an honest coverage gap) |
| M8 | uploads `copytree` failure swallowed (`pass`) — false `[OK] Restore completed` | `test_msg07_…` (`DID NOT RAISE OSError`) | KILLED (new test) |
| M10 | socket `send_message` membership gate replaced with `if False` — relay without sender check | `test_msg01_…` (no error event for intruder) | KILLED (new test) |

Killed: 8. Survived: 0. Not run (out of scope for this harness, not counted):
M5 (stale-socket-session expiry needs a live multi-process server),
M9 (fail-open on Redis outage — the codebase has no Redis broker path;
`MESSAGE_QUEUE=None`), live OIDC/ClamAV/Windows-EXE (no infra; BLOCKED).
