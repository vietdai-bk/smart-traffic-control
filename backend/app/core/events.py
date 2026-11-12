"""Event bus nội bộ: runtime → WebSocket hub. Không chặn (non-blocking); khung hình có thể bị bỏ khi client chậm."""
from __future__ import annotations

import asyncio
import itertools
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

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def subscribe(self, username: str = "", role: str = "", maxsize: int = 256) -> Subscriber:
        sub = Subscriber(queue=asyncio.Queue(maxsize=maxsize), username=username, role=role)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    def has_listeners(self, intersection_id: int) -> bool:
        return any(s.intersection_id == intersection_id for s in self._subs)

    def publish(self, event: dict[str, Any], intersection_id: int | None = None, droppable: bool = False) -> None:
        """Gửi sự kiện tới các subscriber. intersection_id=None → gửi tới tất cả."""
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
