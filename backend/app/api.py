"""Read and decision endpoints for the supervisor board."""
import html
import statistics
import time
from collections import Counter

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import db, sim
from .classify.combine import LANE_RANK
from .classify.rules import REASON_WEIGHT
from .scenarios import LANGUAGES, SCENARIOS
from .supervisor import callbacks, engine
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
        "language": c.get("language") or "en", "neighborhood": c.get("neighborhood"),
    }


CLUSTER_LABEL = {"outage": "outage and \"are you open?\"", "family": "looking for family", "help": "offers to help", "media": "media",
                 "scheduling": "appointments", "billing": "billing", "medication": "medication", "mental_health": "distress",
                 "child": "children under 2", "injury_or_illness": "injury or illness", "other": "other"}


def _clock(t):
    s = sim.STATE
    if s.get("started_at"):
        v = (s["clock_start"] + (t - s["started_at"])) % 86400
    else:
        lt = time.localtime(t)
        v = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
    return f"{int(v // 3600):02d}:{int(v // 60 % 60):02d}"


def hotspots(calls, now, window_s=900):
    spots = {}
    for c in calls:
        if c["started_at"] < now - window_s or not c.get("neighborhood"):
            continue
        e = spots.setdefault(c["neighborhood"], {"place": c["neighborhood"], "count": 0, "red": 0, "flags": Counter(), "clusters": Counter(), "first": c["started_at"]})
        e["count"] += 1
        e["red"] += c["lane"] == "red"
        e["flags"].update(c.get("red_flags") or [])
        e["clusters"][c.get("cluster") or "other"] += 1
        e["first"] = min(e["first"], c["started_at"])
    out = []
    for e in sorted(spots.values(), key=lambda e: -(e["red"] * 5 + e["count"])):
        out.append({"place": e["place"], "count": e["count"], "red": e["red"], "flags": [f for f, _ in e["flags"].most_common(3)],
                    "top": [k for k, _ in e["clusters"].most_common(2)], "first": e["first"], "first_clock": _clock(e["first"])})
    return out


def ic_brief(now=None):
    """A plain-text brief the supervisor can send to incident command. Facts only, from the calls table."""
    now = now or time.time()
    calls = db.q("SELECT * FROM calls WHERE started_at >= ?", (now - 900,))
    spots = hotspots(calls, now)
    sg = db.surge()
    not_connected = sum(1 for c in calls if c["transfer_status"] in ("no_answer", "caller_hung_up", "never_started"))
    lines = [f"Night Ledger brief for incident command, {_clock(now)}. Harbor General after-hours line, last 15 min: "
             f"{len(calls)} calls, {sum(1 for c in calls if c['lane'] == 'red')} red flags."]
    for s in spots[:3]:
        flags = f", red flags: {', '.join(f.replace('_', ' ') for f in s['flags'])}" if s["flags"] else ""
        topics = " and ".join(CLUSTER_LABEL.get(k, k) for k in s["top"])
        lines.append(f"- {s['place']}: {s['count']} callers ({s['red']} red{flags}). Mostly {topics}. First report {s['first_clock']}.")
    if not_connected:
        lines.append(f"- {not_connected} red-flag caller{'s' if not_connected > 1 else ''} did not reach a nurse and were told to call 911.")
    lines.append(f"- Status message playing to callers: {'yes' if sg['status_message'] else 'no'}. Surge mode: {'on' if sg['is_on'] else 'off'}.")
    return {"text": "\n".join(lines), "hotspots": spots[:6], "generated_at": now}


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
        "hotspots": hotspots(calls, now)[:6],
        "languages": dict(Counter(c.get("language") or "en" for c in calls if c["started_at"] >= now - 3600)),
        "callbacks": callbacks.summary(now),
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


@router.get("/ic-brief")
def get_ic_brief():
    return ic_brief()


@router.post("/ic-brief/sent")
def ic_brief_sent():
    b = ic_brief()
    db.event("ic_brief_sent", None, "supervisor", {"text": b["text"]})
    return {"ok": True}


DECISION_TEXT = {
    "surge_on": "Switched surge mode on", "surge_off": "Switched surge mode off", "status_message_cleared": "Stopped the status message",
    "ic_brief_sent": "Sent a brief to incident command", "nurse_line_added": "Added a nurse line", "nurse_line_changed": "Changed a nurse line",
    "callback_reached": "Called back an amber caller: reached", "callback_no_answer": "Called back an amber caller: no answer",
}
SUGGESTION_TEXT = {"surge_mode": "surge mode prompt", "status_message": "status message", "staffing_nurses": "nurse staffing",
                   "staffing_doctors": "ER doctor staffing", "red_not_connected": "red caller not connected",
                   "amber_unreachable": "unreachable amber caller", "callback_unreachable": "unreachable hang-up caller"}


@router.get("/report", response_class=HTMLResponse)
def report(download: bool = False):
    """After-action report, written from the log. Nothing here is generated by a model."""
    now = time.time()
    calls = db.q("SELECT * FROM calls WHERE started_at >= ? ORDER BY started_at", (now - WINDOW_S,))
    events = db.q("SELECT * FROM events WHERE created_at >= ? ORDER BY created_at", (now - WINDOW_S,))
    a = analytics(120)
    cb = callbacks.summary(now)
    e = html.escape
    start = calls[0]["started_at"] if calls else now
    scen = SCENARIOS.get(sim.STATE.get("scenario") or "", {}).get("label", "Live line")
    langs = Counter(c.get("language") or "en" for c in calls)
    red = [c for c in calls if c["lane"] == "red"]

    def tile(v, l):
        return f'<div class="tile"><b>{e(str(v))}</b><span>{e(l)}</span></div>'

    rows = []
    for ev in events:
        if ev["actor"] != "supervisor":
            continue
        p = ev.get("payload") or {}
        if ev["type"] == "suggestion_decided":
            text = f"{p.get('action', '').capitalize()}: {SUGGESTION_TEXT.get(p.get('type'), p.get('type'))}" + (f" ({p['outcome'].replace('_', ' ')})" if p.get("outcome") else "")
        elif ev["type"] == "status_message_set":
            text = f"Activated status message: \u201c{p.get('text', '')}\u201d"
        elif ev["type"] == "lane_lowered":
            text = f"Lowered a caller from {p.get('from')} to {p.get('to')}: {p.get('reason', '')}"
        else:
            text = DECISION_TEXT.get(ev["type"], ev["type"].replace("_", " "))
        rows.append(f"<tr><td>{_clock(ev['created_at'])}</td><td>{e(text)}</td><td>K. Mensah</td></tr>")
    sys_rows = []
    for ev in events:
        if ev["type"] in ("red_flag_detected", "model_under_triage", "transfer_no_answer", "suggestion_opened", "ai_callback_reached_red", "ai_callback_failed"):
            p = ev.get("payload") or {}
            label = {"red_flag_detected": f"Red flag: {', '.join(f.replace('_', ' ') for f in p.get('flags', []))}", "model_under_triage": f"Rules raised a call the model labelled {p.get('model')}",
                     "transfer_no_answer": "Red transfer not answered, caller told to call 911", "suggestion_opened": f"Suggested: {SUGGESTION_TEXT.get(p.get('type'), p.get('type'))}",
                     "ai_callback_reached_red": "AI callback found a red flag, transferred to a nurse", "ai_callback_failed": "AI callback unanswered twice"}[ev["type"]]
            sys_rows.append(f"<tr><td>{_clock(ev['created_at'])}</td><td>{e(label)}</td></tr>")
    spot_rows = "".join(f"<tr><td>{e(s['place'])}</td><td>{s['count']}</td><td>{s['red']}</td><td>{e(', '.join(f.replace('_', ' ') for f in s['flags']) or '-')}</td><td>{s['first_clock']}</td></tr>"
                        for s in hotspots(calls, now, WINDOW_S)[:8])
    open_items = "".join(f"<li>{e(SUGGESTION_TEXT.get(s['type'], s['type']))}</li>" for s in engine.open_suggestions()) or "<li>None</li>"
    lang_txt = ", ".join(f"{LANGUAGES.get(k, k)} {v}" for k, v in langs.most_common())
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Night Ledger after-action report</title><link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>body{{margin:0;background:#E8EFF6;font-family:Manrope,system-ui,sans-serif;color:#111827}}main{{max-width:960px;margin:24px auto;background:#fff;border-radius:24px;padding:36px 40px;border:1px solid #DCE4EE}}
h1{{margin:0;font-size:28px}}h2{{font-size:17px;margin:28px 0 10px}}.sub{{color:#6B7280;margin-top:6px}}.tiles{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px}}
.tile{{background:#F6F8FA;border-radius:14px;padding:12px 14px;display:flex;flex-direction:column}}.tile b{{font-size:24px}}.tile span{{font-size:13px;color:#6B7280}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th{{text-align:left;background:#F7F8FA;color:#6B7280;font-weight:600;padding:8px 10px}}td{{padding:9px 10px;border-top:1px solid #F0F2F5;vertical-align:top}}
.note{{font-size:12px;color:#6B7280;margin-top:28px}}@media print{{body{{background:#fff}}main{{border:0;margin:0}}}}</style></head><body><main>
<h1>After-action report</h1><div class="sub">Night Ledger · Harbor General after-hours line · {e(scen)} · {_clock(start)} to {_clock(now)} · written from the call log</div>
<div class="tiles">{tile(len(calls), 'calls')}{tile(f"{a['lane_mix']['red']} / {a['lane_mix']['amber']} / {a['lane_mix']['green']}", 'now / a person soon / can wait')}
{tile('-' if a['red_median_handoff_s'] is None else str(a['red_median_handoff_s']) + ' s', 'red flag to transfer, median (target 10 s)')}{tile(f"{sum(1 for c in red if c['transfer_status'] == 'no_answer')}", 'red callers told to call 911')}
{tile(cb['hung_up'], 'hung up before an answer')}{tile(cb['reached_ok'] + cb['reached_red'], 'reached again by AI callback')}{tile(cb['reached_red'], 'red flags found on callback')}{tile(len(langs) - (1 if 'en' in langs else 0), 'languages besides English')}</div>
<h2>Supervisor decisions</h2><table><tr><th>Time</th><th>Decision</th><th>By</th></tr>{''.join(rows) or '<tr><td colspan="3">No decisions recorded.</td></tr>'}</table>
<h2>What the system flagged</h2><table><tr><th>Time</th><th>Event</th></tr>{''.join(sys_rows[-30:]) or '<tr><td colspan="2">Nothing flagged.</td></tr>'}</table>
<h2>Hotspots</h2><table><tr><th>Place</th><th>Callers</th><th>Red</th><th>Red flags</th><th>First report</th></tr>{spot_rows or '<tr><td colspan="5">No locations recorded.</td></tr>'}</table>
<h2>Languages</h2><p>{e(lang_txt or 'None')}</p>
<h2>Still open</h2><ul>{open_items}</ul>
<p class="note">Rules and model agreed on {'-' if a['rules_model_agreement'] is None else round(a['rules_model_agreement'] * 100)}% of calls; the rules raised {a['model_under_triage']} call(s) the model under-triaged. Simulated calls are labelled as such in the log. Print this page or save it as PDF.</p>
</main></body></html>"""
    headers = {"Content-Disposition": 'attachment; filename="night-ledger-after-action.html"'} if download else None
    return HTMLResponse(body, headers=headers)
