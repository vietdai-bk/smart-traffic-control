"""US11/US12 — Cảnh báo ùn tắc & sự cố thiết bị: tra cứu, xác nhận, khắc phục."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.models.alert import Alert, DeviceIncident
from app.models.base import utcnow
from app.schemas.common import AckRequest, AlertOut, IncidentOut, Page, ResolveRequest
from app.services.alert_service import publish_alert, publish_incident

router = APIRouter(tags=["Alerts & Incidents"])


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(status: str | None = None, alert_type: str | None = None, level: str | None = None,
                intersection_id: int | None = None, direction: str | None = None,
                start: datetime | None = None, end: datetime | None = None, q: str | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.ALERTS_VIEW))):
    query = db.query(Alert)
    if status == "OPEN":
        query = query.filter(Alert.status != "RESOLVED")
    elif status:
        query = query.filter(Alert.status == status)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if level:
        query = query.filter(Alert.level == level)
    if intersection_id:
        query = query.filter(Alert.intersection_id == intersection_id)
    if direction:
        query = query.filter(Alert.direction == direction)
    if start:
        query = query.filter(Alert.created_at >= start)
    if end:
        query = query.filter(Alert.created_at <= end)
    if q:
        query = query.filter(Alert.title.ilike(f"%{q}%") | Alert.message.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(Alert.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/alerts/active", response_model=list[AlertOut])
def active_alerts(intersection_id: int | None = None, db: Session = Depends(get_db),
                  _: CurrentUser = Depends(require(Perm.ALERTS_VIEW))):
    q = db.query(Alert).filter(Alert.status != "RESOLVED")
    if intersection_id:
        q = q.filter(Alert.intersection_id == intersection_id)
    return q.order_by(Alert.created_at.desc()).limit(200).all()


@router.get("/alerts/stats")
def alert_stats(db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.ALERTS_VIEW))):
    by = db.query(Alert.alert_type, Alert.level, Alert.status, func.count()).group_by(
        Alert.alert_type, Alert.level, Alert.status).all()
    inc = db.query(DeviceIncident.device_type, DeviceIncident.status, func.count()).group_by(
        DeviceIncident.device_type, DeviceIncident.status).all()
    return {
        "alerts": [{"alert_type": a, "level": l, "status": s, "count": c} for a, l, s, c in by],
        "incidents": [{"device_type": d, "status": s, "count": c} for d, s, c in inc],
        "active_alerts": sum(c for _, _, s, c in by if s == "ACTIVE"),
        "open_incidents": sum(c for _, s, c in inc if s != "RESOLVED"),
    }


@router.post("/alerts/{aid}/ack", response_model=AlertOut)
def ack_alert(aid: int, body: AckRequest, request: Request, db: Session = Depends(get_db),
              cur: CurrentUser = Depends(require(Perm.ALERTS_ACK))):
    a = db.get(Alert, aid)
    if not a:
        raise HTTPException(404, "Không tìm thấy cảnh báo")
    if a.status == "ACKNOWLEDGED":
        raise HTTPException(409, f"Cảnh báo đã được {a.acknowledged_by} xác nhận")
    a.acknowledged_by = cur.username
    a.acknowledged_at = utcnow()
    a.ack_note = body.note
    if a.status == "ACTIVE":
        a.status = "ACKNOWLEDGED"
    db.commit()
    db.refresh(a)
    publish_alert(a, "acknowledged")
    audit(db, "ALERT", "ACK_ALERT", f"Xác nhận cảnh báo: {a.title}", username=cur.username, role=cur.role,
          target=f"alert#{a.id}", ip=client_ip(request), details={"note": body.note}, intersection_id=a.intersection_id)
    return a


@router.post("/alerts/ack-all")
def ack_all(body: AckRequest, request: Request, intersection_id: int | None = None, db: Session = Depends(get_db),
            cur: CurrentUser = Depends(require(Perm.ALERTS_ACK))):
    q = db.query(Alert).filter(Alert.status == "ACTIVE")
    if intersection_id:
        q = q.filter(Alert.intersection_id == intersection_id)
    items = q.all()
    now = utcnow()
    for a in items:
        a.status = "ACKNOWLEDGED"
        a.acknowledged_by = cur.username
        a.acknowledged_at = now
        a.ack_note = body.note
    db.commit()
    for a in items:
        publish_alert(a, "acknowledged")
    if items:
        audit(db, "ALERT", "ACK_ALL", f"Xác nhận hàng loạt {len(items)} cảnh báo", username=cur.username,
              role=cur.role, ip=client_ip(request), details={"note": body.note}, intersection_id=intersection_id)
    return {"acknowledged": len(items)}


@router.get("/incidents", response_model=Page[IncidentOut])
def list_incidents(status: str | None = None, device_type: str | None = None, severity: str | None = None,
                   intersection_id: int | None = None, start: datetime | None = None, end: datetime | None = None,
                   q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                   db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.ALERTS_VIEW))):
    query = db.query(DeviceIncident)
    if status == "OPEN":
        query = query.filter(DeviceIncident.status != "RESOLVED")
    elif status:
        query = query.filter(DeviceIncident.status == status)
    if device_type:
        query = query.filter(DeviceIncident.device_type == device_type)
    if severity:
        query = query.filter(DeviceIncident.severity == severity)
    if intersection_id:
        query = query.filter(DeviceIncident.intersection_id == intersection_id)
    if start:
        query = query.filter(DeviceIncident.started_at >= start)
    if end:
        query = query.filter(DeviceIncident.started_at <= end)
    if q:
        query = query.filter(DeviceIncident.device_code.ilike(f"%{q}%") | DeviceIncident.message.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(DeviceIncident.started_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/incidents/{iid}/ack", response_model=IncidentOut)
def ack_incident(iid: int, body: AckRequest, request: Request, db: Session = Depends(get_db),
                 cur: CurrentUser = Depends(require(Perm.ALERTS_ACK))):
    inc = db.get(DeviceIncident, iid)
    if not inc:
        raise HTTPException(404, "Không tìm thấy sự cố")
    if inc.status != "OPEN":
        raise HTTPException(409, "Sự cố đã được xác nhận hoặc đã khắc phục")
    inc.status = "ACKNOWLEDGED"
    inc.acknowledged_by = cur.username
    inc.acknowledged_at = utcnow()
    if body.note:
        inc.resolution_note = body.note
    db.commit()
    db.refresh(inc)
    publish_incident(inc, "acknowledged")
    audit(db, "DEVICE", "ACK_INCIDENT", f"Xác nhận sự cố [{inc.device_code}] {inc.message}", username=cur.username,
          role=cur.role, target=inc.device_code, ip=client_ip(request), intersection_id=inc.intersection_id)
    return inc


@router.post("/incidents/{iid}/resolve", response_model=IncidentOut)
def resolve_incident(iid: int, body: ResolveRequest, request: Request, db: Session = Depends(get_db),
                     cur: CurrentUser = Depends(require(Perm.ALERTS_ACK))):
    inc = db.get(DeviceIncident, iid)
    if not inc:
        raise HTTPException(404, "Không tìm thấy sự cố")
    if inc.status == "RESOLVED":
        raise HTTPException(409, "Sự cố đã được đóng")
    if inc.recovered_at is None:
        raise HTTPException(409, "Thiết bị chưa phục hồi kết nối — chưa thể đóng sự cố")
    now = utcnow()
    inc.status = "RESOLVED"
    inc.resolved_by = cur.username
    inc.resolved_at = now
    inc.resolution_note = body.note
    if not inc.acknowledged_by:
        inc.acknowledged_by = cur.username
        inc.acknowledged_at = now
    db.commit()
    db.refresh(inc)
    publish_incident(inc, "resolved")
    audit(db, "DEVICE", "RESOLVE_INCIDENT", f"Đóng sự cố [{inc.device_code}]: {body.note}", username=cur.username,
          role=cur.role, target=inc.device_code, ip=client_ip(request), intersection_id=inc.intersection_id)
    return inc
