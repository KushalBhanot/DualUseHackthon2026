"""Read and decision endpoints for the supervisor board."""
import statistics
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db, sim
from .classify.combine import LANE_RANK
from .classify.rules import REASON_WEIGHT
from .scenarios import SCENARIOS
from .supervisor import engine
from .supervisor.messages import TEMPLATES

router = APIRouter(prefix="/api")
WINDOW_S = 2 * 3600


def _amber_score(c, now):
    wait_min = (now - c["started_at"]) / 60
    return REASON_WEIGHT.get(c.get("reason"), 1) + (c.get("urgency") or 0) + wait_min / 5


def _row(c, now):
    return {
        "call_id": c["call_id"], "lane": c["lane"], "intent": c["intent"], "cluster": c["cluster"], "reason": c["reason"],
        "red_flags": c["red_flags"], "caller_name": c["caller_name"], "callback_number": c["callback_number"] or c["from_number"],
        "started_at": c["started_at"], "wait_s": round(now - c["started_at"]), "live": bool(c.get("ended_at") and c["ended_at"] > now) or c["status"] == "live",
        "transfer_status": c["transfer_status"], "callback_status": c["callback_status"], "needs_review": bool(c["needs_review"]),
        "source": c["source"], "disconnection_reason": c["disconnection_reason"],
        "model_lane": (c.get("jev_result") or {}).get("lane"), "rules_lane": (c.get("rules_result") or {}).get("lane"),
    }


def board(now=None):
    now = now or time.time()
    calls = db.q("SELECT * FROM calls WHERE started_at >= ? ORDER BY started_at DESC", (now - WINDOW_S,))
    lanes = {"red": [], "amber": [], "green": []}
    for c in calls:
        if c["lane"] in lanes:
            lanes[c["lane"]].append(c)
    amber_waiting = [c for c in lanes["amber"] if (c["callback_status"] or "waiting") in ("waiting", "no_answer")]
    amber_ranked = sorted(amber_waiting, key=lambda c: -_amber_score(c, now))
    # Watch: clusters over the last 10 minutes, with a per-minute series
    clusters = {}
    for c in calls:
        if c["started_at"] < now - 600:
            continue
        k = c["cluster"] or "other"
        e = clusters.setdefault(k, {"cluster": k, "count": 0, "red": 0, "series": [0] * 10})
        e["count"] += 1
        e["red"] += c["lane"] == "red"
        e["series"][min(9, int((c["started_at"] - (now - 600)) // 60))] += 1
    volume = []
    for i in range(20):
        lo = now - (20 - i) * 60
        bucket = [c for c in calls if lo <= c["started_at"] < lo + 60]
        volume.append({l: sum(1 for c in bucket if c["lane"] == l) for l in ("red", "amber", "green")})
    red_times = [c["transfer_started_at"] - c["red_flag_at"] for c in lanes["red"] if c["transfer_started_at"] and c["red_flag_at"]]
    green_ended = [c for c in lanes["green"] if c["disconnection_reason"] != "user_hangup"]
    recent10 = [c for c in calls if c["started_at"] >= now - 600]
    kpis = {
        "calls_10min": len(recent10),
        "on_line": sum(1 for c in calls if (c.get("ended_at") or 0) > now or c["status"] == "live"),
        "red_total": len(lanes["red"]),
        "red_median_handoff_s": round(statistics.median(red_times), 1) if red_times else None,
        "red_not_connected": sum(1 for c in lanes["red"] if c["transfer_status"] in ("no_answer", "caller_hung_up", "never_started")),
        "amber_waiting": len(amber_waiting),
        "oldest_amber_min": round(max(((now - c["started_at"]) / 60 for c in amber_waiting), default=0), 1),
        "ai_handled": len(green_ended),
        "ai_handled_share": round(len(green_ended) / len(calls), 2) if calls else 0,
        "hung_up": sum(1 for c in calls if c["disconnection_reason"] == "user_hangup"),
        "total": len(calls),
    }
    return {
        "now": now,
        "counts": {k: len(v) for k, v in lanes.items()},
        "red": [_row(c, now) for c in lanes["red"][:12]],
        "amber": [_row(c, now) for c in amber_ranked[:14]],
        "green": [_row(c, now) for c in lanes["green"][:12]],
        "clusters": sorted(clusters.values(), key=lambda e: -e["count"]),
        "volume": volume,
        "kpis": kpis,
    }


def analytics(minutes=60):
    now = time.time()
    calls = db.q("SELECT * FROM calls WHERE started_at >= ?", (now - minutes * 60,))
    both = [c for c in calls if (c.get("rules_result") or {}).get("lane") and (c.get("jev_result") or {}).get("lane")]
    agree = sum(1 for c in both if c["rules_result"]["lane"] == c["jev_result"]["lane"])
    under = sum(1 for c in both if LANE_RANK[c["rules_result"]["lane"]] > LANE_RANK.get(c["jev_result"]["lane"], -1))
    details = [d for c in calls for d in (c.get("details") or {}).values() if isinstance(d, dict)]
    red = [c for c in calls if c["lane"] == "red"]
    red_times = [c["transfer_started_at"] - c["red_flag_at"] for c in red if c["transfer_started_at"] and c["red_flag_at"]]
    return {
        "minutes": minutes,
        "total": len(calls),
        "lane_mix": {l: sum(1 for c in calls if c["lane"] == l) for l in ("red", "amber", "green")},
        "rules_model_agreement": round(agree / len(both), 2) if both else None,
        "model_under_triage": under,
        "rules_miss": db.one("SELECT COUNT(*) AS n FROM events WHERE type='rules_miss' AND created_at >= ?", (now - minutes * 60,))["n"],
        "detail_confirmation_rate": round(sum(1 for d in details if d.get("status") in ("confirmed", "caller_id")) / len(details), 2) if details else None,
        "red_median_handoff_s": round(statistics.median(red_times), 1) if red_times else None,
        "red_told_911_share": round(sum(1 for c in red if c["transfer_status"] == "no_answer") / len(red), 2) if red else None,
        "abandonment": round(sum(1 for c in calls if c["disconnection_reason"] == "user_hangup") / len(calls), 2) if calls else None,
    }


def sim_state():
    s = dict(sim.STATE)
    if s["started_at"] is not None:
        s["clock_s"] = (s["clock_start"] + (time.time() - s["started_at"])) % 86400
    s["scenarios"] = {k: v["label"] for k, v in SCENARIOS.items()}
    return s


@router.get("/state")
def state():
    """One poll for the board: lanes, suggestions, surge state and simulator clock."""
    return {"board": board(), "suggestions": engine.open_suggestions(), "surge": db.surge(), "sim": sim_state(),
            "analytics": analytics(60)}


@router.get("/board")
def get_board():
    return board()


@router.get("/calls")
def calls(lane: str | None = None, source: str | None = None, limit: int = 100):
    sql, params = "SELECT * FROM calls WHERE 1=1", []
    if lane:
        sql, params = sql + " AND lane=?", params + [lane]
    if source:
        sql, params = sql + " AND source=?", params + [source]
    now = time.time()
    return [_row(c, now) for c in db.q(sql + " ORDER BY started_at DESC LIMIT ?", params + [limit])]


@router.get("/calls/{call_id}")
def call_detail(call_id: str):
    c = db.one("SELECT * FROM calls WHERE call_id=?", (call_id,))
    if not c:
        raise HTTPException(404, "No such call")
    c.pop("raw", None)
    c["events"] = db.q("SELECT * FROM events WHERE call_id=? ORDER BY created_at", (call_id,))
    return c


class LaneChange(BaseModel):
    lane: str
    reason: str


@router.post("/calls/{call_id}/lane")
def change_lane(call_id: str, body: LaneChange):
    """Only a person can lower a lane. This endpoint is the supervisor's, and it is logged."""
    c = db.one("SELECT lane FROM calls WHERE call_id=?", (call_id,))
    if not c or body.lane not in LANE_RANK or body.lane is None:
        raise HTTPException(400, "Bad call or lane")
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required")
    db.update("calls", "call_id", call_id, {"lane": body.lane})
    db.event("lane_lowered" if LANE_RANK[body.lane] < LANE_RANK[c["lane"]] else "lane_raised", call_id, "supervisor",
             {"from": c["lane"], "to": body.lane, "reason": body.reason})
    return {"ok": True}


class CallbackOutcome(BaseModel):
    outcome: str  # reached / no_answer


@router.post("/calls/{call_id}/callback")
def callback(call_id: str, body: CallbackOutcome):
    c = db.one("SELECT callback_attempts FROM calls WHERE call_id=?", (call_id,))
    if not c:
        raise HTTPException(404, "No such call")
    fields = {"callback_status": body.outcome, "callback_attempts": c["callback_attempts"] + 1}
    db.update("calls", "call_id", call_id, fields)
    db.event("callback_" + body.outcome, call_id, "supervisor", fields)
    engine.check_amber_unreachable(time.time())
    return {"ok": True}


class Decision(BaseModel):
    outcome: str | None = None
    text: str | None = None


@router.get("/suggestions")
def suggestions(status: str = "open"):
    return engine.open_suggestions() if status == "open" else db.q("SELECT * FROM suggestions WHERE status=? ORDER BY id DESC", (status,))


@router.post("/suggestions/{sid}/{action}")
def decide(sid: int, action: str, body: Decision | None = None):
    ok, msg = engine.decide(sid, action, (body or Decision()).outcome, (body or Decision()).text)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True}


class SurgeBody(BaseModel):
    on: bool


@router.get("/surge")
def get_surge():
    return db.surge()


@router.post("/surge")
def post_surge(body: SurgeBody):
    engine.set_surge(body.on)
    return db.surge()


@router.get("/status-messages")
def status_messages():
    return {"templates": TEMPLATES, "active": db.surge()["status_message"]}


class StatusBody(BaseModel):
    text: str | None
    cluster: str | None = None


@router.post("/status-message")
def set_status(body: StatusBody):
    engine.set_status_message(body.text, body.cluster)
    return db.surge()


class NurseLine(BaseModel):
    label: str | None = None
    number: str | None = None
    role: str | None = None
    on_duty: bool | None = None
    priority: int | None = None


@router.get("/nurse-lines")
def nurse_lines():
    return db.q("SELECT * FROM nurse_lines ORDER BY priority, id")


@router.post("/nurse-lines")
def add_line(body: NurseLine):
    if not body.label or not body.number:
        raise HTTPException(400, "label and number are required")
    lid = db.insert("nurse_lines", {"label": body.label, "number": body.number, "role": body.role or "nurse",
                                    "on_duty": int(body.on_duty if body.on_duty is not None else True),
                                    "priority": body.priority or 9, "updated_at": time.time()})
    db.event("nurse_line_added", None, "supervisor", {"id": lid})
    return {"id": lid}


@router.patch("/nurse-lines/{lid}")
def patch_line(lid: int, body: NurseLine):
    fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in body.model_dump().items() if v is not None}
    fields["updated_at"] = time.time()
    db.update("nurse_lines", "id", lid, fields)
    db.event("nurse_line_changed", None, "supervisor", {"id": lid, **fields})
    return {"ok": True}


@router.get("/analytics")
def get_analytics(minutes: int = 60):
    return analytics(minutes)


class SimStart(BaseModel):
    scenario: str
    count: int = 60
    reset: bool = True


@router.post("/sim/start")
async def sim_start(body: SimStart):
    if body.scenario not in SCENARIOS:
        raise HTTPException(400, "Unknown scenario")
    if body.reset:
        sim.reset()
    sim.start(body.scenario, body.count)
    return sim_state()


@router.post("/sim/stop")
def sim_stop():
    sim.stop()
    return sim_state()


@router.post("/sim/reset")
def sim_reset():
    sim.stop()
    sim.reset()
    return sim_state()
