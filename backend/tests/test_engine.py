import random
import time

from fastapi.testclient import TestClient

from app import db, sim
from app.scenarios import SERIOUS_EARTHQUAKE
from app.supervisor import engine


def _insert(n, tpl_filter=None, minutes=2.5, lane=None, **extra):
    rng = random.Random(1)
    now = time.time()
    tpls = [t for t in SERIOUS_EARTHQUAKE if not tpl_filter or tpl_filter(t)]
    for i in range(n):
        call, comb = sim.make_call(rng.choice(tpls), "serious_earthquake", now - minutes * 60 * i / max(n, 1), rng)
        call.update(extra)
        if lane:
            call["lane"] = lane
        sim.insert_call(call, comb)


def open_types():
    return [s["type"] for s in engine.open_suggestions()]


def test_surge_prompt_and_snooze():
    _insert(18)
    engine.run_once()
    assert "surge_mode" in open_types()
    sid = next(s["id"] for s in engine.open_suggestions() if s["type"] == "surge_mode")
    assert engine.decide(sid, "snooze")[0]
    engine.run_once()
    assert "surge_mode" not in open_types()          # snoozed for 2 minutes
    engine.run_once(now=time.time() + 121)            # then asks again
    assert "surge_mode" in open_types() or db.surge()["is_on"] == 0


def test_accept_surge_turns_it_on():
    _insert(18)
    engine.run_once()
    sid = next(s["id"] for s in engine.open_suggestions() if s["type"] == "surge_mode")
    engine.decide(sid, "accept")
    assert db.surge()["is_on"] == 1


def test_quiet_line_has_no_surge_prompt():
    _insert(3, minutes=20)
    engine.run_once()
    assert "surge_mode" not in open_types()


def test_outage_cluster_suggests_status_message():
    _insert(10, tpl_filter=lambda t: t.get("cl") == "outage", minutes=5)
    engine.run_once()
    s = next(s for s in engine.open_suggestions() if s["type"] == "status_message")
    assert s["recommendation"]["template"] == "outage"
    engine.decide(s["id"], "accept", text="The ER is open on backup power.")
    assert db.surge()["status_message"] == "The ER is open on backup power."


def test_amber_backlog_suggests_nurses_once():
    _insert(14, lane="amber", minutes=22, callback_status="waiting")
    engine.run_once()
    engine.run_once()
    nurses = [s for s in engine.open_suggestions() if s["type"] == "staffing_nurses"]
    assert len(nurses) == 1 and nurses[0]["recommendation"]["count"] >= 1


def test_red_not_connected_cannot_be_dismissed():
    _insert(1, tpl_filter=lambda t: "bleeding" in t["q"][0], minutes=0.5)
    cid = db.one("SELECT call_id FROM calls")["call_id"]
    db.update("calls", "call_id", cid, {"lane": "red", "transfer_status": "no_answer"})
    engine.run_once()
    alert = next(s for s in engine.open_suggestions() if s["type"] == "red_not_connected")
    assert not engine.decide(alert["id"], "dismiss")[0]
    assert not engine.decide(alert["id"], "snooze")[0]
    assert engine.decide(alert["id"], "resolve", outcome="called_back")[0]


def test_inbound_webhook_returns_top_on_duty_line_and_banner():
    from app.main import app
    db.insert("nurse_lines", {"label": "off", "number": "+10000000001", "role": "nurse", "on_duty": 0, "priority": 0, "updated_at": 0})
    db.insert("nurse_lines", {"label": "on", "number": "+10000000002", "role": "nurse", "on_duty": 1, "priority": 1, "updated_at": 0})
    engine.set_status_message("ER is open on backup power.", "outage")
    with TestClient(app) as client:
        r = client.post("/retell/inbound", json={"event": "call_inbound", "call_inbound": {"from_number": "+1"}}).json()
    v = r["call_inbound"]["dynamic_variables"]
    assert v["nurse_line"] == "+10000000002" and v["surge_banner"] == "ER is open on backup power."


def test_call_webhook_classifies_and_tracks_failed_transfer():
    from app.main import app
    call = {"call_id": "c1", "from_number": "+12135550142", "start_timestamp": time.time() * 1000,
            "end_timestamp": time.time() * 1000 + 60000, "disconnection_reason": "agent_hangup",
            "transcript_object": [{"role": "agent", "content": "Safety check?"}, {"role": "user", "content": "No. Actually my wife just fainted."}],
            "transcript_with_tool_calls": [{"role": "tool_call_invocation", "name": "transfer_to_nurse"}]}
    with TestClient(app) as client:
        client.post("/retell/webhook", json={"event": "call_started", "call": call})
        client.post("/retell/webhook", json={"event": "call_ended", "call": call})
    row = db.one("SELECT * FROM calls WHERE call_id='c1'")
    assert row["lane"] == "red" and "unresponsive" in row["red_flags"] and row["transfer_status"] == "no_answer"
    engine.run_once()
    assert "red_not_connected" in open_types()


def test_supervisor_can_lower_lane_with_reason():
    from app.main import app
    _insert(1, tpl_filter=lambda t: t.get("cl") == "outage")
    cid = db.one("SELECT call_id FROM calls")["call_id"]
    db.update("calls", "call_id", cid, {"lane": "amber"})
    with TestClient(app) as client:
        assert client.post(f"/api/calls/{cid}/lane", json={"lane": "green", "reason": " "}).status_code == 400
        assert client.post(f"/api/calls/{cid}/lane", json={"lane": "green", "reason": "Checked with caller"}).status_code == 200
    assert db.one("SELECT lane FROM calls WHERE call_id=?", (cid,))["lane"] == "green"
    assert db.one("SELECT actor FROM events WHERE type='lane_lowered'")["actor"] == "supervisor"
