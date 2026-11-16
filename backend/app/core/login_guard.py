"""Chống dò mật khẩu mà không cho phép kẻ tấn công khoá tài khoản của người khác (NFR08).

Đếm lần sai theo cặp (tên đăng nhập, IP) chứ không theo tài khoản: một IP đoán sai 5 lần chỉ khoá chính
cặp đó, người dùng thật ở IP khác vẫn đăng nhập được. Thêm giới hạn theo IP (mọi tên đăng nhập) để chặn
một IP thử lần lượt nhiều tài khoản. Áp dụng như nhau cho tên không tồn tại → không lộ tài khoản có thật.

Trạng thái nằm trong bộ nhớ của tiến trình (backend chạy một tiến trình); khởi động lại sẽ xoá.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from app.core.config import settings

PER_IP_MAX_FAILS = 20
PER_IP_WINDOW_S = 10 * 60


class LoginGuard:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._pair_fails: dict[tuple[str, str], int] = {}
        self._pair_locked: dict[tuple[str, str], float] = {}
        self._ip_fails: dict[str, deque[float]] = {}
        self._ip_locked: dict[str, float] = {}

    @staticmethod
    def _key(username: str, ip: str) -> tuple[str, str]:
        return username.strip().lower(), ip

    def blocked_for(self, username: str, ip: str) -> float:
        """Số giây còn bị chặn (0 = được thử)."""
        now = self._clock()
        with self._lock:
            until = max(self._pair_locked.get(self._key(username, ip), 0.0), self._ip_locked.get(ip, 0.0))
        return max(0.0, until - now)

    def record_failure(self, username: str, ip: str) -> tuple[int, float]:
        """Ghi một lần sai. Trả về (số lần sai của cặp, số giây bị khoá nếu vừa bị khoá, ngược lại 0)."""
        now = self._clock()
        lock_s = settings.lockout_minutes * 60
        key = self._key(username, ip)
        with self._lock:
            n = self._pair_fails.get(key, 0) + 1
            locked = 0.0
            if n >= settings.max_failed_logins:
                self._pair_locked[key] = now + lock_s
                self._pair_fails.pop(key, None)
                locked = lock_s
            else:
                self._pair_fails[key] = n
            q = self._ip_fails.setdefault(ip, deque())
            q.append(now)
            while q and q[0] < now - PER_IP_WINDOW_S:
                q.popleft()
            if len(q) >= PER_IP_MAX_FAILS:
                self._ip_locked[ip] = now + lock_s
                q.clear()
                locked = lock_s
            self._prune(now)
            return n, locked

    def record_success(self, username: str, ip: str) -> None:
        with self._lock:
            self._pair_fails.pop(self._key(username, ip), None)

    def clear_user(self, username: str) -> None:
        """Admin mở khoá: xoá mọi bộ đếm/khoá của tên đăng nhập này ở mọi IP."""
        name = username.strip().lower()
        with self._lock:
            for d in (self._pair_fails, self._pair_locked):
                for k in [k for k in d if k[0] == name]:
                    del d[k]

    def reset(self) -> None:
        with self._lock:
            for d in (self._pair_fails, self._pair_locked, self._ip_fails, self._ip_locked):
                d.clear()

    def _prune(self, now: float) -> None:
        # Giữ bộ nhớ có giới hạn khi bị dò bằng nhiều tên/IP khác nhau
        for d in (self._pair_locked, self._ip_locked):
            for k in [k for k, until in d.items() if until <= now]:
                del d[k]
        for ip in [ip for ip, q in self._ip_fails.items() if not q or q[-1] < now - PER_IP_WINDOW_S]:
            del self._ip_fails[ip]
        if len(self._pair_fails) > 100_000:
            self._pair_fails.clear()


login_guard = LoginGuard()
