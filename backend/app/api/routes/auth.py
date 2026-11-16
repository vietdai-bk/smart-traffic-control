"""US01 — Đăng nhập hệ thống (JWT, bcrypt, khoá tạm chống brute-force)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import CurrentUser, client_ip, get_current_user
from app.core.login_guard import login_guard
from app.core.rbac import Perm, has_perm, perms_of
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tickets import TICKET_TTL_S, stream_purpose, tickets, ws_purpose
from app.db.session import get_db
from app.models.base import utcnow
from app.models.user import User
from app.schemas.user import (
    ChangePassword,
    LoginRequest,
    LoginResponse,
    MeResponse,
    TicketRequest,
    TicketResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# Hash giả để tên không tồn tại vẫn tốn thời gian bcrypt như tên có thật (chống dò qua thời gian phản hồi)
_DUMMY_HASH = hash_password("stcs-timing-equaliser")
_BAD_CREDENTIALS = "Sai tên đăng nhập hoặc mật khẩu"


def _blocked(seconds: float) -> HTTPException:
    mins = max(1, int(seconds // 60) + (1 if seconds % 60 else 0))
    return HTTPException(423, f"Đăng nhập tạm bị chặn do sai nhiều lần. Thử lại sau {mins} phút.")


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Phản hồi cho tên không tồn tại và sai mật khẩu là như nhau (mã, nội dung, thời gian),
    nên không dò được tài khoản nào có thật. Khoá tạm theo cặp (tên, IP) — xem app.core.login_guard."""
    ip = client_ip(request)
    username = body.username.strip()
    wait = login_guard.blocked_for(username, ip)
    if wait > 0:
        audit(db, "AUTH", "LOGIN_BLOCKED", "Đăng nhập bị từ chối: đang khoá tạm do sai nhiều lần từ IP này",
              username=username, ip=ip, result="FAILURE")
        raise _blocked(wait)

    user = db.query(User).filter(User.username == username).first()
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    now = utcnow()
    if not ok or user is None:
        n, locked_s = login_guard.record_failure(username, ip)
        if user is not None:
            user.failed_attempts += 1  # chỉ để hiển thị cho Quản trị viên
            if locked_s:
                user.locked_until = now + timedelta(seconds=locked_s)
            db.commit()
        reason = "tài khoản không tồn tại" if user is None else "sai mật khẩu"
        audit(db, "AUTH", "ACCOUNT_TEMP_LOCKED" if locked_s else "LOGIN_FAILED",
              f"Đăng nhập thất bại: {reason} (lần {n} từ IP này)"
              + (f" — khoá tạm {settings.lockout_minutes} phút với IP này" if locked_s else ""),
              username=username, role=user.role if user else None, ip=ip, result="FAILURE")
        if locked_s:
            raise _blocked(locked_s)
        raise HTTPException(401, _BAD_CREDENTIALS)

    # Chỉ báo "tài khoản bị khoá" cho người đã nhập đúng mật khẩu
    if not user.is_active:
        audit(db, "AUTH", "LOGIN_BLOCKED", "Đăng nhập bị từ chối: tài khoản đã bị khoá", username=username,
              role=user.role, ip=ip, result="FAILURE")
        raise HTTPException(403, "Tài khoản đã bị khoá. Vui lòng liên hệ Quản trị viên.")

    login_guard.record_success(username, ip)
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    token, expires = create_access_token(user.username, user.role, {"tv": user.token_version})
    audit(db, "AUTH", "LOGIN", f"Đăng nhập thành công ({user.full_name})", username=user.username,
          role=user.role, ip=ip)
    return LoginResponse(access_token=token, expires_in=expires, user=UserOut.model_validate(user),
                         permissions=perms_of(user.role))


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.id)
    return MeResponse(user=UserOut.model_validate(user), permissions=perms_of(user.role))


@router.post("/ticket", response_model=TicketResponse)
def ticket(body: TicketRequest, current: CurrentUser = Depends(get_current_user)):
    """Cấp vé dùng một lần (hạn ngắn) để mở WebSocket / luồng MJPEG mà không đặt JWT lên URL."""
    if body.purpose == "stream":
        if body.camera_id is None:
            raise HTTPException(422, "Thiếu camera_id cho vé luồng camera")
        if not has_perm(current.role, Perm.LIVE_VIEW):
            raise HTTPException(403, "Không có quyền xem luồng camera")
        purpose = stream_purpose(body.camera_id)
    else:
        purpose = ws_purpose()
    return TicketResponse(ticket=tickets.issue(current.id, purpose), expires_in=int(TICKET_TTL_S))


@router.post("/logout")
def logout(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # JWT không lưu trạng thái: thu hồi bằng cách tăng token_version (đăng xuất mọi phiên của tài khoản)
    user = db.get(User, current.id)
    user.revoke_tokens()
    db.commit()
    audit(db, "AUTH", "LOGOUT", "Đăng xuất", username=current.username, role=current.role, ip=client_ip(request))
    return {"ok": True}


@router.post("/change-password")
def change_password(body: ChangePassword, request: Request, current: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    user = db.get(User, current.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Mật khẩu hiện tại không đúng")
    user.password_hash = hash_password(body.new_password)
    user.revoke_tokens()
    db.commit()
    audit(db, "USER", "CHANGE_PASSWORD", "Đổi mật khẩu cá nhân", username=current.username, role=current.role,
          target=current.username, ip=client_ip(request))
    return {"ok": True}
