from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import UTCDateTime, utcnow


class Intersection(Base):
    __tablename__ = "intersections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    ns_road: Mapped[str] = mapped_column(String(80), default="Trục Bắc–Nam")
    ew_road: Mapped[str] = mapped_column(String(80), default="Trục Đông–Tây")
    lanes_per_approach: Mapped[int] = mapped_column(Integer, default=3)

    # Kế hoạch đèn chuẩn & ràng buộc an toàn (FR18)
    default_mode: Mapped[str] = mapped_column(String(16), default="AUTO")
    fixed_green_ns: Mapped[int] = mapped_column(Integer, default=30)
    fixed_green_ew: Mapped[int] = mapped_column(Integer, default=30)
    yellow_s: Mapped[int] = mapped_column(Integer, default=3)
    all_red_s: Mapped[int] = mapped_column(Integer, default=2)
    min_green_s: Mapped[int] = mapped_column(Integer, default=10)
    max_green_s: Mapped[int] = mapped_column(Integer, default=60)
    cycle_min_s: Mapped[int] = mapped_column(Integer, default=40)
    cycle_max_s: Mapped[int] = mapped_column(Integer, default=120)
    saturation_flow: Mapped[int] = mapped_column(Integer, default=1800)  # PCU/h/làn
    failsafe_strategy: Mapped[str] = mapped_column(String(24), default="FIXED_TIME")  # FIXED_TIME | FLASHING_YELLOW

    # Ngưỡng cảnh báo mật độ (US11-T01)
    density_medium: Mapped[float] = mapped_column(Float, default=40.0)
    density_high: Mapped[float] = mapped_column(Float, default=70.0)
    alert_hold_s: Mapped[int] = mapped_column(Integer, default=5)

    # Mô phỏng: lưu lượng cơ sở (xe/giờ/hướng) — dùng bởi Traffic Simulator
    base_demand_ns: Mapped[int] = mapped_column(Integer, default=900)
    base_demand_ew: Mapped[int] = mapped_column(Integer, default=700)

    controller_endpoint: Mapped[str] = mapped_column(String(160), default="sim://tsc")
    controller_model: Mapped[str] = mapped_column(String(80), default="STCS-SimTSC v2")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    cameras: Mapped[list["Camera"]] = relationship(
        back_populates="intersection", cascade="all, delete-orphan", order_by="Camera.id"
    )


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("intersection_id", "direction", name="uq_camera_direction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    intersection_id: Mapped[int] = mapped_column(ForeignKey("intersections.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # NORTH | SOUTH | EAST | WEST
    source_type: Mapped[str] = mapped_column(String(16), default="SIMULATED")  # SIMULATED | RTSP | HTTP | FILE
    stream_url: Mapped[str] = mapped_column(String(255), default="")
    resolution: Mapped[str] = mapped_column(String(16), default="1280x720")
    target_fps: Mapped[int] = mapped_column(Integer, default=15)
    roi: Mapped[list] = mapped_column(JSON, default=list)  # polygon toạ độ chuẩn hoá [[x,y],...]
    counting_line: Mapped[list] = mapped_column(JSON, default=list)  # [[x1,y1],[x2,y2]]
    roi_length_m: Mapped[float] = mapped_column(Float, default=60.0)
    density_medium: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    intersection: Mapped[Intersection] = relationship(back_populates="cameras")
