import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stcs-test-")
os.environ["STCS_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STCS_SEED"] = "1"
os.environ["STCS_FRONTEND_DIST"] = os.path.join(_tmp, "no-dist")
os.environ["STCS_NO_DOTENV"] = "1"
os.environ["STCS_JWT_SECRET_FILE"] = os.path.join(_tmp, ".jwt_secret")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_login_guard():
    """Mọi request trong TestClient dùng chung một IP — xoá bộ đếm sai giữa các test."""
    from app.core.login_guard import login_guard

    login_guard.reset()
    yield
