"""FastAPI dependencies: xác thực JWT và kiểm tra quyền RBAC."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.rbac import Perm, has_perm
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: int
    username: str
    full_name: str
    role: str

    def can(self, perm: Perm) -> bool:
        return has_perm(self.role, perm)


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    user = user_from_token(db, creds.credentials if creds else None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(id=user.id, username=user.username, full_name=user.full_name, role=user.role)


def require(*perms: Perm):
    """Dependency factory: yêu cầu người dùng có TẤT CẢ các quyền."""

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        missing = [p.value for p in perms if not user.can(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vai trò {user.role} không có quyền thực hiện thao tác này ({', '.join(missing)})",
            )
        return user

    return _dep


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_any(*perms: Perm):
    """Dependency factory: yêu cầu người dùng có ÍT NHẤT MỘT trong các quyền."""

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(user.can(p) for p in perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vai trò {user.role} không có quyền thực hiện thao tác này",
            )
        return user

    return _dep
