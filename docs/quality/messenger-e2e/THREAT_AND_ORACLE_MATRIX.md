# Threat and oracle matrix (A/B/C timeline vs enforcement points)

Independent oracle rule: expected visibility is stated in the test fixture
(A invites B at version N, B kicked before M3, …) and cross-checked against
HTTP responses, Socket.IO events and raw DB rows. Production helpers
(`can_user_see_message`, role checkers) are used only as the *observed* side,
never to compute the expectation — except where the helper itself is the unit
under test (AUTH-08 token binding).

| ID | Scenario (A/B/C sessions) | Enforcement point | Independent expectation |
|---|---|---|---|
| AUTH-01 | A creates room, sends M1, then invites B | `get_room_messages` key-version filter (`app/models/messages.py`), `search_messages` FTS/LIKE filter, `GET /api/rooms/<id>/messages` 403 for non-members | B: pre-invite M1 = 0 rows everywhere; post-invite M2 visible |
| AUTH-02 | B kicked, then A sends M3 + file F3 | `DELETE room_members` (`kick_member`), `is_room_member` 403 gates in `app/http/messages.py` + `app/http/uploads.py`, `can_user_see_message` JOIN | B: history/files/direct `/uploads/<file>` all 403; `can_see` false |
| AUTH-04 | Invite of nonexistent user id | `invite_member` route pre-filter + `invite_members_with_key_rotation` rollback (`app/models/rooms.py`) | HTTP 400, `key_version` unchanged, member count unchanged |
| AUTH-05 | Logout, then reuse session | `session.clear()` (`app/http/auth.py`), `require_login` 401 | `/api/me` → `logged_in:false`; messages → 401 |
| AUTH-06 | Owner deletes account, viewer stays | `delete_user` file-byte + `room_files` + message-reference cleanup (`app/models/users.py`) | owner file rows 0, bytes gone, dangling 0, viewer room kept, file msg hidden |
| AUTH-07 | Outsider pokes file/search/pins/reactions | `is_room_member` + `can_user_see_message` gates on messages/reactions/files/download routes | 403 on all direct URLs; search returns `[]` |
| AUTH-08 | Token replay / wrong user/room/type | `get_upload_token_failure_reason` + single `getdel_json` consume (`app/upload_tokens.py`) | mismatches rejected; exactly 1 consume succeeds |
| AUTH-10 | room1 auth reused for room2 | per-room `room_members` JOIN in every query | room1 member gets 403 on room2 resources and vice versa |
| MSG-01 | 3 socket clients, outsider intrudes | `handle_send_message` membership gate (`app/socket_events/messages.py`) | member gets `new_message`; outsider gets `error`; DB row delta 0 |
| MSG-03 | duplicate socket send | no server dedup (`create_message` per accepted send) | 2 rows, distinct ids; clients must dedupe (characterization, not exactly-once) |
| MSG-04 | phased concurrent invites + sends + confirmed kick | rotation + membership gates, end-state invariants | unique ids, full count persisted, post-kick visibility 0, no 500s |
| MSG-05/06/07 | WAL backup / restore / copy failure | `backup_sqlite` backup API (`scripts/backup_local.py`), `_checkpoint_and_clear_wal` + sibling snapshot + running-server refuse (`scripts/restore_local.py`) | `integrity_check=ok`, counts/SHA match, no `-wal`/`-shm`, failure never returns 0 |

Key-version mechanics relied upon: `create_room` seeds version 1; every invite
rotates (`invite_members_with_key_rotation`, invitee `joined_key_version` =
new version); leave/kick also rotate for remaining members
(`_rotate_and_emit_room_security` in `app/http/rooms.py`); message rows stamp
the current `key_version`; history/search list only
`m.key_version >= member.joined_key_version`.
