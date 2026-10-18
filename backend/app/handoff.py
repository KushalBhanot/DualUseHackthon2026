"""Red-flag calls: which nurse line, what happened to the transfer, and the alert if it failed.

The agent rings the nurse line for 20 s (transfer_ring_duration_ms in ladder.mjs). If nobody
answers it tells the caller to hang up and call 911. We record the outcome and, for any red
caller who didn't reach a nurse, open an alert a person must resolve.
"""

import json

from . import db
from .settings import NURSE_LINE


async def current_nurse_line() -> str:
    row = await db.fetchrow("SELECT number FROM nurse_lines WHERE on_duty ORDER BY priority, id LIMIT 1")
    return row["number"] if row else NURSE_LINE


async def transfer_started(call_id: str) -> None:
    await db.execute(
        "UPDATE calls SET transfer_started_at = coalesce(transfer_started_at, now()), red_flag_at = coalesce(red_flag_at, now()) WHERE call_id = %s",
        call_id,
    )
    await db.log_event(call_id, "transfer_started")


def outcome_from_result(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in ("fail", "no answer", "not answer", "unanswered", "busy", "timeout", "timed out", "declined", "not connected")):
        return "no_answer"
    if any(w in t for w in ("success", "connected", "bridged", "transferred")):
        return "connected"
    return None


async def transfer_result(call_id: str, item: dict) -> None:
    """The transfer tool's result item from the live transcript. Raw text kept to tune the parser."""
    text = item.get("content") if isinstance(item.get("content"), str) else json.dumps(item)
    status = outcome_from_result(text)
    await db.log_event(call_id, "transfer_result", {"status": status, "raw": text[:500]})
    if status:
        await db.execute(
            "UPDATE calls SET transfer_status = %s, transfer_ended_at = now() WHERE call_id = %s", status, call_id,
        )


async def finish(call_id: str) -> None:
    """At call end: settle transfer_status for red calls and alert if the caller didn't reach a nurse."""
    c = await db.fetchrow(
        "SELECT lane, red_flags, red_flag_at, transfer_started_at, transfer_status, disconnection_reason, "
        "from_number, callback_number, started_at FROM calls WHERE call_id = %s",
        call_id,
    )
    if not c or not (c["lane"] == "red" or c["red_flag_at"]):
        return
    status = c["transfer_status"]
    reason = (c["disconnection_reason"] or "").lower()
    if not status:
        if "transfer" in reason:
            status = "connected"
        elif not c["transfer_started_at"]:
            status = "never_started"
        elif reason == "user_hangup":
            status = "caller_hung_up"
        else:
            status = "no_answer"
    await db.execute(
        """UPDATE calls SET transfer_status = %s,
             transfer_ended_at = coalesce(transfer_ended_at, ended_at, now()),
             callback_number = coalesce(callback_number, %s::text),
             callback_source = coalesce(callback_source, CASE WHEN %s::text IS NOT NULL THEN 'caller_id' END)
           WHERE call_id = %s""",
        status, c["from_number"], c["from_number"], call_id,
    )
    if status != "connected":
        await open_red_alert(call_id, status)


async def open_red_alert(call_id: str, status: str) -> None:
    exists = await db.fetchrow("SELECT 1 FROM suggestions WHERE type = 'red_not_connected' AND call_id = %s", call_id)
    if exists:
        return
    c = await db.fetchrow("SELECT red_flags, callback_number, from_number, started_at, caller_name FROM calls WHERE call_id = %s", call_id)
    what = {"no_answer": "nurse line didn't answer, caller told to call 911",
            "caller_hung_up": "caller hung up before reaching a nurse",
            "never_started": "transfer never started"}.get(status, status)
    evidence = {
        "transfer_status": status,
        "red_flags": c["red_flags"],
        "callback_number": c["callback_number"] or c["from_number"],
        "caller_name": c["caller_name"],
        "call_started": c["started_at"].isoformat(),
        "text": f"Red caller not connected: {what}. Call back {c['callback_number'] or c['from_number'] or 'unknown number'}"
                f" ({', '.join(c['red_flags']) or 'red flag'}).",
    }
    await db.execute(
        "INSERT INTO suggestions (type, call_id, evidence, recommendation) VALUES ('red_not_connected', %s, %s, %s)",
        call_id, evidence, {"action": "call_back_now"},
    )
    await db.log_event(call_id, "red_not_connected", evidence)
