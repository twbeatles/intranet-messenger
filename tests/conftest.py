import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [v4.5] 테스트 DB 분리 개선
@pytest.fixture
def app():
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    
    # 임시 업로드 폴더
    upload_dir = tempfile.mkdtemp()
    
    # config 모듈의 DATABASE_PATH를 패치
    import config
    original_db_path = config.DATABASE_PATH
    original_upload_folder = config.UPLOAD_FOLDER
    config.DATABASE_PATH = db_path
    config.UPLOAD_FOLDER = upload_dir
    
    # models 모듈 재로드하여 새 DB 경로 적용
    import importlib
    import app.models.base as base_module
    importlib.reload(base_module)
    
    # [v4.11] 스레드 로컬 DB 연결 초기화 - 이전 DB 연결 캐시 제거
    base_module._db_initialized = False
    if hasattr(base_module._db_local, 'connection'):
        try:
            base_module._db_local.connection.close()
        except Exception:
            pass
        base_module._db_local.connection = None
    
    from app import create_app
    flask_app, socketio = create_app()
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False
    })
    
    # 테스트 DB 초기화
    with flask_app.app_context():
        base_module.init_db()
    
    yield flask_app
    
    # 원래 config 복원
    config.DATABASE_PATH = original_db_path
    config.UPLOAD_FOLDER = original_upload_folder
    
    # Cleanup
    os.close(db_fd)
    try:
        os.remove(db_path)
    except Exception:
        pass
    
    # [v4.8] 임시 업로드 폴더 정리
    try:
        shutil.rmtree(upload_dir)
    except Exception:
        pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
