"""client_ip: không tin X-Forwarded-For từ client trực tiếp (chống giả mạo IP trong audit)."""
import dataclasses

import pytest
from starlette.requests import Request

from app.core import deps


def _req(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 1234) if peer else None, "headers": headers})


@pytest.fixture(autouse=True)
def proxies(monkeypatch):
    cfg = dataclasses.replace(deps.settings, trusted_proxies=("127.0.0.1", "10.0.0.0/8"))
    monkeypatch.setattr(deps, "settings", cfg)
    deps._trusted_networks.cache_clear()
    yield
    deps._trusted_networks.cache_clear()


@pytest.mark.parametrize("peer,xff,expected", [
    ("203.0.113.9", "1.2.3.4", "203.0.113.9"),               # client trực tiếp tự gửi XFF → bỏ qua
    ("10.0.0.5", "198.51.100.7", "198.51.100.7"),            # qua proxy tin cậy
    ("10.0.0.5", "6.6.6.6, 198.51.100.7", "198.51.100.7"),   # phần bên trái do client giả mạo
    ("10.0.0.5", "198.51.100.7, 10.0.0.9", "198.51.100.7"),  # nhiều tầng proxy
    ("10.0.0.5", "not-an-ip", "10.0.0.5"),                   # giá trị rác
    ("10.0.0.5", None, "10.0.0.5"),
    (None, "1.2.3.4", "unknown"),
])
def test_client_ip(peer, xff, expected):
    assert deps.client_ip(_req(peer, xff)) == expected
