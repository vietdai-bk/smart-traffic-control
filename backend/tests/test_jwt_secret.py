"""JWT secret: không bao giờ dùng giá trị mặc định công khai."""
import os
import stat

import pytest

from app.core.config import _resolve_jwt_secret


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.delenv("STCS_JWT_SECRET", raising=False)
    monkeypatch.setenv("STCS_JWT_SECRET_FILE", str(tmp_path / "sub" / ".jwt_secret"))
    return tmp_path / "sub" / ".jwt_secret"


def test_generates_and_persists_when_unset(env):
    first = _resolve_jwt_secret()
    assert len(first) >= 32 and env.read_text() == first
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600
    assert _resolve_jwt_secret() == first  # ổn định qua lần khởi động sau


@pytest.mark.parametrize("weak", ["stcs-dev-secret-change-me-in-production",
                                  "change-this-secret-in-production", "short"])
def test_rejects_weak_secret(env, monkeypatch, weak):
    monkeypatch.setenv("STCS_JWT_SECRET", weak)
    with pytest.raises(RuntimeError):
        _resolve_jwt_secret()


def test_uses_strong_env_secret(env, monkeypatch):
    monkeypatch.setenv("STCS_JWT_SECRET", "x" * 40)
    assert _resolve_jwt_secret() == "x" * 40
    assert not env.exists()
