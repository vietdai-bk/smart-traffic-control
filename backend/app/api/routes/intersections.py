"""US15 — Quản lý nút giao (CRUD, cấu hình đèn chuẩn, ngưỡng, ràng buộc an toàn, health check bộ điều khiển)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require, require_any
from app.core.rbac import Perm
from app.db.session import get_db
from app.models.intersection import Camera, Intersection
from app.schemas.intersection import IntersectionBase, IntersectionCreate, IntersectionOut, IntersectionUpdate
from app.services.manager import manager
from app.vision_engine.geometry import CameraCalibration

router = APIRouter(prefix="/intersections", tags=["Intersections"])
DIR_VI = {"NORTH": "Bắc", "SOUTH": "Nam", "EAST": "Đông", "WEST": "Tây"}


def _get(db: Session, iid: int) -> Intersection:
    it = db.query(Intersection).options(selectinload(Intersection.cameras)).filter(Intersection.id == iid).first()
    if not it:
        raise HTTPException(404, "Không tìm thấy nút giao")
    return it


@router.get("", response_model=list[IntersectionOut])
def list_intersections(db: Session = Depends(get_db),
                       _: CurrentUser = Depends(require_any(Perm.LIVE_VIEW, Perm.STATS_VIEW))):
    return db.query(Intersection).options(selectinload(Intersection.cameras)).order_by(Intersection.id).all()


@router.get("/summary")
def summary(_: CurrentUser = Depends(require_any(Perm.LIVE_VIEW, Perm.STATS_VIEW))):
    return manager.summary()


@router.get("/{iid}", response_model=IntersectionOut)
def get_intersection(iid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.LIVE_VIEW))):
    return _get(db, iid)


@router.post("", response_model=IntersectionOut, status_code=201)
def create_intersection(body: IntersectionCreate, request: Request, db: Session = Depends(get_db),
                        cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    if db.query(Intersection).filter(Intersection.code == body.code).first():
        raise HTTPException(409, f"Mã nút giao '{body.code}' đã tồn tại")
    data = body.model_dump(exclude={"create_default_cameras"})
    it = Intersection(**data)
    db.add(it)
    db.flush()
    if body.create_default_cameras:
        calib = CameraCalibration(lanes=it.lanes_per_approach)
        for d in DIR_VI:
            code = f"CAM-{it.code}-{d[0]}"[:32]
            if db.query(Camera).filter(Camera.code == code).first():
                code = f"CAM-{it.id}-{d[0]}"
            db.add(Camera(code=code, name=f"Camera hướng {DIR_VI[d]}", intersection_id=it.id, direction=d,
                          source_type="SIMULATED", stream_url=f"rtsp://sim.stcs.local/{it.code.lower()}/{d.lower()}",
                          roi=calib.roi_polygon(60.0), counting_line=calib.counting_line()))
    db.commit()
    audit(db, "CONFIG", "CREATE_INTERSECTION", f"Tạo nút giao {it.name} ({it.code})", username=cur.username,
          role=cur.role, target=it.code, ip=client_ip(request), intersection_id=it.id)
    manager.reload(it.id)
    return _get(db, it.id)


@router.patch("/{iid}", response_model=IntersectionOut)
def update_intersection(iid: int, body: IntersectionUpdate, request: Request, db: Session = Depends(get_db),
                        cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    it = _get(db, iid)
    patch = body.model_dump(exclude_unset=True)
    current = IntersectionBase.model_validate(it, from_attributes=True).model_dump()
    merged = {**current, **{k: v for k, v in patch.items() if v is not None or k == "description"}}
    try:
        validated = IntersectionBase.model_validate(merged)
    except ValidationError as exc:
        msg = "; ".join(e["msg"].replace("Value error, ", "") for e in exc.errors())
        raise HTTPException(422, msg) from exc
    if validated.code != it.code and db.query(Intersection).filter(Intersection.code == validated.code).first():
        raise HTTPException(409, f"Mã nút giao '{validated.code}' đã tồn tại")
    changes = {}
    for k, v in validated.model_dump().items():
        if getattr(it, k) != v:
            changes[k] = {"from": getattr(it, k), "to": v}
            setattr(it, k, v)
    db.commit()
    if changes:
        audit(db, "CONFIG", "UPDATE_INTERSECTION",
              f"Cập nhật nút giao {it.name}: {', '.join(changes)}", username=cur.username, role=cur.role,
              target=it.code, ip=client_ip(request), details={k: str(v) for k, v in changes.items()},
              intersection_id=it.id)
        manager.reload(it.id)
    return _get(db, iid)


@router.delete("/{iid}", status_code=204)
def delete_intersection(iid: int, request: Request, db: Session = Depends(get_db),
                        cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    it = _get(db, iid)
    name, code = it.name, it.code
    manager.remove(iid)
    db.delete(it)
    db.commit()
    audit(db, "CONFIG", "DELETE_INTERSECTION", f"Xoá nút giao {name} ({code})", username=cur.username,
          role=cur.role, target=code, ip=client_ip(request))


@router.post("/{iid}/controller/ping")
def ping_controller(iid: int, request: Request, db: Session = Depends(get_db),
                    cur: CurrentUser = Depends(require(Perm.CONFIG_VIEW))):
    rt = manager.get(iid)
    if rt is None:
        raise HTTPException(409, "Nút giao chưa hoạt động (đang tắt)")
    ack = rt.adapter.ping()
    ok = ack.ok
    audit(db, "CONFIG", "PING_CONTROLLER",
          f"Kiểm tra bộ điều khiển {rt.cfg.controller_endpoint}: {'OK %.0f ms' % ack.latency_ms if ok else 'TIMEOUT'}",
          username=cur.username, role=cur.role, target=rt.cfg.controller_endpoint, ip=client_ip(request),
          result="SUCCESS" if ok else "FAILURE", intersection_id=iid)
    return {"ok": ok, "latency_ms": round(ack.latency_ms, 1), "error": ack.error, "endpoint": rt.cfg.controller_endpoint,
            "model": rt.cfg.controller_model, "signal_state": rt.fsm.state}
