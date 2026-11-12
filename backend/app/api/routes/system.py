from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user
from app.services.manager import manager
from app.vision_engine.detector import yolo_available
from app.vision_engine.stream_manager import opencv_available

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/health")
def health():
    return {"status": "ok", "version": settings.version, **manager.health()}


@router.get("/info")
def info(_: CurrentUser = Depends(get_current_user)):
    return {
        "name": settings.app_name,
        "version": settings.version,
        "tick_hz": settings.tick_hz,
        "snapshot_hz": settings.snapshot_hz,
        "frame_hz": settings.frame_hz,
        "stats_bucket_minutes": settings.stats_bucket_minutes,
        "capabilities": {"opencv": opencv_available(), "yolo": yolo_available()},
        "safety": {
            "hard_min_green_s": settings.hard_min_green_s,
            "hard_min_yellow_s": settings.hard_min_yellow_s,
            "hard_min_all_red_s": settings.hard_min_all_red_s,
        },
        **manager.health(),
    }
