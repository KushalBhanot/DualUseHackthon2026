"""Endpoints Retell calls: call lifecycle webhooks and the inbound webhook that sets per-call variables."""
import os
import time

from fastapi import APIRouter, Request

from . import db
from .classify import jev, rules
from .classify.combine import combine

router = APIRouter(prefix="/retell")

STATE_LANE = {"handoff_now": "red", "person_soon": "amber", "info_status": "green", "callback_routine": "green"}


def _caller_text(transcript):
    return " ".join(t.get("content", "") for t in transcript if t.get("role") == "user")


def _transcript(call):
    items = call.get("transcript_object") or []
    return [{"role": i.get("role"), "content": i.get("content", "")} for i in items if i.get("role") in ("user", "agent")]


def _transfer_outcome(call, red):
    """Work out what happened to a red caller's transfer from Retell's call object."""
    reason = call.get("disconnection_reason") or ""
    tool_items = call.get("transcript_with_tool_calls") or []
    tried = any(i.get("role") == "tool_call_invocation" and i.get("name") == "transfer_to_nurse" for i in tool_items)
    if reason == "call_transfer":
        return "connected"
    if tried and reason in ("user_hangup",):
        return "caller_hung_up"
    if tried:
        return "no_answer"
    return "never_started" if red else None


def _classify_and_store(call_id, transcript, retell_lane=None):
    stored = db.one("SELECT lane FROM calls WHERE call_id=?", (call_id,))
    text = _caller_text(transcript)
    r = rules.classify(text)
    model = jev.classify("\n".join(f"{t['role']}: {t['content']}" for t in transcript))
    comb = combine(r, model, retell_lane, stored["lane"] if stored else None)
    fields = {"rules_result": r, "needs_review": int(comb["needs_review"]), "reason": r["reason"]}
    if model:
        fields["jev_result"] = model
    if r["red_flags"]:
        fields["red_flags"] = r["red_flags"]
    if r["cluster"] and r["cluster"] != "other":
        fields["cluster"] = r["cluster"]
    db.update("calls", "call_id", call_id, fields)
    if comb["rules_miss"]:
        db.event("rules_miss", call_id, "system", {"model": model})
    db.raise_lane(call_id, comb["lane"], "classifier")
    return comb


@router.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    event, call = body.get("event"), body.get("call") or {}
    call_id = call.get("call_id")
    if not call_id:
        return {"ok": False}
    now = time.time()
    db.event(f"retell_{event}", call_id, "system", {"disconnection_reason": call.get("disconnection_reason")})
    existing = db.one("SELECT call_id FROM calls WHERE call_id=?", (call_id,))
    if not existing:
        db.insert("calls", {"call_id": call_id, "source": "retell", "status": "live", "from_number": call.get("from_number"),
                            "started_at": (call.get("start_timestamp") or now * 1000) / 1000, "raw": call})

    if event == "call_ended":
        transcript = _transcript(call)
        comb = _classify_and_store(call_id, transcript)
        # Lane from the agent's own state moves (node transitions), up only
        for item in call.get("transcript_with_tool_calls") or []:
            if item.get("role") == "node_transition" and item.get("new_node_name") in STATE_LANE:
                db.raise_lane(call_id, STATE_LANE[item["new_node_name"]], "agent_state")
        row = db.one("SELECT lane, red_flag_at FROM calls WHERE call_id=?", (call_id,))
        red = row["lane"] == "red"
        fields = {"status": "ended", "transcript": transcript, "raw": call,
                  "ended_at": (call.get("end_timestamp") or now * 1000) / 1000, "duration_ms": call.get("duration_ms"),
                  "disconnection_reason": call.get("disconnection_reason"), "recording_url": call.get("recording_url")}
        if red:
            fields["transfer_status"] = _transfer_outcome(call, red)
            fields["red_flag_at"] = row["red_flag_at"] or fields["ended_at"]
            fields["callback_number"] = call.get("from_number")
        elif row["lane"] == "amber":
            fields["callback_status"] = "waiting"
        db.update("calls", "call_id", call_id, fields)

    elif event == "call_analyzed":
        analysis = call.get("call_analysis") or {}
        data = analysis.get("custom_analysis_data") or {}
        fields = {"summary": analysis.get("call_summary"), "raw": call}
        for k in ("intent", "cluster"):
            if data.get(k):
                fields[k] = data[k]
        if data.get("red_flags") and data["red_flags"] != "none":
            flags = [f.strip() for f in str(data["red_flags"]).split(",") if f.strip()]
            cur = db.one("SELECT red_flags FROM calls WHERE call_id=?", (call_id,))["red_flags"] or []
            fields["red_flags"] = sorted(set(cur) | set(flags))
        for k in ("caller_name", "callback_number"):
            if data.get(k) and data[k] != "unknown":
                # Retell's analysis is kept for comparison only; it never overwrites a confirmed detail.
                d = db.one("SELECT details FROM calls WHERE call_id=?", (call_id,))["details"] or {}
                d.setdefault(k, {"value": data[k], "status": "unconfirmed"})["analysis_value"] = data[k]
                fields["details"] = d
        if data.get("needs_review"):
            fields["needs_review"] = 1
        db.update("calls", "call_id", call_id, fields)
        if data.get("lane"):
            db.raise_lane(call_id, data["lane"], "retell_analysis")
    return {"ok": True}


def top_nurse_line():
    line = db.one("SELECT * FROM nurse_lines WHERE on_duty=1 ORDER BY priority ASC, id ASC LIMIT 1")
    return line["number"] if line else os.environ.get("NURSE_LINE", "+12139940320")


@router.post("/inbound")
async def inbound(request: Request):
    """Before each phone call is answered, Retell asks for this call's variables."""
    await request.body()
    sg = db.surge()
    variables = {
        "surge_banner": sg["status_message"] or "",
        "routine_callback_window": sg["routine_window"],
        "priority_callback_window": sg["priority_window"],
        "nurse_line": top_nurse_line(),
    }
    if sg["status_message"]:
        variables["incident_status"] = sg["status_message"]
    return {"call_inbound": {"dynamic_variables": variables}}
