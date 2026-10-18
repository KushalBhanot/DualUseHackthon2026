"""Classify a stored call and write the result back. Used live, post-call and by the seed."""

from .. import db
from . import jev, rules
from .combine import combine


async def transcript_text(call_id: str) -> tuple[str, str]:
    """(everything the caller said, the full conversation as 'Caller:/Agent:' lines)."""
    items = await db.fetch(
        "SELECT role, content FROM transcript_items WHERE call_id = %s AND role IN ('user', 'agent') ORDER BY time_sec NULLS LAST, updated_at",
        call_id,
    )
    caller = "\n".join(i["content"] or "" for i in items if i["role"] == "user")
    full = "\n".join(f"{'Caller' if i['role'] == 'user' else 'Agent'}: {i['content'] or ''}" for i in items)
    return caller, full


async def classify_and_store(call_id: str, stage: str, use_jev: bool = True) -> dict:
    """Run rules (and Jev), merge with what's stored, save. Returns the result plus `new_red_flags`."""
    caller, full = await transcript_text(call_id)
    row = await db.fetchrow("SELECT lane, red_flags FROM calls WHERE call_id = %s", call_id)
    if row is None:
        return {}

    rules_result = rules.classify(caller)
    jev_result = await jev.classify_call(full) if use_jev and full.strip() else None
    out = combine(rules_result, jev_result, current_lane=row["lane"])

    old_flags = set(row["red_flags"] or [])
    all_flags = sorted(old_flags | set(out["red_flags"]))
    out["new_red_flags"] = [f for f in out["red_flags"] if f not in old_flags]

    await db.execute(
        """UPDATE calls SET
             red_flags = %s,
             reason = coalesce(reason, %s),
             cluster = coalesce(%s, cluster),
             urgency = coalesce(%s, urgency),
             needs_review = needs_review OR %s,
             rules_result = %s,
             jev_result = coalesce(%s, jev_result),
             red_flag_at = CASE WHEN %s AND red_flag_at IS NULL THEN now() ELSE red_flag_at END
           WHERE call_id = %s""",
        all_flags, out["reason"], out["cluster"], out["urgency"], out["needs_review"],
        rules_result | {"stage": stage},
        (jev_result | {"stage": stage}) if jev_result else None,
        bool(all_flags), call_id,
    )
    await db.raise_lane(call_id, out["lane"], f"classify:{stage}")
    if out["rules_miss"] and out["new_red_flags"]:
        await db.log_event(call_id, "rules_miss", {"jev": jev_result, "stage": stage})
    return out
