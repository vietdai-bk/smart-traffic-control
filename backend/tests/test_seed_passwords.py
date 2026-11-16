"""Ngoài chế độ demo, tài khoản khởi tạo không dùng mật khẩu mẫu công khai."""
import dataclasses
import os
import stat

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password, verify_password
from app.db.session import Base
from app.models.user import User
from app.services import seed


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("STCS_INITIAL_CREDENTIALS_FILE", str(tmp_path / "creds.txt"))
    eng = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


def _demo(monkeypatch, on):
    monkeypatch.setattr(seed, "settings", dataclasses.replace(seed.settings, demo_mode=on))


def test_non_demo_generates_random_passwords(db, tmp_path, monkeypatch):
    _demo(monkeypatch, False)
    seed.ensure_default_users(db)
    path = tmp_path / "creds.txt"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    creds = dict(line.split("\t") for line in path.read_text().splitlines() if not line.startswith("#"))
    assert set(creds) == {u[0] for u in seed.USERS}
    for username, demo_pw, *_ in seed.USERS:
        u = db.query(User).filter_by(username=username).one()
        assert not verify_password(demo_pw, u.password_hash)
        assert verify_password(creds[username], u.password_hash)
    assert seed.warn_demo_passwords(db) == []


def test_demo_mode_keeps_sample_passwords(db, tmp_path, monkeypatch):
    _demo(monkeypatch, True)
    seed.ensure_default_users(db)
    admin = db.query(User).filter_by(username="admin").one()
    assert verify_password("admin123", admin.password_hash)
    assert not (tmp_path / "creds.txt").exists()


def test_warns_about_leftover_demo_passwords(db, monkeypatch):
    _demo(monkeypatch, False)
    db.add(User(username="admin", full_name="A", role="ADMIN", password_hash=hash_password("admin123")))
    db.commit()
    assert seed.warn_demo_passwords(db) == ["admin"]
