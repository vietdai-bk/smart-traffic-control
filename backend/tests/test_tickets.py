"""Vé dùng một lần cho WebSocket / MJPEG: JWT không còn nằm trên URL."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.tickets import TicketStore
from app.main import app


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_ticket_single_use_purpose_and_expiry():
    clock = Clock()
    s = TicketStore(clock)
    t = s.issue(7, "ws:live")
    assert s.consume(t, "ws:live") == 7
    assert s.consume(t, "ws:live") is None          # chỉ dùng một lần
    t = s.issue(7, "stream:1")
    assert s.consume(t, "stream:2") is None          # sai mục đích
    assert s.consume(t, "stream:1") is None          # và đã bị huỷ
    t = s.issue(7, "ws:live", ttl_s=30)
    clock.t = 31
    assert s.consume(t, "ws:live") is None           # hết hạn


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _auth(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_websocket_requires_ticket_not_jwt(client):
    h = _auth(client, "operator", "operator123")
    jwt = h["Authorization"].split()[1]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/live?token={jwt}") as ws:
            ws.receive_text()
    t = client.post("/api/auth/ticket", headers=h, json={"purpose": "ws"}).json()["ticket"]
    with client.websocket_connect(f"/ws/live?ticket={t}") as ws:
        assert '"hello"' in ws.receive_text()
    with pytest.raises(WebSocketDisconnect):  # vé đã dùng
        with client.websocket_connect(f"/ws/live?ticket={t}") as ws:
            ws.receive_text()


def test_ticket_endpoint_auth_and_permissions(client):
    assert client.post("/api/auth/ticket", json={"purpose": "ws"}).status_code == 401
    op = _auth(client, "operator", "operator123")
    assert client.post("/api/auth/ticket", headers=op, json={"purpose": "stream"}).status_code == 422
    assert client.post("/api/auth/ticket", headers=op,
                       json={"purpose": "stream", "camera_id": 1}).status_code == 200


def test_mjpeg_rejects_bad_ticket(client):
    assert client.get("/api/cameras/1/stream.mjpg?ticket=bogus").status_code == 401
    assert client.get("/api/cameras/1/stream.mjpg").status_code == 422
