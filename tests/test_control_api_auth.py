import tempfile

from flask import Flask


def test_control_api_requires_token_and_localhost():
    import config
    from app.control_api import control_bp, get_or_create_control_token

    with tempfile.TemporaryDirectory() as d:
        # Ensure token is created in a temp base dir (do not touch repo root)
        old_base_dir = getattr(config, "BASE_DIR", None)
        config.BASE_DIR = d
        try:
            token = get_or_create_control_token(d)

            app = Flask('control_test')
            app.register_blueprint(control_bp)
            app.config.update(TESTING=True)
            client = app.test_client()

            # No token => 401
            r = client.get('/control/status', environ_base={'REMOTE_ADDR': '127.0.0.1'})
            assert r.status_code == 401

            # Token + localhost => 200
            r = client.get(
                '/control/status',
                headers={'X-Control-Token': token},
                environ_base={'REMOTE_ADDR': '127.0.0.1'},
            )
            assert r.status_code == 200
            assert r.json.get('status') == 'running'

            # Token but non-localhost => 403
            r = client.get(
                '/control/status',
                headers={'X-Control-Token': token},
                environ_base={'REMOTE_ADDR': '10.0.0.10'},
            )
            assert r.status_code == 403
        finally:
            # Restore for other tests
            if old_base_dir is not None:
                config.BASE_DIR = old_base_dir
