"""Trợ lý vận hành LLM (Groq tool calling) + báo cáo tự động.

Nguyên tắc an toàn:
  * Danh sách tool được LỌC THEO QUYỀN của người dùng đang đăng nhập (không theo LLM).
  * Tool chỉ-đọc chạy ngay. Tool làm thay đổi trạng thái chỉ TẠO ĐỀ XUẤT; người dùng phải bấm Xác nhận,
    khi đó lệnh mới được thực thi qua đúng đường điều khiển thông thường (FSM + bộ khoá an toàn + audit log).
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func

from app.control_engine.phases import DIRECTION_LABELS
from app.core.audit import audit
from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.events import bus
from app.core.rbac import ROLE_LABELS, Perm, Role
from app.db.session import session_scope
from app.llm.client import LLMError, cap, chat, chat_stream
from app.llm.supervisor import STRATEGIES, decision_out, supervisor
from app.models.alert import Alert, DeviceIncident
from app.models.llm import LlmDecision
from app.models.signal import SignalCommand, SignalCycle
from app.models.traffic import TrafficStat

MAX_ROUNDS = 5
ACTION_TTL_S = 300
_pending: dict[str, dict] = {}


def _mgr():
    from app.services.manager import manager

    return manager


def _rt(iid: Any):
    try:
        rt = _mgr().get(int(iid))
    except (TypeError, ValueError):
        rt = None
    if rt is None:
        raise ValueError(f"Không có nút giao id={iid}")
    return rt


# ---------------------------------------------------------------------------------------------- read tools
def t_list_intersections(_: CurrentUser) -> Any:
    return [{k: s[k] for k in ("id", "code", "name", "mode", "worst_level", "cameras_online", "cameras_total",
                               "controller_online")} for s in _mgr().summary()]


def t_get_status(_: CurrentUser, intersection_id: int) -> Any:
    rt = _rt(intersection_id)
    now = time.time()
    dirs = {}
    for d in rt.pipelines:
        m = rt.direction_metrics(d, now)
        dirs[DIRECTION_LABELS[d]] = {
            "mật_độ_%": round(m["density_smoothed"], 1), "mức": m["level_label"], "hàng_đợi_m": round(m["queue_m"]),
            "lưu_lượng_xe_h": m["flow_vph"], "chờ_TB_s": m["avg_wait_s"], "đã_đếm_hôm_nay": sum(m["counts_total"].values()),
            "camera": m["camera"]["status"] if m["camera"] else None,
        }
    sig = rt.fsm.snapshot()
    plan = rt.latest_plan
    return {
        "nút_giao": rt.cfg.name, "chế_độ": rt.fsm.mode.value, "pha_hiện_tại": sig.get("phase_name"),
        "khoảng": sig.get("interval"), "còn_lại_s": sig.get("remaining"),
        "kế_hoạch_webster": None if plan is None else {
            "xanh_BN_s": round(plan.plan.green_ns), "xanh_DT_s": round(plan.plan.green_ew),
            "chu_kỳ_s": round(plan.cycle_s), "Y": round(plan.flow_ratio_total, 2), "lý_do": plan.reason},
        "llm_supervisor": {k: v for k, v in rt.llm.to_dict(now).items()
                           if k in ("mode", "strategy_label", "weight_ns", "weight_ew", "reason", "expires_in_s")},
        "các_hướng": dirs,
        "sự_cố": rt.health_issues(),
    }


def t_query_stats(_: CurrentUser, intersection_id: int, hours: float = 24, group_by: str = "direction") -> Any:
    hours = min(max(float(hours), 1), 24 * 31)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with session_scope() as db:
        base = db.query(TrafficStat).filter(TrafficStat.intersection_id == int(intersection_id),
                                            TrafficStat.bucket_start >= since)
        if group_by == "hour":
            rows = base.order_by(TrafficStat.bucket_start).all()
            hourly: dict[str, dict] = {}
            for r in rows:
                key = r.bucket_start.astimezone().strftime("%d/%m %H:00")
                h = hourly.setdefault(key, {"xe": 0, "mật_độ_max": 0.0})
                h["xe"] += r.total
                h["mật_độ_max"] = max(h["mật_độ_max"], round(r.max_density, 1))
            return {"khoảng_giờ": hours, "theo_giờ": hourly}
        q = db.query(
            TrafficStat.direction, func.sum(TrafficStat.total), func.sum(TrafficStat.car),
            func.sum(TrafficStat.motorbike), func.sum(TrafficStat.bus), func.sum(TrafficStat.truck),
            func.avg(TrafficStat.avg_density), func.max(TrafficStat.max_density), func.avg(TrafficStat.avg_queue_m),
            func.avg(TrafficStat.avg_wait_s),
        ).filter(TrafficStat.intersection_id == int(intersection_id), TrafficStat.bucket_start >= since) \
            .group_by(TrafficStat.direction).all()
    return {
        "khoảng_giờ": hours,
        "theo_hướng": {
            DIRECTION_LABELS.get(d, d): {"tổng": int(t or 0), "ô_tô": int(c or 0), "xe_máy": int(m or 0),
                                         "buýt": int(b or 0), "tải": int(tr or 0),
                                         "mật_độ_TB_%": round(ad or 0, 1), "mật_độ_max_%": round(md or 0, 1),
                                         "hàng_đợi_TB_m": round(aq or 0, 1), "chờ_TB_s": round(aw or 0, 1)}
            for d, t, c, m, b, tr, ad, md, aq, aw in q
        },
    }


def t_list_alerts(_: CurrentUser, intersection_id: int | None = None) -> Any:
    with session_scope() as db:
        qa = db.query(Alert).filter(Alert.status != "RESOLVED")
        qi = db.query(DeviceIncident).filter(DeviceIncident.status != "RESOLVED")
        if intersection_id:
            qa = qa.filter(Alert.intersection_id == int(intersection_id))
            qi = qi.filter(DeviceIncident.intersection_id == int(intersection_id))
        alerts = [{"id": a.id, "nút": a.intersection_id, "loại": a.alert_type, "mức": a.level, "tiêu_đề": a.title,
                   "trạng_thái": a.status, "lúc": a.created_at.astimezone().strftime("%H:%M %d/%m")}
                  for a in qa.order_by(Alert.created_at.desc()).limit(15)]
        incidents = [{"id": i.id, "nút": i.intersection_id, "thiết_bị": i.device_code, "loại": i.incident_type,
                      "mức": i.severity, "mô_tả": i.message, "lúc": i.started_at.astimezone().strftime("%H:%M %d/%m")}
                     for i in qi.order_by(DeviceIncident.started_at.desc()).limit(15)]
    return {"cảnh_báo": alerts, "sự_cố_thiết_bị": incidents}


def t_llm_decisions(_: CurrentUser, intersection_id: int, limit: int = 5) -> Any:
    with session_scope() as db:
        rows = db.query(LlmDecision).filter(LlmDecision.intersection_id == int(intersection_id)) \
            .order_by(LlmDecision.created_at.desc()).limit(min(int(limit), 20)).all()
        return [decision_out(r) for r in rows]


def t_signal_history(_: CurrentUser, intersection_id: int, limit: int = 10) -> Any:
    with session_scope() as db:
        rows = db.query(SignalCommand).filter(SignalCommand.intersection_id == int(intersection_id)) \
            .order_by(SignalCommand.created_at.desc()).limit(min(int(limit), 30)).all()
        return [{"lúc": r.created_at.astimezone().strftime("%H:%M:%S %d/%m"), "lệnh": r.command, "nguồn": r.source,
                 "bởi": r.issued_by, "trạng_thái": r.status, "ghi_chú": r.message} for r in rows]


# ---------------------------------------------------------------------------------------------- action tool
ACTIONS: dict[str, tuple[Perm, str]] = {
    "SET_MODE": (Perm.SIGNAL_MODE, "Chuyển chế độ điều khiển"),
    "NEXT_PHASE": (Perm.SIGNAL_CONTROL, "Chuyển sang pha kế tiếp (qua Vàng → Toàn đỏ)"),
    "EXTEND_GREEN": (Perm.SIGNAL_CONTROL, "Kéo dài pha xanh hiện tại"),
    "SET_AXIS_PRIORITY": (Perm.LLM_SUPERVISE, "Ưu tiên một trục trong chế độ AUTO"),
}


def t_propose_action(user: CurrentUser, intersection_id: int, action: str, reason: str,
                     params: dict | None = None) -> Any:
    action = str(action).upper()
    if action not in ACTIONS:
        raise ValueError(f"Hành động không hỗ trợ: {action}")
    perm, label = ACTIONS[action]
    if not user.can(perm):
        raise ValueError(f"Người dùng {user.username} không có quyền {perm.value} để {label.lower()}")
    rt = _rt(intersection_id)
    params = dict(params or {})
    if action == "SET_MODE":
        mode = str(params.get("mode", "")).upper()
        if mode not in ("AUTO", "MANUAL", "FIXED_TIME"):
            raise ValueError("params.mode phải là AUTO | MANUAL | FIXED_TIME")
        params = {"mode": mode}
        summary = f"{label}: {rt.fsm.mode.value} → {mode}"
    elif action == "EXTEND_GREEN":
        sec = min(max(float(params.get("seconds", 10)), 5), 30)
        params = {"seconds": sec}
        summary = f"{label} thêm {sec:.0f}s"
    elif action == "SET_AXIS_PRIORITY":
        axis = str(params.get("axis", "")).upper()
        if axis not in ("NS", "EW"):
            raise ValueError("params.axis phải là NS (Bắc–Nam) hoặc EW (Đông–Tây)")
        weight = min(max(float(params.get("weight", 1.4)), 1.1), 2.0)
        minutes = min(max(float(params.get("minutes", 10)), 2), 30)
        params = {"axis": axis, "weight": weight, "minutes": minutes}
        summary = f"Ưu tiên trục {'Bắc–Nam' if axis == 'NS' else 'Đông–Tây'} ×{weight:.2f} trong {minutes:.0f} phút"
    else:
        params = {}
        summary = label
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["created_at"] > ACTION_TTL_S]:
        _pending.pop(k, None)
    aid = uuid.uuid4().hex[:12]
    _pending[aid] = {"id": aid, "username": user.username, "intersection_id": rt.id, "intersection": rt.cfg.name,
                     "action": action, "params": params, "reason": str(reason)[:300], "summary": summary,
                     "created_at": now}
    return {"đề_xuất_id": aid, "tóm_tắt": summary,
            "ghi_chú": "Đã tạo đề xuất. Lệnh CHƯA được thực thi — người dùng phải bấm Xác nhận trên giao diện."}


def pending_out(a: dict) -> dict:
    return {**a, "expires_in_s": max(0, round(a["created_at"] + ACTION_TTL_S - time.time()))}


def confirm_action(aid: str, user: CurrentUser) -> dict:
    a = _pending.get(aid)
    if a is None or time.time() - a["created_at"] > ACTION_TTL_S:
        _pending.pop(aid, None)
        raise ValueError("Đề xuất không tồn tại hoặc đã hết hạn (5 phút)")
    if a["username"] != user.username:
        raise PermissionError("Chỉ người tạo đề xuất mới được xác nhận")
    perm = ACTIONS[a["action"]][0]
    if not user.can(perm):
        raise PermissionError(f"Thiếu quyền {perm.value}")
    _pending.pop(aid, None)
    rt = _rt(a["intersection_id"])
    reason = f"[Trợ lý LLM] {a['reason']}"
    act, p = a["action"], a["params"]
    if act == "SET_MODE":
        res = rt.set_mode(p["mode"], user.username, reason)
        ok, msg = res.ok, res.message
    elif act == "NEXT_PHASE":
        res, _ = rt.execute("NEXT_PHASE", {"reason": reason}, user.username)
        ok, msg = res.ok, res.message
    elif act == "EXTEND_GREEN":
        res, _ = rt.execute("EXTEND_GREEN", {"seconds": p["seconds"], "reason": reason}, user.username)
        ok, msg = res.ok, res.message
    else:
        try:
            r = supervisor.set_priority(rt, p["axis"], p["weight"], p["minutes"], a["reason"] or a["summary"],
                                        f"ASSISTANT:{user.username}")
            ok, msg = True, f"Đã áp dụng {STRATEGIES[r['strategy']]} (B–N ×{r['weight_ns']}, Đ–T ×{r['weight_ew']})"
        except ValueError as exc:
            ok, msg = False, str(exc)
    audit(None, "SIGNAL_CONTROL", f"ASSISTANT_{act}", f"{rt.cfg.name}: {a['summary']} — {msg}",
          username=user.username, role=user.role, target=rt.cfg.code,
          details={"params": p, "reason": a["reason"], "via": "llm-assistant"},
          result="SUCCESS" if ok else "FAILURE", intersection_id=rt.id)
    bus.publish({"type": "command", "data": {"kind": act, "username": user.username,
                                              "status": "EXECUTED" if ok else "REJECTED", "message": msg}}, rt.id)
    return {"ok": ok, "message": msg, "action": a}


def cancel_action(aid: str, user: CurrentUser) -> None:
    a = _pending.get(aid)
    if a and a["username"] == user.username:
        _pending.pop(aid, None)


# ---------------------------------------------------------------------------------------------- registry
def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props,
                                                            "required": required}}}


IID = {"intersection_id": {"type": "integer", "description": "id nút giao"}}
TOOLS: dict[str, tuple[tuple[Perm, ...], Callable, dict]] = {
    "list_intersections": ((Perm.STATS_VIEW,), t_list_intersections,
                           _fn("list_intersections", "Danh sách nút giao với chế độ, mức ùn tắc, tình trạng thiết bị", {}, [])),
    "get_intersection_status": ((Perm.STATS_VIEW,), t_get_status,
                                _fn("get_intersection_status", "Trạng thái thời gian thực của 1 nút giao: đèn, kế hoạch Webster, LLM supervisor, mật độ/hàng đợi từng hướng", IID, ["intersection_id"])),
    "query_traffic_stats": ((Perm.STATS_VIEW,), t_query_stats,
                            _fn("query_traffic_stats", "Thống kê lưu lượng đã lưu theo hướng hoặc theo giờ",
                                {**IID, "hours": {"type": "number", "description": "số giờ gần nhất (1–744)"},
                                 "group_by": {"type": "string", "enum": ["direction", "hour"]}}, ["intersection_id"])),
    "list_active_alerts": ((Perm.ALERTS_VIEW,), t_list_alerts,
                           _fn("list_active_alerts", "Cảnh báo và sự cố thiết bị chưa xử lý xong",
                               {"intersection_id": {"type": "integer", "description": "bỏ trống = tất cả"}}, [])),
    "get_llm_decisions": ((Perm.STATS_VIEW,), t_llm_decisions,
                          _fn("get_llm_decisions", "Các quyết định gần đây của LLM Supervisor tại 1 nút giao",
                              {**IID, "limit": {"type": "integer"}}, ["intersection_id"])),
    "get_signal_history": ((Perm.STATS_VIEW,), t_signal_history,
                           _fn("get_signal_history", "Lịch sử lệnh điều khiển đèn gần đây",
                               {**IID, "limit": {"type": "integer"}}, ["intersection_id"])),
    "propose_action": ((Perm.SIGNAL_CONTROL, Perm.SIGNAL_MODE, Perm.LLM_SUPERVISE), t_propose_action,
                       _fn("propose_action",
                           "TẠO ĐỀ XUẤT thao tác điều khiển (không thực thi ngay; người dùng phải xác nhận). "
                           "SET_MODE{mode: AUTO|MANUAL|FIXED_TIME}, NEXT_PHASE{}, EXTEND_GREEN{seconds 5–30}, "
                           "SET_AXIS_PRIORITY{axis: NS|EW, weight 1.1–2.0, minutes 2–30}",
                           {**IID, "action": {"type": "string", "enum": list(ACTIONS)},
                            "params": {"type": "object"},
                            "reason": {"type": "string", "description": "lý do, dựa trên số liệu"}},
                           ["intersection_id", "action", "reason"])),
}


def tools_for(user: CurrentUser) -> list[dict]:
    return [spec for perms, _, spec in TOOLS.values() if any(user.can(p) for p in perms)]


def _system(user: CurrentUser, intersection_id: int | None) -> str:
    sel = None
    if intersection_id:
        rt = _mgr().get(intersection_id)
        sel = f"{rt.cfg.name} (id={rt.id})" if rt else None
    lst = "; ".join(f"id={s['id']}: {s['name']}" for s in _mgr().summary())
    try:
        role_label = ROLE_LABELS[Role(user.role)]
    except ValueError:
        role_label = user.role
    can_act = any(user.can(p) for p in (Perm.SIGNAL_CONTROL, Perm.SIGNAL_MODE, Perm.LLM_SUPERVISE))
    return (
        "Bạn là trợ lý vận hành của hệ thống điều khiển giao thông STCS (nút giao có camera AI, đèn thích ứng Webster, "
        "LLM Supervisor và bộ khoá an toàn). Trả lời bằng tiếng Việt, ngắn gọn, có số liệu cụ thể, dùng markdown đơn giản (tiêu đề, gạch đầu dòng, bảng, **đậm**); KHÔNG dùng LaTeX — viết công thức dạng chữ thường như c² = a² + b².\n"
        f"Thời gian: {datetime.now().strftime('%H:%M %d/%m/%Y')}. Người dùng: {user.full_name} — {role_label}.\n"
        f"Các nút giao: {lst}. Nút đang chọn trên giao diện: {sel or 'chưa chọn'}.\n"
        + ("Ngoài nghiệp vụ giao thông, bạn được phép trả lời MỌI câu hỏi ngoài lề của người dùng (kiến thức chung, "
           "học tập, lập trình, trò chuyện…) một cách đầy đủ và hữu ích như một trợ lý đa năng; với các câu đó không cần gọi tool. "
           if settings.assistant_open_topic else
           "Chỉ hỗ trợ các chủ đề liên quan giao thông và hệ thống STCS; câu hỏi ngoài lề thì lịch sự từ chối và gợi ý hỏi về giao thông. ")
        + "Với số liệu giao thông: LUÔN gọi tool để lấy số liệu, không bịa số. "
        + ("Khi người dùng muốn thay đổi điều khiển, gọi propose_action — lệnh chỉ chạy sau khi người dùng bấm Xác nhận; "
           "hãy nói rõ điều đó. Không bao giờ khẳng định lệnh đã được thực thi. "
           if can_act else "Người dùng này KHÔNG có quyền điều khiển đèn; nếu họ yêu cầu, giải thích lịch sự. ")
        + "Mọi lệnh đều đi qua bộ khoá an toàn (vàng ≥ 3s, toàn đỏ ≥ 2s, xanh tối thiểu) nên có thể bị xếp lịch hoặc từ chối."
    )


async def run_chat(user: CurrentUser, history: list[dict], intersection_id: int | None) -> dict:
    msgs = _history(user, history, intersection_id)
    tools = tools_for(user)
    allowed = {t["function"]["name"] for t in tools}
    trace: list[dict] = []
    actions: list[dict] = []
    latency = 0.0
    model = settings.llm_model
    for _ in range(MAX_ROUNDS):
        reply = await chat(msgs, tools=tools, max_tokens=1200, temperature=0.3, timeout_s=30)
        latency += reply.latency_ms
        model = reply.model
        if not reply.tool_calls:
            return {"reply": reply.content, "trace": trace, "actions": actions, "model": model,
                    "latency_ms": round(latency)}
        msgs.append({"role": "assistant", "content": reply.content or "", "tool_calls": reply.tool_calls})
        for tc in reply.tool_calls:
            name, args, result, ok, action = _exec_tool(user, allowed, tc)
            if action:
                actions.append(action)
            trace.append({"tool": name, "args": args, "ok": ok})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"),
                         "content": cap(json.dumps(result, ensure_ascii=False, default=str), 6000)})
    raise LLMError("Trợ lý gọi tool quá nhiều vòng — hãy hỏi cụ thể hơn")


def _exec_tool(user: CurrentUser, allowed: set[str], tc: dict) -> tuple[str, dict, Any, bool, dict | None]:
    name = tc.get("function", {}).get("name", "")
    try:
        args = json.loads(tc.get("function", {}).get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    action = None
    try:
        if name not in allowed:
            raise PermissionError(f"Tool {name} không được phép với vai trò {user.role}")
        result = TOOLS[name][1](user, **args)
        ok = True
        if name == "propose_action":
            action = pending_out(_pending[result["đề_xuất_id"]])
    except TypeError as exc:
        result, ok = {"lỗi": f"Tham số không hợp lệ: {exc}"}, False
    except (ValueError, PermissionError, KeyError) as exc:
        result, ok = {"lỗi": str(exc)}, False
    return name, args, result, ok, action


def _history(user: CurrentUser, history: list[dict], intersection_id: int | None) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": _system(user, intersection_id)}]
    for m in history[-12:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": cap(m["content"], 4000)})
    return msgs


async def run_chat_stream(user: CurrentUser, history: list[dict], intersection_id: int | None):
    """Phiên bản streaming của run_chat: sinh sự kiện delta (từng mẩu chữ), tool, action, done, error."""
    msgs = _history(user, history, intersection_id)
    tools = tools_for(user)
    allowed = {t["function"]["name"] for t in tools}
    latency = 0.0
    try:
        for _ in range(MAX_ROUNDS):
            calls: list[dict] = []
            content = ""
            meta: dict = {}
            async for kind, data in chat_stream(msgs, tools=tools, temperature=0.3, timeout_s=60):
                if kind == "delta":
                    yield {"type": "delta", "text": data}
                elif kind == "tool_calls":
                    calls = data
                else:
                    meta = data
                    content = data["content"]
            latency += meta.get("latency_ms", 0.0)
            if not calls:
                yield {"type": "done", "model": meta.get("model", settings.llm_model), "latency_ms": round(latency)}
                return
            msgs.append({"role": "assistant", "content": content, "tool_calls": calls})
            for tc in calls:
                yield {"type": "tool_start", "tool": tc["function"]["name"]}
                name, args, result, ok, action = _exec_tool(user, allowed, tc)
                yield {"type": "tool", "tool": name, "args": args, "ok": ok}
                if action:
                    yield {"type": "action", "action": action}
                msgs.append({"role": "tool", "tool_call_id": tc.get("id"),
                             "content": cap(json.dumps(result, ensure_ascii=False, default=str), 6000)})
        yield {"type": "error", "message": "Trợ lý gọi tool quá nhiều vòng — hãy hỏi cụ thể hơn"}
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}


# ---------------------------------------------------------------------------------------------- report
def _report_data(intersection_id: int, hours: float) -> dict:
    rt = _rt(intersection_id)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stats = t_query_stats(None, intersection_id, hours, "direction")  # type: ignore[arg-type]
    hourly = t_query_stats(None, intersection_id, hours, "hour")["theo_giờ"]  # type: ignore[arg-type]
    peak = sorted(hourly.items(), key=lambda kv: kv[1]["xe"], reverse=True)[:3]
    with session_scope() as db:
        cyc = db.query(SignalCycle.mode, func.count(), func.avg(SignalCycle.avg_wait_s), func.avg(SignalCycle.cycle_length_s),
                       func.sum(SignalCycle.throughput)) \
            .filter(SignalCycle.intersection_id == intersection_id, SignalCycle.started_at >= since) \
            .group_by(SignalCycle.mode).all()
        alerts = db.query(Alert.alert_type, Alert.level, func.count()) \
            .filter(Alert.intersection_id == intersection_id, Alert.created_at >= since) \
            .group_by(Alert.alert_type, Alert.level).all()
        incidents = db.query(DeviceIncident.device_type, DeviceIncident.incident_type, func.count()) \
            .filter(DeviceIncident.intersection_id == intersection_id, DeviceIncident.started_at >= since) \
            .group_by(DeviceIncident.device_type, DeviceIncident.incident_type).all()
        llm = db.query(LlmDecision.status, func.count()) \
            .filter(LlmDecision.intersection_id == intersection_id, LlmDecision.created_at >= since) \
            .group_by(LlmDecision.status).all()
        manual = db.query(func.count()).select_from(SignalCommand) \
            .filter(SignalCommand.intersection_id == intersection_id, SignalCommand.created_at >= since,
                    SignalCommand.source == "MANUAL").scalar()
    return {
        "nút_giao": rt.cfg.name, "mã": rt.cfg.code, "khoảng_giờ": hours,
        "lưu_lượng_theo_hướng": stats["theo_hướng"],
        "giờ_cao_điểm_top3": {k: v for k, v in peak},
        "chu_kỳ_theo_chế_độ": {m: {"số_chu_kỳ": n, "chờ_TB_s": round(w or 0, 1), "chu_kỳ_TB_s": round(c or 0, 1),
                                   "xe_thông_qua": int(t or 0)} for m, n, w, c, t in cyc},
        "cảnh_báo": [{"loại": a, "mức": lv, "số": n} for a, lv, n in alerts],
        "sự_cố_thiết_bị": [{"thiết_bị": d, "loại": t, "số": n} for d, t, n in incidents],
        "quyết_định_llm": {s: n for s, n in llm},
        "lệnh_thủ_công": int(manual or 0),
    }


def _report_messages(data: dict) -> list[dict]:
    prompt = (
        "Viết BÁO CÁO TÌNH HÌNH GIAO THÔNG bằng tiếng Việt, định dạng markdown, từ số liệu JSON dưới đây. Cấu trúc:\n"
        "# tiêu đề (tên nút giao + khoảng thời gian)\n## 1. Tóm tắt (3–4 gạch đầu dòng quan trọng nhất)\n"
        "## 2. Lưu lượng & mật độ theo hướng (bảng markdown)\n## 3. Giờ cao điểm\n"
        "## 4. Hiệu quả điều khiển (so sánh AUTO và FIXED_TIME nếu có; nêu chênh lệch thời gian chờ %)\n"
        "## 5. Cảnh báo, sự cố & hoạt động LLM Supervisor\n## 6. Khuyến nghị (2–4 ý, khả thi, có căn cứ)\n"
        "Chỉ dùng số liệu được cung cấp; mục nào không có dữ liệu thì ghi 'Chưa có dữ liệu'.\n\n"
        + json.dumps(data, ensure_ascii=False, default=str)
    )
    return [{"role": "system", "content": "Bạn là chuyên viên phân tích giao thông đô thị. Không dùng LaTeX."},
            {"role": "user", "content": prompt}]


async def make_report_stream(intersection_id: int, hours: float, user: CurrentUser):
    hours = min(max(float(hours), 1), 24 * 31)
    try:
        data = _report_data(intersection_id, hours)
    except ValueError as exc:
        yield {"type": "error", "message": str(exc)}
        return
    yield {"type": "data", "data": data}
    try:
        async for kind, payload in chat_stream(_report_messages(data), max_tokens=2000, temperature=0.3, timeout_s=90):
            if kind == "delta":
                yield {"type": "delta", "text": payload}
            elif kind == "done":
                audit(None, "SYSTEM", "AI_REPORT", f"Sinh báo cáo AI {data['nút_giao']} ({hours:g} giờ)",
                      username=user.username, role=user.role, target=data["mã"], intersection_id=intersection_id)
                yield {"type": "done", "model": payload["model"], "latency_ms": round(payload["latency_ms"]),
                       "generated_at": datetime.now(timezone.utc).isoformat()}
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}


async def make_report(intersection_id: int, hours: float, user: CurrentUser) -> dict:
    hours = min(max(float(hours), 1), 24 * 31)
    data = _report_data(intersection_id, hours)
    reply = await chat(_report_messages(data), max_tokens=2000, temperature=0.3, timeout_s=45)
    audit(None, "SYSTEM", "AI_REPORT", f"Sinh báo cáo AI {data['nút_giao']} ({hours:g} giờ)", username=user.username,
          role=user.role, target=data["mã"], intersection_id=intersection_id)
    return {"markdown": reply.content, "data": data, "model": reply.model, "latency_ms": round(reply.latency_ms),
            "generated_at": datetime.now(timezone.utc).isoformat()}
