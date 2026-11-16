"""Cấu hình tập trung (NFR10). Đọc từ biến môi trường, có giá trị mặc định an toàn cho môi trường demo."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Nạp backend/.env (KEY=VALUE) nếu có; biến môi trường đã đặt sẵn được ưu tiên."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


if "PYTEST_CURRENT_TEST" not in os.environ and not os.environ.get("STCS_NO_DOTENV"):
    _load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


_log = logging.getLogger("stcs.config")

# Các giá trị mẫu từng nằm công khai trong repo — coi như không có secret
_KNOWN_WEAK_SECRETS = frozenset({
    "stcs-dev-secret-change-me-in-production",
    "change-this-secret-in-production",
    "doi-chuoi-bi-mat-nay-truoc-khi-trien-khai",
    "changeme", "secret",
})
MIN_JWT_SECRET_LEN = 32


def _is_weak_secret(value: str) -> bool:
    return len(value) < MIN_JWT_SECRET_LEN or value.lower() in _KNOWN_WEAK_SECRETS


def _resolve_jwt_secret() -> str:
    """Lấy JWT secret an toàn.

    - STCS_JWT_SECRET đặt và đủ mạnh → dùng.
    - STCS_JWT_SECRET đặt nhưng yếu (giá trị mẫu / < 32 ký tự) → từ chối khởi động.
    - Không đặt → sinh ngẫu nhiên một lần và lưu vào STCS_JWT_SECRET_FILE (mặc định backend/data/.jwt_secret,
      quyền 600) để phiên đăng nhập vẫn hợp lệ sau khi khởi động lại.
    """
    value = os.environ.get("STCS_JWT_SECRET", "").strip()
    if value:
        if _is_weak_secret(value):
            raise RuntimeError(
                "STCS_JWT_SECRET quá yếu hoặc là giá trị mẫu công khai. Dùng chuỗi ngẫu nhiên >= "
                f"{MIN_JWT_SECRET_LEN} ký tự, ví dụ: python -c \"import secrets;print(secrets.token_urlsafe(48))\" "
                "— hoặc bỏ trống để hệ thống tự sinh."
            )
        return value

    path = Path(_env("STCS_JWT_SECRET_FILE", str(BASE_DIR / "data" / ".jwt_secret")))
    try:
        stored = path.read_text(encoding="utf-8").strip()
        if not _is_weak_secret(stored):
            return stored
    except FileNotFoundError:
        pass
    generated = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(generated)
    _log.warning("STCS_JWT_SECRET chưa được đặt — đã sinh secret ngẫu nhiên và lưu tại %s", path)
    return generated


@dataclass(frozen=True)
class Settings:
    app_name: str = "STCS — Smart Traffic Control System"
    version: str = "1.0.0"
    database_url: str = field(
        default_factory=lambda: _env("STCS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'stcs.db'}")
    )
    jwt_secret: str = field(default_factory=_resolve_jwt_secret, repr=False)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = field(default_factory=lambda: int(_env("STCS_JWT_EXPIRE_MINUTES", "480")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("STCS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        )
    )
    # Brute-force protection (NFR08)
    max_failed_logins: int = 5
    lockout_minutes: int = 5

    # Runtime loop
    tick_hz: float = 10.0
    snapshot_hz: float = 4.0
    frame_hz: float = 10.0
    stats_bucket_minutes: int = 5

    # Heartbeat (NFR04)
    camera_timeout_s: float = 3.0
    controller_timeout_s: float = 3.0
    reconnect_base_s: float = 2.0
    reconnect_max_s: float = 15.0

    # Safety hard limits (NFR06) — cấu hình nút giao không thể thấp hơn các giá trị này
    hard_min_green_s: int = 5
    hard_min_yellow_s: int = 3
    hard_min_all_red_s: int = 2

    # LLM Supervisor & trợ lý vận hành — Groq (OpenAI-compatible API)
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY", ""))
    groq_base_url: str = field(default_factory=lambda: _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    llm_model: str = field(default_factory=lambda: _env("STCS_LLM_MODEL", "openai/gpt-oss-120b"))
    llm_fast_model: str = field(default_factory=lambda: _env("STCS_LLM_FAST_MODEL", "openai/gpt-oss-20b"))
    llm_mode: str = field(default_factory=lambda: _env("STCS_LLM_MODE", "ADVISORY"))  # OFF | ADVISORY | AUTONOMOUS
    llm_interval_s: float = field(default_factory=lambda: float(_env("STCS_LLM_INTERVAL_S", "60")))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("STCS_LLM_TIMEOUT_S", "8")))
    # TẠM THỜI để kiểm thử: 1 = không giới hạn độ dài trả lời của LLM (bỏ max_tokens & cắt chuỗi)
    llm_unlimited: bool = field(default_factory=lambda: _env("STCS_LLM_UNLIMITED", "0") == "1")
    # Trợ lý: 1 = trả lời cả câu hỏi ngoài lề (kiến thức chung, lập trình…); 0 = chỉ chủ đề giao thông/STCS
    assistant_open_topic: bool = field(default_factory=lambda: _env("STCS_ASSISTANT_OPEN_TOPIC", "0") == "1")
    llm_min_gap_s: float = 20.0          # không gọi LLM dày hơn mức này kể cả khi có sự kiện
    llm_pending_ttl_s: float = 120.0     # đề xuất chế độ Tư vấn hết hạn nếu không được duyệt

    seed_on_startup: bool = field(default_factory=lambda: _env("STCS_SEED", "1") == "1")
    reset_db: bool = field(default_factory=lambda: _env("STCS_RESET_DB", "0") == "1")
    frontend_dist: Path = field(default_factory=lambda: Path(_env("STCS_FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))))


settings = Settings()
