"""US16 — Tra cứu nhật ký hoạt động: tìm kiếm từ khoá, lọc loại sự kiện, người dùng, thời gian."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.audit import CATEGORIES
from app.core.deps import CurrentUser, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.models.audit import AuditLog
from app.schemas.common import AuditOut, Page

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=Page[AuditOut])
def list_audit(q: str | None = None, category: str | None = None, username: str | None = None,
               result: str | None = None, intersection_id: int | None = None,
               start: datetime | None = None, end: datetime | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
               db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.AUDIT_VIEW))):
    query = db.query(AuditLog)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AuditLog.description.ilike(like), AuditLog.action.ilike(like),
                                 AuditLog.target.ilike(like), AuditLog.username.ilike(like)))
    if category:
        cats = [c for c in category.split(",") if c]
        query = query.filter(AuditLog.category.in_(cats))
    if username:
        query = query.filter(AuditLog.username == username)
    if result:
        query = query.filter(AuditLog.result == result)
    if intersection_id:
        query = query.filter(AuditLog.intersection_id == intersection_id)
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    total = query.count()
    items = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/meta")
def audit_meta(db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.AUDIT_VIEW))):
    users = [u for (u,) in db.query(AuditLog.username).distinct().order_by(AuditLog.username).all()]
    return {"categories": list(CATEGORIES), "usernames": users}
