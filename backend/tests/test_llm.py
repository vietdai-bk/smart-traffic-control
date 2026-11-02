"""Kiểm thử tầng 3 (LLM Supervisor) và trợ lý LLM — LLM được giả lập, không gọi Groq thật."""
import pytest
from fastapi.testclient import TestClient

from app.control_engine.adaptive import AdaptivePlanner, ApproachDemand
from app.control_engine.fsm import GreenPlan
from app.control_engine.safety import TimingConstraints
from app.llm import supervisor as sup_mod
from app.llm.client import LLMReply
from app.llm.supervisor import ProposalInvalid, validate_proposal
from app.main import app


# ------------------------------------------------------------------ lớp kiểm tra đầu ra LLM
def test_validate_accepts_and_clamps():
    p, notes = validate_proposal(
        {"strategy": "prioritize_ns", "weight_ns": 1.4, "weight_ew": 1.0, "duration_min": 99, "reason": "Hàng đợi Bắc 120 m"},
        (1.0, 1.0),
    )
    assert p["strategy"] == "PRIORITIZE_NS" and p["weight_ns"] == 1.4 and p["duration_min"] == 30
    assert notes


@pytest.mark.parametrize("bad", [
    {"strategy": "TURN_ALL_GREEN", "weight_ns": 1, "weight_ew": 1, "reason": "x"},
    {"strategy": "BALANCED", "weight_ns": "abc", "weight_ew": 1, "reason": "x"},
    {"strategy": "BALANCED", "weight_ns": 1, "weight_ew": 1, "reason": ""},
    {"strategy": "PRIORITIZE_EW", "weight_ns": 1.5, "weight_ew": 1.0, "reason": "mâu thuẫn"},
    {"strategy": "BALANCED", "weight_ns": float("nan"), "weight_ew": 1, "reason": "x"},
])
def test_validate_rejects(bad):
    with pytest.raises(ProposalInvalid):
        validate_proposal(bad, (1.0, 1.0))


def test_validate_limits_step_and_range():
    p, notes = validate_proposal({"strategy": "PRIORITIZE_NS", "weight_ns": 9, "weight_ew": 0.1, "reason": "x"}, (1.0, 1.0))
    assert p["weight_ns"] == 1.5 and p["weight_ew"] == 0.5  # kẹp miền [0.5, 2] rồi biên độ ±0.5
    assert len(notes) >= 3


def test_weights_only_shift_split_and_respect_limits():
    planner = AdaptivePlanner(max_step_s=100)
    t = TimingConstraints(min_green=10, max_green=60, yellow=3, all_red=2, cycle_min=40, cycle_max=120)
    dem = {d: ApproachDemand(d, 600, 5, 30, 40) for d in ("NORTH", "SOUTH", "EAST", "WEST")}
    prev = GreenPlan(30, 30)
    neutral = planner.compute(dem, t, 2, 1800, prev)
    biased = planner.compute(dem, t, 2, 1800, prev, weights=(2.0, 0.5))
    assert abs(neutral.plan.green_ns - neutral.plan.green_ew) <= 1
    assert biased.plan.green_ns > biased.plan.green_ew
    assert biased.plan.green_ew >= t.min_green and biased.plan.green_ns <= t.max_green
    assert biased.webster_cycle_s == pytest.approx(neutral.webster_cycle_s)


# ------------------------------------------------------------------ API (LLM giả lập)
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _auth(client, u, p):
    r = client.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def fake_llm(monkeypatch):
    replies: list[LLMReply] = []

    async def fake_chat(messages, **kw):
        return replies.pop(0)

    monkeypatch.setattr(sup_mod, "is_configured", lambda: True)
    monkeypatch.setattr(sup_mod, "chat", fake_chat)
    import app.api.routes.llm as routes
    import app.llm.assistant as asst
    monkeypatch.setattr(routes, "is_configured", lambda: True)
    monkeypatch.setattr(asst, "chat", fake_chat)
    return replies


def test_viewer_role_permissions(client):
    h = _auth(client, "viewer", "viewer123")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.get("/api/signals/1/state", headers=h).status_code == 403   # không xem video/live (NFR15)
    assert client.post("/api/llm/1/mode", json={"mode": "OFF"}, headers=h).status_code == 403


def test_supervisor_advisory_flow(client, fake_llm):
    h = _auth(client, "operator", "operator123")
    client.post("/api/signals/1/mode", json={"mode": "AUTO", "confirm": True, "reason": "test"}, headers=h)
    assert client.post("/api/llm/1/mode", json={"mode": "ADVISORY"}, headers=h).status_code == 200
    fake_llm.append(LLMReply(content='{"strategy":"PRIORITIZE_EW","weight_ns":1.0,"weight_ew":1.3,'
                                     '"duration_min":5,"reason":"Hàng đợi Đông dài 90 m"}', model="fake"))
    r = client.post("/api/llm/1/run", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "PENDING"
    assert client.post(f"/api/llm/1/decisions/{d['id']}/approve", headers=h).status_code == 200
    from app.services.manager import manager
    st = manager.get(1).llm
    assert st.strategy == "PRIORITIZE_EW" and st.weight_ew == 1.3


def test_supervisor_invalid_output_is_rejected(client, fake_llm):
    h = _auth(client, "operator", "operator123")
    from app.services.manager import manager
    manager.get(1).llm.reset()
    fake_llm.append(LLMReply(content='{"strategy":"ALL_GREEN","weight_ns":5}', model="fake"))
    d = client.post("/api/llm/1/run", headers=h).json()
    assert d["status"] == "INVALID"
    assert manager.get(1).llm.strategy == "BALANCED"


def test_assistant_action_needs_confirmation(client, fake_llm):
    h = _auth(client, "operator", "operator123")
    call = {"id": "c1", "type": "function", "function": {"name": "propose_action", "arguments":
            '{"intersection_id":1,"action":"SET_MODE","params":{"mode":"FIXED_TIME"},"reason":"thử"}'}}
    fake_llm.append(LLMReply(content="", tool_calls=[call], model="fake"))
    fake_llm.append(LLMReply(content="Đã tạo đề xuất, vui lòng xác nhận.", model="fake"))
    r = client.post("/api/llm/assistant/chat", json={"messages": [{"role": "user", "content": "chuyển cố định"}],
                                                    "intersection_id": 1}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    from app.services.manager import manager
    assert manager.get(1).fsm.mode.value == "AUTO"  # chưa thực thi
    aid = body["actions"][0]["id"]
    mgr = _auth(client, "manager", "manager123")
    assert client.post(f"/api/llm/assistant/actions/{aid}/confirm", headers=mgr).status_code == 403
    c = client.post(f"/api/llm/assistant/actions/{aid}/confirm", headers=h)
    assert c.status_code == 200 and c.json()["ok"], c.text
    assert manager.get(1).fsm.mode.value == "FIXED_TIME"
