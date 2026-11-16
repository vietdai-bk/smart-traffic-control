"""LLM Supervisor — TẦNG 3 của kiến trúc điều khiển 3 tầng.

    Tầng 3  LLM Supervisor (Groq)   30–60 s / theo sự kiện   → chọn CHIẾN LƯỢC + TRỌNG SỐ 2 trục
    Tầng 2  AdaptivePlanner (Webster) mỗi giây                → tính chu kỳ & thời gian xanh cụ thể
    Tầng 1  SafetyInterlock + FSM     mọi trạng thái đèn      → kẹp giới hạn, ma trận xung đột, fail-safe

LLM KHÔNG BAO GIỜ đặt trực tiếp thời gian pha hay trạng thái đèn. Đầu ra là JSON theo schema cố định, được kiểm tra
(`validate_proposal`) rồi mới thành trọng số (0.5–2.0) cho Webster. LLM lỗi / timeout / sai schema → giữ chiến lược hiện
tại, hệ thống vẫn chạy bình thường bằng tầng 2 (NFR07). Chiến lược có thời hạn, hết hạn tự quay về cân bằng.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.audit import audit
from app.core.concurrency import runtime_lock
from app.core.config import settings
from app.core.events import bus
from app.db.session import session_scope
from app.llm.client import LLMError, cap, chat, is_configured
from app.models.alert import Alert
from app.models.llm import LlmDecision

if TYPE_CHECKING:  # pragma: no cover
    from app.services.runtime import IntersectionRuntime

log = logging.getLogger("stcs.llm")

MODES = ("OFF", "ADVISORY", "AUTONOMOUS")
MODE_LABELS = {"OFF": "Tắt", "ADVISORY": "Tư vấn (cần duyệt)", "AUTONOMOUS": "Tự động"}
STRATEGIES = {
    "BALANCED": "Cân bằng hai trục",
    "PRIORITIZE_NS": "Ưu tiên trục Bắc–Nam",
    "PRIORITIZE_EW": "Ưu tiên trục Đông–Tây",
    "PEAK_HOUR": "Giờ cao điểm – ưu tiên trục chính",
    "INCIDENT_MODE": "Bất thường – giữ cân bằng thận trọng",
}
W_MIN, W_MAX, W_STEP = 0.5, 2.0, 0.5
DUR_MIN, DUR_MAX = 2.0, 30.0

SYSTEM_PROMPT = f"""Bạn là LLM Supervisor (tầng 3) của hệ thống điều khiển đèn giao thông thích ứng tại một nút giao 4 nhánh ở Việt Nam.
Bên dưới bạn là thuật toán Webster (tầng 2) tính thời gian xanh và bộ khoá an toàn (tầng 1). Bạn KHÔNG đặt thời gian pha.
Nhiệm vụ: dựa trên số liệu camera, chọn chiến lược và trọng số ưu tiên cho 2 trục (Bắc–Nam = NS, Đông–Tây = EW).
Trọng số nhân vào tỷ số lưu lượng khi chia thời gian xanh: 1.0 = trung lập, >1 = ưu tiên thêm, <1 = giảm ưu tiên.

Chỉ trả lời DUY NHẤT một JSON object, không thêm chữ nào khác, theo schema:
{{
  "strategy": one of {list(STRATEGIES)},
  "weight_ns": number {W_MIN}–{W_MAX},
  "weight_ew": number {W_MIN}–{W_MAX},
  "duration_min": number {DUR_MIN:.0f}–{DUR_MAX:.0f} (thời gian hiệu lực của chiến lược),
  "reason": "1–2 câu tiếng Việt, nêu số liệu cụ thể làm căn cứ"
}}
Quy tắc:
- Webster đã tự cân theo nhu cầu; chỉ lệch trọng số khi có lý do rõ: hàng đợi/thời gian chờ chênh lệch lớn, xu hướng tăng nhanh, cảnh báo ùn tắc kéo dài, giờ cao điểm.
- Nếu hai trục tương đương hoặc dữ liệu không chắc chắn → BALANCED, trọng số 1.0/1.0.
- PRIORITIZE_NS thì weight_ns > weight_ew; PRIORITIZE_EW thì weight_ew > weight_ns.
- Có sự cố thiết bị/camera (health_issues) → INCIDENT_MODE với trọng số gần 1.0.
- Không thay đổi trọng số quá {W_STEP} so với hiện tại trong một lần. Không suy đoán số liệu không được cung cấp."""


class ProposalInvalid(Exception):
    pass


@dataclass
class SupervisorState:
    mode: str = "ADVISORY"
    strategy: str = "BALANCED"
    weight_ns: float = 1.0
    weight_ew: float = 1.0
    reason: str = ""
    source: str = ""            # LLM | ASSISTANT | OPERATOR
    applied_at: float | None = None
    expires_at: float | None = None
    decision_id: int | None = None
    pending: dict | None = None
    last: dict | None = None
    last_run: float = 0.0
    running: bool = False
    last_error: str | None = None
    last_level: str = "LOW"
    last_saturated: bool = False
    history: deque = field(default_factory=lambda: deque(maxlen=120))  # (ts, demand_ns, demand_ew)

    def active_weights(self, now: float) -> tuple[float, float]:
        if self.expires_at is not None and now >= self.expires_at:
            self.reset("Chiến lược hết hiệu lực → quay về cân bằng")
        return self.weight_ns, self.weight_ew

    def reset(self, why: str = "") -> None:
        self.strategy, self.weight_ns, self.weight_ew = "BALANCED", 1.0, 1.0
        self.reason, self.source, self.expires_at, self.decision_id = why, "", None, None
        self.applied_at = None

    def apply(self, p: dict, source: str, decision_id: int | None, now: float) -> None:
        self.strategy = p["strategy"]
        self.weight_ns, self.weight_ew = p["weight_ns"], p["weight_ew"]
        self.reason = p["reason"]
        self.source = source
        self.applied_at = now
        self.expires_at = now + p["duration_min"] * 60.0
        self.decision_id = decision_id

    def note(self) -> str:
        return STRATEGIES.get(self.strategy, self.strategy)

    def sample(self, now: float, demand_ns: float, demand_ew: float) -> None:
        if not self.history or now - self.history[-1][0] >= 10:
            self.history.append((now, demand_ns, demand_ew))

    def trend(self, now: float, window_s: float = 300) -> dict:
        old = [h for h in self.history if now - h[0] >= window_s]
        if not old or not self.history:
            return {"window_min": window_s / 60, "demand_ns_change_pct": None, "demand_ew_change_pct": None}
        a, b = old[-1], self.history[-1]

        def pct(x, y):
            return round((y - x) / max(x, 1.0) * 100, 1)

        return {"window_min": window_s / 60, "demand_ns_change_pct": pct(a[1], b[1]),
                "demand_ew_change_pct": pct(a[2], b[2])}

    def to_dict(self, now: float) -> dict:
        pending = None
        if self.pending:
            pending = {**self.pending, "expires_in_s": max(0, round(self.pending["expires_at"] - now))}
        return {
            "enabled": is_configured(),
            "model": settings.llm_model,
            "mode": self.mode,
            "mode_label": MODE_LABELS.get(self.mode, self.mode),
            "strategy": self.strategy,
            "strategy_label": self.note(),
            "weight_ns": round(self.weight_ns, 2),
            "weight_ew": round(self.weight_ew, 2),
            "reason": self.reason,
            "source": self.source,
            "expires_in_s": None if self.expires_at is None else max(0, round(self.expires_at - now)),
            "decision_id": self.decision_id,
            "pending": pending,
            "last": self.last,
            "running": self.running,
            "last_error": self.last_error,
            "next_run_in_s": max(0, round(self.last_run + settings.llm_interval_s - now)) if self.mode != "OFF" else None,
        }


# ---------------------------------------------------------------------------------------------- validation
def validate_proposal(data: dict, current: tuple[float, float]) -> tuple[dict, list[str]]:
    """Lớp kiểm tra đầu ra LLM: schema, miền giá trị, tính nhất quán, biên độ thay đổi."""
    notes: list[str] = []
    strategy = str(data.get("strategy", "")).strip().upper()
    if strategy not in STRATEGIES:
        raise ProposalInvalid(f"strategy '{strategy}' không thuộc danh sách cho phép")
    try:
        w_ns, w_ew = float(data["weight_ns"]), float(data["weight_ew"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProposalInvalid("thiếu hoặc sai kiểu weight_ns/weight_ew") from exc
    if not all(math.isfinite(x) for x in (w_ns, w_ew)):
        raise ProposalInvalid("trọng số không hữu hạn")
    reason = str(data.get("reason", "")).strip()
    if not reason:
        raise ProposalInvalid("thiếu lý do (reason)")
    try:
        dur = float(data.get("duration_min", 10))
    except (TypeError, ValueError):
        dur = 10.0
        notes.append("duration_min sai kiểu → 10 phút")

    for name, val in (("weight_ns", w_ns), ("weight_ew", w_ew)):
        if not W_MIN <= val <= W_MAX:
            notes.append(f"{name}={val:g} ngoài [{W_MIN}, {W_MAX}] → kẹp")
    w_ns, w_ew = min(max(w_ns, W_MIN), W_MAX), min(max(w_ew, W_MIN), W_MAX)

    if strategy == "PRIORITIZE_NS" and w_ns <= w_ew:
        raise ProposalInvalid("PRIORITIZE_NS nhưng weight_ns ≤ weight_ew (mâu thuẫn)")
    if strategy == "PRIORITIZE_EW" and w_ew <= w_ns:
        raise ProposalInvalid("PRIORITIZE_EW nhưng weight_ew ≤ weight_ns (mâu thuẫn)")
    if strategy in ("BALANCED", "INCIDENT_MODE") and abs(w_ns - w_ew) > 0.3:
        notes.append(f"{strategy} yêu cầu trọng số gần nhau → đặt 1.0/1.0")
        w_ns = w_ew = 1.0

    for i, (name, val) in enumerate((("weight_ns", w_ns), ("weight_ew", w_ew))):
        cur = current[i]
        if abs(val - cur) > W_STEP + 1e-9:
            new = cur + math.copysign(W_STEP, val - cur)
            notes.append(f"{name} đổi {cur:.2f}→{val:.2f} vượt biên độ ±{W_STEP} → {new:.2f}")
            if i == 0:
                w_ns = new
            else:
                w_ew = new

    if not DUR_MIN <= dur <= DUR_MAX:
        notes.append(f"duration_min={dur:g} ngoài [{DUR_MIN:.0f}, {DUR_MAX:.0f}] → kẹp")
    dur = min(max(dur, DUR_MIN), DUR_MAX)
    return {
        "strategy": strategy,
        "weight_ns": round(w_ns, 2),
        "weight_ew": round(w_ew, 2),
        "duration_min": round(dur, 1),
        "reason": cap(reason, 600),
    }, notes


# ---------------------------------------------------------------------------------------------- context
def build_context(rt: "IntersectionRuntime", now: float) -> dict:
    st = rt.llm
    approaches = {}
    for d, p in rt.pipelines.items():
        m = rt.direction_metrics(d, now)
        approaches[d] = {
            "density_pct": round(m["density_smoothed"], 1),
            "level": m["level"],
            "queue_m": round(m["queue_m"], 1),
            "flow_vph": m["flow_vph"],
            "arrival_pcu_h": m["arrival_pcu_h"],
            "avg_wait_s": m["avg_wait_s"],
            "camera": m["camera"]["status"] if m["camera"] else "NO_CAMERA",
        }
    plan = rt.latest_plan
    t = rt.fsm.timing
    try:
        with session_scope() as db:
            alerts = [a.title for a in db.query(Alert).filter(Alert.intersection_id == rt.id, Alert.status == "ACTIVE")
                      .order_by(Alert.created_at.desc()).limit(5)]
    except Exception:  # pragma: no cover
        alerts = []
    local = datetime.now()
    return {
        "intersection": rt.cfg.name,
        "local_time": local.strftime("%H:%M"),
        "weekday": ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"][local.weekday()],
        "control_mode": rt.fsm.mode.value,
        "current": {"strategy": st.strategy, "weight_ns": st.weight_ns, "weight_ew": st.weight_ew,
                    "expires_in_s": None if st.expires_at is None else round(st.expires_at - now)},
        "webster_plan": None if plan is None else {
            "green_ns_s": round(plan.plan.green_ns), "green_ew_s": round(plan.plan.green_ew),
            "cycle_s": round(plan.cycle_s), "flow_ratio_Y": round(plan.flow_ratio_total, 2),
            "demand_ns_pcu_h": round(plan.demand_ns_pcu_h), "demand_ew_pcu_h": round(plan.demand_ew_pcu_h),
            "saturated": plan.saturated,
        },
        "constraints": {"min_green_s": t.min_green, "max_green_s": t.max_green,
                        "cycle_min_s": t.cycle_min, "cycle_max_s": t.cycle_max},
        "approaches": approaches,
        "trend": st.trend(now),
        "active_alerts": alerts,
        "health_issues": rt.health_issues(),
    }


def _decision_dict(row: LlmDecision) -> dict:
    return {
        "id": row.id, "intersection_id": row.intersection_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "trigger": row.trigger, "supervisor_mode": row.supervisor_mode, "model": row.model, "status": row.status,
        "strategy": row.strategy, "strategy_label": STRATEGIES.get(row.strategy or "", row.strategy),
        "weight_ns": row.weight_ns, "weight_ew": row.weight_ew, "duration_min": row.duration_min,
        "reason": row.reason, "guard_notes": row.guard_notes, "latency_ms": row.latency_ms,
        "decided_by": row.decided_by,
    }


def decision_out(row: LlmDecision, with_context: bool = False) -> dict:
    d = _decision_dict(row)
    if with_context:
        d["context"] = row.context
        d["raw_output"] = row.raw_output
    return d


# ---------------------------------------------------------------------------------------------- service
class SupervisorService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="stcs-llm-supervisor")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        from app.services.manager import manager

        while self._running:
            await asyncio.sleep(2.0)
            now = time.time()
            with runtime_lock:
                for rt in list(manager.runtimes.values()):
                    try:
                        self._expire_pending(rt, now)
                        trigger = self._should_run(rt, now)
                        if trigger:
                            asyncio.create_task(self.run(rt, trigger))
                    except Exception:  # pragma: no cover
                        log.exception("LLM supervisor loop lỗi (nút %s)", rt.id)

    def _should_run(self, rt: "IntersectionRuntime", now: float) -> str | None:
        st = rt.llm
        if st.mode == "OFF" or st.running or not is_configured() or st.pending:
            return None
        if rt.fsm.mode.value != "AUTO" or rt.latest_plan is None:
            return None
        levels = [p.level for p in rt.pipelines.values()]
        level = "HIGH" if "HIGH" in levels else ("MEDIUM" if "MEDIUM" in levels else "LOW")
        saturated = bool(rt.latest_plan.saturated)
        escalated = (level == "HIGH" and st.last_level != "HIGH") or (saturated and not st.last_saturated)
        st.last_level, st.last_saturated = level, saturated
        since = now - st.last_run
        if since < settings.llm_min_gap_s:
            return None
        if escalated:
            return "EVENT"
        if since >= settings.llm_interval_s:
            return "PERIODIC"
        return None

    def _expire_pending(self, rt: "IntersectionRuntime", now: float) -> None:
        st = rt.llm
        if st.pending and now >= st.pending["expires_at"]:
            self._set_status(st.pending["id"], "EXPIRED", None)
            st.pending = None
            self._publish(rt)

    # ------------------------------------------------------------------ core
    async def run(self, rt: "IntersectionRuntime", trigger: str, by: str | None = None) -> dict:
        st = rt.llm
        if st.running:
            raise LLMError("LLM Supervisor đang xử lý yêu cầu trước")
        st.running = True
        st.last_run = time.time()
        mode = st.mode if st.mode != "OFF" else "ADVISORY"
        ctx = build_context(rt, st.last_run)
        row = LlmDecision(intersection_id=rt.id, trigger=trigger, supervisor_mode=mode, model=settings.llm_model,
                          status="ERROR", context=ctx, decided_by=by)
        try:
            reply = await chat(
                [{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content": "Số liệu hiện tại:\n" + json.dumps(ctx, ensure_ascii=False)}],
                json_mode=True, max_tokens=350, temperature=0.1,
            )
            row.model, row.latency_ms, row.raw_output = reply.model, round(reply.latency_ms, 1), cap(reply.content, 4000)
            proposal, notes = validate_proposal(reply.json(), (st.weight_ns, st.weight_ew))
            row.strategy, row.weight_ns, row.weight_ew = proposal["strategy"], proposal["weight_ns"], proposal["weight_ew"]
            row.duration_min, row.reason = proposal["duration_min"], proposal["reason"]
            row.guard_notes = "; ".join(notes) or None
            now = time.time()
            if rt.fsm.mode.value != "AUTO":
                row.status = "SKIPPED"
                row.guard_notes = ((row.guard_notes + "; ") if row.guard_notes else "") + \
                    f"Nút giao đang {rt.fsm.mode.value} — không áp dụng"
            elif mode == "AUTONOMOUS":
                row.status = "APPLIED"
            else:
                row.status = "PENDING"
            st.last_error = None
        except ProposalInvalid as exc:
            row.status, row.guard_notes = "INVALID", f"Từ chối đầu ra LLM: {exc}"
            st.last_error = row.guard_notes
            proposal = None
        except LLMError as exc:
            row.status, row.guard_notes = "ERROR", str(exc)
            st.last_error = str(exc)
            proposal = None
        finally:
            st.running = False

        decision_id = self._save(row)
        # Phần sau await: áp dụng lên runtime dưới khoá (không có await bên trong)
        with runtime_lock:
            return self._finish_run(rt, row, proposal, decision_id)

    def _finish_run(self, rt: "IntersectionRuntime", row: LlmDecision, proposal: dict | None,
                    decision_id: int | None) -> dict:
        st = rt.llm
        if proposal and row.status == "APPLIED" and rt.fsm.mode.value != "AUTO":
            # Chế độ có thể đã đổi trong lúc chờ LLM trả lời
            row.status = "SKIPPED"
            self._set_status(decision_id, "SKIPPED", None)
            proposal = None
        now = time.time()
        if proposal and row.status == "APPLIED":
            st.apply(proposal, "LLM", decision_id, now)
            audit(None, "SIGNAL_CONTROL", "LLM_STRATEGY_APPLIED",
                  f"{rt.cfg.name}: {STRATEGIES[proposal['strategy']]} (B–N ×{proposal['weight_ns']}, "
                  f"Đ–T ×{proposal['weight_ew']}, {proposal['duration_min']:.0f} phút)",
                  username="llm-supervisor", target=rt.cfg.code, details=proposal, intersection_id=rt.id)
        elif proposal and row.status == "PENDING":
            st.pending = {**proposal, "id": decision_id, "created_at": now,
                          "expires_at": now + settings.llm_pending_ttl_s, "guard_notes": row.guard_notes}
        out = decision_out(row)
        out["id"] = decision_id
        st.last = out
        self._publish(rt, out)
        return out

    def approve(self, rt: "IntersectionRuntime", decision_id: int, username: str) -> dict:
        st = rt.llm
        if not st.pending or st.pending["id"] != decision_id:
            raise ValueError("Đề xuất không còn chờ duyệt (đã hết hạn hoặc đã xử lý)")
        if rt.fsm.mode.value != "AUTO":
            raise ValueError(f"Nút giao đang ở chế độ {rt.fsm.mode.value} — chỉ áp dụng chiến lược LLM khi AUTO")
        p = st.pending
        st.pending = None
        st.apply(p, "LLM", decision_id, time.time())
        self._set_status(decision_id, "APPROVED", username)
        if st.last and st.last.get("id") == decision_id:
            st.last = {**st.last, "status": "APPROVED", "decided_by": username}
        self._publish(rt)
        return p

    def reject(self, rt: "IntersectionRuntime", decision_id: int, username: str) -> None:
        st = rt.llm
        if not st.pending or st.pending["id"] != decision_id:
            raise ValueError("Đề xuất không còn chờ duyệt")
        st.pending = None
        self._set_status(decision_id, "REJECTED", username)
        if st.last and st.last.get("id") == decision_id:
            st.last = {**st.last, "status": "REJECTED", "decided_by": username}
        self._publish(rt)

    def set_priority(self, rt: "IntersectionRuntime", axis: str, weight: float, minutes: float, reason: str,
                     source: str) -> dict:
        """Ưu tiên trục do người vận hành/trợ lý yêu cầu — vẫn đi qua validate + Webster + bộ khoá an toàn."""
        if rt.fsm.mode.value != "AUTO":
            raise ValueError("Chỉ đặt ưu tiên trục khi nút giao ở chế độ AUTO")
        data = {"strategy": "PRIORITIZE_NS" if axis == "NS" else "PRIORITIZE_EW",
                "weight_ns": weight if axis == "NS" else 1.0, "weight_ew": weight if axis == "EW" else 1.0,
                "duration_min": minutes, "reason": reason}
        proposal, notes = validate_proposal(data, (rt.llm.weight_ns, rt.llm.weight_ew))
        rt.llm.apply(proposal, source, None, time.time())
        self._publish(rt)
        return {**proposal, "guard_notes": notes}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _save(row: LlmDecision) -> int | None:
        try:
            with session_scope() as db:
                db.add(row)
                db.flush()
                return row.id
        except Exception:  # pragma: no cover
            log.exception("Không ghi được quyết định LLM")
            return None

    @staticmethod
    def _set_status(decision_id: int | None, status: str, by: str | None) -> None:
        if decision_id is None:
            return
        try:
            with session_scope() as db:
                row = db.get(LlmDecision, decision_id)
                if row:
                    row.status = status
                    if by:
                        row.decided_by = by
        except Exception:  # pragma: no cover
            log.exception("Không cập nhật được quyết định LLM")

    @staticmethod
    def _publish(rt: "IntersectionRuntime", decision: dict | None = None) -> None:
        bus.publish({"type": "llm", "data": {"state": rt.llm.to_dict(time.time()), "decision": decision}}, rt.id)


supervisor = SupervisorService()
