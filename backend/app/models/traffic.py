from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import UTCDateTime


class TrafficStat(Base):
    """Thống kê lưu lượng theo bucket thời gian / hướng (US13-T01, US14-T01)."""

    __tablename__ = "traffic_stats"
    __table_args__ = (Index("ix_stats_iid_bucket", "intersection_id", "bucket_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"))
    direction: Mapped[str] = mapped_column(String(8))
    bucket_start: Mapped[datetime] = mapped_column(UTCDateTime)
    bucket_minutes: Mapped[int] = mapped_column(Integer, default=5)
    car: Mapped[int] = mapped_column(Integer, default=0)
    motorbike: Mapped[int] = mapped_column(Integer, default=0)
    bus: Mapped[int] = mapped_column(Integer, default=0)
    truck: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    pcu: Mapped[float] = mapped_column(Float, default=0.0)
    avg_density: Mapped[float] = mapped_column(Float, default=0.0)
    max_density: Mapped[float] = mapped_column(Float, default=0.0)
    avg_queue_m: Mapped[float] = mapped_column(Float, default=0.0)
    max_queue_m: Mapped[float] = mapped_column(Float, default=0.0)
    avg_wait_s: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String(16), default="AUTO")
