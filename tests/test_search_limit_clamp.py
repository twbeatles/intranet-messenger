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
