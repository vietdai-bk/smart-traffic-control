"""Role-Based Access Control (US01-T04, US10-T03)."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    MANAGER = "MANAGER"
    VIEWER = "VIEWER"


class Perm(str, enum.Enum):
    LIVE_VIEW = "live:view"
    STATS_VIEW = "stats:view"
    STATS_EXPORT = "stats:export"
    ALERTS_VIEW = "alerts:view"
    ALERTS_ACK = "alerts:ack"
    SIGNAL_CONTROL = "signal:control"
    SIGNAL_MODE = "signal:mode"
    SIM_CONTROL = "sim:control"
    CONFIG_VIEW = "config:view"
    CONFIG_MANAGE = "config:manage"
    USERS_MANAGE = "users:manage"
    AUDIT_VIEW = "audit:view"
    LLM_SUPERVISE = "llm:supervise"   # bật/tắt LLM Supervisor, duyệt đề xuất
    ASSISTANT_USE = "assistant:use"   # trợ lý vận hành LLM (tool theo quyền người dùng)
    REPORT_AI = "report:ai"           # báo cáo tự động bằng LLM


_COMMON = {Perm.LIVE_VIEW, Perm.STATS_VIEW, Perm.STATS_EXPORT, Perm.ALERTS_VIEW, Perm.CONFIG_VIEW}

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.ADMIN: frozenset(Perm),
    Role.OPERATOR: frozenset(_COMMON | {Perm.SIGNAL_CONTROL, Perm.SIGNAL_MODE, Perm.ALERTS_ACK, Perm.SIM_CONTROL,
                                        Perm.LLM_SUPERVISE, Perm.ASSISTANT_USE, Perm.REPORT_AI}),
    Role.MANAGER: frozenset(_COMMON | {Perm.AUDIT_VIEW, Perm.ASSISTANT_USE, Perm.REPORT_AI}),
    # FR02 "Người xem dữ liệu": chỉ xem thống kê & cảnh báo, không xem video trực tiếp (NFR15)
    Role.VIEWER: frozenset({Perm.STATS_VIEW, Perm.ALERTS_VIEW, Perm.ASSISTANT_USE}),
}

ROLE_LABELS = {
    Role.ADMIN: "Quản trị viên",
    Role.OPERATOR: "Người vận hành",
    Role.MANAGER: "Người quản lý",
    Role.VIEWER: "Người xem dữ liệu",
}


def has_perm(role: str | Role, perm: Perm) -> bool:
    try:
        r = Role(role)
    except ValueError:
        return False
    return perm in ROLE_PERMISSIONS[r]


def perms_of(role: str | Role) -> list[str]:
    try:
        return sorted(p.value for p in ROLE_PERMISSIONS[Role(role)])
    except ValueError:
        return []
