import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stcs-test-")
os.environ["STCS_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STCS_SEED"] = "1"
os.environ["STCS_FRONTEND_DIST"] = os.path.join(_tmp, "no-dist")
os.environ["STCS_NO_DOTENV"] = "1"
