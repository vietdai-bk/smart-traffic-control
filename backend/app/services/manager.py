"""Intersection Manager: quản lý N runtime nút giao trong một vòng lặp asyncio 10 Hz (NFR11, NFR13)."""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.orm import selectinload

from app.core.concurrency import runtime_lock
from app.core.config import settings
from app.core.events import bus
from app.db.session import session_scope
from app.models.intersection import Intersection
from app.services.runtime import IntersectionConfig, IntersectionRuntime

log = logging.getLogger("stcs.manager")


class IntersectionManager:
    def __init__(self) -> None:
        self.runtimes: dict[int, IntersectionRuntime] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self.loop_ms = 0.0
        self.tick_errors = 0
        self.started_at = time.time()
        self._t_summary = 0.0

    # ------------------------------------------------------------ lifecycle
    def load_all(self) -> None:
        with session_scope() as db:
            rows = (
                db.query(Intersection)
                .options(selectinload(Intersection.cameras))
                .filter(Intersection.is_active.is_(True))
                .order_by(Intersection.id)
                .all()
            )
            cfgs = [IntersectionConfig.from_model(r) for r in rows]
        for cfg in cfgs:
            self.runtimes[cfg.id] = IntersectionRuntime(cfg)
        log.info("Đã khởi tạo %d nút giao", len(self.runtimes))

    async def start(self) -> None:
        bus.bind_loop()
        self.load_all()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="stcs-runtime-loop")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        for rt in self.runtimes.values():
            try:
                rt.close()
            except Exception:  # pragma: no cover
                log.exception("Lỗi khi đóng runtime")

    def get(self, intersection_id: int) -> IntersectionRuntime | None:
        return self.runtimes.get(intersection_id)

    def reload(self, intersection_id: int) -> None:
        """Áp cấu hình mới từ CSDL cho runtime (tạo mới / cập nhật / gỡ bỏ)."""
        with session_scope() as db:
            row = (
                db.query(Intersection)
                .options(selectinload(Intersection.cameras))
                .filter(Intersection.id == intersection_id)
                .first()
            )
            cfg = IntersectionConfig.from_model(row) if row and row.is_active else None
        with runtime_lock:
            self._apply_reload(intersection_id, cfg)

    def _apply_reload(self, intersection_id: int, cfg: IntersectionConfig | None) -> None:
        rt = self.runtimes.get(intersection_id)
        if cfg is None:
            if rt:
                rt.close()
                self.runtimes.pop(intersection_id, None)
            return
        if rt is None:
            self.runtimes[intersection_id] = IntersectionRuntime(cfg)
        else:
            rt.apply_config(cfg)

    def remove(self, intersection_id: int) -> None:
        with runtime_lock:
            rt = self.runtimes.pop(intersection_id, None)
            if rt:
                rt.close()

    # ------------------------------------------------------------ loop
    async def _loop(self) -> None:
        period = 1.0 / settings.tick_hz
        last = time.time()
        while self._running:
            t0 = time.time()
            dt = min(max(t0 - last, 0.0), 0.25)
            last = t0
            # Giữ khoá trong cả tick: lệnh từ route (threadpool) không thể chen vào giữa bước chuyển FSM
            with runtime_lock:
                for rt in list(self.runtimes.values()):
                    try:
                        rt.tick(dt, t0)
                    except Exception:
                        # Tự phục hồi: lỗi một tick không làm dừng hệ thống (NFR13)
                        self.tick_errors += 1
                        log.exception("Lỗi tick nút giao %s", rt.id)
                self._t_summary += dt
                if self._t_summary >= 1.0:
                    self._t_summary = 0.0
                    bus.publish({"type": "summary", "data": self.summary()}, droppable=True)
            elapsed = time.time() - t0
            self.loop_ms = 0.9 * self.loop_ms + 0.1 * elapsed * 1000.0
            await asyncio.sleep(max(0.0, period - elapsed))

    def summary(self) -> list[dict]:
        return [rt.summary() for rt in self.runtimes.values()]

    def health(self) -> dict:
        return {
            "runtimes": len(self.runtimes),
            "loop_ms": round(self.loop_ms, 2),
            "tick_errors": self.tick_errors,
            "uptime_s": round(time.time() - self.started_at),
            "ws_clients": bus.subscriber_count,
        }


manager = IntersectionManager()
