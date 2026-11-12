from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UTCDateTime, utcnow


class SignalCycle(Base):
    """Lịch sử chu kỳ đèn (US14-T02)."""

    __tablename__ = "signal_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ended_at: Mapped[datetime] = mapped_column(UTCDateTime)
    mode: Mapped[str] = mapped_column(String(16))
    cycle_length_s: Mapped[float] = mapped_column(Float)
    green_ns_s: Mapped[float] = mapped_column(Float)
    green_ew_s: Mapped[float] = mapped_column(Float)
    yellow_s: Mapped[float] = mapped_column(Float)
    all_red_s: Mapped[float] = mapped_column(Float)
    demand_ns_pcu: Mapped[float] = mapped_column(Float, default=0.0)
    demand_ew_pcu: Mapped[float] = mapped_column(Float, default=0.0)
    queue_ns_m: Mapped[float] = mapped_column(Float, default=0.0)
    queue_ew_m: Mapped[float] = mapped_column(Float, default=0.0)
    avg_wait_s: Mapped[float] = mapped_column(Float, default=0.0)
    throughput: Mapped[int] = mapped_column(Integer, default=0)
    plan_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignalCommand(Base):
    """Lịch sử lệnh điều khiển đèn (US16-T02)."""

    __tablename__ = "signal_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    command: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16))  # MANUAL | AUTO | SYSTEM
    issued_by: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    from_state: Mapped[str] = mapped_column(String(64))
    to_state: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # ACCEPTED | SCHEDULED | EXECUTED | REJECTED
    ack: Mapped[bool] = mapped_column(Boolean, default=False)
    ack_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
