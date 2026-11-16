"""Công cụ giả lập tình huống (NFR14): lưu lượng đột biến, kịch bản, sự cố camera / bộ điều khiển / thuật toán."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.concurrency import with_runtime_lock
from app.core.deps import CurrentUser, client_ip, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.services.manager import manager
from app.vision_engine.simulator import SCENARIOS

router = APIRouter(prefix="/simulation", tags=["Simulation"])
DIR_VI = {"NORTH": "Bắc", "SOUTH": "Nam", "EAST": "Đông", "WEST": "Tây"}
DirT = Literal["NORTH", "SOUTH", "EAST", "WEST"]


class SurgeRequest(BaseModel):
    directions: list[DirT] = Field(min_length=1)
    multiplier: float = Field(ge=1.0, le=5.0)
    duration_s: int | None = Field(default=180, ge=10, le=3600)


class ScenarioRequest(BaseModel):
    scenario: Literal["NORMAL", "RUSH_HOUR", "NIGHT", "EVENT"]


class CameraFaultRequest(BaseModel):
    direction: DirT
    action: Literal["DISCONNECT", "DEGRADE", "RESTORE"]


class FaultRequest(BaseModel):
    action: Literal["FAULT", "RESTORE"]


def _rt(iid: int):
    rt = manager.get(iid)
    if rt is None:
        raise HTTPException(404, "Nút giao không tồn tại hoặc đang tắt")
    return rt


def _log(db, cur, request, rt, action, desc, details=None):
    audit(db, "SYSTEM", action, f"[GIẢ LẬP] {rt.cfg.name}: {desc}", username=cur.username, role=cur.role,
          target=rt.cfg.code, ip=client_ip(request), details=details or {}, intersection_id=rt.id)


@router.get("/scenarios")
def scenarios(_: CurrentUser = Depends(require(Perm.LIVE_VIEW))):
    return [{"id": k, "label": v[0], "factor": v[1]} for k, v in SCENARIOS.items()]


@router.post("/{iid}/surge")
@with_runtime_lock
def surge(iid: int, body: SurgeRequest, request: Request, db: Session = Depends(get_db),
          cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    rt.sim.set_surge(list(body.directions), body.multiplier, body.duration_s)
    dirs = ", ".join(DIR_VI[d] for d in body.directions)
    desc = (f"Tăng lưu lượng ×{body.multiplier:g} hướng {dirs} trong {body.duration_s}s" if body.multiplier > 1
            else f"Huỷ lưu lượng đột biến hướng {dirs}")
    _log(db, cur, request, rt, "SIM_SURGE", desc, body.model_dump())
    return {"ok": True, "message": desc, "sim": rt.sim.state()}


@router.post("/{iid}/scenario")
@with_runtime_lock
def scenario(iid: int, body: ScenarioRequest, request: Request, db: Session = Depends(get_db),
             cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    rt.sim.scenario = body.scenario
    desc = f"Chuyển kịch bản: {SCENARIOS[body.scenario][0]}"
    _log(db, cur, request, rt, "SIM_SCENARIO", desc, body.model_dump())
    return {"ok": True, "message": desc, "sim": rt.sim.state()}


@router.post("/{iid}/camera")
@with_runtime_lock
def camera_fault(iid: int, body: CameraFaultRequest, request: Request, db: Session = Depends(get_db),
                 cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    p = rt.pipelines.get(body.direction)
    if not p or not p.camera:
        raise HTTPException(404, "Hướng này chưa có camera")
    fault = None if body.action == "RESTORE" else body.action
    p.camera.inject_fault(fault)
    if fault is None:
        p.camera.force_reconnect()
    labels = {"DISCONNECT": "Ngắt kết nối", "DEGRADE": "Suy giảm chất lượng", "RESTORE": "Khôi phục kết nối"}
    desc = f"{labels[body.action]} camera {p.camera.info.code} (hướng {DIR_VI[body.direction]})"
    _log(db, cur, request, rt, f"SIM_CAMERA_{body.action}", desc, body.model_dump())
    return {"ok": True, "message": desc}


@router.post("/{iid}/controller")
@with_runtime_lock
def controller_fault(iid: int, body: FaultRequest, request: Request, db: Session = Depends(get_db),
                     cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    rt.adapter.inject_fault("OFFLINE" if body.action == "FAULT" else None)
    desc = "Giả lập mất kết nối bộ điều khiển đèn" if body.action == "FAULT" else "Khôi phục kết nối bộ điều khiển đèn"
    _log(db, cur, request, rt, f"SIM_CONTROLLER_{body.action}", desc)
    return {"ok": True, "message": desc}


@router.post("/{iid}/vision")
@with_runtime_lock
def vision_fault(iid: int, body: FaultRequest, request: Request, db: Session = Depends(get_db),
                 cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    rt.set_vision_fault(body.action == "FAULT")
    desc = "Giả lập lỗi thuật toán phân tích AI" if body.action == "FAULT" else "Khôi phục thuật toán phân tích AI"
    _log(db, cur, request, rt, f"SIM_VISION_{body.action}", desc)
    return {"ok": True, "message": desc}


@router.post("/{iid}/reset")
@with_runtime_lock
def reset(iid: int, request: Request, db: Session = Depends(get_db),
          cur: CurrentUser = Depends(require(Perm.SIM_CONTROL))):
    rt = _rt(iid)
    rt.sim.scenario = "NORMAL"
    rt.sim.surges.clear()
    rt.adapter.inject_fault(None)
    rt.set_vision_fault(False)
    for p in rt.pipelines.values():
        if p.camera and p.camera.fault:
            p.camera.inject_fault(None)
            p.camera.force_reconnect()
    _log(db, cur, request, rt, "SIM_RESET", "Xoá toàn bộ giả lập (kịch bản, đột biến, sự cố thiết bị)")
    return {"ok": True, "message": "Đã xoá toàn bộ giả lập. Nếu đang FAILSAFE, hãy khôi phục thủ công."}
