"""A whole red call through the live pipeline, with fake Retell monitor messages."""

import uuid

from fastapi.testclient import TestClient

from app import db, handoff, monitor
from app.main import app


class FakeRetell:
    def __init__(self):
        self.calls = []
        self.call = self

    async def update_live(self, call_id, call_control=None, **kw):
        self.calls.append((call_id, call_control))


def run(client, coro_fn, *args):
    return client.portal.call(coro_fn, *args)


def test_red_call_steered_then_not_connected(monkeypatch):
    fake = FakeRetell()
    monkeypatch.setattr(monitor, "retell", lambda: fake)
    call_id = f"test_{uuid.uuid4().hex[:8]}"

    async def scenario():
        await db.execute("INSERT INTO calls (call_id, from_number) VALUES (%s, '+14155550142')", call_id)
        live = monitor.LiveCall(call_id)
        items = [
            {"id": "1", "role": "agent", "content": "Is anyone having chest pain, trouble breathing, or bleeding?", "time_sec": 0},
            {"id": "2", "role": "user", "content": "No, nobody.", "time_sec": 4},
            {"id": "3", "role": "tool_call_invocation", "name": "transition_to_callback_routine", "tool_call_id": "t1", "time_sec": 9},
            {"id": "4", "role": "user", "content": "It's about a bill", "time_sec": 10},
            {"id": "4", "role": "user", "content": "It's about a bill, oh no, my wife just fainted", "time_sec": 10},
            {"id": "5", "role": "tool_call_invocation", "name": "transition_to_handoff_now", "tool_call_id": "t2", "time_sec": 14},
            {"id": "6", "role": "tool_call_invocation", "name": "transfer_to_nurse", "tool_call_id": "t3", "time_sec": 16},
            {"id": "7", "role": "tool_call_result", "tool_call_id": "t3", "content": "Transfer failed: no answer", "time_sec": 37},
        ]
        for item in items:
            await live.on_item(item)
        await db.execute("UPDATE calls SET disconnection_reason = 'agent_hangup', ended_at = now() WHERE call_id = %s", call_id)
        await handoff.finish(call_id)
        await handoff.finish(call_id)  # second time must not duplicate the alert

        call = await db.fetchrow("SELECT * FROM calls WHERE call_id = %s", call_id)
        events = [e["type"] for e in await db.fetch("SELECT type FROM events WHERE call_id = %s ORDER BY id", call_id)]
        alerts = await db.fetch("SELECT * FROM suggestions WHERE call_id = %s", call_id)
        n_items = (await db.fetchrow("SELECT count(*) AS n FROM transcript_items WHERE call_id = %s", call_id))["n"]
        await db.execute("DELETE FROM calls WHERE call_id = %s", call_id)
        return call, events, alerts, n_items

    with TestClient(app) as client:
        call, events, alerts, n_items = run(client, scenario)

    # "No, nobody." did not fire; the fainting did, and the agent was steered once.
    assert call["red_flags"] == ["unresponsive"]
    assert len(fake.calls) == 1 and "handoff_now" in fake.calls[0][1]["additional_context"]
    assert fake.calls[0][1]["trigger_response"] is True
    assert call["lane"] == "red" and call["red_flag_at"] and call["transfer_started_at"]
    assert call["transfer_status"] == "no_answer"
    assert call["callback_number"] == "+14155550142" and call["callback_source"] == "caller_id"
    assert n_items == 7  # item 4 was updated in place, not duplicated
    assert events.index("red_flag_detected") < events.index("context_injected") < events.index("transfer_started")
    assert len(alerts) == 1 and alerts[0]["type"] == "red_not_connected" and alerts[0]["status"] == "open"


def test_inbound_gives_nurse_line_and_banner():
    async def setup():
        await db.execute("INSERT INTO nurse_lines (label, number, priority, on_duty) VALUES ('off', '+10000000000', 0, false), ('test charge nurse', '+15550001111', 0, true)")
        await db.execute("UPDATE surge_state SET surge_on = true, status_message = 'The ER is open on backup power.'")

    async def teardown():
        await db.execute("DELETE FROM nurse_lines WHERE number IN ('+10000000000', '+15550001111')")
        await db.execute("UPDATE surge_state SET surge_on = false, status_message = NULL")
        await db.execute("DELETE FROM calls WHERE call_id = 'test_inbound'")

    with TestClient(app) as client:
        client.portal.call(setup)
        try:
            r = client.post("/retell/inbound", json={"event": "call_inbound", "call_inbound": {"call_id": "test_inbound", "from_number": "+14155550142"}})
        finally:
            client.portal.call(teardown)
    v = r.json()["call_inbound"]["dynamic_variables"]
    assert v["nurse_line"] == "+15550001111"
    assert v["surge_banner"] == "The ER is open on backup power."
    assert v["priority_callback_window"] == "within 45 minutes"
