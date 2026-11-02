"""Cấu hình tập trung (NFR10). Đọc từ biến môi trường, có giá trị mặc định an toàn cho môi trường demo."""
from __future__ import annotations

import os
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


@dataclass(frozen=True)
class Settings:
    app_name: str = "STCS — Smart Traffic Control System"
    version: str = "1.0.0"
    database_url: str = field(
        default_factory=lambda: _env("STCS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'stcs.db'}")
    )
    jwt_secret: str = field(default_factory=lambda: _env("STCS_JWT_SECRET", "stcs-dev-secret-change-me-in-production"))
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
    llm_model: str = field(default_factory=lambda: _env("STCS_LLM_MODEL", "llama-3.3-70b-versatile"))
    llm_fast_model: str = field(default_factory=lambda: _env("STCS_LLM_FAST_MODEL", "llama-3.1-8b-instant"))
    llm_mode: str = field(default_factory=lambda: _env("STCS_LLM_MODE", "ADVISORY"))  # OFF | ADVISORY | AUTONOMOUS
    llm_interval_s: float = field(default_factory=lambda: float(_env("STCS_LLM_INTERVAL_S", "60")))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("STCS_LLM_TIMEOUT_S", "8")))
    llm_min_gap_s: float = 20.0          # không gọi LLM dày hơn mức này kể cả khi có sự kiện
    llm_pending_ttl_s: float = 120.0     # đề xuất chế độ Tư vấn hết hạn nếu không được duyệt

    seed_on_startup: bool = field(default_factory=lambda: _env("STCS_SEED", "1") == "1")
    reset_db: bool = field(default_factory=lambda: _env("STCS_RESET_DB", "0") == "1")
    frontend_dist: Path = field(default_factory=lambda: Path(_env("STCS_FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))))


settings = Settings()
