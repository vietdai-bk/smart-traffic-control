"""STCS FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import models as _orm_models  # noqa: F401 — đăng ký ORM models
from app.api.router import api_router
from app.api.ws import router as ws_router
from app.core.audit import audit
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.services.alert_service import cleanup_stale_on_startup
from app.llm.supervisor import supervisor
from app.services.manager import manager
from app.services.seed import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("stcs")


def _migrate(eng) -> None:
    """Bổ sung cột mới cho CSDL tạo từ phiên bản cũ (create_all không ALTER bảng đã có)."""
    from sqlalchemy import inspect, text

    cols = {c["name"] for c in inspect(eng).get_columns("users")}
    if "token_version" not in cols:
        with eng.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
        log.info("Đã thêm cột users.token_version")


def init_db() -> None:
    if settings.reset_db:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _migrate(engine)
    if settings.seed_on_startup:
        with SessionLocal() as db:
            seed_if_empty(db)
    cleanup_stale_on_startup()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    await manager.start()
    await supervisor.start()
    audit(None, "SYSTEM", "STARTUP", f"Khởi động {settings.app_name} v{settings.version} "
                                     f"({len(manager.runtimes)} nút giao)")
    try:
        yield
    finally:
        await supervisor.stop()
        await manager.stop()
        audit(None, "SYSTEM", "SHUTDOWN", "Dừng hệ thống")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Phần mềm điều khiển giao thông tích hợp camera — REST API + WebSocket",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(ws_router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):  # pragma: no cover
    log.exception("Lỗi không xử lý: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Lỗi hệ thống nội bộ"})


# Phục vụ frontend đã build (production / docker) nếu có
_dist = settings.frontend_dist
if _dist.exists() and (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith(("api/", "ws/")):
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy"})
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")