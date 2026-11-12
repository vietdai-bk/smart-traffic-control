from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intersection_id: int
    direction: str | None
    alert_type: str
    level: str
    title: str
    message: str
    density: float | None
    queue_m: float | None
    peak_density: float | None
    status: str
    created_at: datetime
    resolved_at: datetime | None
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    ack_note: str | None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intersection_id: int
    device_type: str
    device_id: int | None
    device_code: str
    incident_type: str
    severity: str
    message: str
    status: str
    started_at: datetime
    recovered_at: datetime | None
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None


class AckRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ResolveRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    category: str
    action: str
    username: str
    role: str | None
    target: str | None
    description: str
    details: dict
    ip: str | None
    result: str
    intersection_id: int | None
