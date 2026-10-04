# -*- coding: utf-8 -*-
"""
사용자 삭제 및 데이터 정리 테스트
"""
import pytest
import os
import tempfile


def test_user_deletion_cleanup(client, app):
    """사용자 삭제 시 관련 데이터 정리 테스트"""
    # 사용자 등록
    response = client.post('/api/register', json={
        'username': 'delete_test_user',
        'password': 'password123',
        'nickname': 'Delete Tester'
    })
    assert response.status_code == 200
    
    # 로그인
    client.post('/api/login', json={
        'username': 'delete_test_user',
        'password': 'password123'
    })
    
    # 계정 삭제
    response = client.delete('/api/me', json={
        'password': 'password123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    
    # 삭제 후 로그인 실패 확인
    response = client.post('/api/login', json={
        'username': 'delete_test_user',
        'password': 'password123'
    })
    assert response.status_code == 401


def test_user_deletion_wrong_password(client):
    """잘못된 비밀번호로 삭제 시도"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'nodelete_user',
        'password': 'password123',
        'nickname': 'No Delete'
    })
    client.post('/api/login', json={
        'username': 'nodelete_user',
        'password': 'password123'
    })
    
    # 잘못된 비밀번호로 삭제 시도
    response = client.delete('/api/me', json={
        'password': 'wrongpassword'
    })
    assert response.status_code == 400
    assert '비밀번호' in response.json.get('error', '')


def test_change_password(client):
    """비밀번호 변경 테스트"""
    # 사용자 등록 및 로그인
    client.post('/api/register', json={
        'username': 'pwchange_user',
        'password': 'oldpassword123',
        'nickname': 'PW Changer'
    })
    client.post('/api/login', json={
        'username': 'pwchange_user',
        'password': 'oldpassword123'
    })
    
    # 비밀번호 변경
    response = client.put('/api/me/password', json={
        'current_password': 'oldpassword123',
        'new_password': 'newpassword123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True
    
    # 로그아웃 후 새 비밀번호로 로그인
    client.post('/api/logout')
    response = client.post('/api/login', json={
        'username': 'pwchange_user',
        'password': 'newpassword123'
    })
    assert response.status_code == 200
    assert response.json['success'] is True


def test_user_deletion_clears_file_message_references(client, app):
    """ISSUE-002: 탈퇴자의 파일 바이트 삭제 시 메시지 참조도 함께 정리된다."""
    import os

    from app.models import create_message, create_room, delete_user, get_db
    from app.services.runtime_paths import get_upload_folder

    client.post('/api/register', json={
        'username': 'file_owner',
        'password': 'password123',
        'nickname': 'File Owner'
    })
    client.post('/api/register', json={
        'username': 'file_viewer',
        'password': 'password123',
        'nickname': 'File Viewer'
    })
    client.post('/api/login', json={
        'username': 'file_owner',
        'password': 'password123'
    })
    me = client.get('/api/me').json['user']
    owner_id = me['id']
    viewer_id = next(u['id'] for u in client.get('/api/users').json if u['username'] == 'file_viewer')

    room_id = create_room('file-room', 'group', owner_id, [owner_id, viewer_id])
    assert room_id

    upload_folder = get_upload_folder()
    stored_name = 'owner_attachment.bin'
    disk_path = os.path.join(upload_folder, stored_name)
    with open(disk_path, 'wb') as fh:
        fh.write(b'attachment-bytes')
    msg = create_message(room_id, owner_id, 'shared file', 'file',
                         file_path=stored_name, file_name=stored_name)
    assert msg and msg['id']

    success, error = delete_user(owner_id, 'password123')
    assert success, error

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT file_path, file_name FROM messages WHERE sender_id = ?", (owner_id,))
    for row in cur.fetchall():
        assert row['file_path'] is None
        assert row['file_name'] is None
    cur.execute("SELECT COUNT(*) AS cnt FROM room_files WHERE uploaded_by = ?", (owner_id,))
    assert cur.fetchone()['cnt'] == 0
    assert not os.path.exists(disk_path)


def test_messages_sender_fk_migration_on_legacy_db(tmp_path, monkeypatch):
    """구 스키마(DB)에서도 마이그레이션 후 탈퇴자 메시지가 보존된다."""
    import sqlite3

    import app.models.base as base_module

    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "username TEXT UNIQUE NOT NULL, "
        "password_hash TEXT NOT NULL, "
        "nickname TEXT)"
    )
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT,
            encrypted INTEGER DEFAULT 1,
            message_type TEXT DEFAULT 'text',
            file_path TEXT,
            file_name TEXT,
            reply_to INTEGER,
            key_version INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id))"""
    )
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "INSERT INTO users (username, password_hash, nickname) VALUES ('legacy_user', 'x', 'Legacy')"
    )
    conn.execute("INSERT INTO messages (room_id, sender_id, content) VALUES (1, 1, 'hello')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM users WHERE id = 1")
    conn.rollback()
    conn.close()

    monkeypatch.setattr(base_module, "DATABASE_PATH", db_path)
    assert base_module._migrate_messages_sender_fk() is True
    assert base_module._migrate_messages_sender_fk() is False

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DELETE FROM users WHERE id = 1")
    conn.commit()
    row = conn.execute("SELECT content FROM messages WHERE sender_id = 1").fetchone()
    assert row and row[0] == "hello"
    conn.close()


def test_oidc_linked_account_delete_flow(client):
    """OIDC 연동 계정은 oidc_confirm 확인 절차로 탈퇴할 수 있다."""
    from app.models import get_user_by_id
    from app.models.users import get_or_create_oidc_user, get_user_sso_providers

    user = get_or_create_oidc_user(
        provider="test-idp",
        subject="sub-oidc-delete-1",
        email="oidc-delete@example.com",
        nickname="Oidc Deleter",
    )
    assert user and user["id"]
    user_id = user["id"]
    assert get_user_sso_providers(user_id) == ["test-idp"]

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["session_token"] = user["session_token"]

    # 비밀번호 없이 확인 절차도 없으면 거부된다.
    denied = client.delete('/api/me', json={})
    assert denied.status_code == 400

    # 명시적 확인 절차로 탈퇴 성공한다.
    response = client.delete('/api/me', json={"oidc_confirm": True})
    assert response.status_code == 200
    assert response.json['success'] is True
    assert get_user_by_id(user_id) is None


def test_local_account_cannot_delete_with_oidc_confirm_only(client):
    """일반 계정은 oidc_confirm만으로 탈퇴할 수 없다."""
    client.post('/api/register', json={
        'username': 'local_confirm_user',
        'password': 'password123',
        'nickname': 'Local'
    })
    client.post('/api/login', json={
        'username': 'local_confirm_user',
        'password': 'password123'
    })

    response = client.delete('/api/me', json={"oidc_confirm": True})
    assert response.status_code == 400
