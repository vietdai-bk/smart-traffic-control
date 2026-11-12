"""Audit Logger (US02-T03, US16-T01). Mọi thao tác quan trọng đều đi qua hàm `audit`."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.events import bus
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.base import utcnow

log = logging.getLogger("stcs.audit")

CATEGORIES = ("AUTH", "SIGNAL_CONTROL", "ALERT", "DEVICE", "CONFIG", "USER", "SYSTEM")


def audit(
    db: Session | None,
    category: str,
    action: str,
    description: str,
    *,
    username: str = "system",
    role: str | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    result: str = "SUCCESS",
    intersection_id: int | None = None,
) -> None:
    entry = AuditLog(
        created_at=utcnow(),
        category=category,
        action=action,
        username=username,
        role=role,
        target=target,
        description=description,
        details=details or {},
        ip=ip,
        result=result,
        intersection_id=intersection_id,
    )
    try:
        if db is None:
            with session_scope() as s:
                s.add(entry)
        else:
            db.add(entry)
            db.commit()
    except Exception:  # pragma: no cover - audit không được làm hỏng nghiệp vụ chính
        log.exception("Không ghi được audit log")
        return
    bus.publish(
        {
            "type": "log",
            "data": {
                "id": entry.id,
                "created_at": entry.created_at.isoformat(),
                "category": category,
                "action": action,
                "username": username,
                "description": description,
                "result": result,
                "intersection_id": intersection_id,
            },
        },
        droppable=True,
    )
