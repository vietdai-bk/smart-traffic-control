"""US08/US09/US10 — Điều khiển đèn tín hiệu, chuyển chế độ, khôi phục fail-safe, lịch sử lệnh & chu kỳ."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.control_engine.phases import DIRECTIONS, MODE_LABELS, PHASES, Mode, conflict_matrix
from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require
from app.core.events import bus
from app.core.rbac import Perm
from app.db.session import get_db
from app.models.signal import SignalCommand, SignalCycle
from app.schemas.common import Page
from app.schemas.signal import (
    CommandResultOut,
    ModeRequest,
    RecoverRequest,
    SignalCommandOut,
    SignalCommandRequest,
    SignalCycleOut,
)
from app.services.manager import manager

router = APIRouter(prefix="/signals", tags=["Signals"])

COMMAND_LABELS = {
    "NEXT_PHASE": "Chuyển pha kế tiếp",
    "GOTO_PHASE": "Chuyển đến pha",
    "HOLD_PHASE": "Giữ pha xanh khẩn cấp",
    "RELEASE_HOLD": "Giải phóng giữ pha",
    "EXTEND_GREEN": "Kéo dài pha xanh",
    "SET_TIMING": "Điều chỉnh thời gian pha",
    "FLASHING_YELLOW": "Chớp vàng",
}


def _runtime(iid: int):
    rt = manager.get(iid)
    if rt is None:
        raise HTTPException(404, "Nút giao không tồn tại hoặc đang tắt")
    return rt


def _require_confirm(confirm: bool) -> None:
    if not confirm:
        raise HTTPException(428, "Thao tác can thiệp đèn tín hiệu cần xác nhận an toàn (confirm=true)")


def _publish(iid: int, kind: str, username: str, payload: dict) -> None:
    bus.publish({"type": "command", "data": {"kind": kind, "username": username, **payload}}, iid)


@router.get("/meta")
def meta(_: CurrentUser = Depends(require(Perm.LIVE_VIEW))):
    return {
        "directions": DIRECTIONS,
        "phases": [{"id": p.id, "name": p.name, "axis": p.axis, "greens": p.greens} for p in PHASES.values()],
        "conflict_matrix": conflict_matrix(),
        "modes": [{"mode": m.value, "label": MODE_LABELS[m]} for m in Mode],
        "commands": COMMAND_LABELS,
    }


@router.get("/{iid}/state")
def state(iid: int, _: CurrentUser = Depends(require(Perm.LIVE_VIEW))):
    return _runtime(iid).snapshot_message()


@router.post("/{iid}/command", response_model=CommandResultOut)
def command(iid: int, body: SignalCommandRequest, request: Request, db: Session = Depends(get_db),
            cur: CurrentUser = Depends(require(Perm.SIGNAL_CONTROL))):
    _require_confirm(body.confirm)
    rt = _runtime(iid)
    params = {**body.params, "reason": body.reason} if body.reason else dict(body.params)
    res, ack = rt.execute(body.command, params, cur.username)
    label = COMMAND_LABELS.get(body.command, body.command)
    audit(db, "SIGNAL_CONTROL", body.command, f"{rt.cfg.name}: {label} — {res.message}", username=cur.username,
          role=cur.role, target=rt.cfg.code, ip=client_ip(request),
          details={"params": body.params, "reason": body.reason, "status": res.status, "from": res.from_state,
                   "to": res.to_state, "ack": ack},
          result="SUCCESS" if res.ok else "FAILURE", intersection_id=iid)
    _publish(iid, body.command, cur.username, {"status": res.status, "message": res.message, "ack": ack})
    return CommandResultOut(status=res.status, message=res.message, from_state=res.from_state, to_state=res.to_state,
                            eta_s=res.eta_s, ack=ack, signal=rt.fsm.snapshot())


@router.post("/{iid}/mode", response_model=CommandResultOut)
def set_mode(iid: int, body: ModeRequest, request: Request, db: Session = Depends(get_db),
             cur: CurrentUser = Depends(require(Perm.SIGNAL_MODE))):
    _require_confirm(body.confirm)
    rt = _runtime(iid)
    prev = rt.fsm.mode.value
    res = rt.set_mode(body.mode, cur.username, body.reason)
    audit(db, "SIGNAL_CONTROL", "SET_MODE", f"{rt.cfg.name}: {prev} → {body.mode} — {res.message}",
          username=cur.username, role=cur.role, target=rt.cfg.code, ip=client_ip(request),
          details={"from": prev, "to": body.mode, "reason": body.reason, "status": res.status},
          result="SUCCESS" if res.ok else "FAILURE", intersection_id=iid)
    _publish(iid, "SET_MODE", cur.username, {"status": res.status, "message": res.message})
    return CommandResultOut(status=res.status, message=res.message, from_state=res.from_state, to_state=res.to_state,
                            signal=rt.fsm.snapshot())


@router.post("/{iid}/recover", response_model=CommandResultOut)
def recover(iid: int, body: RecoverRequest, request: Request, db: Session = Depends(get_db),
            cur: CurrentUser = Depends(require(Perm.SIGNAL_MODE))):
    _require_confirm(body.confirm)
    rt = _runtime(iid)
    res = rt.recover(body.mode, cur.username, body.reason)
    audit(db, "SIGNAL_CONTROL", "RECOVER_FAILSAFE", f"{rt.cfg.name}: {res.message}", username=cur.username,
          role=cur.role, target=rt.cfg.code, ip=client_ip(request),
          details={"mode": body.mode, "reason": body.reason, "status": res.status},
          result="SUCCESS" if res.ok else "FAILURE", intersection_id=iid)
    _publish(iid, "RECOVER", cur.username, {"status": res.status, "message": res.message})
    return CommandResultOut(status=res.status, message=res.message, from_state=res.from_state, to_state=res.to_state,
                            signal=rt.fsm.snapshot())


@router.get("/{iid}/commands", response_model=Page[SignalCommandOut])
def commands(iid: int, source: str | None = None, status: str | None = None, page: int = Query(1, ge=1),
             page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
             _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    q = db.query(SignalCommand).filter(SignalCommand.intersection_id == iid)
    if source:
        q = q.filter(SignalCommand.source == source)
    if status:
        q = q.filter(SignalCommand.status == status)
    total = q.count()
    items = q.order_by(SignalCommand.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{iid}/cycles", response_model=Page[SignalCycleOut])
def cycles(iid: int, hours: float = Query(24, gt=0, le=24 * 31), mode: str | None = None,
           page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
           _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(SignalCycle).filter(SignalCycle.intersection_id == iid, SignalCycle.started_at >= since)
    if mode:
        q = q.filter(SignalCycle.mode == mode)
    total = q.count()
    items = q.order_by(SignalCycle.started_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)
