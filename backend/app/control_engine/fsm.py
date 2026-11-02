"""Signal Controller Finite State Machine (US08, US09-T04/T05, US10).

Trình tự bất biến: GREEN (≥ min green) → YELLOW_CLEARANCE → ALL_RED_CLEARANCE → GREEN(pha kế tiếp).
Mọi bước chuyển gọi `SafetyInterlockValidator` trước khi được chấp nhận; nếu vi phạm, FSM ép về toàn đỏ
và chuyển sang FAILSAFE.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace
from typing import Callable

from app.control_engine.phases import (
    DIRECTIONS,
    MODE_LABELS,
    PHASES,
    Color,
    Interval,
    Mode,
    heads_for,
    other_phase,
)
from app.control_engine.safety import InterlockViolation, SafetyInterlockValidator, TimingConstraints


@dataclass
class GreenPlan:
    green_ns: float
    green_ew: float
    source: str = "FIXED"  # FIXED | ADAPTIVE | MANUAL
    reason: str = ""
    cycle_s: float | None = None
    created_at: float = field(default_factory=time.time)

    def green_for(self, phase_id: int) -> float:
        return self.green_ns if phase_id == 1 else self.green_ew


@dataclass
class CommandResult:
    status: str  # ACCEPTED | SCHEDULED | EXECUTED | REJECTED
    message: str
    from_state: str
    to_state: str
    eta_s: float | None = None

    @property
    def ok(self) -> bool:
        return self.status != "REJECTED"


@dataclass
class TransitionEvent:
    prev_state: str
    new_state: str
    prev_interval: Interval
    new_interval: Interval
    phase_id: int
    heads: dict[str, Color]
    cause: str
    mode: Mode


@dataclass
class CycleRecord:
    started_at: float
    ended_at: float
    mode: str
    cycle_length_s: float
    green_ns_s: float
    green_ew_s: float
    yellow_s: float
    all_red_s: float
    plan_reason: str


class SignalControllerFSM:
    def __init__(
        self,
        timing: TimingConstraints,
        fixed_plan: GreenPlan,
        mode: Mode = Mode.AUTO,
        failsafe_strategy: str = "FIXED_TIME",
        on_transition: Callable[[TransitionEvent], None] | None = None,
        on_cycle: Callable[[CycleRecord], None] | None = None,
        on_violation: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.validator = SafetyInterlockValidator(timing)
        self.mode = Mode(mode) if mode != Mode.FAILSAFE else Mode.FIXED_TIME
        self.failsafe_strategy = failsafe_strategy
        self.fixed_plan = self._clamped(fixed_plan)
        self.active_plan = replace(self.fixed_plan)
        self.pending_plan: GreenPlan | None = None
        # Khởi động an toàn: toàn đỏ rồi mới sang pha 1
        self.phase_id = 2
        self.interval = Interval.ALL_RED
        self.next_phase_id = 1
        self.elapsed = 0.0
        self.green_target = self.fixed_plan.green_ns
        self.hold_phase: int | None = None
        self.hold_remaining: float | None = None
        self.hold_by: str | None = None
        self.scheduled_target: int | None = None
        self.scheduled_by: str | None = None
        self.flash_requested = False
        self.failsafe_reason: str | None = None
        self.on_transition = on_transition
        self.on_cycle = on_cycle
        self.on_violation = on_violation
        self.clock = clock
        self.last_violation: str | None = None
        # Theo dõi chu kỳ
        self._cycle_start: float | None = None
        self._acc = {"g1": 0.0, "g2": 0.0, "y": 0.0, "r": 0.0}

    # ---------------------------------------------------------------- helpers
    @property
    def timing(self) -> TimingConstraints:
        return self.validator.timing

    @property
    def state(self) -> str:
        return f"P{self.phase_id}:{self.interval.value}"

    @property
    def auto_locked(self) -> bool:
        return self.mode == Mode.FAILSAFE

    def heads(self) -> dict[str, Color]:
        return heads_for(self.phase_id, self.interval)

    def _clamped(self, plan: GreenPlan) -> GreenPlan:
        return replace(
            plan,
            green_ns=self.validator.clamp_green(plan.green_ns),
            green_ew=self.validator.clamp_green(plan.green_ew),
        )

    def _holding(self) -> bool:
        return (
            self.hold_phase is not None
            and self.hold_phase == self.phase_id
            and (self.hold_remaining is None or self.hold_remaining > 0)
        )

    def _result(self, status: str, message: str, before: str, eta: float | None = None) -> CommandResult:
        return CommandResult(status=status, message=message, from_state=before, to_state=self.state, eta_s=eta)

    # ---------------------------------------------------------------- core transition
    def _transition(self, to_interval: Interval, to_phase: int, cause: str, emergency: bool = False) -> None:
        prev_interval, prev_phase, prev_state = self.interval, self.phase_id, self.state
        self.validator.validate_transition(
            prev_interval, prev_phase, to_interval, to_phase, elapsed=self.elapsed, emergency=emergency
        )
        heads = heads_for(to_phase, to_interval)
        self.validator.validate_heads(heads)

        # Tích luỹ thời gian khoảng vừa kết thúc vào chu kỳ hiện tại
        self._accumulate(prev_interval, prev_phase, self.elapsed)

        if to_interval == Interval.GREEN:
            if to_phase == 1:
                self._close_cycle()
            self._apply_plan_at_green_start()
            self.green_target = self.validator.clamp_green(self.active_plan.green_for(to_phase))
        if to_interval == Interval.FLASHING:
            self._cycle_start = None
            self._acc = {"g1": 0.0, "g2": 0.0, "y": 0.0, "r": 0.0}

        self.interval = to_interval
        self.phase_id = to_phase
        self.elapsed = 0.0
        if self.on_transition:
            self.on_transition(
                TransitionEvent(prev_state, self.state, prev_interval, to_interval, to_phase, heads, cause, self.mode)
            )

    def _accumulate(self, interval: Interval, phase: int, duration: float) -> None:
        if self._cycle_start is None:
            return
        if interval == Interval.GREEN:
            self._acc[f"g{phase}"] += duration
        elif interval == Interval.YELLOW:
            self._acc["y"] += duration
        elif interval == Interval.ALL_RED:
            self._acc["r"] += duration

    def _close_cycle(self) -> None:
        now = self.clock()
        if self._cycle_start is not None and self.on_cycle and (self._acc["g1"] > 0 and self._acc["g2"] > 0):
            total = sum(self._acc.values())
            self.on_cycle(
                CycleRecord(
                    started_at=self._cycle_start,
                    ended_at=now,
                    mode=self.mode.value,
                    cycle_length_s=round(total, 1),
                    green_ns_s=round(self._acc["g1"], 1),
                    green_ew_s=round(self._acc["g2"], 1),
                    yellow_s=round(self._acc["y"] / 2, 1),
                    all_red_s=round(self._acc["r"] / 2, 1),
                    plan_reason=self.active_plan.reason,
                )
            )
        self._cycle_start = now
        self._acc = {"g1": 0.0, "g2": 0.0, "y": 0.0, "r": 0.0}

    def _apply_plan_at_green_start(self) -> None:
        """US09-T04: kế hoạch mới chỉ được áp dụng khi bắt đầu pha xanh tiếp theo."""
        if self.mode == Mode.AUTO and self.pending_plan is not None:
            self.active_plan = self._clamped(self.pending_plan)
            self.pending_plan = None
        elif self.mode in (Mode.FIXED_TIME, Mode.FAILSAFE):
            self.active_plan = replace(self.fixed_plan)

    def _safety_fallback(self, reason: str) -> None:
        """Vi phạm interlock: ép toàn đỏ (luôn an toàn) và chuyển FAILSAFE."""
        self.last_violation = reason
        prev_state = self.state
        self.interval = Interval.ALL_RED
        self.elapsed = 0.0
        self.next_phase_id = other_phase(self.phase_id)
        self.scheduled_target = None
        self.hold_phase = None
        self.hold_remaining = None
        self.mode = Mode.FAILSAFE
        self.failsafe_reason = f"Vi phạm khoá an toàn: {reason}"
        if self.on_violation:
            self.on_violation(reason)
        if self.on_transition:
            self.on_transition(
                TransitionEvent(
                    prev_state, self.state, Interval.ALL_RED, Interval.ALL_RED, self.phase_id,
                    heads_for(self.phase_id, Interval.ALL_RED), f"SAFETY_FALLBACK: {reason}", self.mode,
                )
            )

    # ---------------------------------------------------------------- tick
    def tick(self, dt: float) -> None:
        self.elapsed += dt
        if self.interval == Interval.GREEN and self._holding() and self.hold_remaining is not None:
            self.hold_remaining = max(0.0, self.hold_remaining - dt)
            if self.hold_remaining <= 0:
                self.hold_phase = None
                self.hold_remaining = None
                self.hold_by = None
        try:
            self._step()
        except InterlockViolation as exc:
            self._safety_fallback(str(exc))

    def _step(self) -> None:
        t = self.timing
        if self.interval == Interval.GREEN:
            if not self.validator.can_leave_green(self.elapsed):
                return
            if self.scheduled_target is not None:
                target = self.scheduled_target
                self.scheduled_target = None
                if target == self.phase_id:
                    return
                self.next_phase_id = target
                self._transition(Interval.YELLOW, self.phase_id, f"Lệnh chuyển pha ({self.scheduled_by or 'hệ thống'})")
                return
            if self.flash_requested:
                self.next_phase_id = other_phase(self.phase_id)
                self._transition(Interval.YELLOW, self.phase_id, "Chuẩn bị chớp vàng")
                return
            if self._holding() or self.mode == Mode.MANUAL:
                return
            if self.elapsed + 1e-6 >= self.green_target:
                self.next_phase_id = other_phase(self.phase_id)
                self._transition(Interval.YELLOW, self.phase_id, "Hết thời gian xanh")
        elif self.interval == Interval.YELLOW:
            if self.elapsed + 1e-6 >= t.yellow:
                self._transition(Interval.ALL_RED, self.phase_id, "Hết pha vàng")
        elif self.interval == Interval.ALL_RED:
            if self.elapsed + 1e-6 >= t.all_red:
                if self.flash_requested:
                    self._transition(Interval.FLASHING, self.phase_id, "Vào chế độ chớp vàng")
                else:
                    self._transition(Interval.GREEN, self.next_phase_id, "Hết pha toàn đỏ")
        elif self.interval == Interval.FLASHING:
            if not self.flash_requested:
                self._transition(Interval.ALL_RED, self.phase_id, "Thoát chớp vàng (qua toàn đỏ)")

    # ---------------------------------------------------------------- commands
    def _guarded(self, fn: Callable[[], CommandResult]) -> CommandResult:
        before = self.state
        try:
            return fn()
        except InterlockViolation as exc:
            return self._result("REJECTED", f"Khoá an toàn từ chối: {exc}", before)

    def goto_phase(self, target: int, by: str = "system") -> CommandResult:
        if target not in PHASES:
            return self._result("REJECTED", f"Pha {target} không tồn tại", self.state)

        def run() -> CommandResult:
            before = self.state
            t = self.timing
            if self.hold_phase is not None and self.hold_phase != target:
                self.hold_phase, self.hold_remaining, self.hold_by = None, None, None
            if self.interval == Interval.FLASHING:
                if self.mode == Mode.FAILSAFE and self.failsafe_strategy == "FLASHING_YELLOW":
                    return self._result("REJECTED", "Đang FAILSAFE chớp vàng — cần khôi phục hệ thống trước", before)
                self.flash_requested = False
                self.next_phase_id = target
                self._step()
                return self._result(
                    "ACCEPTED", f"Thoát chớp vàng → toàn đỏ {t.all_red:.0f}s → {PHASES[target].name}",
                    before, eta=t.all_red,
                )
            if self.interval == Interval.GREEN:
                if self.phase_id == target:
                    return self._result("ACCEPTED", f"{PHASES[target].name} đang xanh — không cần chuyển", before, 0)
                self.scheduled_target = target
                self.scheduled_by = by
                if self.validator.can_leave_green(self.elapsed):
                    self._step()
                    return self._result(
                        "EXECUTED",
                        f"Đã bắt đầu chuyển tiếp: Vàng {t.yellow:.0f}s → Toàn đỏ {t.all_red:.0f}s → {PHASES[target].name}",
                        before, eta=t.yellow + t.all_red,
                    )
                wait = t.min_green - self.elapsed
                return self._result(
                    "SCHEDULED",
                    f"Chưa đủ xanh tối thiểu {t.min_green:.0f}s — lệnh sẽ thực thi sau {wait:.1f}s",
                    before, eta=wait + t.yellow + t.all_red,
                )
            # Đang trong khoảng chuyển tiếp: chỉ đổi pha đích (vẫn đi qua toàn đỏ)
            self.next_phase_id = target
            remaining = (t.yellow - self.elapsed + t.all_red) if self.interval == Interval.YELLOW else (t.all_red - self.elapsed)
            return self._result(
                "ACCEPTED", f"Đang chuyển tiếp an toàn — pha kế tiếp: {PHASES[target].name}",
                before, eta=max(0.0, remaining),
            )

        return self._guarded(run)

    def next_phase(self, by: str = "system") -> CommandResult:
        if self.interval == Interval.GREEN:
            return self.goto_phase(other_phase(self.phase_id), by)
        if self.interval == Interval.FLASHING:
            return self.goto_phase(other_phase(self.phase_id), by)
        return self.goto_phase(self.next_phase_id, by)

    def hold_phase_cmd(self, target: int, duration_s: float | None, by: str = "system") -> CommandResult:
        if target not in PHASES:
            return self._result("REJECTED", f"Pha {target} không tồn tại", self.state)
        before = self.state
        if self.interval == Interval.FLASHING and self.mode == Mode.FAILSAFE:
            return self._result("REJECTED", "Đang FAILSAFE chớp vàng — không thể giữ pha", before)
        self.hold_phase = target
        self.hold_remaining = float(duration_s) if duration_s else None
        self.hold_by = by
        dur = f"{duration_s:.0f}s" if duration_s else "đến khi giải phóng"
        if self.interval == Interval.GREEN and self.phase_id == target:
            return self._result("EXECUTED", f"Giữ xanh khẩn cấp {PHASES[target].name} ({dur})", before, 0)
        res = self.goto_phase(target, by)
        if not res.ok:
            self.hold_phase, self.hold_remaining, self.hold_by = None, None, None
            return res
        self.hold_phase = target
        self.hold_remaining = float(duration_s) if duration_s else None
        self.hold_by = by
        return self._result(
            res.status if res.status != "EXECUTED" else "ACCEPTED",
            f"Giữ xanh khẩn cấp {PHASES[target].name} ({dur}). {res.message}", before, res.eta_s,
        )

    def release_hold(self, by: str = "system") -> CommandResult:
        before = self.state
        if self.hold_phase is None:
            return self._result("REJECTED", "Không có pha nào đang được giữ", before)
        self.hold_phase, self.hold_remaining, self.hold_by = None, None, None
        return self._result("EXECUTED", "Đã giải phóng giữ pha — trở lại điều khiển theo chế độ hiện tại", before)

    def extend_green(self, seconds: float, by: str = "system") -> CommandResult:
        before = self.state
        if self.interval != Interval.GREEN:
            return self._result("REJECTED", "Chỉ có thể kéo dài khi đang ở pha xanh", before)
        if self.mode == Mode.MANUAL:
            return self._result("REJECTED", "Chế độ thủ công: pha xanh được giữ đến khi có lệnh chuyển", before)
        if seconds <= 0:
            return self._result("REJECTED", "Số giây kéo dài phải > 0", before)
        new_target = min(self.green_target + seconds, self.timing.max_green)
        added = new_target - self.green_target
        if added <= 0:
            return self._result("REJECTED", f"Đã đạt xanh tối đa {self.timing.max_green:.0f}s", before)
        self.green_target = new_target
        capped = " (giới hạn bởi Max Green)" if added < seconds else ""
        return self._result("EXECUTED", f"Kéo dài xanh thêm {added:.0f}s{capped}", before)

    def set_fixed_timing(self, green_ns: float, green_ew: float, by: str = "system") -> CommandResult:
        before = self.state
        plan = self._clamped(GreenPlan(green_ns, green_ew, source="FIXED", reason=f"Thiết lập bởi {by}"))
        self.fixed_plan = plan
        note = ""
        if plan.green_ns != green_ns or plan.green_ew != green_ew:
            note = f" (đã kẹp vào [{self.timing.min_green:.0f}–{self.timing.max_green:.0f}]s)"
        return self._result(
            "ACCEPTED",
            f"Kế hoạch cố định: Bắc–Nam {plan.green_ns:.0f}s / Đông–Tây {plan.green_ew:.0f}s{note} — áp dụng từ pha xanh kế tiếp",
            before,
        )

    def set_flashing(self, on: bool, by: str = "system") -> CommandResult:
        before = self.state

        def run() -> CommandResult:
            if on:
                if self.interval == Interval.FLASHING:
                    return self._result("ACCEPTED", "Đang chớp vàng", before)
                self.flash_requested = True
                self.scheduled_target = None
                self._step()
                if self.interval == Interval.GREEN:
                    wait = self.timing.min_green - self.elapsed
                    return self._result("SCHEDULED", f"Chớp vàng sau khi đủ xanh tối thiểu ({wait:.1f}s) + Vàng + Toàn đỏ", before, wait)
                return self._result("ACCEPTED", "Chuyển chớp vàng qua trình tự Vàng → Toàn đỏ", before)
            if self.mode == Mode.FAILSAFE and self.failsafe_strategy == "FLASHING_YELLOW":
                return self._result("REJECTED", "Đang FAILSAFE chớp vàng — cần khôi phục hệ thống", before)
            if not self.flash_requested and self.interval != Interval.FLASHING:
                return self._result("REJECTED", "Không ở chế độ chớp vàng", before)
            self.flash_requested = False
            self._step()
            return self._result("ACCEPTED", f"Thoát chớp vàng → Toàn đỏ {self.timing.all_red:.0f}s → pha kế tiếp", before)

        return self._guarded(run)

    def set_mode(self, mode: Mode, by: str = "system") -> CommandResult:
        before = self.state
        mode = Mode(mode)
        if mode == Mode.FAILSAFE:
            return self._result("REJECTED", "FAILSAFE chỉ do hệ thống tự kích hoạt khi có sự cố", before)
        if self.mode == Mode.FAILSAFE:
            return self._result("REJECTED", "Hệ thống đang FAILSAFE — dùng chức năng Khôi phục sau khi khắc phục sự cố", before)
        if mode == self.mode:
            return self._result("ACCEPTED", f"Đang ở chế độ {MODE_LABELS[mode]}", before)
        prev = self.mode
        self.mode = mode
        msg = f"Chuyển {MODE_LABELS[prev]} → {MODE_LABELS[mode]}. Pha hiện tại tiếp tục an toàn"
        if mode == Mode.MANUAL:
            msg += "; pha xanh sẽ được giữ đến khi có lệnh"
        else:
            msg += "; thời gian mới áp dụng từ pha xanh kế tiếp"
        return self._result("EXECUTED", msg, before)

    def propose_plan(self, plan: GreenPlan) -> bool:
        """Thuật toán tự động đề xuất kế hoạch — bị khoá khi FAILSAFE hoặc không ở AUTO."""
        if self.mode != Mode.AUTO:
            return False
        self.pending_plan = self._clamped(plan)
        return True

    def enter_failsafe(self, reason: str, emergency_flash: bool = False) -> CommandResult:
        before = self.state
        self.mode = Mode.FAILSAFE
        self.failsafe_reason = reason
        self.pending_plan = None
        self.hold_phase, self.hold_remaining, self.hold_by = None, None, None
        self.scheduled_target = None
        strategy_flash = self.failsafe_strategy == "FLASHING_YELLOW" or emergency_flash
        self.flash_requested = strategy_flash
        try:
            if emergency_flash and self.interval in (Interval.GREEN, Interval.YELLOW):
                self._transition(Interval.FLASHING, self.phase_id, f"FAILSAFE khẩn cấp: {reason}", emergency=True)
            else:
                self._step()
        except InterlockViolation as exc:
            self._safety_fallback(str(exc))
        how = "chớp vàng" if strategy_flash else "chu kỳ cố định chuẩn"
        return self._result("EXECUTED", f"Kích hoạt FAILSAFE ({how}): {reason}", before)

    def recover(self, target_mode: Mode, by: str = "system") -> CommandResult:
        before = self.state
        if self.mode != Mode.FAILSAFE:
            return self._result("REJECTED", "Hệ thống không ở trạng thái FAILSAFE", before)
        target_mode = Mode(target_mode)
        if target_mode == Mode.FAILSAFE:
            return self._result("REJECTED", "Chế độ khôi phục không hợp lệ", before)
        self.mode = target_mode
        self.failsafe_reason = None
        self.last_violation = None
        self.flash_requested = False
        try:
            self._step()
        except InterlockViolation as exc:
            self._safety_fallback(str(exc))
        return self._result("EXECUTED", f"Đã khôi phục từ FAILSAFE → {MODE_LABELS[target_mode]}", before)

    def update_config(self, timing: TimingConstraints, fixed_plan: GreenPlan, failsafe_strategy: str) -> None:
        self.validator.update_timing(timing)
        self.fixed_plan = self._clamped(fixed_plan)
        self.failsafe_strategy = failsafe_strategy

    # ---------------------------------------------------------------- snapshot
    def green_remaining(self) -> float | None:
        if self.interval != Interval.GREEN:
            return None
        min_left = max(0.0, self.timing.min_green - self.elapsed)
        if self.scheduled_target is not None or self.flash_requested:
            return min_left
        if self._holding():
            if self.hold_remaining is None:
                return None
            return max(self.hold_remaining, self.green_target - self.elapsed, min_left)
        if self.mode == Mode.MANUAL:
            return None
        return max(0.0, self.green_target - self.elapsed, min_left)

    def interval_remaining(self) -> float | None:
        t = self.timing
        if self.interval == Interval.GREEN:
            return self.green_remaining()
        if self.interval == Interval.YELLOW:
            return max(0.0, t.yellow - self.elapsed)
        if self.interval == Interval.ALL_RED:
            return max(0.0, t.all_red - self.elapsed)
        return None

    def interval_duration(self) -> float | None:
        rem = self.interval_remaining()
        return None if rem is None else self.elapsed + rem

    def _head_remaining(self, direction: str) -> float | None:
        t = self.timing
        rem = self.interval_remaining()
        if rem is None:
            return None
        in_current = direction in PHASES[self.phase_id].greens
        in_next = direction in PHASES[self.next_phase_id].greens
        if self.interval == Interval.GREEN:
            return rem if in_current else rem + t.yellow + t.all_red
        if self.interval == Interval.YELLOW:
            if in_current:
                return rem
            return rem + t.all_red if in_next else None
        if self.interval == Interval.ALL_RED:
            if in_next:
                return rem
            nxt = self.validator.clamp_green(
                (self.pending_plan or self.active_plan).green_for(self.next_phase_id)
            )
            return rem + nxt + t.yellow + t.all_red
        return None

    def snapshot(self) -> dict:
        heads = self.heads()
        rem = self.interval_remaining()
        return {
            "mode": self.mode.value,
            "mode_label": MODE_LABELS[self.mode],
            "state": self.state,
            "phase_id": self.phase_id,
            "phase_name": PHASES[self.phase_id].name,
            "interval": self.interval.value,
            "elapsed": round(self.elapsed, 2),
            "remaining": None if rem is None else round(rem, 2),
            "duration": None if rem is None else round(self.elapsed + rem, 2),
            "green_target": round(self.green_target, 1),
            "next_phase_id": self.next_phase_id,
            "heads": {
                d: {
                    "color": heads[d].value,
                    "remaining": None if (r := self._head_remaining(d)) is None else round(r, 1),
                }
                for d in DIRECTIONS
            },
            "hold": None
            if self.hold_phase is None
            else {"phase_id": self.hold_phase, "remaining": self.hold_remaining, "by": self.hold_by},
            "scheduled": None
            if self.scheduled_target is None
            else {
                "phase_id": self.scheduled_target,
                "by": self.scheduled_by,
                "eta": round(max(0.0, self.timing.min_green - self.elapsed), 1),
            },
            "flash_requested": self.flash_requested,
            "failsafe_reason": self.failsafe_reason,
            "failsafe_strategy": self.failsafe_strategy,
            "auto_locked": self.auto_locked,
            "min_green_ok": self.interval == Interval.GREEN and self.validator.can_leave_green(self.elapsed),
            "timing": asdict(self.timing),
            "active_plan": _plan_dict(self.active_plan),
            "pending_plan": _plan_dict(self.pending_plan) if self.pending_plan else None,
            "fixed_plan": _plan_dict(self.fixed_plan),
            "last_violation": self.last_violation,
        }


def _plan_dict(plan: GreenPlan) -> dict:
    return {
        "green_ns": round(plan.green_ns, 1),
        "green_ew": round(plan.green_ew, 1),
        "source": plan.source,
        "reason": plan.reason,
        "cycle_s": None if plan.cycle_s is None else round(plan.cycle_s, 1),
    }
