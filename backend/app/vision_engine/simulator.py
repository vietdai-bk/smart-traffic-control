"""Real-time Traffic Simulator cho nút giao 4 hướng (NFR14).

Mỗi hướng tiếp cận là một đoạn đường nhiều làn. Xe (car / motorbike / bus / truck) đến theo quá trình Poisson với
cường độ phụ thuộc giờ trong ngày, kịch bản và lưu lượng đột biến; di chuyển theo mô hình bám xe IDM; dừng trước vạch
khi đèn đỏ (hoặc vàng nếu đủ khoảng cách dừng), xả hàng khi đèn xanh. Xe máy có thể đi song song hai hàng trong một làn.

Simulator chỉ là "thế giới thật": hệ thống thị giác KHÔNG đọc trực tiếp trạng thái này mà nhận detection có nhiễu từ
`SyntheticDetector`, sau đó tự tracking / đếm / ước lượng mật độ như với camera thật.
"""
from __future__ import annotations

import itertools
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.control_engine.phases import DIRECTIONS, Color
from app.vision_engine.geometry import VISIBLE_FAR_M, VISIBLE_NEAR_M, CameraCalibration

VEHICLE_TYPES = ("car", "motorbike", "bus", "truck")

# length, width, height (m), desired speed (m/s), a_max, s0, T
SPECS = {
    "car": (4.5, 1.8, 1.5, 11.0, 2.0, 1.8, 1.2),
    "motorbike": (1.9, 0.75, 1.2, 10.0, 2.6, 0.9, 0.9),
    "bus": (11.0, 2.5, 3.1, 9.0, 1.2, 2.5, 1.5),
    "truck": (8.0, 2.4, 3.0, 8.5, 1.1, 2.5, 1.5),
}
MIX = {"motorbike": 0.60, "car": 0.29, "bus": 0.04, "truck": 0.07}
# Hệ số lưu lượng theo giờ địa phương (0–23h)
TOD_PROFILE = [0.25, 0.18, 0.15, 0.15, 0.2, 0.4, 0.8, 1.45, 1.6, 1.15, 0.95, 1.0,
               1.05, 0.95, 0.95, 1.05, 1.3, 1.6, 1.55, 1.1, 0.85, 0.7, 0.55, 0.38]
SCENARIOS = {
    "NORMAL": ("Bình thường (theo giờ thực)", None),
    "RUSH_HOUR": ("Giờ cao điểm", 1.6),
    "NIGHT": ("Ban đêm thấp điểm", 0.25),
    "EVENT": ("Sự kiện / tan tầm đột biến", 2.1),
}
SPAWN_DIST = 160.0
EXIT_DIST = -25.0
B_COMF = 3.0
YELLOW_DECEL = 4.0

_vid = itertools.count(1)


def tod_factor(now: datetime | None = None) -> float:
    now = now or datetime.now()
    h = now.hour + now.minute / 60.0
    i = int(h) % 24
    frac = h - int(h)
    return TOD_PROFILE[i] * (1 - frac) + TOD_PROFILE[(i + 1) % 24] * frac


@dataclass
class Vehicle:
    id: int
    vtype: str
    lane: int
    sub: int
    dist: float
    v: float
    v0: float
    a_max: float
    s0: float
    T: float
    length: float
    width: float
    height: float
    lateral: float
    color: int
    wait: float = 0.0
    crossed: bool = False
    stop_decision: bool | None = None
    braking: bool = False


@dataclass
class CrossingEvent:
    vtype: str
    wait_s: float


@dataclass
class ApproachSim:
    direction: str
    calib: CameraCalibration
    demand_vph: float
    rng: random.Random
    vehicles: list[Vehicle] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    crossings: list[CrossingEvent] = field(default_factory=list)
    spawned: int = 0

    @property
    def lanes(self) -> int:
        return self.calib.lanes

    def _pick_lane(self, vtype: str) -> int:
        n = self.lanes
        if n == 1:
            return 0
        if vtype == "motorbike":
            weights = [0.5 + i * 1.2 for i in range(n)]  # xe máy ưu tiên làn phải
        elif vtype in ("bus",):
            weights = [0.6 + (i == n - 1) * 1.5 + 0.4 for i in range(n)]
        elif vtype == "truck":
            weights = [1.5 - i * 0.4 for i in range(n)]
        else:
            weights = [1.4 - i * 0.3 for i in range(n)]
        weights = [max(w, 0.1) for w in weights]
        return self.rng.choices(range(n), weights=weights)[0]

    def _entry_free(self, lane: int, sub: int, length: float) -> bool:
        for veh in self.vehicles:
            if veh.lane != lane:
                continue
            if veh.vtype == "motorbike" and sub >= 0 and veh.sub >= 0 and veh.sub != sub:
                continue
            if veh.dist + veh.length > SPAWN_DIST - length - 4.0:
                return False
        return True

    def spawn(self, vtype: str) -> bool:
        length, width, height, v0, a_max, s0, T = SPECS[vtype]
        lane = self._pick_lane(vtype)
        sub = self.rng.choice((0, 1)) if vtype == "motorbike" else -1
        if not self._entry_free(lane, sub, length):
            # thử làn khác
            for alt in range(self.lanes):
                if self._entry_free(alt, sub, length):
                    lane = alt
                    break
            else:
                return False
        lat = self.calib.lane_center(lane)
        if sub >= 0:
            lat += (-0.85 if sub == 0 else 0.85) + self.rng.uniform(-0.15, 0.15)
        else:
            lat += self.rng.uniform(-0.2, 0.2)
        k = self.rng.uniform(0.88, 1.12)
        self.vehicles.append(
            Vehicle(
                id=next(_vid), vtype=vtype, lane=lane, sub=sub, dist=SPAWN_DIST, v=v0 * k * 0.9, v0=v0 * k,
                a_max=a_max, s0=s0, T=T, length=length, width=width, height=height, lateral=lat,
                color=self.rng.randrange(8),
            )
        )
        self.spawned += 1
        return True

    def _leader(self, veh: Vehicle, ordered: list[Vehicle]) -> Vehicle | None:
        best = None
        for other in ordered:
            if other is veh or other.lane != veh.lane or other.dist >= veh.dist:
                continue
            if veh.sub >= 0 and other.sub >= 0 and other.sub != veh.sub:
                continue  # xe máy hàng bên cạnh
            if best is None or other.dist > best.dist:
                best = other
        return best

    def step(self, dt: float, color: Color, rate_multiplier: float) -> None:
        # 1) Phát sinh xe (Poisson)
        lam = self.demand_vph * rate_multiplier / 3600.0
        n_new = _poisson(self.rng, lam * dt)
        for _ in range(n_new):
            self.pending.append(self.rng.choices(list(MIX), weights=list(MIX.values()))[0])
        if self.pending:
            remaining = []
            for vt in self.pending:
                if not self.spawn(vt):
                    remaining.append(vt)
            self.pending = remaining[-40:]

        # 2) Động học IDM
        ordered = sorted(self.vehicles, key=lambda x: x.dist)
        for veh in ordered:
            v0 = veh.v0
            must_stop = False
            if not veh.crossed:
                if color == Color.RED:
                    must_stop = True
                elif color == Color.YELLOW:
                    if veh.stop_decision is None:
                        need = veh.v * veh.v / (2 * YELLOW_DECEL) + 1.0
                        veh.stop_decision = veh.dist > need
                    must_stop = veh.stop_decision
                elif color == Color.FLASHING_YELLOW and veh.dist < 35:
                    v0 = min(v0, 5.5)
                if color == Color.GREEN:
                    veh.stop_decision = None

            leader = self._leader(veh, ordered)
            gap, dv = 1e9, 0.0
            if leader is not None:
                gap = veh.dist - (leader.dist + leader.length)
                dv = veh.v - leader.v
            if must_stop and veh.dist > -0.5:
                stop_gap = veh.dist - 0.6
                if stop_gap < gap:
                    gap, dv = stop_gap, veh.v
            s_star = veh.s0 + max(0.0, veh.v * veh.T + veh.v * dv / (2 * math.sqrt(veh.a_max * B_COMF)))
            acc = veh.a_max * (1 - (veh.v / max(v0, 0.1)) ** 4 - (s_star / max(gap, 0.05)) ** 2)
            acc = max(acc, -8.0)
            veh.braking = acc < -0.6
            veh.v = max(0.0, veh.v + acc * dt)
            veh.dist -= veh.v * dt
            if leader is not None:
                min_pos = leader.dist + leader.length + 0.3
                if veh.dist < min_pos:
                    veh.dist = min_pos
                    veh.v = min(veh.v, leader.v)
            if not veh.crossed:
                if veh.v < 1.0:
                    veh.wait += dt
                if veh.dist <= 0.0:
                    veh.crossed = True
                    self.crossings.append(CrossingEvent(veh.vtype, veh.wait))
        self.vehicles = [v for v in self.vehicles if v.dist > EXIT_DIST]

    def visible_objects(self) -> list[dict]:
        """Ground truth những xe nằm trong khung hình camera."""
        out = []
        for veh in self.vehicles:
            if veh.dist > VISIBLE_FAR_M or veh.dist + veh.length < VISIBLE_NEAR_M:
                continue
            x1, y1, x2, y2 = self.calib.project_box(veh.dist, veh.lateral, veh.length, veh.width, veh.height)
            if y1 >= 1.0 or x2 <= 0 or x1 >= 1:
                continue
            out.append(
                {
                    "id": veh.id,
                    "cls": veh.vtype,
                    "box": (x1, y1, x2, min(y2, 1.25)),
                    "dist": veh.dist,
                    "v": veh.v,
                    "color": veh.color,
                    "brake": veh.braking,
                }
            )
        return out

    def ground_truth_queue(self) -> tuple[int, float]:
        stopped = [v for v in self.vehicles if not v.crossed and v.v < 1.5 and v.dist < 120]
        if not stopped:
            return 0, 0.0
        return len(stopped), max(v.dist + v.length for v in stopped)


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class TrafficSimulator:
    """Mô phỏng 4 hướng của một nút giao."""

    def __init__(self, lanes: int, demand_ns: float, demand_ew: float, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.calib = CameraCalibration(lanes=lanes)
        self.demand_ns = demand_ns
        self.demand_ew = demand_ew
        asym = {"NORTH": 1.08, "SOUTH": 0.92, "EAST": 1.05, "WEST": 0.95}
        self.approaches: dict[str, ApproachSim] = {}
        for d in DIRECTIONS:
            base = demand_ns if d in ("NORTH", "SOUTH") else demand_ew
            self.approaches[d] = ApproachSim(d, self.calib, base * asym[d], random.Random(self.rng.random()))
        self.scenario = "NORMAL"
        self.surges: dict[str, tuple[float, float]] = {}  # direction -> (multiplier, until_ts)
        self.speed = 1.0
        self._prewarm()

    def set_demand(self, lanes: int, demand_ns: float, demand_ew: float) -> None:
        self.demand_ns, self.demand_ew = demand_ns, demand_ew
        asym = {"NORTH": 1.08, "SOUTH": 0.92, "EAST": 1.05, "WEST": 0.95}
        if lanes != self.calib.lanes:
            self.calib = CameraCalibration(lanes=lanes)
            for a in self.approaches.values():
                a.calib = self.calib
                a.vehicles.clear()
                a.pending.clear()
        for d, a in self.approaches.items():
            base = demand_ns if d in ("NORTH", "SOUTH") else demand_ew
            a.demand_vph = base * asym[d]

    def _prewarm(self) -> None:
        """Rải sẵn xe trên đường để khung hình không trống khi khởi động."""
        for a in self.approaches.values():
            # ~45 giây lưu lượng rải trên đoạn đường để khung hình có xe ngay khi khởi động
            n = int(a.demand_vph * self.multiplier(a.direction) / 3600.0 * 45)
            for _ in range(n):
                vt = a.rng.choices(list(MIX), weights=list(MIX.values()))[0]
                if a.spawn(vt):
                    a.vehicles[-1].dist = a.rng.uniform(2, SPAWN_DIST)
            a.vehicles.sort(key=lambda v: v.dist)
            # loại chồng lấn
            kept: list[Vehicle] = []
            for v in a.vehicles:
                if all(not (o.lane == v.lane and (o.sub == v.sub or o.sub < 0 or v.sub < 0)
                            and abs(o.dist - v.dist) < max(o.length, v.length) + 3) for o in kept):
                    kept.append(v)
            a.vehicles = kept

    def multiplier(self, direction: str, now_ts: float | None = None) -> float:
        now_ts = now_ts or time.time()
        _, fixed = SCENARIOS.get(self.scenario, SCENARIOS["NORMAL"])
        base = fixed if fixed is not None else tod_factor()
        surge = self.surges.get(direction)
        if surge:
            mult, until = surge
            if until and now_ts > until:
                self.surges.pop(direction, None)
            else:
                base *= mult
        return base

    def set_surge(self, directions: list[str], multiplier: float, duration_s: float | None) -> None:
        until = time.time() + duration_s if duration_s else 0.0
        for d in directions:
            if multiplier <= 1.0:
                self.surges.pop(d, None)
            else:
                self.surges[d] = (multiplier, until)

    def step(self, dt: float, heads: dict[str, Color]) -> None:
        now = time.time()
        for d, a in self.approaches.items():
            a.step(dt, heads.get(d, Color.RED), self.multiplier(d, now))

    def state(self) -> dict:
        now = time.time()
        return {
            "scenario": self.scenario,
            "scenario_label": SCENARIOS.get(self.scenario, SCENARIOS["NORMAL"])[0],
            "tod_factor": round(tod_factor(), 2),
            "surges": {
                d: {"multiplier": m, "remaining": (round(u - now) if u else None)} for d, (m, u) in self.surges.items()
            },
            "vehicles": {d: len(a.vehicles) for d, a in self.approaches.items()},
            "pending": {d: len(a.pending) for d, a in self.approaches.items()},
        }
