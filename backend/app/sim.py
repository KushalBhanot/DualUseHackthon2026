"""Simulated emergencies. Scenario calls go straight into the database (source='simulated'),
so the supervisor board has realistic data without a phone. Run from the API or the CLI:

    uv run python -m app.sim serious_earthquake --count 40 [--reset]
"""
import argparse
import asyncio
import random
import time
import uuid

from . import db
from .classify import rules
from .classify.combine import combine
from .scenarios import CHEST, FIRST, LAST, MODEL_LANE, SCENARIOS

STATE = {"scenario": None, "running": False, "started_at": None, "clock_start": None, "inserted": 0, "total": 0}
_task = None


def _pick(templates, rng):
    total = sum(t["w"] for t in templates)
    r = rng.random() * total
    for t in templates:
        r -= t["w"]
        if r <= 0:
            return t
    return templates[0]


def make_call(tpl, scenario, at, rng, surge_on=False):
    """Build one simulated call: classify the caller's words with the real rules, combine with the model label."""
    caller_text, agent_text = tpl["q"]
    r = rules.classify(caller_text, tpl.get("stt"))
    label, conf = tpl["model"]
    model = {"source": "simulated_model", "label": label, "lane": MODEL_LANE.get(label, "green"), "confidence": conf}
    comb = combine(r, model)
    lane = comb["lane"]
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    number = f"+1213555{rng.randint(1000, 9999)}"
    duration = rng.uniform(40, 150)
    call = {
        "call_id": f"sim_{uuid.uuid4().hex[:10]}", "source": "simulated", "scenario": scenario, "status": "ended",
        "from_number": number, "started_at": at, "ended_at": at + duration, "duration_ms": int(duration * 1000),
        "disconnection_reason": "agent_hangup", "lane": lane, "red_flags": r["red_flags"],
        "cluster": tpl.get("cl") or r["cluster"], "intent": tpl["intent"], "reason": r["reason"],
        "urgency": {"red": 5, "amber": 3, "green": 1}[lane], "caller_name": name, "callback_number": number,
        "needs_review": int(comb["needs_review"]), "rules_result": r, "jev_result": model,
        "transcript": [
            {"role": "agent", "content": "Harbor General. I'm an automated assistant, not a person, and you can ask for a person at any time. First, a quick safety check: is anyone with you having chest pain, trouble breathing, or bleeding that won't stop?", "t": 0},
            {"role": "user", "content": caller_text, "t": 6},
            {"role": "agent", "content": agent_text, "t": 9},
        ],
        "details": {
            "caller_name": {"value": name, "status": "confirmed" if rng.random() > .12 else "unconfirmed"},
            "callback_number": {"value": number, "status": "caller_id" if lane == "red" else ("confirmed" if rng.random() > .1 else "unconfirmed")},
        },
        "summary": tpl["intent"],
    }
    if lane == "red":
        call["red_flag_at"] = at + rng.uniform(5, 8)
        call["transfer_started_at"] = call["red_flag_at"] + rng.uniform(2, 5)
        call["transfer_target"] = "ED charge nurse"
        connected = tpl.get("star") or rng.random() > 0.22
        call["transfer_status"] = "connected" if connected else "no_answer"
        call["transfer_ended_at"] = call["transfer_started_at"] + (rng.uniform(4, 12) if connected else 20)
        call["ended_at"] = call["transfer_ended_at"] + (rng.uniform(60, 200) if connected else 6)
    elif lane == "amber":
        call["callback_status"] = "waiting"
    elif not surge_on and rng.random() < SCENARIOS[scenario]["abandon"]:
        call["disconnection_reason"] = "user_hangup"
        call["ended_at"] = at + rng.uniform(8, 25)
        call["duration_ms"] = int((call["ended_at"] - at) * 1000)
        call["summary"] = "Hung up while waiting"
    return call, comb


def insert_call(call, comb):
    db.insert("calls", call)
    at = call["started_at"]
    db.event("call_started", call["call_id"], "system", {"source": "simulated", "scenario": call["scenario"]}, at=at)
    if call["red_flags"]:
        db.event("red_flag_detected", call["call_id"], "system", {"flags": call["red_flags"], "by": "rules"}, at=call.get("red_flag_at") or at)
    if comb.get("model_under_triage"):
        db.event("model_under_triage", call["call_id"], "system",
                 {"model": call["jev_result"].get("label"), "model_lane": call["jev_result"].get("lane"), "final": call["lane"]}, at=at)
    if call.get("transfer_status"):
        db.event("transfer_" + call["transfer_status"], call["call_id"], "system", {"target": call.get("transfer_target")},
                 at=call.get("transfer_ended_at") or at)


def seed_nurse_lines():
    if db.one("SELECT id FROM nurse_lines LIMIT 1"):
        return
    now = time.time()
    db.insert("nurse_lines", {"label": "ED charge nurse · R. Okafor", "number": "+12139940320", "role": "nurse", "on_duty": 1, "priority": 1, "updated_at": now})
    db.insert("nurse_lines", {"label": "House supervisor · K. Mensah", "number": "+12135550188", "role": "house_supervisor", "on_duty": 1, "priority": 2, "updated_at": now})
    db.insert("nurse_lines", {"label": "Float nurse · L. Brooks", "number": "+12135550142", "role": "nurse", "on_duty": 0, "priority": 3, "updated_at": now})


def reset():
    sim_ids = [r["call_id"] for r in db.q("SELECT call_id FROM calls WHERE source='simulated'")]
    db.run("DELETE FROM calls WHERE source='simulated'")
    for cid in sim_ids:
        db.run("DELETE FROM events WHERE call_id=?", (cid,))
    db.run("DELETE FROM suggestions")
    db.run("DELETE FROM events WHERE call_id IS NULL")
    db.update("surge_state", "id", 1, {"is_on": 0, "switched_at": None, "status_message": None, "status_cluster": None})
    STATE.update({"scenario": None, "running": False, "started_at": None, "clock_start": None, "inserted": 0, "total": 0})


def backfill(scenario, count, minutes=20, seed=None):
    """Insert `count` calls spread over the last `minutes`, oldest first."""
    rng = random.Random(seed)
    sc = SCENARIOS[scenario]
    now = time.time()
    for i in range(count):
        at = now - minutes * 60 * (1 - (i + 1) / count) ** 1.6
        tpl = CHEST if sc.get("star_at") == i else _pick(sc["templates"], rng)
        insert_call(*make_call(tpl, scenario, at, rng))


async def _drip(scenario, count, rng):
    sc = SCENARIOS[scenario]
    start_i, end_i = sc["interval"]
    for i in range(count):
        if not STATE["running"]:
            break
        tpl = CHEST if sc.get("star_at") == i else _pick(sc["templates"], rng)
        call, comb = make_call(tpl, scenario, time.time(), rng, surge_on=bool(db.surge()["is_on"]))
        insert_call(call, comb)
        STATE["inserted"] = i + 1
        frac = i / max(count - 1, 1)
        await asyncio.sleep(start_i + (end_i - start_i) * min(1, frac * 1.6))
    STATE["running"] = False


def start(scenario, count=60, seed=None):
    global _task
    stop()
    seed_nurse_lines()
    STATE.update({"scenario": scenario, "running": True, "started_at": time.time(),
                  "clock_start": SCENARIOS[scenario]["clock"], "inserted": 0, "total": count})
    db.event("simulation_started", None, "system", {"scenario": scenario, "count": count})
    _task = asyncio.get_running_loop().create_task(_drip(scenario, count, random.Random(seed)))


def stop():
    global _task
    STATE["running"] = False
    if _task and not _task.done():
        _task.cancel()
    _task = None


def main():
    p = argparse.ArgumentParser(description="Insert simulated calls")
    p.add_argument("scenario", choices=list(SCENARIOS))
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--minutes", type=int, default=20)
    p.add_argument("--reset", action="store_true")
    a = p.parse_args()
    if a.reset:
        reset()
    seed_nurse_lines()
    backfill(a.scenario, a.count, a.minutes)
    print(f"inserted {a.count} {a.scenario} calls")


if __name__ == "__main__":
    main()
