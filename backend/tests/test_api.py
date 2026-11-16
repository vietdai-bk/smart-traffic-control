"""Kiểm thử API: xác thực, RBAC, xác nhận an toàn, cấu hình, thống kê (US01, US02, US08, US10, US13, US15)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture(scope="module")
def tokens(client):
    out = {}
    for u, p in (("admin", "admin123"), ("operator", "operator123"), ("manager", "manager123")):
        r = login(client, u, p)
        assert r.status_code == 200, r.text
        out[u] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return out


def test_login_errors(client):
    nobody = login(client, "nobody", "x")
    wrong = login(client, "manager", "wrong")
    # Không phân biệt được tên không tồn tại với sai mật khẩu
    assert nobody.status_code == wrong.status_code == 401
    assert nobody.json() == wrong.json()
    assert login(client, "operator2", "wrong").status_code == 401        # khoá nhưng sai mật khẩu: không lộ
    assert login(client, "operator2", "operator123").status_code == 403  # tài khoản bị khoá


def test_temporary_lockout_after_failed_attempts(client, tokens):
    client.post("/api/users", headers=tokens["admin"], json={
        "username": "brute", "full_name": "Brute Force", "role": "MANAGER", "password": "secret123"})
    for _ in range(4):
        assert login(client, "brute", "nope").status_code == 401
    assert login(client, "brute", "nope").status_code == 423
    assert login(client, "brute", "secret123").status_code == 423


def test_me_and_permissions(client, tokens):
    r = client.get("/api/auth/me", headers=tokens["operator"])
    assert r.status_code == 200
    perms = r.json()["permissions"]
    assert "signal:control" in perms and "users:manage" not in perms
    assert client.get("/api/auth/me").status_code == 401


def test_rbac(client, tokens):
    assert client.get("/api/users", headers=tokens["operator"]).status_code == 403
    assert client.get("/api/users", headers=tokens["admin"]).status_code == 200
    assert client.get("/api/audit", headers=tokens["manager"]).status_code == 200
    assert client.get("/api/audit", headers=tokens["operator"]).status_code == 403
    body = {"command": "NEXT_PHASE", "confirm": True}
    assert client.post("/api/signals/1/command", headers=tokens["manager"], json=body).status_code == 403


def test_signal_command_requires_confirmation(client, tokens):
    r = client.post("/api/signals/1/command", headers=tokens["operator"], json={"command": "NEXT_PHASE"})
    assert r.status_code == 428
    r = client.post("/api/signals/1/mode", headers=tokens["operator"], json={"mode": "MANUAL"})
    assert r.status_code == 428


def test_mode_switch_and_command(client, tokens):
    r = client.post("/api/signals/1/mode", headers=tokens["operator"], json={"mode": "MANUAL", "confirm": True})
    assert r.status_code == 200 and r.json()["signal"]["mode"] == "MANUAL"
    r = client.post("/api/signals/1/command", headers=tokens["operator"],
                    json={"command": "NEXT_PHASE", "confirm": True, "reason": "test"})
    assert r.status_code == 200 and r.json()["status"] in ("EXECUTED", "SCHEDULED", "ACCEPTED")
    r = client.post("/api/signals/1/mode", headers=tokens["operator"], json={"mode": "FAILSAFE", "confirm": True})
    assert r.status_code == 422  # FAILSAFE không thể chọn thủ công
    r = client.post("/api/signals/1/mode", headers=tokens["operator"], json={"mode": "AUTO", "confirm": True})
    assert r.json()["signal"]["mode"] == "AUTO"
    cmds = client.get("/api/signals/1/commands?source=MANUAL", headers=tokens["manager"]).json()
    assert cmds["total"] >= 3


def test_failsafe_on_camera_loss(client, tokens):
    import time

    client.post("/api/simulation/1/camera", headers=tokens["operator"], json={"direction": "EAST", "action": "DISCONNECT"})
    deadline = time.time() + 8
    mode = None
    while time.time() < deadline:
        mode = client.get("/api/signals/1/state", headers=tokens["operator"]).json()["signal"]["mode"]
        if mode == "FAILSAFE":
            break
        time.sleep(0.5)
    assert mode == "FAILSAFE"
    r = client.post("/api/signals/1/recover", headers=tokens["operator"], json={"mode": "AUTO", "confirm": True})
    assert r.json()["status"] == "REJECTED"
    client.post("/api/simulation/1/reset", headers=tokens["operator"])
    time.sleep(1.5)
    r = client.post("/api/signals/1/recover", headers=tokens["operator"], json={"mode": "AUTO", "confirm": True})
    assert r.json()["status"] == "EXECUTED"


def test_intersection_config_validation(client, tokens):
    r = client.patch("/api/intersections/1", headers=tokens["admin"], json={"min_green_s": 90, "max_green_s": 60})
    assert r.status_code == 422
    r = client.patch("/api/intersections/1", headers=tokens["operator"], json={"density_high": 75})
    assert r.status_code == 403
    r = client.patch("/api/intersections/1", headers=tokens["admin"], json={"density_high": 75})
    assert r.status_code == 200 and r.json()["density_high"] == 75


def test_camera_crud_and_ping(client, tokens):
    r = client.post("/api/intersections", headers=tokens["admin"], json={
        "code": "TEST-01", "name": "Nút giao kiểm thử", "create_default_cameras": False})
    assert r.status_code == 201
    iid = r.json()["id"]
    r = client.post("/api/cameras", headers=tokens["admin"], json={
        "intersection_id": iid, "code": "CAM-T-N", "name": "Cam test", "direction": "NORTH"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert len(r.json()["roi"]) == 4
    dup = client.post("/api/cameras", headers=tokens["admin"], json={
        "intersection_id": iid, "code": "CAM-T-N2", "name": "Cam test 2", "direction": "NORTH"})
    assert dup.status_code == 409
    assert client.post(f"/api/cameras/{cid}/ping", headers=tokens["operator"]).status_code == 200
    assert client.delete(f"/api/intersections/{iid}", headers=tokens["admin"]).status_code == 204


def test_stats_and_evaluation(client, tokens):
    h = tokens["manager"]
    assert client.get("/api/stats/timeseries?preset=7d", headers=h).json()
    by = client.get("/api/stats/by-direction?preset=24h&intersection_id=1", headers=h).json()
    assert {d["direction"] for d in by} == {"NORTH", "SOUTH", "EAST", "WEST"}
    r = client.get("/api/stats/export?preset=24h&format=csv", headers=h)
    assert r.status_code == 200 and "Nút giao" in r.text
    r = client.get("/api/stats/export?preset=24h&format=json", headers=h)
    assert r.json()["rows"]
    ev = client.get("/api/evaluation/summary?days=7", headers=h).json()
    assert ev["improvement"]["wait_reduction_pct"] > 0
    assert len(client.get("/api/evaluation/hourly", headers=h).json()) == 24
    assert client.get("/api/stats/overview?preset=custom", headers=h).status_code == 422


def test_alert_ack_flow(client, tokens):
    page = client.get("/api/incidents?status=OPEN", headers=tokens["operator"]).json()
    inc = next((i for i in page["items"] if i["recovered_at"]), None)
    if inc:
        r = client.post(f"/api/incidents/{inc['id']}/resolve", headers=tokens["operator"],
                        json={"note": "Đã thay cáp mạng"})
        assert r.status_code == 200 and r.json()["status"] == "RESOLVED"
    assert client.post("/api/alerts/999999/ack", headers=tokens["operator"], json={}).status_code == 404
    assert client.post("/api/alerts/1/ack", headers=tokens["manager"], json={}).status_code == 403
