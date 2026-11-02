from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RoleT = Literal["ADMIN", "OPERATOR", "MANAGER", "VIEWER"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str | None
    phone: str | None
    role: RoleT
    is_active: bool
    failed_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    permissions: list[str]


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=128)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role: RoleT
    password: str = Field(min_length=6, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=128)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role: RoleT | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v and "@" not in v:
            raise ValueError("Email không hợp lệ")
        return v or None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)
