"""Directional Counter (US06): đếm xe qua vạch đếm, đếm xe đi vào ROI (lưu lượng đến) và đo thời gian chờ."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from app.vision_engine.tracker import Track

PCU = {"car": 1.0, "motorbike": 0.3, "bus": 2.5, "truck": 2.0}


@dataclass
class CountEvent:
    ts: float
    cls: str
    pcu: float
    wait_s: float


class DirectionalCounter:
    def __init__(self, line_y: float, roi_top_y: float, roi_length_m: float) -> None:
        self.line_y = line_y
        self.roi_top_y = roi_top_y
        self.roi_length_m = roi_length_m
        self.totals = {k: 0 for k in PCU}
        self.events: deque[CountEvent] = deque()
        self.arrivals: deque[tuple[float, float]] = deque()

    def configure(self, line_y: float, roi_top_y: float, roi_length_m: float) -> None:
        self.line_y, self.roi_top_y, self.roi_length_m = line_y, roi_top_y, roi_length_m

    def update(self, tracks: list[Track], dt: float, now: float | None = None) -> list[CountEvent]:
        now = now or time.time()
        new: list[CountEvent] = []
        for t in tracks:
            in_zone = t.dist is not None and -2.0 <= t.dist <= self.roi_length_m + 25
            if in_zone and t.stopped and not t.counted:
                t.stopped_time += dt
            if not t.arrived and t.dist is not None and t.dist <= self.roi_length_m:
                t.arrived = True
                # Chỉ tính là xe mới đến nếu track xuất hiện gần mép trên ROI hoặc cắt qua mép trên;
                # track sinh ra sâu trong ROI thường là do đổi ID (ID switch) → không đếm lặp.
                crossed_top = t.prev_bottom is not None and t.prev_bottom < self.roi_top_y <= t.bottom
                if crossed_top or t.dist >= self.roi_length_m - 18:
                    self.arrivals.append((now, PCU.get(t.cls, 1.0)))
            if not t.counted and t.prev_bottom is not None and t.prev_bottom < self.line_y <= t.bottom:
                t.counted = True
                ev = CountEvent(now, t.cls, PCU.get(t.cls, 1.0), t.stopped_time)
                self.totals[t.cls] = self.totals.get(t.cls, 0) + 1
                self.events.append(ev)
                new.append(ev)
        cutoff = now - 3600
        while self.events and self.events[0].ts < cutoff:
            self.events.popleft()
        while self.arrivals and self.arrivals[0][0] < now - 600:
            self.arrivals.popleft()
        return new

    def window(self, seconds: float, now: float | None = None) -> list[CountEvent]:
        now = now or time.time()
        cutoff = now - seconds
        return [e for e in self.events if e.ts >= cutoff]

    def flow_vph(self, seconds: float = 300, now: float | None = None, uptime: float | None = None) -> float:
        span = max(min(seconds, uptime), 30.0) if uptime else seconds
        return len(self.window(span, now)) * 3600.0 / span

    def arrival_pcu_h(self, seconds: float = 180, now: float | None = None, uptime: float | None = None) -> float:
        now = now or time.time()
        span = min(seconds, uptime) if uptime else seconds
        span = max(span, 30.0)
        total = sum(p for ts, p in self.arrivals if ts >= now - span)
        return total * 3600.0 / span

    def avg_wait(self, seconds: float = 300, now: float | None = None) -> float | None:
        evs = self.window(seconds, now)
        return sum(e.wait_s for e in evs) / len(evs) if evs else None

    def by_class(self, seconds: float, now: float | None = None) -> dict[str, int]:
        out = {k: 0 for k in PCU}
        for e in self.window(seconds, now):
            out[e.cls] = out.get(e.cls, 0) + 1
        return out
