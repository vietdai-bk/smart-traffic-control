from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UTCDateTime, utcnow


class LlmDecision(Base):
    """Nhật ký quyết định của LLM Supervisor (tầng 3) — phục vụ truy vết & giải thích (US16, NFR12)."""

    __tablename__ = "llm_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    trigger: Mapped[str] = mapped_column(String(24))          # PERIODIC | EVENT | MANUAL
    supervisor_mode: Mapped[str] = mapped_column(String(16))  # ADVISORY | AUTONOMOUS
    model: Mapped[str] = mapped_column(String(64))
    # APPLIED | PENDING | APPROVED | REJECTED | EXPIRED | INVALID | ERROR | SKIPPED
    status: Mapped[str] = mapped_column(String(16), index=True)
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weight_ns: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_ew: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    guard_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # ghi chú của lớp kiểm tra (clamp/từ chối)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
