"""Kiểm thử bộ khoá an toàn & FSM (NFR06, US08-T04, US09-T05, US10-T04)."""
import random

import pytest

from app.control_engine.adaptive import AdaptivePlanner, ApproachDemand
from app.control_engine.fsm import GreenPlan, SignalControllerFSM
from app.control_engine.phases import OPEN_COLORS, Color, Interval, Mode
from app.control_engine.safety import InterlockViolation, SafetyInterlockValidator, TimingConstraints

TIMING = TimingConstraints(min_green=10, max_green=60, yellow=3, all_red=2, cycle_min=40, cycle_max=120)
DT = 0.1


def make_fsm(**kw):
    events = []
    fsm = SignalControllerFSM(TIMING, GreenPlan(30, 25), on_transition=events.append, **kw)
    return fsm, events


def run(fsm, seconds):
    for _ in range(int(round(seconds / DT))):
        fsm.tick(DT)


def test_conflict_detection():
    v = SafetyInterlockValidator(TIMING)
    with pytest.raises(InterlockViolation):
        v.validate_heads({"NORTH": Color.GREEN, "SOUTH": Color.RED, "EAST": Color.GREEN, "WEST": Color.RED})
    with pytest.raises(InterlockViolation):
        v.validate_heads({"NORTH": Color.YELLOW, "SOUTH": Color.RED, "EAST": Color.RED, "WEST": Color.GREEN})
    v.validate_heads({"NORTH": Color.GREEN, "SOUTH": Color.GREEN, "EAST": Color.RED, "WEST": Color.RED})


def test_illegal_sequences_rejected():
    v = SafetyInterlockValidator(TIMING)
    with pytest.raises(InterlockViolation):
        v.validate_transition(Interval.GREEN, 1, Interval.GREEN, 2, elapsed=30)
    with pytest.raises(InterlockViolation):
        v.validate_transition(Interval.GREEN, 1, Interval.ALL_RED, 1, elapsed=30)
    with pytest.raises(InterlockViolation):
        v.validate_transition(Interval.YELLOW, 1, Interval.GREEN, 2, elapsed=3)
    with pytest.raises(InterlockViolation):  # chưa đủ min green
        v.validate_transition(Interval.GREEN, 1, Interval.YELLOW, 1, elapsed=4)
    with pytest.raises(InterlockViolation):  # toàn đỏ chưa đủ
        v.validate_transition(Interval.ALL_RED, 1, Interval.GREEN, 2, elapsed=1)
    with pytest.raises(InterlockViolation):  # chớp vàng ngay từ xanh chỉ khi khẩn cấp
        v.validate_transition(Interval.GREEN, 1, Interval.FLASHING, 1, elapsed=30)
    v.validate_transition(Interval.GREEN, 1, Interval.FLASHING, 1, elapsed=30, emergency=True)


def test_hard_limits_cannot_be_configured_below_safety():
    t = TimingConstraints(min_green=1, yellow=1, all_red=0).sanitized()
    assert t.min_green >= 5 and t.yellow >= 3 and t.all_red >= 2


def test_normal_cycle_sequence():
    fsm, events = make_fsm(mode=Mode.FIXED_TIME)
    run(fsm, 200)
    seq = [(e.prev_interval, e.new_interval) for e in events]
    allowed = {
        (Interval.ALL_RED, Interval.GREEN),
        (Interval.GREEN, Interval.YELLOW),
        (Interval.YELLOW, Interval.ALL_RED),
    }
    assert set(seq) <= allowed
    greens = [e for e in events if e.new_interval == Interval.GREEN]
    assert [g.phase_id for g in greens[:4]] == [1, 2, 1, 2]


def test_manual_switch_before_min_green_is_scheduled():
    fsm, events = make_fsm(mode=Mode.MANUAL)
    run(fsm, 2.05)  # vào xanh pha 1
    assert fsm.interval == Interval.GREEN and fsm.phase_id == 1
    run(fsm, 3)
    res = fsm.goto_phase(2, by="operator")
    assert res.status == "SCHEDULED"
    run(fsm, 6.9)
    assert fsm.interval == Interval.GREEN, "Không được cắt xanh trước min green"
    run(fsm, 0.3)
    assert fsm.interval == Interval.YELLOW
    run(fsm, 3.05)
    assert fsm.interval == Interval.ALL_RED
    run(fsm, 2.05)
    assert fsm.interval == Interval.GREEN and fsm.phase_id == 2


def test_manual_mode_holds_green():
    fsm, _ = make_fsm(mode=Mode.MANUAL)
    run(fsm, 300)
    assert fsm.interval == Interval.GREEN and fsm.phase_id == 1


def test_randomized_commands_never_violate_safety():
    rng = random.Random(42)
    fsm, events = make_fsm(mode=Mode.AUTO)
    for step in range(30000):
        if rng.random() < 0.01:
            choice = rng.choice(["goto", "next", "hold", "release", "extend", "flash", "unflash", "mode", "plan", "failsafe", "recover"])
            if choice == "goto":
                fsm.goto_phase(rng.choice([1, 2]))
            elif choice == "next":
                fsm.next_phase()
            elif choice == "hold":
                fsm.hold_phase_cmd(rng.choice([1, 2]), rng.choice([None, 15, 40]))
            elif choice == "release":
                fsm.release_hold()
            elif choice == "extend":
                fsm.extend_green(rng.choice([5, 10, 30]))
            elif choice == "flash":
                fsm.set_flashing(True)
            elif choice == "unflash":
                fsm.set_flashing(False)
            elif choice == "mode":
                fsm.set_mode(rng.choice([Mode.AUTO, Mode.MANUAL, Mode.FIXED_TIME]))
            elif choice == "plan":
                fsm.propose_plan(GreenPlan(rng.uniform(0, 100), rng.uniform(0, 100), source="ADAPTIVE"))
            elif choice == "failsafe":
                fsm.enter_failsafe("test")
            elif choice == "recover":
                fsm.recover(Mode.AUTO)
        fsm.tick(DT)
        heads = fsm.heads()
        open_dirs = {d for d, c in heads.items() if c in OPEN_COLORS}
        assert not ({"NORTH", "SOUTH"} & open_dirs and {"EAST", "WEST"} & open_dirs), f"Xung đột tại bước {step}"
    assert fsm.last_violation is None
    for e in events:
        assert (e.prev_interval, e.new_interval) in {
            (Interval.ALL_RED, Interval.GREEN),
            (Interval.GREEN, Interval.YELLOW),
            (Interval.YELLOW, Interval.ALL_RED),
            (Interval.ALL_RED, Interval.FLASHING),
            (Interval.FLASHING, Interval.ALL_RED),
        }
    assert any(e.new_interval == Interval.GREEN for e in events)


def test_min_green_respected_in_event_stream():
    """Khoảng thời gian giữa ALL_RED→GREEN và GREEN→YELLOW kế tiếp luôn ≥ min green."""
    rng = random.Random(7)
    clock = {"t": 0.0}
    stamps = []
    fsm = SignalControllerFSM(TIMING, GreenPlan(30, 25), mode=Mode.MANUAL,
                              on_transition=lambda e: stamps.append((clock["t"], e)), clock=lambda: clock["t"])
    for _ in range(20000):
        if rng.random() < 0.02:
            fsm.next_phase()
        clock["t"] += DT
        fsm.tick(DT)
    green_at = None
    for ts, e in stamps:
        if e.new_interval == Interval.GREEN:
            green_at = ts
        elif e.new_interval == Interval.YELLOW and green_at is not None:
            assert ts - green_at >= TIMING.min_green - 1e-6
    assert len(stamps) > 20


def test_failsafe_locks_auto_and_requires_recover():
    fsm, _ = make_fsm(mode=Mode.AUTO)
    run(fsm, 15)
    fsm.enter_failsafe("Camera CAM-N mất kết nối")
    assert fsm.mode == Mode.FAILSAFE and fsm.auto_locked
    assert fsm.propose_plan(GreenPlan(50, 10)) is False
    assert fsm.set_mode(Mode.AUTO).status == "REJECTED"
    run(fsm, 120)  # vẫn chạy chu kỳ cố định
    assert fsm.recover(Mode.AUTO).ok
    assert fsm.mode == Mode.AUTO


def test_failsafe_flashing_strategy_goes_through_clearance():
    fsm, events = make_fsm(mode=Mode.AUTO, failsafe_strategy="FLASHING_YELLOW")
    run(fsm, 15)
    fsm.enter_failsafe("Lỗi thuật toán")
    run(fsm, 10)
    assert fsm.interval == Interval.FLASHING
    kinds = [(e.prev_interval, e.new_interval) for e in events][-3:]
    assert kinds == [
        (Interval.GREEN, Interval.YELLOW),
        (Interval.YELLOW, Interval.ALL_RED),
        (Interval.ALL_RED, Interval.FLASHING),
    ]


def test_adaptive_allocates_more_green_to_heavier_axis():
    planner = AdaptivePlanner(max_step_s=100)
    demand = {
        "NORTH": ApproachDemand("NORTH", 1500, 20, 80, 70),
        "SOUTH": ApproachDemand("SOUTH", 1200, 15, 60, 60),
        "EAST": ApproachDemand("EAST", 400, 2, 10, 15),
        "WEST": ApproachDemand("WEST", 350, 1, 5, 10),
    }
    res = planner.compute(demand, TIMING, lanes=3, saturation_flow=1800, prev=GreenPlan(30, 30))
    assert res.plan.green_ns > res.plan.green_ew
    assert TIMING.min_green <= res.plan.green_ew <= TIMING.max_green
    assert TIMING.min_green <= res.plan.green_ns <= TIMING.max_green
    assert TIMING.cycle_min - 1 <= res.cycle_s
    assert "Bắc–Nam" in res.reason
