"""WebSocket hub /ws/live (US03-T02, US06-T04, NFR01, NFR05).

Client gửi {"type":"subscribe","intersection_id":N} để nhận snapshot (4 Hz) + frames (10 Hz) của nút giao;
các sự kiện toàn cục (alert, incident, summary, log) được gửi tới mọi client.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import bus
from app.core.rbac import Perm, has_perm
from app.core.deps import user_from_token
from app.db.session import SessionLocal
from app.services.manager import manager

log = logging.getLogger("stcs.ws")
router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket):
    token = ws.query_params.get("token")
    db = SessionLocal()
    try:
        user = user_from_token(db, token)
        identity = (user.username, user.role) if user else None
    finally:
        db.close()
    if identity is None or not (has_perm(identity[1], Perm.LIVE_VIEW) or has_perm(identity[1], Perm.STATS_VIEW)):
        await ws.close(code=4401)
        return
    # Người xem dữ liệu (không có live:view) chỉ nhận tổng hợp/cảnh báo, không nhận khung hình camera (NFR15)
    live_ok = has_perm(identity[1], Perm.LIVE_VIEW)
    await ws.accept()
    sub = bus.subscribe(username=identity[0], role=identity[1])
    await ws.send_text(json.dumps({"type": "hello", "user": identity[0], "summary": manager.summary()},
                                  ensure_ascii=False))

    async def receiver():
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "subscribe":
                iid = msg.get("intersection_id")
                sub.intersection_id = int(iid) if iid is not None else None
                rt = manager.get(sub.intersection_id) if sub.intersection_id else None
                if rt and live_ok:
                    await ws.send_text(json.dumps(rt.snapshot_message(), ensure_ascii=False))
            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong", "t": msg.get("t")}))

    async def sender():
        while True:
            event = await sub.queue.get()
            if not live_ok and event.get("type") in ("frames", "snapshot"):
                continue
            await ws.send_text(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    tasks = [asyncio.create_task(receiver()), asyncio.create_task(sender())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                log.debug("WebSocket đóng: %s", exc)
    finally:
        for t in tasks:
            t.cancel()
        bus.unsubscribe(sub)
