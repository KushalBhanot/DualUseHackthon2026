"""Abandoned-call callbacks. Everyone who hangs up within 30 s gets an AI callback that discloses it's an AI
and asks "Do you need help?". A red flag on the callback goes straight to a nurse; two unanswered
callbacks open an alert that only a person can close.

Simulated calls get a scripted outcome. Live Retell calls place a real outbound call when
RETELL_API_KEY, RETELL_FROM_NUMBER and RETELL_CALLBACK_AGENT_ID are set; the outcome then arrives
through the normal call webhook (see webhooks.py, `callback_for`).
"""
import hashlib
import os
import time

import httpx

from .. import db

DELAY_S = 15        # wait before the first (and next) callback attempt
RING_S = 20         # simulated length of a callback attempt
MAX_ATTEMPTS = 2
OPEN = ("scheduled", "ai_queued", "ai_calling", "ai_no_answer")


def live_enabled():
    return all(os.environ.get(k) for k in ("RETELL_API_KEY", "RETELL_FROM_NUMBER", "RETELL_CALLBACK_AGENT_ID"))


def _place_live_call(c):
    try:
        r = httpx.post("https://api.retellai.com/v2/create-phone-call", timeout=8,
                       headers={"Authorization": f"Bearer {os.environ['RETELL_API_KEY']}"},
                       json={"from_number": os.environ["RETELL_FROM_NUMBER"], "to_number": c["from_number"],
                             "override_agent_id": os.environ["RETELL_CALLBACK_AGENT_ID"],
                             "metadata": {"callback_for": c["call_id"]}})
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        db.event("ai_callback_error", c["call_id"], "system", {"error": str(e)[:200]})
        return False


def _outcome(call_id, attempt):
    """Deterministic scripted outcome for simulated calls."""
    h = int(hashlib.md5(f"{call_id}:{attempt}".encode()).hexdigest(), 16) % 100
    return "ai_reached_ok" if h < 55 else "ai_reached_red" if h < 68 else "ai_no_answer"


def run(now=None):
    now = now or time.time()
    rows = db.q("SELECT * FROM calls WHERE disconnection_reason='user_hangup' AND COALESCE(duration_ms,0) < 30000 "
                "AND COALESCE(lane,'green') != 'red' AND (callback_status IS NULL OR callback_status IN (?,?,?,?))", OPEN)
    for c in rows:
        st = c["callback_status"]
        last = c["callback_at"] or c["ended_at"] or c["started_at"]
        if st in (None, "scheduled"):
            db.update("calls", "call_id", c["call_id"], {"callback_status": "ai_queued", "callback_at": max(now, last)})
            db.event("ai_callback_queued", c["call_id"], "system", at=now)
        elif st in ("ai_queued", "ai_no_answer") and now - last >= DELAY_S:
            if c["source"] == "retell":
                if not live_enabled() or not _place_live_call(c):
                    continue  # stays queued; shown as waiting for a live callback line
            attempts = c["callback_attempts"] + 1
            db.update("calls", "call_id", c["call_id"], {"callback_status": "ai_calling", "callback_at": now, "callback_attempts": attempts})
            db.event("ai_callback_started", c["call_id"], "system", {"attempt": attempts}, at=now)
        elif st == "ai_calling" and c["source"] == "simulated" and now - last >= RING_S:
            outcome = _outcome(c["call_id"], c["callback_attempts"])
            fields = {"callback_status": outcome, "callback_at": now}
            if outcome == "ai_reached_red":
                fields.update({"red_flags": ["breathing"], "red_flag_at": now, "transfer_started_at": now + 3.2,
                               "transfer_ended_at": now + 9, "transfer_status": "connected", "transfer_target": "ED charge nurse · R. Okafor",
                               "intent": "Callback: " + (c["intent"] or "caller") + ". Now short of breath",
                               "cluster": "injury_or_illness", "urgency": 5})
            elif outcome == "ai_no_answer" and c["callback_attempts"] >= MAX_ATTEMPTS:
                fields["callback_status"] = "callback_failed"
            db.update("calls", "call_id", c["call_id"], fields)
            if outcome == "ai_reached_red":
                db.raise_lane(c["call_id"], "red", "ai_callback")
            db.event("ai_callback_" + fields["callback_status"].removeprefix("ai_"), c["call_id"], "system", at=now)


def summary(now=None):
    now = now or time.time()
    rows = db.q("SELECT * FROM calls WHERE disconnection_reason='user_hangup' AND started_at >= ? ORDER BY started_at DESC", (now - 7200,))
    count = lambda *s: sum(1 for c in rows if c["callback_status"] in s)
    return {
        "hung_up": len(rows),
        "queued": count("ai_queued", "scheduled", None),
        "calling": count("ai_calling"),
        "reached_ok": count("ai_reached_ok"),
        "reached_red": count("ai_reached_red"),
        "no_answer": count("ai_no_answer"),
        "failed": count("callback_failed", "welfare_check", "closed"),
        "live_enabled": live_enabled(),
        "recent": [{"call_id": c["call_id"], "caller_name": c["caller_name"], "intent": c["intent"], "status": c["callback_status"],
                    "attempts": c["callback_attempts"], "neighborhood": c["neighborhood"]} for c in rows[:8]],
    }
