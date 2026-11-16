"""Thu hồi JWT: đăng xuất, đổi/đặt lại mật khẩu, đổi vai trò, khoá tài khoản."""
import itertools

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.main import _migrate, app

_n = itertools.count(1)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _new_user(client, admin):
    """Tạo tài khoản riêng cho mỗi test để không thu hồi token của test khác."""
    name = f"revoke{next(_n)}"
    r = client.post("/api/users", headers=admin, json={"username": name, "full_name": "Thu hoi",
                                                       "role": "OPERATOR", "password": "pass123456"})
    assert r.status_code == 201, r.text
    return r.json()["id"], name


def _login(client, name, password="pass123456"):
    r = client.post("/api/auth/login", json={"username": name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _me(client, h):
    return client.get("/api/auth/me", headers=h).status_code


def test_logout_revokes_token(client, admin):
    _, name = _new_user(client, admin)
    h = _login(client, name)
    assert _me(client, h) == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert _me(client, h) == 401
    assert _me(client, _login(client, name)) == 200  # đăng nhập lại vẫn được


def test_change_password_revokes_old_tokens(client, admin):
    _, name = _new_user(client, admin)
    old = _login(client, name)
    other_session = _login(client, name)
    r = client.post("/api/auth/change-password", headers=old,
                    json={"current_password": "pass123456", "new_password": "newpass123456"})
    assert r.status_code == 200, r.text
    assert _me(client, old) == 401 and _me(client, other_session) == 401
    assert _me(client, _login(client, name, "newpass123456")) == 200


@pytest.mark.parametrize("patch", [{"password": "reset123456"}, {"role": "VIEWER"}, {"is_active": False}])
def test_admin_changes_revoke_tokens(client, admin, patch):
    uid, name = _new_user(client, admin)
    h = _login(client, name)
    assert client.patch(f"/api/users/{uid}", headers=admin, json=patch).status_code == 200
    assert _me(client, h) == 401


def test_profile_edit_keeps_tokens(client, admin):
    uid, name = _new_user(client, admin)
    h = _login(client, name)
    assert client.patch(f"/api/users/{uid}", headers=admin, json={"full_name": "Ten moi"}).status_code == 200
    assert _me(client, h) == 200


def test_token_without_version_rejected(client, admin):
    from app.core.security import create_access_token

    _, name = _new_user(client, admin)
    legacy, _ = create_access_token(name, "OPERATOR")  # token kiểu cũ, không có "tv"
    assert _me(client, {"Authorization": f"Bearer {legacy}"}) == 401


def test_migrate_adds_column_to_old_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64))"))
        c.execute(text("INSERT INTO users (id, username) VALUES (1, 'a')"))
    _migrate(eng)
    _migrate(eng)  # chạy lại không lỗi
    assert "token_version" in {c["name"] for c in inspect(eng).get_columns("users")}
    with eng.connect() as c:
        assert c.execute(text("SELECT token_version FROM users")).scalar() == 0
