"""The supervisor check. It reads the calls table and opens suggestions with the numbers behind them.

The AI never acts on its own: surge mode, broadcasts and staff call-ins happen only on a supervisor click.
"""
import math
import time

from .. import db
from . import config as C
from .messages import CLUSTER_TEMPLATE, TEMPLATES

UNSNOOZABLE = {"red_not_connected", "amber_unreachable"}


def _open(type_, call_id=None):
    sql = "SELECT * FROM suggestions WHERE type=? AND status IN ('open','snoozed')"
    params = [type_]
    if call_id:
        sql += " AND call_id=?"
        params.append(call_id)
    return db.one(sql + " ORDER BY id DESC", params)


def _new(type_, evidence, recommendation, call_id=None, now=None):
    sid = db.insert("suggestions", {"type": type_, "call_id": call_id, "evidence": evidence,
                                    "recommendation": recommendation, "status": "open", "created_at": now or time.time()})
    db.event("suggestion_opened", call_id, "system", {"id": sid, "type": type_, "evidence": evidence}, at=now)
    return sid


def line_stats(now=None):
    now = now or time.time()
    calls = db.q("SELECT * FROM calls WHERE started_at >= ?", (now - 3600,))
    in_win = lambda c, m: c["started_at"] >= now - m * 60
    recent3 = [c for c in calls if in_win(c, C.SURGE_WINDOW_MIN)]
    recent10 = [c for c in calls if in_win(c, C.STATUS_WINDOW_MIN)]
    recent30 = [c for c in calls if in_win(c, C.STAFF_WINDOW_MIN)]
    clusters = {}
    for c in recent10:
        clusters[c.get("cluster") or "other"] = clusters.get(c.get("cluster") or "other", 0) + 1
    top = max(clusters.items(), key=lambda kv: kv[1]) if clusters else (None, 0)
    amber_waiting = db.q("SELECT * FROM calls WHERE lane='amber' AND COALESCE(callback_status,'waiting')='waiting'")
    oldest_amber_min = max(((now - c["started_at"]) / 60 for c in amber_waiting), default=0)
    hung_up = [c for c in recent3 if c.get("disconnection_reason") == "user_hangup" and (c.get("duration_ms") or 0) < 30000]
    red_waiting = db.q("SELECT call_id FROM calls WHERE lane='red' AND status='live' AND transfer_status IS NULL")
    return {
        "now": now,
        "calls_3min": len(recent3),
        "normal_3min": round(C.BASELINE_CALLS_PER_HOUR * C.SURGE_WINDOW_MIN / 60, 1),
        "calls_10min": len(recent10),
        "calls_30min": len(recent30),
        "clusters_10min": clusters,
        "top_cluster": top[0],
        "top_cluster_count": top[1],
        "red_30min": sum(1 for c in recent30 if c.get("lane") == "red"),
        "red_injury_30min": sum(1 for c in recent30 if c.get("lane") == "red" and c.get("cluster") == "injury_or_illness"),
        "amber_30min": sum(1 for c in recent30 if c.get("lane") == "amber"),
        "amber_waiting": len(amber_waiting),
        "oldest_amber_min": round(oldest_amber_min, 1),
        "hung_up_3min": len(hung_up),
        "red_waiting": len(red_waiting),
        "no_answer_10min": sum(1 for c in recent10 if c.get("transfer_status") == "no_answer"),
    }


def _expire_snoozes(now):
    for s in db.q("SELECT * FROM suggestions WHERE status='snoozed' AND snooze_until <= ?", (now,)):
        db.update("suggestions", "id", s["id"], {"status": "expired", "decided_at": now})


def check_surge(st, now):
    sg = db.surge()
    existing = _open("surge_mode")
    threshold = max(C.SURGE_MIN_CALLS, C.SURGE_MULTIPLIER * st["normal_3min"])
    if sg["is_on"]:
        if existing:
            db.update("suggestions", "id", existing["id"], {"status": "expired", "decided_at": now})
        return
    if st["calls_3min"] < threshold:
        if existing and existing["status"] == "open":
            db.update("suggestions", "id", existing["id"], {"status": "expired", "decided_at": now})
        return
    evidence = {
        "calls_3min": st["calls_3min"], "normal_3min": st["normal_3min"],
        "top_cluster": st["top_cluster"], "top_cluster_count": st["top_cluster_count"],
        "red_waiting": st["red_waiting"], "hung_up_3min": st["hung_up_3min"], "amber_waiting": st["amber_waiting"],
    }
    if existing:
        if existing["status"] == "open":
            db.update("suggestions", "id", existing["id"], {"evidence": evidence})
        return
    _new("surge_mode", evidence, {"action": "switch_on_surge"}, now=now)


def check_status_message(st, now):
    sg = db.surge()
    cl = st["top_cluster"]
    template = CLUSTER_TEMPLATE.get(cl)
    if not template or st["calls_10min"] < C.STATUS_MIN_CALLS:
        return
    share = st["top_cluster_count"] / max(st["calls_10min"], 1)
    if share < C.STATUS_CLUSTER_SHARE or sg["status_cluster"] == template:
        return
    evidence = {"cluster": cl, "count": st["top_cluster_count"], "calls_10min": st["calls_10min"], "share": round(share, 2)}
    existing = _open("status_message")
    if existing:
        if existing["status"] == "open" and existing["recommendation"].get("template") == template:
            db.update("suggestions", "id", existing["id"], {"evidence": evidence})
        return
    recent = db.one("SELECT * FROM suggestions WHERE type='status_message' AND decided_at > ? AND status IN ('dismissed','accepted')",
                    (now - C.STATUS_WINDOW_MIN * 60,))
    if recent:
        return
    _new("status_message", evidence, {"template": template, **TEMPLATES[template]}, now=now)


def check_staffing(st, now):
    per_h = 60 / C.STAFF_WINDOW_MIN
    minutes = st["red_30min"] * per_h * C.RED_MIN + st["amber_30min"] * per_h * C.AMBER_MIN
    needed = max(0, math.ceil(minutes / 60 / C.NURSE_UTILIZATION) - C.NURSES_ON_PHONES)
    if st["oldest_amber_min"] > C.AMBER_TARGET_MIN or st["no_answer_10min"] >= 2:
        needed = max(needed, 1)
    if needed > 0:
        _staff_suggestion("staffing_nurses", needed, {
            "red_per_h": round(st["red_30min"] * per_h), "amber_per_h": round(st["amber_30min"] * per_h),
            "amber_waiting": st["amber_waiting"], "oldest_amber_min": st["oldest_amber_min"],
            "target_min": C.AMBER_TARGET_MIN, "nurse_min_per_h": round(minutes), "on_phones": C.NURSES_ON_PHONES,
            "no_answer_10min": st["no_answer_10min"],
        }, now)
    injury_per_h = st["red_injury_30min"] * per_h
    for rate, label in C.DOCTOR_TIERS:
        if injury_per_h >= rate:
            _staff_suggestion("staffing_doctors", label, {"red_injury_30min": st["red_injury_30min"],
                                                          "per_hour": round(injury_per_h)}, now)
            break


def _staff_suggestion(type_, value, evidence, now):
    """Open a new staffing suggestion only when the number goes up, so the supervisor isn't asked again every check."""
    rank = lambda v: {"1-2": 1.5, "3+": 3}.get(v, v) if isinstance(v, str) else v
    last = db.one("SELECT * FROM suggestions WHERE type=? AND created_at > ? ORDER BY id DESC", (type_, now - 3600))
    if last and rank(last["recommendation"].get("count")) >= rank(value):
        if last["status"] == "open":
            db.update("suggestions", "id", last["id"], {"evidence": evidence})
        return
    if last and last["status"] == "open":
        db.update("suggestions", "id", last["id"], {"status": "expired", "decided_at": now})
    _new(type_, evidence, {"count": value}, now=now)


def check_red_not_connected(now):
    rows = db.q("SELECT * FROM calls WHERE lane='red' AND transfer_status IN ('no_answer','caller_hung_up','never_started')")
    for c in rows:
        if db.one("SELECT id FROM suggestions WHERE type='red_not_connected' AND call_id=?", (c["call_id"],)):
            continue
        _new("red_not_connected", {
            "transfer_status": c["transfer_status"], "red_flags": c["red_flags"], "callback_number": c["callback_number"] or c["from_number"],
            "caller_name": c["caller_name"], "intent": c["intent"], "at": c["red_flag_at"] or c["started_at"],
        }, {"action": "call_back"}, call_id=c["call_id"], now=now)
    # Red flag seen but no transfer began within 10 s
    stale = db.q("SELECT call_id FROM calls WHERE lane='red' AND transfer_status IS NULL AND red_flag_at IS NOT NULL AND red_flag_at < ? AND status='live'",
                 (now - C.RED_TRANSFER_TARGET_S,))
    for c in stale:
        db.update("calls", "call_id", c["call_id"], {"transfer_status": "never_started"})


def check_amber_unreachable(now):
    rows = db.q("SELECT * FROM calls WHERE lane='amber' AND callback_attempts >= 2 AND callback_status='no_answer'")
    for c in rows:
        if db.one("SELECT id FROM suggestions WHERE type='amber_unreachable' AND call_id=?", (c["call_id"],)):
            continue
        _new("amber_unreachable", {"caller_name": c["caller_name"], "callback_number": c["callback_number"] or c["from_number"],
                                   "reason": c["reason"], "intent": c["intent"], "attempts": c["callback_attempts"]},
             {"options": ["try_again", "welfare_check", "close"]}, call_id=c["call_id"], now=now)


def run_once(now=None):
    now = now or time.time()
    _expire_snoozes(now)
    st = line_stats(now)
    check_red_not_connected(now)
    check_amber_unreachable(now)
    check_surge(st, now)
    check_status_message(st, now)
    check_staffing(st, now)
    return st


PRIORITY = {"red_not_connected": 0, "amber_unreachable": 1, "surge_mode": 2, "status_message": 3, "staffing_nurses": 4, "staffing_doctors": 5}


def open_suggestions():
    rows = db.q("SELECT * FROM suggestions WHERE status='open'")
    return sorted(rows, key=lambda s: (PRIORITY.get(s["type"], 9), -s["created_at"]))


def decide(sid, action, outcome=None, text=None, actor="supervisor"):
    """accept / snooze / dismiss / resolve. Returns (ok, message)."""
    s = db.one("SELECT * FROM suggestions WHERE id=?", (sid,))
    if not s or s["status"] not in ("open", "snoozed"):
        return False, "Suggestion is not open"
    now = time.time()
    if s["type"] in UNSNOOZABLE and action in ("snooze", "dismiss"):
        return False, "This alert can only be resolved by a person"
    if action == "snooze":
        db.update("suggestions", "id", sid, {"status": "snoozed", "snooze_until": now + C.SNOOZE_MIN * 60, "decided_at": now})
    elif action == "dismiss":
        db.update("suggestions", "id", sid, {"status": "dismissed", "decided_at": now})
    elif action == "accept":
        db.update("suggestions", "id", sid, {"status": "accepted", "decided_at": now})
        if s["type"] == "surge_mode":
            set_surge(True, actor)
        elif s["type"] == "status_message":
            rec = s["recommendation"]
            set_status_message(text or rec.get("text"), rec.get("template"), actor)
    elif action == "resolve":
        db.update("suggestions", "id", sid, {"status": "resolved", "outcome": outcome, "decided_at": now})
        if s["call_id"]:
            db.update("calls", "call_id", s["call_id"], {"callback_status": outcome or "resolved"})
    else:
        return False, "Unknown action"
    db.event("suggestion_decided", s["call_id"], actor, {"id": sid, "type": s["type"], "action": action, "outcome": outcome})
    return True, "ok"


def set_surge(on: bool, actor="supervisor"):
    now = time.time()
    db.update("surge_state", "id", 1, {"is_on": 1 if on else 0, "switched_at": now})
    db.event("surge_on" if on else "surge_off", None, actor)
    if on:
        # Callers who hung up while waiting get a callback, since their number is known.
        for c in db.q("SELECT call_id FROM calls WHERE disconnection_reason='user_hangup' AND lane='green' AND callback_status IS NULL AND started_at > ?",
                      (now - 1800,)):
            db.update("calls", "call_id", c["call_id"], {"callback_status": "scheduled"})


def set_status_message(text, cluster=None, actor="supervisor"):
    db.update("surge_state", "id", 1, {"status_message": text or None, "status_cluster": cluster if text else None})
    db.event("status_message_set" if text else "status_message_cleared", None, actor, {"text": text, "cluster": cluster})
