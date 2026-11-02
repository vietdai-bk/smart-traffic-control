"""Camera Stream Manager (US03): kết nối nguồn camera, đo FPS/bitrate, trạng thái kết nối, tự động kết nối lại.

Nguồn hỗ trợ:
* SIMULATED — luồng tổng hợp từ TrafficSimulator (render phía client trên canvas).
* RTSP / HTTP / FILE — đọc bằng OpenCV trong thread riêng, suy luận YOLO (nếu có), phát MJPEG đã chú thích.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

from app.core.config import settings
from app.vision_engine.detector import Detection, YoloDetector, yolo_available

log = logging.getLogger("stcs.stream")

ONLINE, DEGRADED, OFFLINE, CONNECTING = "ONLINE", "DEGRADED", "OFFLINE", "CONNECTING"


def opencv_available() -> bool:
    try:
        import cv2  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class CameraInfo:
    id: int
    code: str
    name: str
    direction: str
    source_type: str
    stream_url: str
    resolution: str
    target_fps: int
    is_enabled: bool = True


class CameraStream:
    def __init__(self, info: CameraInfo, frame_hz: float) -> None:
        self.info = info
        self.frame_hz = frame_hz
        self.rng = random.Random(info.id)
        self.status = CONNECTING
        self.connected = False
        self.fault: str | None = None  # DISCONNECT | DEGRADE
        self.fps = 0.0
        self.frame_no = 0
        self.last_frame_at = 0.0
        self.connected_since: float | None = None
        self.reconnect_attempts = 0
        self.next_reconnect_at = 0.0
        self.error: str | None = None
        self.bitrate_kbps = 0.0
        self.latency_ms = 0.0
        self._last_ts: float | None = None
        self.real: OpenCVSource | None = None
        if info.source_type != "SIMULATED" and info.is_enabled:
            self.real = OpenCVSource(info)
        self._try_connect(time.time())

    # ------------------------------------------------------------- connection
    def _try_connect(self, now: float) -> bool:
        if not self.info.is_enabled:
            self.connected = False
            self.error = "Camera đã bị vô hiệu hoá"
            return False
        if self.info.source_type == "SIMULATED":
            ok = self.fault != "DISCONNECT"
            if not ok:
                self.error = "Không phản hồi RTSP DESCRIBE (timeout 3000 ms)"
        else:
            ok = self.real is not None and self.real.start()
            if not ok:
                self.error = self.real.error if self.real else "Nguồn không hợp lệ"
        if ok:
            self.connected = True
            self.connected_since = now
            self.reconnect_attempts = 0
            self.error = None
            self.last_frame_at = now
            self._last_ts = None
        else:
            self.connected = False
            self.reconnect_attempts += 1
            delay = min(settings.reconnect_base_s * (2 ** (self.reconnect_attempts - 1)), settings.reconnect_max_s)
            self.next_reconnect_at = now + delay
        return ok

    def force_reconnect(self) -> None:
        self.next_reconnect_at = 0.0
        if self.real is not None:
            self.real.stop()
        self.connected = False
        self._try_connect(time.time())

    def inject_fault(self, fault: str | None) -> None:
        self.fault = fault
        if fault == "DISCONNECT":
            self.connected = False
            self.error = "Mất tín hiệu video (RTSP session timeout)"
            self.next_reconnect_at = time.time() + settings.reconnect_base_s
        elif fault is None and not self.connected:
            self.next_reconnect_at = 0.0  # thử lại ngay

    def _mark_frame(self, now: float) -> None:
        self.frame_no += 1
        if self._last_ts is not None:
            inst = 1.0 / max(now - self._last_ts, 1e-3)
            self.fps = 0.85 * self.fps + 0.15 * inst if self.fps else inst
        self._last_ts = now
        self.last_frame_at = now
        w, h = self._res()
        bpp = 0.085 if self.fault != "DEGRADE" else 0.03
        self.bitrate_kbps = w * h * max(self.fps, 0.1) * bpp / 1000.0 * self.rng.uniform(0.92, 1.08)
        self.latency_ms = self.rng.uniform(38, 70) if self.fault != "DEGRADE" else self.rng.uniform(250, 600)

    def _res(self) -> tuple[int, int]:
        try:
            w, h = self.info.resolution.lower().split("x")
            return int(w), int(h)
        except ValueError:
            return 1280, 720

    # ------------------------------------------------------------- read
    def read_simulated(self, objects_fn, now: float) -> list[dict] | None:
        if not self.connected:
            if now >= self.next_reconnect_at:
                self._try_connect(now)
            if not self.connected:
                return None
        if self.fault == "DISCONNECT":
            self.connected = False
            return None
        if self.fault == "DEGRADE" and self.rng.random() < 0.68:
            return None
        self._mark_frame(now)
        return objects_fn()

    def read_real(self, now: float) -> list[Detection] | None:
        src = self.real
        if src is None:
            return None
        if not src.running:
            self.connected = False
            if now >= self.next_reconnect_at:
                self._try_connect(now)
            return None
        frame_no, dets, fps = src.poll()
        if frame_no is None or frame_no == self.frame_no:
            return None
        self.frame_no = frame_no - 1
        self._mark_frame(now)
        self.fps = fps or self.fps
        if self.fault == "DISCONNECT":
            return None
        return dets

    def evaluate(self, now: float) -> str:
        expected = min(float(self.info.target_fps), self.frame_hz)
        if not self.info.is_enabled:
            self.status = OFFLINE
        elif not self.connected or now - self.last_frame_at > settings.camera_timeout_s:
            if self.connected and now - self.last_frame_at > settings.camera_timeout_s:
                self.connected = False
                self.error = self.error or "Không nhận được khung hình (timeout)"
                self.next_reconnect_at = now + settings.reconnect_base_s
            self.status = OFFLINE
        elif self.fault == "DEGRADE" or (self.frame_no > 20 and self.fps < 0.6 * expected):
            self.status = DEGRADED
        else:
            self.status = ONLINE
        if self.status != OFFLINE:
            self.fps = self.fps if now - self.last_frame_at < 1.0 else self.fps * 0.8
        else:
            self.fps = 0.0
            self.bitrate_kbps = 0.0
        return self.status

    def snapshot(self, now: float) -> dict:
        w, h = self._res()
        return {
            "id": self.info.id,
            "code": self.info.code,
            "name": self.info.name,
            "direction": self.info.direction,
            "source_type": self.info.source_type,
            "status": self.status,
            "fps": round(self.fps, 1),
            "target_fps": self.info.target_fps,
            "resolution": f"{w}x{h}",
            "bitrate_kbps": round(self.bitrate_kbps),
            "latency_ms": round(self.latency_ms),
            "frame_no": self.frame_no,
            "fault": self.fault,
            "error": self.error,
            "reconnect_attempts": self.reconnect_attempts,
            "next_reconnect_in": round(max(0.0, self.next_reconnect_at - now), 1) if not self.connected else None,
            "uptime_s": round(now - self.connected_since) if self.connected and self.connected_since else 0,
            "mjpeg": self.info.source_type != "SIMULATED",
        }

    def close(self) -> None:
        if self.real is not None:
            self.real.stop()


class OpenCVSource:
    """Đọc RTSP/HTTP/FILE bằng OpenCV trong thread nền, suy luận YOLO, giữ JPEG đã chú thích mới nhất cho MJPEG."""

    def __init__(self, info: CameraInfo) -> None:
        self.info = info
        self.error: str | None = None
        self.running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame_no = 0
        self._dets: list[Detection] = []
        self._jpeg: bytes | None = None
        self._fps = 0.0
        self._stop = threading.Event()
        self.detector: YoloDetector | None = None

    def start(self) -> bool:
        if self.running:
            return True
        if not opencv_available():
            self.error = "Chưa cài OpenCV (pip install -r requirements-vision.txt)"
            return False
        import cv2  # type: ignore

        cap = cv2.VideoCapture(self.info.stream_url)
        if not cap.isOpened():
            self.error = f"Không mở được nguồn {self.info.source_type}: {self.info.stream_url}"
            cap.release()
            return False
        if self.detector is None and yolo_available():
            try:
                self.detector = YoloDetector()
            except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
                log.warning("Không nạp được YOLO: %s", exc)
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(cap,), daemon=True, name=f"cam-{self.info.code}")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self.running = False

    def _loop(self, cap) -> None:  # pragma: no cover - cần camera thật
        import cv2  # type: ignore

        last = time.time()
        interval = 1.0 / max(self.info.target_fps, 1)
        is_file = self.info.source_type == "FILE"
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.error = "Mất luồng video từ camera"
                break
            dets: list[Detection] = []
            if self.detector is not None:
                try:
                    dets = self.detector.detect_frame(frame)
                except Exception as exc:
                    self.error = str(exc)
            h, w = frame.shape[:2]
            for d in dets:
                x1, y1, x2, y2 = (int(d.box[0] * w), int(d.box[1] * h), int(d.box[2] * w), int(d.box[3] * h))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (16, 185, 129), 2)
                cv2.putText(frame, f"{d.cls} {d.conf:.2f}", (x1, max(12, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (16, 185, 129), 1)
            ok_j, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            now = time.time()
            with self._lock:
                self._frame_no += 1
                self._dets = dets
                if ok_j:
                    self._jpeg = buf.tobytes()
                inst = 1.0 / max(now - last, 1e-3)
                self._fps = 0.9 * self._fps + 0.1 * inst if self._fps else inst
            last = now
            if is_file:
                time.sleep(interval)
        cap.release()
        self.running = False

    def poll(self) -> tuple[int | None, list[Detection], float]:
        with self._lock:
            if self._frame_no == 0:
                return None, [], 0.0
            return self._frame_no, list(self._dets), self._fps

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg
