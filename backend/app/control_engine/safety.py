"""Safety Interlock Validator (NFR06, US08-T04, US09-T05).

Mọi trạng thái đèn và mọi bước chuyển — từ thuật toán AI hay lệnh thủ công — đều phải đi qua validator này.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.control_engine.phases import CONFLICTS, OPEN_COLORS, Color, Interval
from app.core.config import settings


class InterlockViolation(Exception):
    """Vi phạm ràng buộc an toàn tín hiệu."""


@dataclass
class TimingConstraints:
    min_green: float = 10.0
    max_green: float = 60.0
    yellow: float = 3.0
    all_red: float = 2.0
    cycle_min: float = 40.0
    cycle_max: float = 120.0

    def sanitized(self) -> "TimingConstraints":
        """Áp giới hạn cứng: cấu hình không bao giờ được thấp hơn ngưỡng an toàn."""
        min_green = max(float(self.min_green), settings.hard_min_green_s)
        max_green = max(float(self.max_green), min_green)
        yellow = max(float(self.yellow), settings.hard_min_yellow_s)
        all_red = max(float(self.all_red), settings.hard_min_all_red_s)
        lost = 2 * (yellow + all_red)
        cycle_min = max(float(self.cycle_min), 2 * min_green + lost)
        cycle_max = max(float(self.cycle_max), cycle_min)
        return TimingConstraints(min_green, max_green, yellow, all_red, cycle_min, cycle_max)

    @property
    def lost_time(self) -> float:
        return 2 * (self.yellow + self.all_red)


# Các bước chuyển hợp lệ giữa các khoảng (interval) — ngoài danh sách này đều bị từ chối.
_ALLOWED: set[tuple[Interval, Interval]] = {
    (Interval.GREEN, Interval.YELLOW),
    (Interval.YELLOW, Interval.ALL_RED),
    (Interval.ALL_RED, Interval.GREEN),
    (Interval.ALL_RED, Interval.ALL_RED),
    (Interval.ALL_RED, Interval.FLASHING),
    (Interval.FLASHING, Interval.ALL_RED),
}
# Chỉ cho phép khi phần cứng bộ điều khiển lỗi (bộ điều khiển hiện trường tự rơi về chớp vàng)
_EMERGENCY_ONLY: set[tuple[Interval, Interval]] = {
    (Interval.GREEN, Interval.FLASHING),
    (Interval.YELLOW, Interval.FLASHING),
}


class SafetyInterlockValidator:
    def __init__(self, timing: TimingConstraints) -> None:
        self.timing = timing.sanitized()

    def update_timing(self, timing: TimingConstraints) -> None:
        self.timing = timing.sanitized()

    # 1) Không xung đột -----------------------------------------------------------------------------------
    @staticmethod
    def conflicts_in(heads: dict[str, Color]) -> list[tuple[str, str]]:
        found = []
        for pair in CONFLICTS:
            a, b = sorted(pair)
            if heads.get(a) in OPEN_COLORS and heads.get(b) in OPEN_COLORS:
                found.append((a, b))
        return found

    def validate_heads(self, heads: dict[str, Color]) -> None:
        bad = self.conflicts_in(heads)
        if bad:
            pairs = ", ".join(f"{a}/{b}" for a, b in bad)
            raise InterlockViolation(f"Xung đột tín hiệu: các hướng cắt nhau cùng mở ({pairs})")

    # 2) Trình tự bắt buộc ----------------------------------------------------------------------------------
    def validate_transition(
        self,
        from_interval: Interval,
        from_phase: int,
        to_interval: Interval,
        to_phase: int,
        *,
        elapsed: float,
        emergency: bool = False,
    ) -> None:
        step = (from_interval, to_interval)
        if step not in _ALLOWED and not (emergency and step in _EMERGENCY_ONLY):
            raise InterlockViolation(
                f"Bước chuyển không hợp lệ {from_interval.value} → {to_interval.value}: "
                "bắt buộc GREEN → YELLOW_CLEARANCE → ALL_RED_CLEARANCE → GREEN"
            )
        if step == (Interval.GREEN, Interval.YELLOW):
            if to_phase != from_phase:
                raise InterlockViolation("Pha vàng phải thuộc cùng pha với pha xanh đang kết thúc")
            if elapsed + 1e-6 < self.timing.min_green:
                raise InterlockViolation(
                    f"Chưa đủ thời gian xanh tối thiểu ({elapsed:.1f}s < {self.timing.min_green:.0f}s)"
                )
        if step == (Interval.YELLOW, Interval.ALL_RED) and elapsed + 1e-6 < self.timing.yellow:
            raise InterlockViolation(f"Pha vàng chưa đủ {self.timing.yellow:.0f}s")
        if from_interval == Interval.ALL_RED and to_interval in (Interval.GREEN, Interval.FLASHING):
            if elapsed + 1e-6 < self.timing.all_red:
                raise InterlockViolation(f"Pha toàn đỏ chưa đủ {self.timing.all_red:.0f}s")

    # 3) Min/Max green ---------------------------------------------------------------------------------------
    def can_leave_green(self, elapsed: float) -> bool:
        return elapsed + 1e-6 >= self.timing.min_green

    def clamp_green(self, value: float) -> float:
        return float(min(max(value, self.timing.min_green), self.timing.max_green))
