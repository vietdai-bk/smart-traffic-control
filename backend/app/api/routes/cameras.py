"""US03/US04/US15 — Camera: CRUD, cấu hình hướng/ROI/ngưỡng, health check, MJPEG cho camera thực."""
from __future__ import annotations

import asyncio
import random

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require, user_from_ticket
from app.core.tickets import stream_purpose
from app.core.rbac import Perm, has_perm
from app.db.session import SessionLocal, get_db
from app.models.intersection import Camera, Intersection
from app.schemas.intersection import CameraBase, CameraCreate, CameraOut, CameraUpdate
from app.services.manager import manager
from app.vision_engine.geometry import CameraCalibration
from app.vision_engine.stream_manager import opencv_available

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get("", response_model=list[CameraOut])
def list_cameras(intersection_id: int | None = None, db: Session = Depends(get_db),
                 _: CurrentUser = Depends(require(Perm.LIVE_VIEW))):
    q = db.query(Camera)
    if intersection_id:
        q = q.filter(Camera.intersection_id == intersection_id)
    return q.order_by(Camera.intersection_id, Camera.id).all()


@router.get("/default-geometry")
def default_geometry(lanes: int = Query(3, ge=1, le=5), roi_length_m: float = Query(60, ge=15, le=150),
                     _: CurrentUser = Depends(require(Perm.CONFIG_VIEW))):
    c = CameraCalibration(lanes=lanes)
    return {"roi": c.roi_polygon(roi_length_m), "counting_line": c.counting_line(), "calibration": c.to_dict()}


@router.get("/capabilities")
def capabilities(_: CurrentUser = Depends(require(Perm.CONFIG_VIEW))):
    from app.vision_engine.detector import yolo_available

    return {"opencv": opencv_available(), "yolo": yolo_available(),
            "sources": ["SIMULATED", "RTSP", "HTTP", "FILE"]}


def _check_intersection(db: Session, iid: int) -> Intersection:
    it = db.get(Intersection, iid)
    if not it:
        raise HTTPException(404, "Nút giao không tồn tại")
    return it


@router.post("", response_model=CameraOut, status_code=201)
def create_camera(body: CameraCreate, request: Request, db: Session = Depends(get_db),
                  cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    it = _check_intersection(db, body.intersection_id)
    if db.query(Camera).filter(Camera.code == body.code).first():
        raise HTTPException(409, f"Mã camera '{body.code}' đã tồn tại")
    if db.query(Camera).filter(Camera.intersection_id == it.id, Camera.direction == body.direction).first():
        raise HTTPException(409, f"Hướng {body.direction} của nút giao này đã có camera")
    data = body.model_dump()
    calib = CameraCalibration(lanes=it.lanes_per_approach)
    if not data["roi"]:
        data["roi"] = calib.roi_polygon(body.roi_length_m)
    if not data["counting_line"]:
        data["counting_line"] = calib.counting_line()
    cam = Camera(**data)
    db.add(cam)
    db.commit()
    db.refresh(cam)
    audit(db, "CONFIG", "CREATE_CAMERA", f"Thêm camera {cam.code} hướng {cam.direction} — {it.name}",
          username=cur.username, role=cur.role, target=cam.code, ip=client_ip(request), intersection_id=it.id)
    manager.reload(it.id)
    return cam


@router.patch("/{cid}", response_model=CameraOut)
def update_camera(cid: int, body: CameraUpdate, request: Request, db: Session = Depends(get_db),
                  cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    cam = db.get(Camera, cid)
    if not cam:
        raise HTTPException(404, "Không tìm thấy camera")
    old_iid = cam.intersection_id
    patch = body.model_dump(exclude_unset=True)
    clear = patch.pop("clear_thresholds", False)
    current = CameraBase.model_validate(cam, from_attributes=True).model_dump()
    merged = {**current, **{k: v for k, v in patch.items() if k != "intersection_id"}}
    if clear:
        merged["density_medium"] = None
        merged["density_high"] = None
    try:
        validated = CameraBase.model_validate(merged)
    except ValidationError as exc:
        msg = "; ".join(e["msg"].replace("Value error, ", "") for e in exc.errors())
        raise HTTPException(422, msg) from exc
    new_iid = patch.get("intersection_id") or cam.intersection_id
    _check_intersection(db, new_iid)
    changes = {}
    for k, v in validated.model_dump().items():
        if getattr(cam, k) != v:
            changes[k] = v
            setattr(cam, k, v)
    if new_iid != cam.intersection_id:
        changes["intersection_id"] = new_iid
        cam.intersection_id = new_iid
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Trùng mã camera hoặc hướng này của nút giao đã có camera") from exc
    db.refresh(cam)
    if changes:
        audit(db, "CONFIG", "UPDATE_CAMERA", f"Cập nhật camera {cam.code}: {', '.join(changes)}",
              username=cur.username, role=cur.role, target=cam.code, ip=client_ip(request),
              details={k: str(v)[:120] for k, v in changes.items()}, intersection_id=cam.intersection_id)
        manager.reload(cam.intersection_id)
        if old_iid != cam.intersection_id:
            manager.reload(old_iid)
    return cam


@router.delete("/{cid}", status_code=204)
def delete_camera(cid: int, request: Request, db: Session = Depends(get_db),
                  cur: CurrentUser = Depends(require(Perm.CONFIG_MANAGE))):
    cam = db.get(Camera, cid)
    if not cam:
        raise HTTPException(404, "Không tìm thấy camera")
    iid, code = cam.intersection_id, cam.code
    db.delete(cam)
    db.commit()
    audit(db, "CONFIG", "DELETE_CAMERA", f"Xoá camera {code}", username=cur.username, role=cur.role, target=code,
          ip=client_ip(request), intersection_id=iid)
    manager.reload(iid)


@router.post("/{cid}/ping")
def ping_camera(cid: int, request: Request, db: Session = Depends(get_db),
                cur: CurrentUser = Depends(require(Perm.CONFIG_VIEW))):
    cam = db.get(Camera, cid)
    if not cam:
        raise HTTPException(404, "Không tìm thấy camera")
    rt = manager.get(cam.intersection_id)
    stream = None
    if rt:
        p = rt.pipelines.get(cam.direction)
        if p and p.camera and p.camera.info.id == cam.id:
            stream = p.camera
    if stream is None:
        result = {"ok": False, "status": "OFFLINE", "latency_ms": None, "error": "Camera chưa được nạp vào runtime"}
    elif stream.connected:
        latency = stream.latency_ms or random.uniform(35, 60)
        result = {"ok": True, "status": stream.status, "latency_ms": round(latency, 1), "fps": round(stream.fps, 1),
                  "resolution": stream.info.resolution, "bitrate_kbps": round(stream.bitrate_kbps), "error": None}
    else:
        result = {"ok": False, "status": "OFFLINE", "latency_ms": None, "error": stream.error or "Không phản hồi"}
    audit(db, "CONFIG", "PING_CAMERA",
          f"Kiểm tra kết nối camera {cam.code}: {'OK %s ms' % result['latency_ms'] if result['ok'] else result['error']}",
          username=cur.username, role=cur.role, target=cam.code, ip=client_ip(request),
          result="SUCCESS" if result["ok"] else "FAILURE", intersection_id=cam.intersection_id)
    return result


@router.get("/{cid}/stream.mjpg")
async def mjpeg(cid: int, ticket: str = Query(...)):
    """Luồng MJPEG đã chú thích AI cho camera thực (RTSP/HTTP/FILE).

    Thẻ <img> không gửi được header nên xác thực bằng ?ticket= (vé dùng một lần từ POST /api/auth/ticket).
    """
    db = SessionLocal()
    try:
        user = user_from_ticket(db, ticket, stream_purpose(cid))
        cam = db.get(Camera, cid)
    finally:
        db.close()
    if user is None or not has_perm(user.role, Perm.LIVE_VIEW):
        raise HTTPException(401, "Không có quyền xem luồng camera")
    if cam is None:
        raise HTTPException(404, "Không tìm thấy camera")
    rt = manager.get(cam.intersection_id)
    p = rt.pipelines.get(cam.direction) if rt else None
    if not p or not p.camera or not p.camera.real:
        raise HTTPException(409, "Camera này không phải nguồn video thực (SIMULATED được render trên client)")
    src = p.camera.real

    async def gen():
        last = None
        while True:
            jpeg = src.latest_jpeg()
            if jpeg is not None and jpeg is not last:
                last = jpeg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
