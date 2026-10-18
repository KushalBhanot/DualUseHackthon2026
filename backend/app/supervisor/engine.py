"""The 15-second check: read recent calls, open or update suggestions for the supervisor.

Suggestions only. Nothing here switches surge mode on, plays a message or calls staff in.
Each suggestion type keeps at most one live row (open or snoozed). Staffing re-asks only
when the number goes up, so the supervisor isn't asked the same thing every 15 s.
"""

import asyncio
import logging
import math

from .. import db
from . import config as C
from . import messages

log = logging.getLogger(__name__)
_tick_lock = asyncio.Lock()  # the 15 s loop and the demo simulator both tick; one at a time


async def metrics() -> dict:
    m = await db.fetchrow(
        f"""SELECT
          count(*) FILTER (WHERE started_at > now() - interval '{C.SURGE_WINDOW_MIN} minutes') AS calls_surge_window,
          count(*) FILTER (WHERE started_at > now() - interval '{C.MESSAGE_WINDOW_MIN} minutes') AS calls_msg_window,
          count(*) FILTER (WHERE lane = 'red' AND status = 'ongoing' AND transfer_started_at IS NULL) AS red_waiting,
          count(*) FILTER (WHERE started_at > now() - interval '{C.MESSAGE_WINDOW_MIN} minutes'
                           AND disconnection_reason = 'user_hangup' AND duration_ms < {C.HUNG_UP_EARLY_MS}) AS hung_up_early,
          count(*) FILTER (WHERE lane = 'red' AND started_at > now() - interval '{C.STAFFING_WINDOW_MIN} minutes') AS red_staff_window,
          count(*) FILTER (WHERE lane = 'amber' AND started_at > now() - interval '{C.STAFFING_WINDOW_MIN} minutes') AS amber_staff_window,
          count(*) FILTER (WHERE lane = 'amber' AND started_at > now() - interval '{C.AMBER_LOOKBACK_MIN} minutes') AS amber_queue,
          extract(epoch FROM now() - min(started_at) FILTER (
            WHERE lane = 'amber' AND started_at > now() - interval '{C.AMBER_LOOKBACK_MIN} minutes')) / 60 AS oldest_amber_min,
          count(*) FILTER (WHERE transfer_status = 'no_answer'
                           AND started_at > now() - interval '{C.RED_NO_ANSWER_WINDOW_MIN} minutes') AS red_no_answer
        FROM calls"""
    )
    m = {k: (float(v) if k == "oldest_amber_min" and v is not None else v) for k, v in m.items()}
    m["top_cluster"], m["top_cluster_n"] = await top_cluster(C.MESSAGE_WINDOW_MIN)
    m["surge_top_cluster"], m["surge_top_cluster_n"] = await top_cluster(C.SURGE_WINDOW_MIN)
    m["surge"] = await db.fetchrow("SELECT surge_on, status_message FROM surge_state WHERE id = 1")
    return m


async def top_cluster(window_min: int) -> tuple[str | None, int]:
    top = await db.fetchrow(
        f"""SELECT cluster, count(*) AS n FROM calls
            WHERE started_at > now() - interval '{window_min} minutes' AND cluster IS NOT NULL
            GROUP BY cluster ORDER BY n DESC LIMIT 1"""
    )
    return (top["cluster"], top["n"]) if top else (None, 0)


async def live_suggestion(type_: str) -> dict | None:
    return await db.fetchrow(
        "SELECT * FROM suggestions WHERE type = %s AND status IN ('open', 'snoozed') ORDER BY id DESC LIMIT 1", type_,
    )


async def upsert(type_: str, wanted: bool, evidence: dict, recommendation: dict, rank: float = 0) -> None:
    """Keep one live suggestion per type in step with the current numbers.

    rank: for staffing, the suggested count. A decided (accepted/dismissed) suggestion is only
    re-asked when rank goes above what was last decided.
    """
    live = await live_suggestion(type_)
    if not wanted:
        if live:  # numbers dropped back: close it, snoozed or not
            await db.execute("UPDATE suggestions SET status = 'expired', decided_at = now() WHERE id = %s", live["id"])
        return
    if live:
        if live["status"] == "snoozed":
            due = await db.fetchrow("SELECT now() >= %s AS due", live["snooze_until"])
            if not due["due"]:
                return
        # Open (or snooze is over): refresh with the latest numbers and ask again.
        await db.execute(
            "UPDATE suggestions SET status = 'open', snooze_until = NULL, evidence = %s, recommendation = %s WHERE id = %s",
            evidence, recommendation | {"rank": rank}, live["id"],
        )
        return
    last = await db.fetchrow(
        "SELECT recommendation FROM suggestions WHERE type = %s AND status IN ('accepted', 'dismissed') ORDER BY id DESC LIMIT 1", type_,
    )
    if last and rank and rank <= (last["recommendation"].get("rank") or 0):
        return
    await db.execute(
        "INSERT INTO suggestions (type, evidence, recommendation) VALUES (%s, %s, %s)",
        type_, evidence, recommendation | {"rank": rank},
    )


async def tick() -> None:
    async with _tick_lock:
        await _tick()


async def _tick() -> None:
    m = await metrics()
    surge_on, active_message = m["surge"]["surge_on"], m["surge"]["status_message"]

    # 1. Surge mode prompt
    threshold = max(C.SURGE_MIN_CALLS, math.ceil(C.BASELINE_CALLS_PER_HOUR / 60 * C.SURGE_WINDOW_MIN * C.SURGE_MULTIPLIER))
    normal = C.BASELINE_CALLS_PER_HOUR / 60 * C.SURGE_WINDOW_MIN
    n = m["calls_surge_window"]
    top = f" {m['surge_top_cluster_n']} about {m['surge_top_cluster']}." if m["surge_top_cluster"] else ""
    await upsert(
        "surge_mode", not surge_on and n >= threshold,
        {"calls": n, "window_min": C.SURGE_WINDOW_MIN, "normal": round(normal, 1), "red_waiting": m["red_waiting"],
         "hung_up_early": m["hung_up_early"],
         "text": f"{n} calls in {C.SURGE_WINDOW_MIN} min (normal ≈ {normal:.0f}).{top} {m['red_waiting']} red flags waiting."
                 + (f" {m['hung_up_early']} callers hung up early." if m["hung_up_early"] else "")},
        {"action": "switch_on_surge_mode"},
    )

    # 2. Status message for every caller
    share = m["top_cluster_n"] / m["calls_msg_window"] if m["calls_msg_window"] else 0
    template = messages.for_cluster(m["top_cluster"]) if m["top_cluster"] else None
    await upsert(
        "status_message",
        not active_message and template is not None and share >= C.MESSAGE_CLUSTER_SHARE and m["top_cluster_n"] >= C.MESSAGE_MIN_CALLS,
        {"cluster": m["top_cluster"], "calls": m["top_cluster_n"], "share": round(share, 2),
         "text": f"{m['top_cluster_n']} of {m['calls_msg_window']} calls in {C.MESSAGE_WINDOW_MIN} min are about {m['top_cluster']}."},
        {"template_id": template["id"], "message": template["text"]} if template else {},
    )

    # 3a. Nurses
    per_hour = 60 / C.STAFFING_WINDOW_MIN
    minutes = (m["red_staff_window"] * C.RED_MIN + m["amber_staff_window"] * C.AMBER_MIN) * per_hour
    nurses = math.ceil(minutes / 60 / C.UTILIZATION) - C.NURSES_ON_PHONES
    oldest = m["oldest_amber_min"] or 0
    late = oldest > C.AMBER_TARGET_MIN
    unanswered = m["red_no_answer"] >= C.RED_NO_ANSWER_TRIGGER
    if late or unanswered:
        nurses = max(nurses, 1)
    reasons = []
    if m["amber_queue"]:
        reasons.append(f"{m['amber_queue']} callers in 'A person soon', oldest waiting {oldest:.0f} min (target {C.AMBER_TARGET_MIN})")
    if m["red_staff_window"]:
        reasons.append(f"{m['red_staff_window']} red calls in {C.STAFFING_WINDOW_MIN} min")
    if unanswered:
        reasons.append(f"{m['red_no_answer']} red callers sent to 911 in {C.RED_NO_ANSWER_WINDOW_MIN} min: nurse line not answering")
    await upsert(
        "staffing_nurses", nurses >= 1,
        {"nurse_minutes_per_hour": round(minutes), "on_phones": C.NURSES_ON_PHONES, "amber_queue": m["amber_queue"],
         "oldest_amber_min": round(oldest), "red_calls": m["red_staff_window"], "red_no_answer": m["red_no_answer"],
         "text": f"Call in {nurses} nurse{'s' if nurses != 1 else ''}: " + "; ".join(reasons) + "."},
        {"role": "nurse", "count": nurses}, rank=nurses,
    )

    # 3b. Doctors: a rough signal only. Phone calls can't see how full the ER is.
    red_per_hour = m["red_staff_window"] * per_hour
    tier = next(((i, label) for i, (rate, label) in enumerate(C.DOCTOR_TIERS) if red_per_hour >= rate), None)
    await upsert(
        "staffing_doctors", tier is not None,
        {"red_calls": m["red_staff_window"], "window_min": C.STAFFING_WINDOW_MIN, "rough_signal": True,
         "text": f"Consider calling in {tier[1] if tier else ''} ER doctors: {m['red_staff_window']} red-flag calls in "
                 f"{C.STAFFING_WINDOW_MIN} min. Rough signal: phone calls can't see how full the ER is."},
        {"role": "er_doctor", "count": tier[1] if tier else None},
        rank=(len(C.DOCTOR_TIERS) - tier[0]) if tier else 0,
    )


async def run_forever() -> None:
    while True:
        try:
            await tick()
        except Exception:  # noqa: BLE001 - one bad tick shouldn't stop the board
            log.exception("supervisor tick failed")
        await asyncio.sleep(C.TICK_SECONDS)
