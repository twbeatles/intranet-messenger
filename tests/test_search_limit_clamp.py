# -*- coding: utf-8 -*-

from unittest.mock import patch


def test_search_limit_and_offset_are_clamped(client):
    client.post("/api/register", json={"username": "searchclamp", "password": "Password123!", "nickname": "Search"})
    client.post("/api/login", json={"username": "searchclamp", "password": "Password123!"})

    with patch("app.routes.advanced_search", return_value={"messages": []}) as mocked:
        resp = client.get("/api/search?q=hello&limit=9999&offset=-25")
        assert resp.status_code == 200
        assert resp.json == []
        assert mocked.called
        kwargs = mocked.call_args.kwargs
        assert kwargs["limit"] == 200
        assert kwargs["offset"] == 0


def test_search_messages_fallback_escapes_like_wildcards(client, app):
    """ISSUE-006: FTS 미사용 fallback에서 %/_/\\는 리터럴로 매칭된다."""
    from app.models import create_room, get_db, search_messages

    client.post("/api/register", json={"username": "likesc", "password": "Password123!", "nickname": "Like"})
    client.post("/api/login", json={"username": "likesc", "password": "Password123!"})
    user_id = client.get("/api/me").json["user"]["id"]

    room_id = create_room("like-room", "group", user_id, [user_id])

    from app.models.messages import create_message
    create_message(room_id, user_id, "100% coverage", "text", encrypted=False)
    create_message(room_id, user_id, "100X coverage", "text", encrypted=False)
    create_message(room_id, user_id, "under_score test", "text", encrypted=False)
    create_message(room_id, user_id, "underscoreXtest", "text", encrypted=False)

    # FTS를 제거해 LIKE fallback 경로를 강제한다.
    conn = get_db()
    conn.execute("DROP TABLE IF EXISTS messages_fts")
    conn.commit()

    percent = search_messages(user_id, "100%")
    assert {m["content"] for m in percent["messages"]} == {"100% coverage"}

    underscore = search_messages(user_id, "under_score")
    assert {m["content"] for m in underscore["messages"]} == {"under_score test"}
