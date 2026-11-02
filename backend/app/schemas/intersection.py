from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DirectionT = Literal["NORTH", "SOUTH", "EAST", "WEST"]
SourceT = Literal["SIMULATED", "RTSP", "HTTP", "FILE"]


class CameraBase(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    direction: DirectionT
    source_type: SourceT = "SIMULATED"
    stream_url: str = Field(default="", max_length=255)
    resolution: str = Field(default="1280x720", pattern=r"^\d{3,4}x\d{3,4}$")
    target_fps: int = Field(default=15, ge=1, le=60)
    roi: list[list[float]] = Field(default_factory=list)
    counting_line: list[list[float]] = Field(default_factory=list)
    roi_length_m: float = Field(default=60.0, ge=15, le=150)
    density_medium: float | None = Field(default=None, ge=5, le=95)
    density_high: float | None = Field(default=None, ge=10, le=100)
    is_enabled: bool = True

    @field_validator("roi")
    @classmethod
    def _roi(cls, v: list[list[float]]) -> list[list[float]]:
        if v and (len(v) < 3 or any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in v)):
            raise ValueError("ROI phải là đa giác ≥ 3 điểm với toạ độ chuẩn hoá trong [0, 1]")
        return v

    @field_validator("counting_line")
    @classmethod
    def _line(cls, v: list[list[float]]) -> list[list[float]]:
        if v and (len(v) != 2 or any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in v)):
            raise ValueError("Vạch đếm gồm đúng 2 điểm chuẩn hoá trong [0, 1]")
        return v

    @model_validator(mode="after")
    def _thresholds(self):
        if self.density_medium is not None and self.density_high is not None and self.density_medium >= self.density_high:
            raise ValueError("Ngưỡng Đông đúc phải nhỏ hơn ngưỡng Ùn tắc")
        if self.source_type != "SIMULATED" and not self.stream_url:
            raise ValueError("Camera thực cần Stream URL")
        return self


class CameraCreate(CameraBase):
    intersection_id: int


class CameraUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=32)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    intersection_id: int | None = None
    direction: DirectionT | None = None
    source_type: SourceT | None = None
    stream_url: str | None = Field(default=None, max_length=255)
    resolution: str | None = Field(default=None, pattern=r"^\d{3,4}x\d{3,4}$")
    target_fps: int | None = Field(default=None, ge=1, le=60)
    roi: list[list[float]] | None = None
    counting_line: list[list[float]] | None = None
    roi_length_m: float | None = Field(default=None, ge=15, le=150)
    density_medium: float | None = Field(default=None, ge=5, le=95)
    density_high: float | None = Field(default=None, ge=10, le=100)
    clear_thresholds: bool = False
    is_enabled: bool | None = None


class CameraOut(CameraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intersection_id: int
    created_at: datetime
    updated_at: datetime


class IntersectionBase(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=3, max_length=160)
    description: str | None = None
    district: str | None = Field(default=None, max_length=80)
    latitude: float = Field(default=16.0544, ge=-90, le=90)
    longitude: float = Field(default=108.2022, ge=-180, le=180)
    ns_road: str = Field(default="Trục Bắc–Nam", max_length=80)
    ew_road: str = Field(default="Trục Đông–Tây", max_length=80)
    lanes_per_approach: int = Field(default=3, ge=1, le=5)
    default_mode: Literal["AUTO", "FIXED_TIME", "MANUAL"] = "AUTO"
    fixed_green_ns: int = Field(default=30, ge=5, le=180)
    fixed_green_ew: int = Field(default=30, ge=5, le=180)
    yellow_s: int = Field(default=3, ge=3, le=6)
    all_red_s: int = Field(default=2, ge=2, le=6)
    min_green_s: int = Field(default=10, ge=5, le=60)
    max_green_s: int = Field(default=60, ge=10, le=180)
    cycle_min_s: int = Field(default=40, ge=20, le=200)
    cycle_max_s: int = Field(default=120, ge=30, le=300)
    saturation_flow: int = Field(default=1800, ge=600, le=2400)
    failsafe_strategy: Literal["FIXED_TIME", "FLASHING_YELLOW"] = "FIXED_TIME"
    density_medium: float = Field(default=40, ge=5, le=95)
    density_high: float = Field(default=70, ge=10, le=100)
    alert_hold_s: int = Field(default=5, ge=0, le=120)
    base_demand_ns: int = Field(default=900, ge=0, le=5000)
    base_demand_ew: int = Field(default=700, ge=0, le=5000)
    controller_endpoint: str = Field(default="sim://tsc", max_length=160)
    controller_model: str = Field(default="STCS-SimTSC v2", max_length=80)
    is_active: bool = True

    @model_validator(mode="after")
    def _safety(self):
        if self.min_green_s > self.max_green_s:
            raise ValueError("Min Green phải ≤ Max Green")
        if self.cycle_min_s > self.cycle_max_s:
            raise ValueError("Chu kỳ tối thiểu phải ≤ chu kỳ tối đa")
        if self.density_medium >= self.density_high:
            raise ValueError("Ngưỡng Đông đúc phải nhỏ hơn ngưỡng Ùn tắc")
        if not (self.min_green_s <= self.fixed_green_ns <= self.max_green_s) or not (
            self.min_green_s <= self.fixed_green_ew <= self.max_green_s
        ):
            raise ValueError("Thời gian xanh cố định phải nằm trong [Min Green, Max Green]")
        return self


class IntersectionCreate(IntersectionBase):
    create_default_cameras: bool = True


class IntersectionUpdate(BaseModel):
    """Cập nhật từng phần — được hợp nhất với bản ghi hiện có rồi kiểm tra lại toàn bộ bằng IntersectionBase."""

    code: str | None = None
    name: str | None = None
    description: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    ns_road: str | None = None
    ew_road: str | None = None
    lanes_per_approach: int | None = None
    default_mode: Literal["AUTO", "FIXED_TIME", "MANUAL"] | None = None
    fixed_green_ns: int | None = None
    fixed_green_ew: int | None = None
    yellow_s: int | None = None
    all_red_s: int | None = None
    min_green_s: int | None = None
    max_green_s: int | None = None
    cycle_min_s: int | None = None
    cycle_max_s: int | None = None
    saturation_flow: int | None = None
    failsafe_strategy: Literal["FIXED_TIME", "FLASHING_YELLOW"] | None = None
    density_medium: float | None = None
    density_high: float | None = None
    alert_hold_s: int | None = None
    base_demand_ns: int | None = None
    base_demand_ew: int | None = None
    controller_endpoint: str | None = None
    controller_model: str | None = None
    is_active: bool | None = None


class IntersectionOut(IntersectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    cameras: list[CameraOut] = []
