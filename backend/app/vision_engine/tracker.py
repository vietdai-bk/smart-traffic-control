"""Multi-object tracker (IoU + centroid, greedy) với ước lượng khoảng cách/tốc độ nhờ hiệu chuẩn camera."""
from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass, field

from app.vision_engine.detector import Detection, iou
from app.vision_engine.geometry import CameraCalibration


@dataclass
class Track:
    id: int
    box: tuple[float, float, float, float]
    conf: float
    votes: Counter = field(default_factory=Counter)
    hits: int = 1
    misses: int = 0
    dist: float | None = None
    speed: float = 0.0
    stopped_time: float = 0.0
    prev_bottom: float | None = None
    counted: bool = False
    arrived: bool = False

    @property
    def cls(self) -> str:
        return self.votes.most_common(1)[0][0] if self.votes else "car"

    @property
    def bottom(self) -> float:
        return self.box[3]

    @property
    def confirmed(self) -> bool:
        return self.hits >= 2

    @property
    def stopped(self) -> bool:
        return self.confirmed and self.speed < 1.6


class CentroidTracker:
    def __init__(self, calib: CameraCalibration, iou_threshold: float = 0.15, max_misses: int = 6) -> None:
        self.calib = calib
        self.iou_threshold = iou_threshold
        self.max_misses = max_misses
        self.tracks: list[Track] = []
        self._ids = itertools.count(1)

    def reset(self) -> None:
        self.tracks.clear()

    def update(self, dets: list[Detection], dt: float) -> list[Track]:
        pairs = []
        for ti, t in enumerate(self.tracks):
            for di, d in enumerate(dets):
                v = iou(t.box, d.box)
                if v >= self.iou_threshold:
                    pairs.append((v, ti, di))
                else:
                    # dự phòng: khoảng cách tâm nhỏ so với kích thước
                    tcx, tcy = (t.box[0] + t.box[2]) / 2, (t.box[1] + t.box[3]) / 2
                    dcx, dcy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
                    size = max(t.box[2] - t.box[0], t.box[3] - t.box[1], 1e-3)
                    dd = ((tcx - dcx) ** 2 + (tcy - dcy) ** 2) ** 0.5
                    if dd < 0.5 * size and d.cls == t.cls:
                        pairs.append((0.1 - dd, ti, di))
        pairs.sort(reverse=True)
        used_t: set[int] = set()
        used_d: set[int] = set()
        for _, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            self._update_track(self.tracks[ti], dets[di], dt)
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.misses += 1
                t.prev_bottom = t.bottom
        for di, d in enumerate(dets):
            if di not in used_d:
                t = Track(id=next(self._ids), box=d.box, conf=d.conf)
                t.votes[d.cls] += 1
                t.dist = self.calib.dist_of(d.box[3])
                self.tracks.append(t)
        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses and t.box[1] < 1.0]
        # Trả về cả track "coasting" (mất ≤ 2 khung) để hàng đợi / mật độ không chập chờn khi detector bỏ sót
        return [t for t in self.tracks if t.confirmed and t.misses <= 2]

    def _update_track(self, t: Track, d: Detection, dt: float) -> None:
        a = 0.65
        t.prev_bottom = t.bottom
        t.box = tuple(a * n + (1 - a) * o for n, o in zip(d.box, t.box))  # type: ignore[assignment]
        t.conf = 0.7 * d.conf + 0.3 * t.conf
        t.votes[d.cls] += 1
        t.hits += 1
        t.misses = 0
        new_dist = self.calib.dist_of(d.box[3])
        if t.dist is None:
            t.dist = new_dist
            return
        prev = t.dist
        t.dist = 0.4 * new_dist + 0.6 * prev
        inst_speed = (prev - t.dist) / max(dt, 1e-3)
        t.speed = max(0.0, 0.3 * inst_speed + 0.7 * t.speed)
