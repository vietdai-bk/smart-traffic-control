"""FastAPI dependencies: xác thực JWT và kiểm tra quyền RBAC."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
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
    # Token cấp trước lần thu hồi gần nhất (đăng xuất, đổi mật khẩu…) không còn hiệu lực
    if payload.get("tv") != user.token_version:
        return None
    return user


def user_from_ticket(db: Session, ticket: str | None, purpose: str) -> User | None:
    """Xác thực bằng vé dùng một lần (WebSocket / MJPEG) — xem app.core.tickets."""
    from app.core.tickets import tickets

    uid = tickets.consume(ticket, purpose)
    if uid is None:
        return None
    user = db.get(User, uid)
    return user if user and user.is_active else None


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


@lru_cache(maxsize=1)
def _trusted_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(p, strict=False) for p in settings.trusted_proxies)


def _is_trusted(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in _trusted_networks())


def client_ip(request: Request) -> str:
    """IP thật của client để ghi audit.

    X-Forwarded-For do client tự gửi nên có thể giả mạo; chỉ tin khi kết nối trực tiếp đến từ proxy tin cậy
    (STCS_TRUSTED_PROXIES). Khi đó duyệt chuỗi từ PHẢI sang TRÁI và lấy địa chỉ đầu tiên không phải proxy
    tin cậy — các phần bên trái do client tự điền (nginx $proxy_add_x_forwarded_for chỉ nối thêm vào cuối).
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    if not _is_trusted(peer):
        return peer
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer  # giá trị rác → không tin, dùng địa chỉ proxy
    return hops[0] if hops else peer


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
