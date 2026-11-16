"""US02 — Quản lý tài khoản (CRUD, phân quyền, khoá/mở khoá)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require
from app.core.rbac import ROLE_LABELS, ROLE_PERMISSIONS, Perm, Role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])
_admin = require(Perm.USERS_MANAGE)


@router.get("/roles")
def roles(_: CurrentUser = Depends(_admin)):
    return [
        {"role": r.value, "label": ROLE_LABELS[r], "permissions": sorted(p.value for p in ROLE_PERMISSIONS[r])}
        for r in Role
    ]


@router.get("", response_model=list[UserOut])
def list_users(q: str | None = Query(None), role: str | None = None, db: Session = Depends(get_db),
               _: CurrentUser = Depends(_admin)):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.username.ilike(like), User.full_name.ilike(like), User.email.ilike(like)))
    if role:
        query = query.filter(User.role == role)
    return query.order_by(User.id).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), cur: CurrentUser = Depends(_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, f"Tên đăng nhập '{body.username}' đã tồn tại")
    user = User(username=body.username, full_name=body.full_name, email=body.email, phone=body.phone,
                role=body.role, is_active=body.is_active, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, "USER", "CREATE_USER", f"Tạo tài khoản {user.username} ({ROLE_LABELS[Role(user.role)]})",
          username=cur.username, role=cur.role, target=user.username, ip=client_ip(request),
          details={"role": user.role})
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                cur: CurrentUser = Depends(_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    data = body.model_dump(exclude_unset=True)
    if user.id == cur.id and (data.get("is_active") is False or (data.get("role") and data["role"] != user.role)):
        raise HTTPException(400, "Không thể tự khoá hoặc tự thay đổi vai trò của chính mình")
    changes = {}
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data.pop("password"))
        changes["password"] = "đã đặt lại"
    data.pop("password", None)
    for k, v in data.items():
        if getattr(user, k) != v:
            changes[k] = {"from": getattr(user, k), "to": v}
            setattr(user, k, v)
    if data.get("is_active") is True:
        user.failed_attempts = 0
        user.locked_until = None
    # Đặt lại mật khẩu, đổi vai trò hoặc khoá tài khoản → đăng xuất mọi phiên hiện có của người đó
    if "password" in changes or "role" in changes or changes.get("is_active", {}).get("to") is False:
        user.revoke_tokens()
    db.commit()
    db.refresh(user)
    if "is_active" in changes:
        action = "UNLOCK_USER" if user.is_active else "LOCK_USER"
        desc = f"{'Mở khoá' if user.is_active else 'Khoá'} tài khoản {user.username}"
    elif "role" in changes:
        action, desc = "CHANGE_ROLE", f"Đổi vai trò {user.username}: {changes['role']['from']} → {changes['role']['to']}"
    else:
        action, desc = "UPDATE_USER", f"Cập nhật tài khoản {user.username}"
    audit(db, "USER", action, desc, username=cur.username, role=cur.role, target=user.username,
          ip=client_ip(request), details={k: str(v) for k, v in changes.items()})
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), cur: CurrentUser = Depends(_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if user.id == cur.id:
        raise HTTPException(400, "Không thể xoá chính mình")
    if user.role == "ADMIN" and db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).count() <= 1:
        raise HTTPException(400, "Phải còn ít nhất một Quản trị viên hoạt động")
    username = user.username
    db.delete(user)
    db.commit()
    audit(db, "USER", "DELETE_USER", f"Xoá tài khoản {username}", username=cur.username, role=cur.role,
          target=username, ip=client_ip(request))
