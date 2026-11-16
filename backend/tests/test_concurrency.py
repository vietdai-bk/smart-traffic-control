"""Đồng bộ giữa threadpool (route `def`) và event loop (vòng tick, WebSocket)."""
import asyncio
import threading
import time

from app.core.concurrency import runtime_lock, with_runtime_lock
from app.core.events import EventBus


def test_publish_from_worker_thread_wakes_subscriber():
    async def main():
        bus = EventBus()
        sub = bus.subscribe()
        loop_thread = threading.get_ident()
        put_threads: list[int] = []
        orig_put = sub.queue.put_nowait

        def spy_put(item):
            put_threads.append(threading.get_ident())
            orig_put(item)

        sub.queue.put_nowait = spy_put
        waiter = asyncio.create_task(sub.queue.get())
        await asyncio.sleep(0)
        t = threading.Thread(target=bus.publish, args=({"type": "command"}, None))
        t.start()
        t.join()
        event = await asyncio.wait_for(waiter, timeout=1.0)
        # asyncio.Queue không thread-safe: chỉ được ghi trên thread của event loop
        assert put_threads == [loop_thread]
        return event

    assert asyncio.run(main())["type"] == "command"


def test_route_waits_while_tick_holds_lock():
    order: list[str] = []

    @with_runtime_lock
    def route():
        order.append("route")

    with runtime_lock:
        t = threading.Thread(target=route)
        t.start()
        time.sleep(0.05)
        order.append("tick-end")
    t.join()
    assert order == ["tick-end", "route"]
