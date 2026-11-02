from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UTCDateTime, utcnow


class AuditLog(Base):
    """Nhật ký hệ thống (US02-T03, US16)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)  # AUTH | SIGNAL_CONTROL | ALERT | DEVICE | CONFIG | USER | SYSTEM
    action: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(16), default="SUCCESS")  # SUCCESS | FAILURE
    intersection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
