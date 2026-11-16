"""Kiểm tra nguồn video camera trước khi lưu (chống SSRF / đọc file tuỳ ý qua OpenCV).

OpenCV (FFmpeg) mở được rất nhiều giao thức và mọi đường dẫn trên máy chủ, nên người có quyền cấu hình có thể
trỏ camera tới file nhạy cảm hoặc dịch vụ nội bộ (vd. metadata cloud 169.254.169.254). Quy tắc:

- RTSP: chỉ rtsp:// / rtsps://;  HTTP: chỉ http:// / https://.
- Không cho host là loopback, link-local (gồm metadata cloud), multicast, 0.0.0.0. Dải LAN riêng (10/8,
  192.168/16…) VẪN được phép vì camera thật thường nằm ở đó.
- FILE: đường dẫn phải nằm trong một thư mục cho phép (STCS_CAMERA_FILE_DIRS, mặc định backend/data/videos).
"""
from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import BASE_DIR

_SCHEMES = {"RTSP": {"rtsp", "rtsps"}, "HTTP": {"http", "https"}}


class SourceNotAllowed(ValueError):
    pass


def allowed_file_dirs() -> list[Path]:
    raw = os.environ.get("STCS_CAMERA_FILE_DIRS", str(BASE_DIR / "data" / "videos"))
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved


def _check_host(host: str) -> None:
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return  # chưa phân giải được (camera chưa lên mạng) — runtime sẽ báo OFFLINE
        addrs = {ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos}
    for ip in addrs:
        if _blocked_ip(ip):
            raise SourceNotAllowed(f"Không cho phép nguồn camera trỏ tới địa chỉ nội bộ máy chủ ({ip})")


def validate_source(source_type: str, stream_url: str) -> None:
    if source_type == "SIMULATED":
        return
    url = (stream_url or "").strip()
    if source_type == "FILE":
        if "://" in url:
            raise SourceNotAllowed("Nguồn FILE phải là đường dẫn file, không phải URL")
        path = Path(url).expanduser().resolve()
        dirs = allowed_file_dirs()
        if not any(path.is_relative_to(d) for d in dirs):
            raise SourceNotAllowed("File video phải nằm trong thư mục cho phép: " + ", ".join(map(str, dirs)))
        return
    parts = urlsplit(url)
    if parts.scheme.lower() not in _SCHEMES.get(source_type, set()):
        raise SourceNotAllowed(f"Nguồn {source_type} phải dùng giao thức {'/'.join(sorted(_SCHEMES[source_type]))}")
    if not parts.hostname:
        raise SourceNotAllowed("Stream URL thiếu địa chỉ máy")
    _check_host(parts.hostname)
