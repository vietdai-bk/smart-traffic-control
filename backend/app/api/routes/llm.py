"""LLM Supervisor (tầng 3), trợ lý vận hành và báo cáo tự động — Groq."""
from __future__ import annotations

import time
from typing import Literal

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import CurrentUser, client_ip, get_current_user, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.llm import assistant
from app.llm.client import LLMError, is_configured
from app.llm.supervisor import MODE_LABELS, STRATEGIES, decision_out, supervisor
from app.models.llm import LlmDecision
from app.services.manager import manager

router = APIRouter(prefix="/llm", tags=["LLM"])


def _rt(iid: int):
    rt = manager.get(iid)
    if rt is None:
        raise HTTPException(404, "Nút giao không tồn tại hoặc đang tắt")
    return rt


@router.get("/info")
def info(_: CurrentUser = Depends(get_current_user)):
    return {
        "provider": "Groq",
        "configured": is_configured(),
        "model": settings.llm_model,
        "interval_s": settings.llm_interval_s,
        "timeout_s": settings.llm_timeout_s,
        "modes": [{"id": k, "label": v} for k, v in MODE_LABELS.items()],
        "strategies": [{"id": k, "label": v} for k, v in STRATEGIES.items()],
    }


class SupervisorModeIn(BaseModel):
    mode: Literal["OFF", "ADVISORY", "AUTONOMOUS"]
    confirm: bool = False


@router.post("/{iid}/mode")
def set_supervisor_mode(iid: int, body: SupervisorModeIn, request: Request, db: Session = Depends(get_db),
                        cur: CurrentUser = Depends(require(Perm.LLM_SUPERVISE))):
    if body.mode == "AUTONOMOUS" and not body.confirm:
        raise HTTPException(428, "Bật chế độ LLM tự động cần xác nhận (confirm=true)")
    rt = _rt(iid)
    prev = rt.llm.mode
    rt.llm.mode = body.mode
    if body.mode == "OFF":
        rt.llm.reset("LLM Supervisor đã tắt")
        rt.llm.pending = None
    audit(db, "SIGNAL_CONTROL", "LLM_MODE", f"{rt.cfg.name}: LLM Supervisor {prev} → {body.mode}",
          username=cur.username, role=cur.role, target=rt.cfg.code, ip=client_ip(request), intersection_id=iid)
    supervisor._publish(rt)
    return rt.llm.to_dict(time.time())


@router.post("/{iid}/run")
async def run_now(iid: int, cur: CurrentUser = Depends(require(Perm.LLM_SUPERVISE))):
    rt = _rt(iid)
    if not is_configured():
        raise HTTPException(503, "Chưa cấu hình GROQ_API_KEY")
    if rt.fsm.mode.value != "AUTO":
        raise HTTPException(409, f"Nút giao đang {rt.fsm.mode.value} — LLM Supervisor chỉ hoạt động ở chế độ AUTO")
    if rt.llm.pending:
        raise HTTPException(409, "Đang có đề xuất chờ duyệt")
    try:
        return await supervisor.run(rt, "MANUAL", by=cur.username)
    except LLMError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{iid}/decisions/{did}/approve")
def approve(iid: int, did: int, request: Request, db: Session = Depends(get_db),
            cur: CurrentUser = Depends(require(Perm.LLM_SUPERVISE))):
    rt = _rt(iid)
    try:
        p = supervisor.approve(rt, did, cur.username)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit(db, "SIGNAL_CONTROL", "LLM_APPROVE",
          f"{rt.cfg.name}: duyệt đề xuất LLM #{did} — {STRATEGIES[p['strategy']]}", username=cur.username,
          role=cur.role, target=rt.cfg.code, ip=client_ip(request), details=p, intersection_id=iid)
    return {"ok": True}


@router.post("/{iid}/decisions/{did}/reject")
def reject(iid: int, did: int, request: Request, db: Session = Depends(get_db),
           cur: CurrentUser = Depends(require(Perm.LLM_SUPERVISE))):
    rt = _rt(iid)
    try:
        supervisor.reject(rt, did, cur.username)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit(db, "SIGNAL_CONTROL", "LLM_REJECT", f"{rt.cfg.name}: từ chối đề xuất LLM #{did}", username=cur.username,
          role=cur.role, target=rt.cfg.code, ip=client_ip(request), intersection_id=iid)
    return {"ok": True}


@router.post("/{iid}/reset")
def reset(iid: int, cur: CurrentUser = Depends(require(Perm.LLM_SUPERVISE))):
    rt = _rt(iid)
    rt.llm.reset(f"Đặt lại về cân bằng bởi {cur.username}")
    supervisor._publish(rt)
    audit(None, "SIGNAL_CONTROL", "LLM_RESET", f"{rt.cfg.name}: đặt lại chiến lược LLM về cân bằng",
          username=cur.username, role=cur.role, target=rt.cfg.code, intersection_id=iid)
    return {"ok": True}


@router.get("/decisions")
def decisions(intersection_id: int | None = None, status: str | None = None, page: int = Query(1, ge=1),
              page_size: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
              _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    q = db.query(LlmDecision)
    if intersection_id:
        q = q.filter(LlmDecision.intersection_id == intersection_id)
    if status:
        q = q.filter(LlmDecision.status == status)
    total = q.count()
    rows = q.order_by(LlmDecision.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [decision_out(r, with_context=True) for r in rows], "total": total, "page": page,
            "page_size": page_size}


# ------------------------------------------------------------------ trợ lý vận hành
class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=100_000)  # trả lời dài của trợ lý được gửi lại trong lịch sử


class ChatIn(BaseModel):
    messages: list[ChatMsg] = Field(min_length=1, max_length=40)
    intersection_id: int | None = None


@router.post("/assistant/chat")
async def assistant_chat(body: ChatIn, cur: CurrentUser = Depends(require(Perm.ASSISTANT_USE))):
    if not is_configured():
        raise HTTPException(503, "Chưa cấu hình GROQ_API_KEY — trợ lý LLM đang tắt")
    try:
        return await assistant.run_chat(cur, [m.model_dump() for m in body.messages], body.intersection_id)
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/assistant/actions/{aid}/confirm")
def confirm(aid: str, cur: CurrentUser = Depends(require(Perm.ASSISTANT_USE))):
    try:
        return assistant.confirm_action(aid, cur)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/assistant/actions/{aid}/cancel")
def cancel(aid: str, cur: CurrentUser = Depends(require(Perm.ASSISTANT_USE))):
    assistant.cancel_action(aid, cur)
    return {"ok": True}


class ReportIn(BaseModel):
    intersection_id: int
    hours: float = Field(24, ge=1, le=24 * 31)


@router.post("/report")
async def report(body: ReportIn, cur: CurrentUser = Depends(require(Perm.REPORT_AI))):
    if not is_configured():
        raise HTTPException(503, "Chưa cấu hình GROQ_API_KEY — báo cáo AI đang tắt")
    try:
        return await assistant.make_report(body.intersection_id, body.hours, cur)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


# ------------------------------------------------------------------ streaming (SSE) — hiển thị từng chữ
def _sse(gen):
    async def body():
        async for ev in gen:
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/assistant/chat/stream")
async def assistant_chat_stream(body: ChatIn, cur: CurrentUser = Depends(require(Perm.ASSISTANT_USE))):
    if not is_configured():
        raise HTTPException(503, "Chưa cấu hình GROQ_API_KEY — trợ lý LLM đang tắt")
    return _sse(assistant.run_chat_stream(cur, [m.model_dump() for m in body.messages], body.intersection_id))


@router.post("/report/stream")
async def report_stream(body: ReportIn, cur: CurrentUser = Depends(require(Perm.REPORT_AI))):
    if not is_configured():
        raise HTTPException(503, "Chưa cấu hình GROQ_API_KEY — báo cáo AI đang tắt")
    return _sse(assistant.make_report_stream(body.intersection_id, body.hours, cur))
