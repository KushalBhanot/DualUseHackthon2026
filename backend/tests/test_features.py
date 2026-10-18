import random
import time

from fastapi.testclient import TestClient

from app import api, db, sim
from app.scenarios import LANG_EARTHQUAKE, SERIOUS_EARTHQUAKE
from app.supervisor import callbacks, engine


def _hangup(call_id="h1", at=None):
    at = at or time.time() - 60
    rng = random.Random(3)
    call, comb = sim.make_call(SERIOUS_EARTHQUAKE[0], "serious_earthquake", at, rng)
    call.update({"call_id": call_id, "disconnection_reason": "user_hangup", "ended_at": at + 10, "duration_ms": 10000, "lane": "green"})
    sim.insert_call(call, comb)
    return call_id


def _status(cid):
    return db.one("SELECT callback_status, callback_attempts, lane FROM calls WHERE call_id=?", (cid,))


def test_hangup_gets_ai_callback_and_an_outcome():
    cid = _hangup()
    now = time.time()
    callbacks.run(now)
    assert _status(cid)["callback_status"] == "ai_queued"
    callbacks.run(now + callbacks.DELAY_S + 1)
    assert _status(cid)["callback_status"] == "ai_calling" and _status(cid)["callback_attempts"] == 1
    callbacks.run(now + callbacks.DELAY_S + callbacks.RING_S + 2)
    assert _status(cid)["callback_status"] in ("ai_reached_ok", "ai_reached_red", "ai_no_answer")


def test_red_on_callback_raises_lane_and_two_misses_open_alert(monkeypatch):
    monkeypatch.setattr(callbacks, "_outcome", lambda cid, attempt: "ai_reached_red")
    cid = _hangup("red1")
    t = time.time()
    for step in range(4):
        callbacks.run(t + step * 40)
    assert _status(cid)["lane"] == "red" and _status(cid)["callback_status"] == "ai_reached_red"

    monkeypatch.setattr(callbacks, "_outcome", lambda cid, attempt: "ai_no_answer")
    cid2 = _hangup("miss1")
    for step in range(8):
        engine.run_once(t + step * 40)
    assert _status(cid2)["callback_status"] == "callback_failed"
    alert = next(s for s in engine.open_suggestions() if s["type"] == "callback_unreachable")
    assert not engine.decide(alert["id"], "dismiss")[0]
    assert engine.decide(alert["id"], "resolve", outcome="try_again")[0]
    assert _status(cid2)["callback_status"] == "ai_queued"


def test_non_english_calls_are_classified_from_the_translation():
    rng = random.Random(5)
    armenian = next(t for t in LANG_EARTHQUAKE if t["lang"] == "hy")
    call, _ = sim.make_call(armenian, "serious_earthquake", time.time(), rng)
    assert call["language"] == "hy" and call["lane"] == "red" and "breathing" in call["red_flags"]
    assert call["transcript"][1]["en"].startswith("My father can't breathe")


def test_hotspots_and_incident_command_brief():
    sim.backfill("serious_earthquake", 40, minutes=10, seed=7)
    b = api.ic_brief()
    assert b["hotspots"] and b["hotspots"][0]["count"] >= 2
    assert "incident command" in b["text"] and b["hotspots"][0]["place"] in b["text"]


def test_report_and_brief_endpoints():
    from app.main import app
    sim.backfill("serious_earthquake", 30, minutes=10, seed=9)
    engine.set_surge(True)
    with TestClient(app) as client:
        assert client.post("/api/ic-brief/sent").status_code == 200
        r = client.get("/api/report")
        assert r.status_code == 200 and "After-action report" in r.text
        assert "Switched surge mode on" in r.text and "Sent a brief to incident command" in r.text
        assert "attachment" in client.get("/api/report?download=1").headers.get("content-disposition", "")
        board = client.get("/api/board").json()
        assert board["languages"] and "callbacks" in board and board["hotspots"]
