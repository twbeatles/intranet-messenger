# -*- coding: utf-8 -*-
"""Message interleaving and duplicate-send characterization (MSG-03/04).

MSG-04 runs phased concurrent traffic (invites + sends + a confirmed kick)
and asserts end-state invariants that hold under ANY interleaving: unique DB
ids, zero server errors, and zero post-kick visibility for the kicked user.
MSG-03 pins the real duplicate-send behavior so a future dedup change is an
explicit, reviewed decision instead of a silent semantic shift.
"""
from __future__ import annotations

import threading

from app.models import get_db
from app.models.messages import can_user_see_message
from tests.test_feature_risk_review_plan import (
    _create_room,
    _create_socket_client,
    _first_event,
    _login,
    _register,
)


def _user_id(client, username: str) -> int:
    users = client.get("/api/users").json
    return next(u["id"] for u in users if u["username"] == username)


def test_msg04_concurrent_invite_send_kick_keeps_end_state_consistent(app):
    """MSG-04: phased concurrent traffic; unauthorized visibility 0, no 500s."""
    import time

    owner = app.test_client()
    _register(owner, "ilv_owner")
    _register(owner, "ilv_b")
    _register(owner, "ilv_c")
    _login(owner, "ilv_owner")
    member_b = _user_id(owner, "ilv_b")
    member_c = _user_id(owner, "ilv_c")
    room_id = _create_room(owner, name="ilv-room")

    clients = {name: app.test_client() for name in ("s1", "s2")}
    for name, uname in (("s1", "ilv_b"), ("s2", "ilv_c")):
        _login(clients[name], uname)

    invite_done = threading.Event()
    errors: list = []

    def inviter():
        try:
            for uid in (member_b, member_c):
                r = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": uid})
                assert r.status_code in (200, 400), r.status_code
            invite_done.set()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    # Sends go through the real socket handler from two independent sessions.
    sc_owner = _create_socket_client(app, owner)

    def socket_sender(count: int):
        try:
            for i in range(count):
                sc_owner.emit("send_message", {"room_id": room_id,
                                              "content": f"ilv-msg-{i}",
                                              "type": "text", "encrypted": False})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t_inv = threading.Thread(target=inviter)
    t_s1 = threading.Thread(target=socket_sender, args=(15,))
    t_s2 = threading.Thread(target=socket_sender, args=(15,))
    t_inv.start()
    t_s1.start()
    t_s2.start()
    t_inv.join(timeout=60)
    t_s1.join(timeout=60)
    t_s2.join(timeout=60)
    assert not errors

    # Phase 2: kick B only after the invite phase finished (deterministic order
    # across phases, concurrency within each phase).
    assert invite_done.is_set()
    deadline = time.time() + 30
    kicked = False
    while time.time() < deadline:
        r = owner.delete(f"/api/rooms/{room_id}/members/{member_b}")
        if r.status_code == 200:
            kicked = True
            break
        time.sleep(0.05)
    assert kicked

    # Phase 3: messages sent after the confirmed kick.
    post_kick_ids: list[int] = []
    for i in range(5):
        sc_owner.emit("send_message", {"room_id": room_id,
                                      "content": f"ilv-postkick-{i}",
                                      "type": "text", "encrypted": False})
    received = sc_owner.get_received()
    for evt in received:
        if evt.get("name") == "new_message":
            args = evt.get("args") or []
            if args and str(args[0].get("content", "")).startswith("ilv-postkick-"):
                post_kick_ids.append(args[0]["id"])
    sc_owner.disconnect()
    assert len(post_kick_ids) == 5

    # End-state invariants (interleaving-independent).
    cur = get_db().cursor()
    cur.execute("SELECT id FROM messages WHERE room_id = ?", (room_id,))
    ids = [row["id"] for row in cur.fetchall()]
    assert len(ids) == len(set(ids))  # unique DB ids
    assert len(ids) == 30 + 5  # every accepted send persisted exactly once
    for mid in post_kick_ids:
        assert can_user_see_message(room_id, member_b, int(mid)) is False
    kicked_view = clients["s1"].get(f"/api/rooms/{room_id}/messages")
    assert kicked_view.status_code == 403


def test_msg03_duplicate_socket_send_is_recorded_twice(app):
    """MSG-03: duplicate sends are NOT deduplicated (at-least-once).

    Characterization: the server records one row per accepted send. Clients
    must dedupe by message id; do not claim exactly-once without an ACK/idempotency key.
    """
    owner = app.test_client()
    _register(owner, "dup_owner")
    _login(owner, "dup_owner")
    room_id = _create_room(owner, name="dup-room")

    sc = _create_socket_client(app, owner)
    try:
        sc.get_received()
        payload = {"room_id": room_id, "content": "dup-payload", "type": "text",
                   "encrypted": False}
        sc.emit("send_message", payload)
        sc.emit("send_message", payload)
        got = [e for e in sc.get_received() if e.get("name") == "new_message"]
        assert len(got) == 2
        first = _first_event([got[0]], "new_message")
        second = _first_event([got[1]], "new_message")
        assert first and second and first["id"] != second["id"]
    finally:
        sc.disconnect()

    cur = get_db().cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM messages WHERE room_id = ? AND content = ?",
                (room_id, "dup-payload"))
    assert cur.fetchone()["cnt"] == 2
