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

        assert {"kpis", "volume_1min", "green", "unsorted", "cluster_series"} <= b.keys()
        assert b["kpis"]["total"] == 5 and b["kpis"]["red_median_handoff_s"] == 4.5
        assert b["kpis"]["ai_handled_share"] == 0.2
        assert len(b["volume_1min"]) == 20 and b["volume_1min"][-1]["calls"] == 5
        assert b["cluster_series"]["injury_or_illness"][-1] == 2
        assert [c["call_id"] for c in b["green"]] == ["g1"]
        assert "details" not in b["red"][0]  # board rows stay slim


def test_supervisor_lowers_a_lane():
    async def setup():
        await db.execute("TRUNCATE calls, suggestions, events CASCADE")
        await db.execute("INSERT INTO calls (call_id, lane) VALUES ('c1', 'amber')")
    with TestClient(app) as client:
        client.portal.call(setup)
        assert client.post("/api/calls/c1/lane", json={"lane": "green", "reason": " "}).status_code == 422
        assert client.post("/api/calls/nope/lane", json={"lane": "green", "reason": "x"}).status_code == 404
        r = client.post("/api/calls/c1/lane", json={"lane": "green", "reason": "Spoke to caller, routine refill"})
        assert r.json() == {"call_id": "c1", "lane": "green"}
        card = client.get("/api/calls/c1").json()
        assert card["lane"] == "green"
        assert card["events"][-1]["actor"] == "supervisor" and card["events"][-1]["payload"]["from"] == "amber"


def test_sim_instant_and_reset():
    import time

    with TestClient(app) as client:
        client.portal.call(lambda: db.execute("TRUNCATE calls, suggestions, events CASCADE"))
        assert client.post("/api/sim/start", json={"scenario": "nope"}).status_code == 422
        s = client.post("/api/sim/start", json={"scenario": "tuesday", "count": 5, "mode": "instant", "seed": 1}).json()
        assert s["running"] and s["total"] == 5
        for _ in range(100):
            if not client.get("/api/sim").json()["running"]:
                break
            time.sleep(0.05)
        assert client.get("/api/sim").json()["inserted"] == 5
        assert len(client.get("/api/calls?source=simulated").json()) == 5
        assert client.post("/api/sim/reset").json()["scenario"] is None
        assert client.get("/api/calls?source=simulated").json() == []


def test_on_the_line_counts_unfinished_simulated_calls():
    async def setup():
        await db.execute("TRUNCATE calls, suggestions, events CASCADE")
        await db.execute(
            """INSERT INTO calls (call_id, source, status, lane, ended_at) VALUES
               ('live', 'retell', 'ongoing', 'green', NULL),
               ('sim_now', 'simulated', 'analyzed', 'amber', now() + interval '90 s'),
               ('sim_done', 'simulated', 'analyzed', 'green', now() - interval '5 s')""")
    with TestClient(app) as client:
        client.portal.call(setup)
        b = client.get("/api/board").json()
        assert b["kpis"]["on_line"] == 2
        rows = {c["call_id"]: c["on_line"] for c in b["green"] + b["amber_queue"]}
        assert rows == {"live": True, "sim_now": True, "sim_done": False}
        assert client.get("/api/calls/sim_done").json()["on_line"] is False
