from fastapi.testclient import TestClient

from app import db
from app.main import app


def test_board_calls_and_analytics():
    async def setup():
        await db.execute("TRUNCATE calls, suggestions, events CASCADE")
        await db.execute(
            """INSERT INTO calls (call_id, lane, cluster, reason, red_flags, red_flag_at, transfer_started_at, transfer_ended_at, transfer_status, details, recording) VALUES
               ('a1', 'amber', 'family', 'family_locating', '{}', NULL, NULL, NULL, NULL, '{"caller_name": {"value": "Daniel Reyes", "status": "confirmed"}}', NULL),
               ('a2', 'amber', 'child', 'child_under_2', '{}', NULL, NULL, NULL, NULL, '{}', NULL),
               ('r1', 'red', 'injury_or_illness', NULL, '{chest_pain}', now() - interval '20 s', now() - interval '16 s', now() - interval '10 s', 'connected', '{}', '\\x00ff'),
               ('r2', 'red', 'injury_or_illness', NULL, '{bleeding}', now() - interval '30 s', now() - interval '25 s', now(), 'no_answer', '{"callback_number": {"value": "4155550142", "status": "unconfirmed"}}', NULL),
               ('g1', 'green', 'outage', NULL, '{}', NULL, NULL, NULL, NULL, '{}', NULL)""")
        await db.execute("INSERT INTO transcript_items (call_id, item_id, role, content, time_sec) VALUES ('r1', '1', 'user', 'chest feels tight', 1)")
    with TestClient(app) as client:
        client.portal.call(setup)
        b = client.get("/api/board").json()
        assert b["lanes"] == {"amber": 2, "red": 2, "green": 1}
        assert [c["call_id"] for c in b["amber_queue"]] == ["a2", "a1"]  # child under 2 first
        assert {"cluster": "injury_or_illness", "calls": 2, "red_flags": 2} in b["clusters"]

        assert [c["call_id"] for c in client.get("/api/calls?lane=red").json()] in (["r1", "r2"], ["r2", "r1"])
        card = client.get("/api/calls/r1").json()
        assert card["has_recording"] and card["transcript"][0]["content"] == "chest feels tight"
        assert client.get("/api/calls/r1/recording").content == b"\x00\xff"
        assert client.get("/api/calls/nope").status_code == 404

        a = client.get("/api/analytics").json()
        assert a["handoff"]["red_calls"] == 2 and a["handoff"]["told_to_call_911"] == 1
        assert a["handoff"]["share_told_to_call_911"] == 0.5
        assert float(a["handoff"]["mean_sec_flag_to_transfer"]) == 4.5
        assert a["details"]["confirmation_rate"] == 0.5
