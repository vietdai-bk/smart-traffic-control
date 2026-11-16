"""Đồng bộ truy cập trạng thái runtime giữa vòng lặp asyncio và threadpool của FastAPI.

Route `def` (đồng bộ) chạy trên threadpool, còn `IntersectionManager._loop` chạy trên event loop.
Mọi thao tác đọc-ghi FSM / runtime / supervisor từ HTTP phải giữ `runtime_lock`, và vòng lặp tick
cũng giữ khoá này trong suốt một tick, để lệnh tay không bao giờ chen vào giữa một bước chuyển FSM.

Lưu ý: không giữ khoá qua `await` (sẽ chặn event loop).
"""
from __future__ import annotations

import functools
import inspect
import threading
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)

runtime_lock = threading.RLock()


def with_runtime_lock(fn: F) -> F:
    """Decorator cho route FastAPI ĐỒNG BỘ: chạy toàn bộ handler dưới `runtime_lock`.

    Gắn sẵn chữ ký đã resolve annotation (eval_str) để FastAPI vẫn đọc đúng Depends/Body
    khi module dùng `from __future__ import annotations`.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError("with_runtime_lock chỉ dùng cho hàm đồng bộ; với async hãy dùng `with runtime_lock:` không qua await")

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with runtime_lock:
            return fn(*args, **kwargs)

    wrapper.__signature__ = inspect.signature(fn, eval_str=True)  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]
