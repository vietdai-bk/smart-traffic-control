"""Vehicle Detector (US05).

* `SyntheticDetector`: mô phỏng đầu ra của một mô hình phát hiện (YOLO-like) trên luồng camera tổng hợp — có nhiễu
  bounding box, confidence phụ thuộc kích thước/khoảng cách, bỏ sót, nhầm lớp và false positive. Có ground truth
  nên đo được Precision/Recall thực tế theo từng khung (US05-T04, NFR02).
* `YoloDetector`: suy luận YOLO thật (ultralytics) cho camera RTSP/HTTP/FILE — chỉ nạp khi thư viện có sẵn.
"""
from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass

CLASSES = ("car", "motorbike", "bus", "truck")
CONF_THRESHOLD = 0.35

# Ma trận nhầm lớp (xác suất bị gán sang lớp khác)
_CONFUSION = {
    "car": {"truck": 0.015},
    "motorbike": {"car": 0.004},
    "bus": {"truck": 0.04},
    "truck": {"bus": 0.03, "car": 0.01},
}


@dataclass
class Detection:
    box: tuple[float, float, float, float]
    cls: str
    conf: float
    gt_id: int | None = None


class VisionAlgorithmError(RuntimeError):
    pass


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class DetectionMetrics:
    """Theo dõi hiệu suất nhận diện trượt (cửa sổ ~10 giây)."""

    def __init__(self, window: int = 100) -> None:
        self.infer_ms: deque[float] = deque(maxlen=window)
        self.tp: deque[int] = deque(maxlen=window)
        self.fp: deque[int] = deque(maxlen=window)
        self.fn: deque[int] = deque(maxlen=window)
        self.conf: deque[float] = deque(maxlen=window)
        self.cls_ok: deque[int] = deque(maxlen=window)
        self.cls_total: deque[int] = deque(maxlen=window)

    def record(self, infer_ms: float, tp: int, fp: int, fn: int, avg_conf: float | None, cls_ok: int) -> None:
        self.infer_ms.append(infer_ms)
        self.tp.append(tp)
        self.fp.append(fp)
        self.fn.append(fn)
        self.cls_ok.append(cls_ok)
        self.cls_total.append(tp)
        if avg_conf is not None:
            self.conf.append(avg_conf)

    def summary(self) -> dict:
        tp, fp, fn = sum(self.tp), sum(self.fp), sum(self.fn)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        cls_total = sum(self.cls_total)
        return {
            "inference_ms": round(sum(self.infer_ms) / len(self.infer_ms), 3) if self.infer_ms else None,
            "precision": None if precision is None else round(precision, 4),
            "recall": None if recall is None else round(recall, 4),
            "f1": None if f1 is None else round(f1, 4),
            "avg_confidence": round(sum(self.conf) / len(self.conf), 4) if self.conf else None,
            "class_accuracy": round(sum(self.cls_ok) / cls_total, 4) if cls_total else None,
        }


class SyntheticDetector:
    name = "SimDet-YOLOv8n (synthetic)"

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.metrics = DetectionMetrics()
        self.fault = False

    def detect(self, objects: list[dict], degraded: bool = False) -> list[Detection]:
        if self.fault:
            raise VisionAlgorithmError("Mô hình nhận diện trả về tensor không hợp lệ (NaN) — lỗi suy luận")
        t0 = time.perf_counter()
        rng = self.rng
        dets: list[Detection] = []
        for obj in objects:
            x1, y1, x2, y2 = obj["box"]
            cy2 = min(y2, 1.0)
            w, h = x2 - x1, cy2 - y1
            if w <= 0 or h <= 0:
                continue
            area = w * h
            size_f = min(1.0, area / 0.004)
            p_detect = 0.70 + 0.29 * size_f - (0.15 if degraded else 0.0)
            if cy2 >= 0.995 and y2 > 1.05:
                p_detect -= 0.25  # bị cắt ở mép khung
            if rng.random() > p_detect:
                continue
            jit = 0.035 if degraded else 0.02
            jx, jy = w * jit, h * jit
            box = (
                x1 + rng.gauss(0, jx), y1 + rng.gauss(0, jy),
                x2 + rng.gauss(0, jx), cy2 + rng.gauss(0, jy * 0.6),
            )
            cls = obj["cls"]
            for other, p in _CONFUSION.get(cls, {}).items():
                if rng.random() < p * (2.5 if degraded else 1.0):
                    cls = other
                    break
            conf = rng.gauss(0.58 + 0.38 * size_f - (0.08 if degraded else 0), 0.05)
            conf = max(0.2, min(0.99, conf))
            if conf < CONF_THRESHOLD:
                continue
            dets.append(Detection(box, cls, conf, obj["id"]))
        # False positive hiếm
        if rng.random() < (0.03 if degraded else 0.008):
            cx, cy = rng.uniform(0.2, 0.8), rng.uniform(0.4, 0.9)
            s = rng.uniform(0.02, 0.05)
            dets.append(Detection((cx - s, cy - s * 0.8, cx + s, cy), rng.choice(CLASSES), rng.uniform(0.36, 0.48)))
        infer_ms = (time.perf_counter() - t0) * 1000.0
        self._evaluate(objects, dets, infer_ms)
        return dets

    def _evaluate(self, objects: list[dict], dets: list[Detection], infer_ms: float) -> None:
        """So khớp detection ↔ ground truth (IoU ≥ 0.5). Đối tượng quá nhỏ / bị cắt mạnh ở mép là "vùng bỏ qua":
        detection khớp với chúng không tính TP lẫn FP; bỏ sót chúng không tính FN."""

        def ignored(o: dict) -> bool:
            x1, y1, x2, y2 = o["box"]
            return y2 > 1.08 or (x2 - x1) * (min(y2, 1.0) - y1) < 0.0006

        gts = [(o, ignored(o)) for o in objects]
        used: set[int] = set()
        tp = cls_ok = ign = 0
        for d in sorted(dets, key=lambda x: -x.conf):
            best_j, best_iou = -1, 0.5
            for j, (g, _) in enumerate(gts):
                if j in used:
                    continue
                gb = (g["box"][0], g["box"][1], g["box"][2], min(g["box"][3], 1.0))
                v = iou(d.box, gb)
                if v >= best_iou:
                    best_j, best_iou = j, v
            if best_j < 0:
                continue
            used.add(best_j)
            g, is_ignored = gts[best_j]
            if is_ignored:
                ign += 1
                continue
            tp += 1
            cls_ok += int(g["cls"] == d.cls)
        fp = len(dets) - tp - ign
        fn = sum(1 for j, (_, is_ignored) in enumerate(gts) if not is_ignored and j not in used)
        avg_conf = sum(d.conf for d in dets) / len(dets) if dets else None
        self.metrics.record(infer_ms, tp, fp, fn, avg_conf, cls_ok)


class YoloDetector:
    """Bộ nhận diện YOLO thật (tuỳ chọn). Ánh xạ lớp COCO → 4 lớp của hệ thống."""

    COCO_MAP = {2: "car", 3: "motorbike", 5: "bus", 7: "truck"}

    def __init__(self, weights: str = "yolov8n.pt") -> None:
        from ultralytics import YOLO  # type: ignore  # noqa: WPS433 - import tuỳ chọn

        self.model = YOLO(weights)
        self.name = f"YOLO ({weights})"
        self.metrics = DetectionMetrics()
        self.fault = False

    def detect_frame(self, frame) -> list[Detection]:
        if self.fault:
            raise VisionAlgorithmError("Lỗi suy luận mô hình YOLO")
        t0 = time.perf_counter()
        h, w = frame.shape[:2]
        res = self.model.predict(frame, verbose=False, conf=CONF_THRESHOLD, classes=list(self.COCO_MAP))[0]
        dets = []
        for box, cls_id, conf in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            cls = self.COCO_MAP.get(int(cls_id))
            if cls:
                x1, y1, x2, y2 = box
                dets.append(Detection((x1 / w, y1 / h, x2 / w, y2 / h), cls, float(conf)))
        infer_ms = (time.perf_counter() - t0) * 1000.0
        avg_conf = sum(d.conf for d in dets) / len(dets) if dets else None
        self.metrics.record(infer_ms, 0, 0, 0, avg_conf, 0)
        return dets


def yolo_available() -> bool:
    try:
        import ultralytics  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False
