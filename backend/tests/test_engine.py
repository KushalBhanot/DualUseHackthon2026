import uuid

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.supervisor import engine


async def reset():
    await db.execute("TRUNCATE calls, suggestions, events CASCADE")
    await db.execute("UPDATE surge_state SET surge_on = false, status_message = NULL")


async def add_calls(n, minutes_ago=1, **cols):
    for _ in range(n):
        await db.execute(
            f"INSERT INTO calls (call_id, started_at, {', '.join(cols)}) VALUES (%s, now() - make_interval(mins => %s){', %s' * len(cols)})",
            f"t_{uuid.uuid4().hex[:8]}", minutes_ago, *cols.values(),
        )


async def open_of(type_):
    return await db.fetch("SELECT * FROM suggestions WHERE type = %s AND status = 'open'", type_)


def test_surge_prompt_not_yet_and_reask():
    async def go():
        await reset()
        await add_calls(18, minutes_ago=1, cluster="outage", status="ended", lane="green")
        await engine.tick()
        first = await open_of("surge_mode")
        await engine.tick()  # same numbers: still one suggestion, not two
        again = await open_of("surge_mode")
        return first, again
    with TestClient(app) as client:
        first, again = client.portal.call(go)
        assert len(first) == 1 and len(again) == 1
        assert first[0]["evidence"]["text"].startswith("18 calls in 3 min (normal ≈ 1). 18 about outage.")

        sid = first[0]["id"]
        assert client.post(f"/api/suggestions/{sid}/snooze").json()["status"] == "snoozed"

        async def after_snooze():
            await engine.tick()
            hidden = await open_of("surge_mode")
            await db.execute("UPDATE suggestions SET snooze_until = now() - interval '1 second' WHERE id = %s", sid)
            await add_calls(4, minutes_ago=0, cluster="outage", status="ended")
            await engine.tick()
            return hidden, await open_of("surge_mode")
        hidden, back = client.portal.call(after_snooze)
        assert hidden == [] and len(back) == 1 and back[0]["evidence"]["calls"] == 22

        assert client.post(f"/api/suggestions/{sid}/accept").json()["status"] == "accepted"
        assert client.get("/api/surge").json()["surge_on"] is True


def test_status_message_suggestion_and_accept_with_edit():
    async def go():
        await reset()
        await add_calls(6, cluster="outage", lane="green")
        await add_calls(3, cluster="billing", lane="green")
        await engine.tick()
        return await open_of("status_message")
    with TestClient(app) as client:
        [s] = client.portal.call(go)
        assert s["recommendation"]["template_id"] == "power_outage"
        edited = "The ER is open on backup power. Use the Elm Street entrance."
        client.post(f"/api/suggestions/{s['id']}/accept", json={"message": edited})
        assert client.get("/api/status-messages").json()["active"] == edited

        async def next_tick():
            await engine.tick()  # a message is active now: no new suggestion
            return await open_of("status_message")
        assert client.portal.call(next_tick) == []


def test_nurse_staffing_rises_only_when_numbers_go_up():
    async def go():
        await reset()
        await add_calls(14, minutes_ago=22, lane="amber", status="ended")
        await engine.tick()
        return await open_of("staffing_nurses")
    with TestClient(app) as client:
        [s] = client.portal.call(go)
        assert s["recommendation"]["count"] >= 1 and "oldest waiting 22 min" in s["evidence"]["text"]
        client.post(f"/api/suggestions/{s['id']}/dismiss")

        async def same_then_more():
            await engine.tick()
            same = await open_of("staffing_nurses")
            await add_calls(20, minutes_ago=5, lane="red", status="ended")
            await engine.tick()
            return same, await open_of("staffing_nurses"), await open_of("staffing_doctors")
        same, more, doctors = client.portal.call(same_then_more)
        assert same == []  # dismissed, numbers unchanged: don't nag
        assert len(more) == 1 and more[0]["recommendation"]["count"] > s["recommendation"]["count"]
        assert doctors[0]["recommendation"]["count"] == "3+"  # 40 red calls/hour


def test_red_alert_cannot_be_snoozed_only_resolved():
    async def go():
        await reset()
        await db.execute("INSERT INTO calls (call_id, lane) VALUES ('t_red', 'red')")
        await db.execute("INSERT INTO suggestions (type, call_id) VALUES ('red_not_connected', 't_red')")
        return (await db.fetchrow("SELECT id FROM suggestions"))["id"]
    with TestClient(app) as client:
        sid = client.portal.call(go)
        assert client.post(f"/api/suggestions/{sid}/snooze").status_code == 409
        assert client.post(f"/api/suggestions/{sid}/dismiss").status_code == 409
        assert client.post(f"/api/suggestions/{sid}/resolve", json={"outcome": "called_back"}).json()["status"] == "resolved"


def test_nurse_line_api_feeds_inbound():
    with TestClient(app) as client:
        client.portal.call(lambda: db.execute("TRUNCATE nurse_lines"))
        assert client.post("/api/nurse-lines", json={"label": "x", "number": "415"}).status_code == 422
        a = client.post("/api/nurse-lines", json={"label": "Charge nurse", "number": "+14155550001", "priority": 1}).json()
        client.post("/api/nurse-lines", json={"label": "House supervisor", "number": "+14155550002", "priority": 2})
        r = client.post("/retell/inbound", json={"call_inbound": {"call_id": "t_in1"}})
        assert r.json()["call_inbound"]["dynamic_variables"]["nurse_line"] == "+14155550001"
        client.patch(f"/api/nurse-lines/{a['id']}", json={"on_duty": False})
        r = client.post("/retell/inbound", json={"call_inbound": {"call_id": "t_in2"}})
        assert r.json()["call_inbound"]["dynamic_variables"]["nurse_line"] == "+14155550002"
