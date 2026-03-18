def test_critical_routes_registered(app):
    expected = {
        ("/", "GET"),
        ("/api/me", "GET"),
        ("/api/login", "POST"),
        ("/api/logout", "POST"),
        ("/api/rooms", "GET"),
        ("/api/rooms", "POST"),
        ("/api/rooms/<int:room_id>/messages", "GET"),
        ("/api/upload", "POST"),
        ("/api/profile", "GET"),
        ("/api/profile", "PUT"),
        ("/api/search/advanced", "POST"),
    }

    rules = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    missing = expected - rules
    assert not missing, f"missing routes: {sorted(missing)}"
