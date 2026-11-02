"""Density Analyzer (US07): occupancy ROI, PCU, hàng đợi, chỉ số mật độ 0–100 và phân loại mức độ."""
from __future__ import annotations

from dataclasses import dataclass

from app.vision_engine.counter import PCU
from app.vision_engine.tracker import Track

EFFECTIVE_LENGTH = {"car": 4.5, "motorbike": 1.1, "bus": 11.0, "truck": 8.0}
LEVELS = ("LOW", "MEDIUM", "HIGH")
LEVEL_LABELS = {"LOW": "Thông thoáng", "MEDIUM": "Đông đúc", "HIGH": "Ùn tắc"}


@dataclass
class DensityResult:
    in_roi: dict[str, int]
    roi_pcu: float
    occupancy: float
    queue_count: int
    queue_pcu: float
    queue_m: float
    density: float
    density_smoothed: float


def classify(value: float, medium: float, high: float, prev: str = "LOW", hysteresis: float = 4.0) -> str:
    """Phân loại có trễ: cần vượt ngưỡng để tăng mức, giảm dưới (ngưỡng − hysteresis) để hạ mức."""
    if prev == "HIGH":
        if value >= high - hysteresis:
            return "HIGH"
        return "MEDIUM" if value >= medium - hysteresis else "LOW"
    if prev == "MEDIUM":
        if value >= high:
            return "HIGH"
        return "MEDIUM" if value >= medium - hysteresis else "LOW"
    if value >= high:
        return "HIGH"
    if value >= medium:
        return "MEDIUM"
    return "LOW"


class DensityAnalyzer:
    def __init__(self, roi_length_m: float, lanes: int, tau_s: float = 8.0) -> None:
        self.roi_length_m = roi_length_m
        self.lanes = max(1, lanes)
        self.tau_s = tau_s
        self.smoothed = 0.0
        self.last: DensityResult | None = None

    def configure(self, roi_length_m: float, lanes: int) -> None:
        self.roi_length_m = roi_length_m
        self.lanes = max(1, lanes)

    def update(self, tracks: list[Track], dt: float) -> DensityResult:
        L = self.roi_length_m
        in_roi = {k: 0 for k in PCU}
        occ_len = 0.0
        roi_pcu = 0.0
        stopped: list[Track] = []
        for t in tracks:
            if t.dist is None:
                continue
            if t.stopped and 0.0 <= t.dist <= L * 1.5:
                stopped.append(t)
            if not (-1.0 <= t.dist <= L):
                continue
            in_roi[t.cls] = in_roi.get(t.cls, 0) + 1
            occ_len += EFFECTIVE_LENGTH.get(t.cls, 4.5)
            roi_pcu += PCU.get(t.cls, 1.0)
        occupancy = min(1.0, occ_len / (L * self.lanes))

        # Hàng đợi: chuỗi xe dừng liên tục (khoảng hở ≤ 20 m) bắt đầu từ xe dừng gần vạch nhất.
        # Không bắt buộc chuỗi bắt đầu tại vạch dừng: khi vừa bật xanh, đầu hàng đã chạy nhưng đuôi hàng vẫn đứng yên.
        stopped.sort(key=lambda t: t.dist or 0.0)
        queue_m = 0.0
        queue_count = 0
        queue_pcu = 0.0
        if stopped and (stopped[0].dist or 0.0) <= L * 0.8:
            front = stopped[0].dist or 0.0
            for t in stopped:
                d = t.dist or 0.0
                if d - front > 20.0:
                    break
                length = EFFECTIVE_LENGTH.get(t.cls, 4.5) if t.cls != "motorbike" else 1.9
                front = d + length
                queue_m = front
                queue_count += 1
                queue_pcu += PCU.get(t.cls, 1.0)
        queue_m = min(queue_m, L * 1.5)

        density = 100.0 * min(1.0, 0.55 * occupancy / 0.6 + 0.45 * min(queue_m / L, 1.0))
        alpha = min(1.0, dt / self.tau_s)
        self.smoothed += alpha * (density - self.smoothed)
        self.last = DensityResult(
            in_roi=in_roi,
            roi_pcu=round(roi_pcu, 2),
            occupancy=round(occupancy, 4),
            queue_count=queue_count,
            queue_pcu=round(queue_pcu, 2),
            queue_m=round(queue_m, 1),
            density=round(density, 1),
            density_smoothed=round(self.smoothed, 1),
        )
        return self.last
