"""Vé kết nối ngắn hạn, dùng một lần, cho WebSocket và luồng MJPEG.

Trình duyệt không gửi được header Authorization cho `new WebSocket()` hay thẻ `<img>`, nên trước đây JWT
nằm trên query string và bị ghi vào access log (nginx/uvicorn), lịch sử trình duyệt… Thay vào đó client gọi
POST /api/auth/ticket (có Bearer) để lấy một vé ngẫu nhiên: chỉ dùng cho đúng một mục đích, hết hạn sau
TICKET_TTL_S giây và bị huỷ ngay khi dùng — lộ trong log cũng vô dụng.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

TICKET_TTL_S = 30.0
_MAX_OUTSTANDING = 10_000


@dataclass(frozen=True)
class _Ticket:
    user_id: int
    purpose: str
    expires_at: float


class TicketStore:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._tickets: dict[str, _Ticket] = {}

    def issue(self, user_id: int, purpose: str, ttl_s: float = TICKET_TTL_S) -> str:
        now = self._clock()
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._prune(now)
            if len(self._tickets) >= _MAX_OUTSTANDING:
                oldest = min(self._tickets, key=lambda k: self._tickets[k].expires_at)
                del self._tickets[oldest]
            self._tickets[ticket] = _Ticket(user_id, purpose, now + ttl_s)
        return ticket

    def consume(self, ticket: str | None, purpose: str) -> int | None:
        """Trả về user_id nếu vé hợp lệ cho mục đích này. Vé bị huỷ dù hợp lệ hay sai mục đích."""
        if not ticket:
            return None
        with self._lock:
            t = self._tickets.pop(ticket, None)
        if t is None or t.purpose != purpose or t.expires_at < self._clock():
            return None
        return t.user_id

    def _prune(self, now: float) -> None:
        for k in [k for k, t in self._tickets.items() if t.expires_at < now]:
            del self._tickets[k]


tickets = TicketStore()


def ws_purpose() -> str:
    return "ws:live"


def stream_purpose(camera_id: int) -> str:
    return f"stream:{camera_id}"
