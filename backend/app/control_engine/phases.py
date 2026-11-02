"""Định nghĩa pha đèn, khoảng chuyển tiếp và ma trận xung đột (NFR06)."""
from __future__ import annotations

import enum
from dataclasses import dataclass

DIRECTIONS: tuple[str, ...] = ("NORTH", "SOUTH", "EAST", "WEST")
DIRECTION_LABELS = {"NORTH": "Bắc", "SOUTH": "Nam", "EAST": "Đông", "WEST": "Tây"}


class Color(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    FLASHING_YELLOW = "FLASHING_YELLOW"
    OFF = "OFF"


class Interval(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW_CLEARANCE"
    ALL_RED = "ALL_RED_CLEARANCE"
    FLASHING = "FLASHING_YELLOW"


class Mode(str, enum.Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    FIXED_TIME = "FIXED_TIME"
    FAILSAFE = "FAILSAFE"


MODE_LABELS = {
    Mode.AUTO: "Tự động AI",
    Mode.MANUAL: "Thủ công",
    Mode.FIXED_TIME: "Chu kỳ cố định",
    Mode.FAILSAFE: "An toàn khi lỗi",
}


@dataclass(frozen=True)
class Phase:
    id: int
    name: str
    axis: str  # NS | EW
    greens: tuple[str, ...]


PHASES: dict[int, Phase] = {
    1: Phase(1, "Pha 1 · Bắc–Nam", "NS", ("NORTH", "SOUTH")),
    2: Phase(2, "Pha 2 · Đông–Tây", "EW", ("EAST", "WEST")),
}

AXIS_OF_DIRECTION = {"NORTH": "NS", "SOUTH": "NS", "EAST": "EW", "WEST": "EW"}
PHASE_OF_AXIS = {"NS": 1, "EW": 2}

# Các cặp hướng cắt nhau — không bao giờ được cùng mở (GREEN/YELLOW)
CONFLICTS: frozenset[frozenset[str]] = frozenset(
    frozenset(p)
    for p in (
        ("NORTH", "EAST"),
        ("NORTH", "WEST"),
        ("SOUTH", "EAST"),
        ("SOUTH", "WEST"),
    )
)

OPEN_COLORS = frozenset({Color.GREEN, Color.YELLOW})


def other_phase(phase_id: int) -> int:
    return 2 if phase_id == 1 else 1


def heads_for(phase_id: int, interval: Interval) -> dict[str, Color]:
    """Trạng thái đèn từng hướng cho (pha, khoảng)."""
    if interval == Interval.FLASHING:
        return {d: Color.FLASHING_YELLOW for d in DIRECTIONS}
    if interval == Interval.ALL_RED:
        return {d: Color.RED for d in DIRECTIONS}
    phase = PHASES[phase_id]
    open_color = Color.GREEN if interval == Interval.GREEN else Color.YELLOW
    return {d: (open_color if d in phase.greens else Color.RED) for d in DIRECTIONS}


def conflict_matrix() -> dict[str, dict[str, bool]]:
    return {a: {b: frozenset((a, b)) in CONFLICTS for b in DIRECTIONS} for a in DIRECTIONS}
