"""US14 — Đánh giá hiệu quả điều khiển: Trước (FIXED_TIME) và Sau (AI Adaptive)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.services import evaluation
from app.services.manager import manager

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.get("/summary")
def summary(intersection_id: int | None = None, days: int = Query(7, ge=1, le=60),
            tz_offset_min: int = Query(420, ge=-720, le=840), db: Session = Depends(get_db),
            _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    return evaluation.summary(db, intersection_id, days, tz_offset_min)


@router.get("/hourly")
def hourly(intersection_id: int | None = None, days: int = Query(7, ge=1, le=60),
           tz_offset_min: int = Query(420, ge=-720, le=840), db: Session = Depends(get_db),
           _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    return evaluation.hourly(db, intersection_id, days, tz_offset_min)


@router.get("/live")
def live(_: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    out = []
    for rt in manager.runtimes.values():
        snap = rt.snapshot_message()
        out.append({"intersection_id": rt.id, "name": rt.cfg.name, "mode": snap["signal"]["mode"],
                    "kpi": snap["kpi"], "plan": snap["plan"], "detection": snap["detection"]})
    return out
