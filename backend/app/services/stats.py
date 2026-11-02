"""Stats Recorder (US13-T01, US14-T01): gom số liệu theo bucket 5 phút và ghi CSDL."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.control_engine.phases import DIRECTIONS
from app.db.session import session_scope
from app.models.traffic import TrafficStat
from app.vision_engine.counter import PCU, CountEvent


def align_bucket(dt: datetime, minutes: int) -> datetime:
    dt = dt.astimezone(timezone.utc)
    m = (dt.minute // minutes) * minutes
    return dt.replace(minute=m, second=0, microsecond=0)


def local_midnight_utc(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(timezone.utc)).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


@dataclass
class _Acc:
    counts: Counter = field(default_factory=Counter)
    pcu: float = 0.0
    d_sum: float = 0.0
    d_n: int = 0
    d_max: float = 0.0
    q_sum: float = 0.0
    q_max: float = 0.0
    w_sum: float = 0.0
    w_n: int = 0


class StatsAccumulator:
    def __init__(self, intersection_id: int, bucket_minutes: int = 5) -> None:
        self.intersection_id = intersection_id
        self.bucket_minutes = bucket_minutes
        self.bucket_start = align_bucket(datetime.now(timezone.utc), bucket_minutes)
        self.acc: dict[str, _Acc] = {d: _Acc() for d in DIRECTIONS}
        self.modes: Counter = Counter()

    def add_events(self, direction: str, events: list[CountEvent]) -> None:
        a = self.acc[direction]
        for e in events:
            a.counts[e.cls] += 1
            a.pcu += e.pcu
            a.w_sum += e.wait_s
            a.w_n += 1

    def sample(self, direction: str, density: float, queue_m: float) -> None:
        a = self.acc[direction]
        a.d_sum += density
        a.d_n += 1
        a.d_max = max(a.d_max, density)
        a.q_sum += queue_m
        a.q_max = max(a.q_max, queue_m)

    def sample_mode(self, mode: str) -> None:
        self.modes[mode] += 1

    def maybe_flush(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if now < self.bucket_start + timedelta(minutes=self.bucket_minutes):
            return False
        self.flush()
        self.bucket_start = align_bucket(now, self.bucket_minutes)
        return True

    def flush(self) -> None:
        mode = self.modes.most_common(1)[0][0] if self.modes else "AUTO"
        rows = []
        for d, a in self.acc.items():
            if a.d_n == 0 and not a.counts:
                continue
            rows.append(
                TrafficStat(
                    intersection_id=self.intersection_id,
                    direction=d,
                    bucket_start=self.bucket_start,
                    bucket_minutes=self.bucket_minutes,
                    car=a.counts["car"],
                    motorbike=a.counts["motorbike"],
                    bus=a.counts["bus"],
                    truck=a.counts["truck"],
                    total=sum(a.counts.values()),
                    pcu=round(a.pcu, 2),
                    avg_density=round(a.d_sum / a.d_n, 2) if a.d_n else 0.0,
                    max_density=round(a.d_max, 2),
                    avg_queue_m=round(a.q_sum / a.d_n, 2) if a.d_n else 0.0,
                    max_queue_m=round(a.q_max, 2),
                    avg_wait_s=round(a.w_sum / a.w_n, 2) if a.w_n else 0.0,
                    mode=mode,
                )
            )
        if rows:
            with session_scope() as db:
                db.add_all(rows)
        self.acc = {d: _Acc() for d in DIRECTIONS}
        self.modes = Counter()

    def current(self, direction: str) -> dict:
        a = self.acc[direction]
        return {
            "bucket_start": self.bucket_start.isoformat(),
            "counts": {k: a.counts[k] for k in PCU},
            "avg_wait_s": round(a.w_sum / a.w_n, 1) if a.w_n else None,
        }


def load_today_totals(intersection_id: int) -> dict[str, dict[str, int]]:
    since = local_midnight_utc()
    out = {d: {k: 0 for k in PCU} for d in DIRECTIONS}
    with session_scope() as db:
        rows = (
            db.query(
                TrafficStat.direction,
                func.sum(TrafficStat.car), func.sum(TrafficStat.motorbike),
                func.sum(TrafficStat.bus), func.sum(TrafficStat.truck),
            )
            .filter(TrafficStat.intersection_id == intersection_id, TrafficStat.bucket_start >= since)
            .group_by(TrafficStat.direction)
            .all()
        )
    for d, car, moto, bus, truck in rows:
        if d in out:
            out[d] = {"car": int(car or 0), "motorbike": int(moto or 0), "bus": int(bus or 0), "truck": int(truck or 0)}
    return out
