"""Các mục nhỏ: tham số lệnh, WebSocket dữ liệu sai, nguồn camera."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.vision_engine.source_policy import SourceNotAllowed, validate_source


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _auth(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize("params", [{"seconds": "abc"}, {"seconds": "nan"}, {"seconds": None}, {"seconds": True}])
def test_bad_command_params_are_422_not_500(client, params):
    op = _auth(client, "operator", "operator123")
    r = client.post("/api/signals/1/command", headers=op,
                    json={"command": "EXTEND_GREEN", "params": params, "confirm": True})
    assert r.status_code == 422, r.text


def test_goto_phase_rejects_fractional_id(client):
    op = _auth(client, "operator", "operator123")
    r = client.post("/api/signals/1/command", headers=op,
                    json={"command": "GOTO_PHASE", "params": {"phase_id": 1.5}, "confirm": True})
    assert r.status_code == 422


def test_websocket_survives_garbage(client):
    op = _auth(client, "operator", "operator123")
    t = client.post("/api/auth/ticket", headers=op, json={"purpose": "ws"}).json()["ticket"]
    with client.websocket_connect(f"/ws/live?ticket={t}") as ws:
        ws.receive_text()  # hello
        ws.send_text('{"type":"subscribe","intersection_id":"abc"}')
        ws.send_text("[1,2,3]")
        ws.send_text('{"type":"ping","t":1}')
        for _ in range(50):
            if '"pong"' in ws.receive_text():
                break
        else:
            pytest.fail("không nhận được pong")


@pytest.mark.parametrize("stype,url", [
    ("RTSP", "rtsp://127.0.0.1/x"),
    ("HTTP", "http://169.254.169.254/latest/meta-data"),
    ("HTTP", "http://[::1]/"),
    ("HTTP", "file:///etc/passwd"),
    ("RTSP", "http://192.168.1.10/x"),
    ("FILE", "/etc/passwd"),
    ("FILE", "file:///etc/passwd"),
])
def test_disallowed_sources(stype, url):
    with pytest.raises(SourceNotAllowed):
        validate_source(stype, url)


def test_allowed_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("STCS_CAMERA_FILE_DIRS", str(tmp_path))
    validate_source("RTSP", "rtsp://192.168.1.10:554/stream1")
    validate_source("HTTP", "http://10.0.0.5/mjpg")
    validate_source("FILE", str(tmp_path / "clip.mp4"))
    validate_source("SIMULATED", "rtsp://127.0.0.1/whatever")
    with pytest.raises(SourceNotAllowed):
        validate_source("FILE", str(tmp_path / ".." / "escape.mp4"))


def test_camera_api_rejects_ssrf(client):
    admin = _auth(client, "admin", "admin123")
    cam = client.get("/api/cameras", headers=admin).json()[0]
    r = client.patch(f"/api/cameras/{cam['id']}", headers=admin,
                     json={"source_type": "HTTP", "stream_url": "http://169.254.169.254/"})
    assert r.status_code == 422

