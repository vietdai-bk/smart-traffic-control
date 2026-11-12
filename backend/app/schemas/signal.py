from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CommandT = Literal[
    "NEXT_PHASE", "GOTO_PHASE", "HOLD_PHASE", "RELEASE_HOLD", "EXTEND_GREEN", "SET_TIMING", "FLASHING_YELLOW"
]


class SignalCommandRequest(BaseModel):
    command: CommandT
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=300)
    confirm: bool = Field(default=False, description="Xác nhận an toàn từ hộp thoại (NFR12)")


class ModeRequest(BaseModel):
    mode: Literal["AUTO", "MANUAL", "FIXED_TIME"]
    reason: str | None = Field(default=None, max_length=300)
    confirm: bool = False


class RecoverRequest(BaseModel):
    mode: Literal["AUTO", "MANUAL", "FIXED_TIME"] = "AUTO"
    reason: str | None = Field(default=None, max_length=300)
    confirm: bool = False


class CommandResultOut(BaseModel):
    status: str
    message: str
    from_state: str
    to_state: str
    eta_s: float | None = None
    ack: dict | None = None
    signal: dict | None = None


class SignalCommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intersection_id: int
    created_at: datetime
    command: str
    params: dict
    source: str
    issued_by: str
    mode: str
    from_state: str
    to_state: str
    reason: str | None
    status: str
    ack: bool
    ack_latency_ms: float | None
    message: str | None


class SignalCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intersection_id: int
    started_at: datetime
    ended_at: datetime
    mode: str
    cycle_length_s: float
    green_ns_s: float
    green_ew_s: float
    yellow_s: float
    all_red_s: float
    demand_ns_pcu: float
    demand_ew_pcu: float
    queue_ns_m: float
    queue_ew_m: float
    avg_wait_s: float
    throughput: int
    plan_reason: str | None
