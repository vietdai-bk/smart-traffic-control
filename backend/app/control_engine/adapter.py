"""Traffic Signal Controller Adapter (US08-T02/T03).

Lớp trừu tượng giữa phần mềm và bộ điều khiển đèn hiện trường. Mỗi trạng thái đèn được gửi xuống bộ điều khiển và
phải nhận ACK. `SimulatedSignalController` mô phỏng độ trễ mạng, heartbeat và lỗi phần cứng để kiểm thử.
Có thể thay bằng adapter NTCIP/UTMC/Modbus thật mà không đổi phần còn lại (NFR11).
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.control_engine.phases import Color


@dataclass
class Ack:
    ok: bool
    seq: int
    latency_ms: float
    error: str | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "seq": self.seq, "latency_ms": round(self.latency_ms, 1), "error": self.error}


class TrafficSignalControllerAdapter(ABC):
    def __init__(self, endpoint: str, model: str) -> None:
        self.endpoint = endpoint
        self.model = model
        self.last_heartbeat_at: float = time.time()
        self.last_ack: Ack | None = None
        self.consecutive_failures = 0

    @abstractmethod
    def apply_state(self, heads: dict[str, Color], mode: str) -> Ack: ...

    @abstractmethod
    def poll_heartbeat(self) -> bool: ...

    @abstractmethod
    def ping(self) -> Ack: ...

    @property
    @abstractmethod
    def fault(self) -> str | None: ...


class SimulatedSignalController(TrafficSignalControllerAdapter):
    """Bộ điều khiển đèn mô phỏng: phản hồi ACK 6–35 ms, heartbeat 1 Hz, giả lập mất kết nối / lỗi phần cứng."""

    def __init__(self, endpoint: str, model: str, seed: int | None = None) -> None:
        super().__init__(endpoint, model)
        self._rng = random.Random(seed)
        self._seq = 0
        self._fault: str | None = None  # None | OFFLINE | HARDWARE_FAULT
        self.applied_heads: dict[str, Color] = {}
        self._next_beat = 0.0

    @property
    def fault(self) -> str | None:
        return self._fault

    def inject_fault(self, fault: str | None) -> None:
        self._fault = fault

    def _latency(self) -> float:
        base = self._rng.uniform(6.0, 22.0)
        if self._rng.random() < 0.05:
            base += self._rng.uniform(10, 25)
        return base

    def apply_state(self, heads: dict[str, Color], mode: str) -> Ack:
        self._seq += 1
        if self._fault is not None:
            self.consecutive_failures += 1
            ack = Ack(False, self._seq, 1000.0, "TIMEOUT: bộ điều khiển không phản hồi")
        else:
            self.applied_heads = dict(heads)
            self.consecutive_failures = 0
            ack = Ack(True, self._seq, self._latency())
        self.last_ack = ack
        return ack

    def poll_heartbeat(self) -> bool:
        now = time.time()
        if self._fault is not None:
            return False
        if now >= self._next_beat:
            self.last_heartbeat_at = now
            self._next_beat = now + 1.0
        return True

    def ping(self) -> Ack:
        self._seq += 1
        if self._fault is not None:
            return Ack(False, self._seq, 1000.0, "TIMEOUT")
        return Ack(True, self._seq, self._latency())
