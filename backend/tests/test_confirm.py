import uuid

import pytest
from fastapi.testclient import TestClient

from app.details.confirm import judge_reply
from app.main import app


@pytest.mark.parametrize("reply, want", [
    ("yeah that's right", "yes"),
    ("yes", "yes"),
    ("correct", "yes"),
    ("no, it's zero one four three", "no"),
    ("yes, no wait, it's 43", "no"),
    ("hmm", None),
])
def test_judge_reply(reply, want):
    assert judge_reply(reply) == want


def tool(client, name, call, **args):
    r = client.post(f"/retell/tools/{name}", json={"name": name, "call": call, "args": args})
    assert r.status_code == 200, r.text
    return r.json()


def test_confirm_loop_against_db():
    call_id = f"test_{uuid.uuid4().hex[:8]}"
    turns = ["I need to move my appointment", "four one five five five five zero one four three"]
    call = lambda: {"call_id": call_id, "from_number": "+14155550000",
                    "transcript_object": [{"role": "user", "content": t} for t in turns]}
    with TestClient(app) as client:
        # 1st capture: the transcript heard ...0143, the speech model heard ...0142.
        r = tool(client, "capture_detail", call(), field="callback_number", model_heard="4155550142")
        assert r["read_back"] == "four one five, five five five, zero one four three"

        # Caller says no. The agent wrongly reports "confirmed": the transcript wins.
        turns.append("no, it's zero one four two")
        assert tool(client, "confirm_detail", call(), field="callback_number", confirmed=True)["status"] == "retry"

        # 2nd capture, then a real yes.
        turns.append("four one five, five five five, zero one four two")
        tool(client, "capture_detail", call(), field="callback_number", model_heard="4155550142")
        turns.append("yes that's right")
        assert tool(client, "confirm_detail", call(), field="callback_number", confirmed=True)["status"] == "confirmed"

        # Read back through the API layer's DB connection.
        from app import db
        import asyncio
        async def check():
            row = await db.fetchrow("SELECT callback_number, callback_source, details FROM calls WHERE call_id = %s", call_id)
            types = [e["type"] for e in await db.fetch("SELECT type FROM events WHERE call_id = %s ORDER BY id", call_id)]
            await db.execute("DELETE FROM calls WHERE call_id = %s", call_id)
            return row, types
        row, types = client.portal.call(check)
    assert row["callback_number"] == "4155550142" and row["callback_source"] == "confirmed"
    assert row["details"]["callback_number"]["attempts"] == 2
    assert types == ["stt_model_mismatch", "confirm_disagreement", "detail_rejected", "detail_confirmed"]
