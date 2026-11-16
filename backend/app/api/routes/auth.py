"""US01 — Đăng nhập hệ thống (JWT, bcrypt, khoá tạm chống brute-force)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import CurrentUser, client_ip, get_current_user
from app.core.rbac import perms_of
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.base import utcnow
from app.models.user import User
from app.schemas.user import ChangePassword, LoginRequest, LoginResponse, MeResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    username = body.username.strip()
    user = db.query(User).filter(User.username == username).first()
    now = utcnow()
    if user is None:
        audit(db, "AUTH", "LOGIN_FAILED", f"Đăng nhập thất bại: tài khoản '{username}' không tồn tại",
              username=username, ip=ip, result="FAILURE")
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
    if not user.is_active:
        audit(db, "AUTH", "LOGIN_BLOCKED", "Đăng nhập bị từ chối: tài khoản đã bị khoá", username=username,
              role=user.role, ip=ip, result="FAILURE")
        raise HTTPException(403, "Tài khoản đã bị khoá. Vui lòng liên hệ Quản trị viên.")
    if user.locked_until and user.locked_until > now:
        mins = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        audit(db, "AUTH", "LOGIN_BLOCKED", "Đăng nhập bị từ chối: đang khoá tạm do sai mật khẩu nhiều lần",
              username=username, role=user.role, ip=ip, result="FAILURE")
        raise HTTPException(423, f"Tài khoản tạm khoá do đăng nhập sai nhiều lần. Thử lại sau {mins} phút.")
    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        remaining = settings.max_failed_logins - user.failed_attempts
        if remaining <= 0:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
            db.commit()
            audit(db, "AUTH", "ACCOUNT_TEMP_LOCKED",
                  f"Khoá tạm {settings.lockout_minutes} phút sau {settings.max_failed_logins} lần sai mật khẩu",
                  username=username, role=user.role, ip=ip, result="FAILURE")
            raise HTTPException(423, f"Sai mật khẩu {settings.max_failed_logins} lần. "
                                     f"Tài khoản bị khoá tạm {settings.lockout_minutes} phút.")
        db.commit()
        audit(db, "AUTH", "LOGIN_FAILED",
              f"Sai mật khẩu (lần {user.failed_attempts}/{settings.max_failed_logins})",
              username=username, role=user.role, ip=ip, result="FAILURE")
        raise HTTPException(401, f"Sai tên đăng nhập hoặc mật khẩu. Còn {remaining} lần thử trước khi bị khoá tạm.")

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
