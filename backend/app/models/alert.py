from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UTCDateTime, utcnow


class Alert(Base):
    """Cảnh báo ùn tắc / an toàn / fail-safe (US11-T04)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(16), index=True)  # CONGESTION | FAILSAFE | SAFETY
    level: Mapped[str] = mapped_column(String(16))  # WARNING | CRITICAL
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)  # ACTIVE | ACKNOWLEDGED | RESOLVED
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ack_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeviceIncident(Base):
    """Sự cố thiết bị & lịch sử khắc phục (US12-T04)."""

    __tablename__ = "device_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    device_type: Mapped[str] = mapped_column(String(16))  # CAMERA | CONTROLLER | VISION
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_code: Mapped[str] = mapped_column(String(64))
    incident_type: Mapped[str] = mapped_column(String(24))  # CONNECTION_LOST | TIMEOUT | DEGRADED | HARDWARE_FAULT | ALGORITHM_ERROR
    severity: Mapped[str] = mapped_column(String(16))  # WARNING | CRITICAL
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)  # OPEN | ACKNOWLEDGED | RESOLVED
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    recovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
