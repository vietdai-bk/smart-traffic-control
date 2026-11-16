"""Event bus nội bộ: runtime → WebSocket hub. Không chặn (non-blocking); khung hình có thể bị bỏ khi client chậm."""
from __future__ import annotations

import asyncio
import itertools
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    username: str = ""
    role: str = ""
    intersection_id: int | None = None
    id: int = field(default_factory=lambda: next(_ids))

    def wants(self, intersection_id: int | None) -> bool:
        return intersection_id is None or self.intersection_id == intersection_id


_ids = itertools.count(1)


class EventBus:
    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    def bind_loop(self) -> None:
        """Ghi nhận event loop đang chạy (gọi từ code async, vd. lúc khởi động)."""
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.get_ident()

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def subscribe(self, username: str = "", role: str = "", maxsize: int = 256) -> Subscriber:
        self.bind_loop()  # subscribe() luôn được gọi trên event loop (WebSocket handler)
        sub = Subscriber(queue=asyncio.Queue(maxsize=maxsize), username=username, role=role)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    def has_listeners(self, intersection_id: int) -> bool:
        return any(s.intersection_id == intersection_id for s in self._subs)

    def publish(self, event: dict[str, Any], intersection_id: int | None = None, droppable: bool = False) -> None:
        """Gửi sự kiện tới các subscriber. intersection_id=None → gửi tới tất cả.

        An toàn khi gọi từ thread khác (route đồng bộ trên threadpool): asyncio.Queue không thread-safe,
        nên khi không ở trên thread của event loop, việc đẩy vào queue được chuyển về loop qua
        call_soon_threadsafe để getter đang chờ được đánh thức đúng cách.
        """
        loop = self._loop
        if loop is not None and threading.get_ident() != self._loop_thread:
            if loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(self._publish_local, event, intersection_id, droppable)
            except RuntimeError:  # loop đã đóng
                pass
            return
        self._publish_local(event, intersection_id, droppable)

    def _publish_local(self, event: dict[str, Any], intersection_id: int | None, droppable: bool) -> None:
        if intersection_id is not None and "intersection_id" not in event:
            event["intersection_id"] = intersection_id
        for sub in list(self._subs):
            if not sub.wants(intersection_id):
                continue
            q = sub.queue
            if q.full():
                if droppable:
                    continue
                # Ưu tiên sự kiện quan trọng: bỏ phần tử cũ nhất để nhường chỗ
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


bus = EventBus()
