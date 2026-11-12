"""Alert & Incident services (US11, US12): phát hiện vượt ngưỡng, lưu CSDL, đẩy thời gian thực."""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.control_engine.phases import DIRECTION_LABELS
from app.core.audit import audit
from app.core.events import bus
from app.db.session import session_scope
from app.models.alert import Alert, DeviceIncident
from app.models.base import utcnow
from app.vision_engine.density import LEVEL_LABELS, classify


def alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "intersection_id": a.intersection_id,
        "direction": a.direction,
        "alert_type": a.alert_type,
        "level": a.level,
        "title": a.title,
        "message": a.message,
        "density": a.density,
        "queue_m": a.queue_m,
        "peak_density": a.peak_density,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "ack_note": a.ack_note,
    }


def incident_dict(i: DeviceIncident) -> dict:
    return {
        "id": i.id,
        "intersection_id": i.intersection_id,
        "device_type": i.device_type,
        "device_id": i.device_id,
        "device_code": i.device_code,
        "incident_type": i.incident_type,
        "severity": i.severity,
        "message": i.message,
        "status": i.status,
        "started_at": i.started_at.isoformat() if i.started_at else None,
        "recovered_at": i.recovered_at.isoformat() if i.recovered_at else None,
        "acknowledged_by": i.acknowledged_by,
        "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
        "resolved_by": i.resolved_by,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "resolution_note": i.resolution_note,
    }


def publish_alert(a: Alert, event: str) -> None:
    bus.publish({"type": "alert", "event": event, "data": alert_dict(a)})


def publish_incident(i: DeviceIncident, event: str) -> None:
    bus.publish({"type": "incident", "event": event, "data": incident_dict(i)})


def create_alert(intersection_id: int, alert_type: str, level: str, title: str, message: str,
                 direction: str | None = None, density: float | None = None, queue_m: float | None = None) -> int:
    with session_scope() as db:
        a = Alert(
            intersection_id=intersection_id, direction=direction, alert_type=alert_type, level=level,
            title=title, message=message, density=density, queue_m=queue_m, peak_density=density,
            status="ACTIVE", created_at=utcnow(),
        )
        db.add(a)
        db.flush()
        publish_alert(a, "created")
        aid = a.id
    audit(None, "ALERT", f"{alert_type}_RAISED", title, target=f"alert#{aid}",
          details={"level": level, "direction": direction, "density": density}, intersection_id=intersection_id)
    return aid


def escalate_alert(alert_id: int, level: str, title: str, message: str, density: float, queue_m: float) -> None:
    with session_scope() as db:
        a = db.get(Alert, alert_id)
        if a is None:
            return
        a.level = level
        a.title = title
        a.message = message
        a.density = density
        a.queue_m = queue_m
        a.peak_density = max(a.peak_density or 0, density)
        if a.status == "ACKNOWLEDGED" and level == "CRITICAL":
            a.status = "ACTIVE"  # leo thang → cần xác nhận lại
        publish_alert(a, "updated")


def touch_alert(alert_id: int, density: float, queue_m: float) -> None:
    with session_scope() as db:
        a = db.get(Alert, alert_id)
        if a is not None:
            a.density = density
            a.queue_m = queue_m
            a.peak_density = max(a.peak_density or 0, density)


def resolve_alert(alert_id: int, note: str | None = None) -> None:
    with session_scope() as db:
        a = db.get(Alert, alert_id)
        if a is None or a.status == "RESOLVED":
            return
        a.status = "RESOLVED"
        a.resolved_at = utcnow()
        if note and not a.ack_note:
            a.ack_note = note
        publish_alert(a, "resolved")


def create_incident(intersection_id: int, device_type: str, device_id: int | None, device_code: str,
                    incident_type: str, severity: str, message: str) -> int:
    with session_scope() as db:
        inc = DeviceIncident(
            intersection_id=intersection_id, device_type=device_type, device_id=device_id, device_code=device_code,
            incident_type=incident_type, severity=severity, message=message, status="OPEN", started_at=utcnow(),
        )
        db.add(inc)
        db.flush()
        publish_incident(inc, "created")
        iid = inc.id
    audit(None, "DEVICE", f"{device_type}_{incident_type}", f"[{device_code}] {message}", target=device_code,
          details={"severity": severity, "incident_id": iid}, result="FAILURE", intersection_id=intersection_id)
    return iid


def recover_incident(incident_id: int) -> None:
    with session_scope() as db:
        inc = db.get(DeviceIncident, incident_id)
        if inc is None or inc.recovered_at is not None:
            return
        inc.recovered_at = utcnow()
        publish_incident(inc, "recovered")
        code, iid = inc.device_code, inc.intersection_id
    audit(None, "DEVICE", "DEVICE_RECOVERED", f"[{code}] Thiết bị đã kết nối lại", target=code,
          details={"incident_id": incident_id}, intersection_id=iid)


def cleanup_stale_on_startup() -> None:
    """Sau khi khởi động lại, các cảnh báo/sự cố đang mở từ phiên trước sẽ được phát hiện lại nếu còn tồn tại."""
    now = utcnow()
    with session_scope() as db:
        for a in db.query(Alert).filter(Alert.status != "RESOLVED", Alert.alert_type.in_(["CONGESTION", "FAILSAFE"])):
            a.status = "RESOLVED"
            a.resolved_at = now
            a.ack_note = a.ack_note or "Tự đóng khi hệ thống khởi động lại"
        for inc in db.query(DeviceIncident).filter(DeviceIncident.recovered_at.is_(None)):
            inc.recovered_at = now


@dataclass
class _DirState:
    level: str = "LOW"
    candidate: str = "LOW"
    candidate_since: float = 0.0
    alert_id: int | None = None
    last_touch: float = 0.0


class CongestionMonitor:
    """Phát hiện ùn tắc theo ngưỡng (có hysteresis + thời gian duy trì) — US11-T02."""

    def __init__(self, intersection_id: int, name: str) -> None:
        self.intersection_id = intersection_id
        self.name = name
        self.state: dict[str, _DirState] = {}

    def level_of(self, direction: str) -> str:
        return self.state.get(direction, _DirState()).level

    def update(self, direction: str, density: float, queue_m: float, medium: float, high: float,
               hold_s: float, now: float | None = None) -> str:
        now = now or time.time()
        st = self.state.setdefault(direction, _DirState())
        cand = classify(density, medium, high, st.level)
        if cand != st.candidate:
            st.candidate = cand
            st.candidate_since = now
        if cand != st.level and now - st.candidate_since >= hold_s:
            self._commit(direction, st, cand, density, queue_m, medium, high)
        elif st.alert_id and now - st.last_touch > 10:
            touch_alert(st.alert_id, density, queue_m)
            st.last_touch = now
        return st.level

    def _commit(self, direction: str, st: _DirState, new: str, density: float, queue_m: float,
                medium: float, high: float) -> None:
        prev = st.level
        st.level = new
        label = DIRECTION_LABELS.get(direction, direction)
        if new == "LOW":
            if st.alert_id:
                resolve_alert(st.alert_id, "Mật độ trở về mức thông thoáng")
                st.alert_id = None
            return
        level = "CRITICAL" if new == "HIGH" else "WARNING"
        title = f"{LEVEL_LABELS[new].upper()} hướng {label} — {self.name}"
        threshold = high if new == "HIGH" else medium
        msg = (f"Mật độ hướng {label} đạt {density:.0f}% (ngưỡng {threshold:.0f}%), hàng đợi ước tính {queue_m:.0f} m.")
        if st.alert_id is None:
            st.alert_id = create_alert(self.intersection_id, "CONGESTION", level, title, msg, direction, density, queue_m)
        elif LEVELS_ORDER[new] > LEVELS_ORDER[prev]:
            escalate_alert(st.alert_id, level, title, msg, density, queue_m)
        else:
            escalate_alert(st.alert_id, level, title, msg + " (đã giảm mức)", density, queue_m)

    def reset(self) -> None:
        for st in self.state.values():
            if st.alert_id:
                resolve_alert(st.alert_id, "Cấu hình nút giao thay đổi")
        self.state.clear()


LEVELS_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
