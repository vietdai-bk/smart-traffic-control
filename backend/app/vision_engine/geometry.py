"""Hiệu chuẩn camera (phối cảnh mặt đường) — dùng chung cho simulator, phân tích mật độ và frontend.

Camera gắn trên cần vươn, nhìn ngược chiều dòng xe đang tiến vào nút giao: xe đi từ xa (trên khung hình) về gần
(dưới khung hình), vạch dừng nằm ở `stop_y`. Toạ độ ảnh chuẩn hoá [0, 1].

    y(dist)  = y_h + A / (cam_offset + dist + d0)
    x(lat)   = 0.5 + lat · fx / (cam_offset + dist + d0)

`dist` là khoảng cách (m) từ vạch dừng ngược lên thượng lưu (âm = đã qua vạch).
Hàm ngược `dist_of(y)` cho phép quy đổi đáy bounding box sang mét (homography 1D) để đo hàng đợi & tốc độ.
"""
from __future__ import annotations

from dataclasses import dataclass

VISIBLE_FAR_M = 100.0
VISIBLE_NEAR_M = -8.0


@dataclass(frozen=True)
class CameraCalibration:
    lanes: int = 3
    lane_width: float = 3.5
    y_horizon: float = 0.12
    stop_y: float = 0.80
    d0: float = 20.0
    cam_offset: float = 12.0
    fx: float = 1.89

    @property
    def A(self) -> float:
        return (self.stop_y - self.y_horizon) * (self.cam_offset + self.d0)

    def _den(self, dist: float) -> float:
        return max(self.cam_offset + dist + self.d0, 1.0)

    def y_of(self, dist: float) -> float:
        return self.y_horizon + self.A / self._den(dist)

    def dist_of(self, y: float) -> float:
        dy = max(y - self.y_horizon, 1e-4)
        return self.A / dy - self.d0 - self.cam_offset

    def scale(self, dist: float) -> float:
        return self.fx / self._den(dist)

    def x_of(self, lateral_m: float, dist: float) -> float:
        return 0.5 + lateral_m * self.scale(dist)

    def lane_center(self, lane: int) -> float:
        """Làn 0 = sát dải phân cách; làn cuối = bên phải người lái (hiển thị bên trái khung hình)."""
        return ((self.lanes - 1) / 2.0 - lane) * self.lane_width

    @property
    def half_road(self) -> float:
        return self.lanes * self.lane_width / 2.0

    def project_box(self, dist_front: float, lateral: float, length: float, width: float, height: float):
        """Bounding box chuẩn hoá (x1, y1, x2, y2) của xe có đầu xe cách vạch dừng `dist_front` m."""
        y_front = self.y_of(dist_front)
        dist_rear = dist_front + length
        y_rear = self.y_of(dist_rear)
        s_front = self.scale(dist_front)
        s_rear = self.scale(dist_rear)
        half_w = width / 2.0
        x1 = 0.5 + (lateral - half_w) * s_front
        x2 = 0.5 + (lateral + half_w) * s_front
        # Chiều cao xe (khung nhìn từ trên cao → nén 0.5), quy đổi sang đơn vị y theo tỷ lệ 16:9
        h = height * s_rear * 0.5 * (16 / 9)
        return x1, y_rear - h, x2, y_front

    def roi_polygon(self, roi_length_m: float) -> list[list[float]]:
        far = roi_length_m
        hr = self.half_road
        return [
            [round(self.x_of(-hr, far), 4), round(self.y_of(far), 4)],
            [round(self.x_of(hr, far), 4), round(self.y_of(far), 4)],
            [round(self.x_of(hr, 0.0), 4), round(self.y_of(0.0), 4)],
            [round(self.x_of(-hr, 0.0), 4), round(self.y_of(0.0), 4)],
        ]

    def counting_line(self) -> list[list[float]]:
        hr = self.half_road
        return [[round(self.x_of(-hr, 0.0), 4), self.stop_y], [round(self.x_of(hr, 0.0), 4), self.stop_y]]

    def to_dict(self) -> dict:
        return {
            "lanes": self.lanes,
            "lane_width": self.lane_width,
            "y_horizon": self.y_horizon,
            "stop_y": self.stop_y,
            "d0": self.d0,
            "cam_offset": self.cam_offset,
            "fx": self.fx,
            "A": round(self.A, 4),
            "visible_far_m": VISIBLE_FAR_M,
        }


def polygon_y_range(poly: list[list[float]]) -> tuple[float, float]:
    ys = [p[1] for p in poly] or [0.0, 1.0]
    return min(ys), max(ys)


def point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside
