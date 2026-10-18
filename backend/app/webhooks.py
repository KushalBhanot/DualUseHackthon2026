"""Retell call webhooks: call_started, call_ended, call_analyzed.

We answer fast (204) and do the slow parts (classification, audio download) in the background.
"""

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Request, Response

from . import db, handoff, monitor, recordings
from .classify.service import classify_and_store
from .details.tools import same_value
from .retell_auth import retell_body

router = APIRouter()


def ts(ms) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) if ms else None


@router.post("/retell/webhook", status_code=204)
async def webhook(request: Request, background: BackgroundTasks):
    body = await retell_body(request)
    event, call = body.get("event"), body.get("call") or {}
    call_id = call.get("call_id")
    if not call_id:
        return Response(status_code=204)

    await db.execute(
        """INSERT INTO calls (call_id, from_number, started_at, raw) VALUES (%s, %s, coalesce(%s, now()), %s)
           ON CONFLICT (call_id) DO UPDATE SET raw = EXCLUDED.raw,
             from_number = coalesce(calls.from_number, EXCLUDED.from_number),
             started_at = coalesce(%s, calls.started_at)""",
        call_id, call.get("from_number"), ts(call.get("start_timestamp")), call, ts(call.get("start_timestamp")),
    )
    await db.log_event(call_id, f"webhook_{event}")

    if event == "call_started":
        monitor.start(call_id)
    elif event == "call_ended":
        await db.execute(
            """UPDATE calls SET status = 'ended', ended_at = coalesce(%s, now()), duration_ms = %s,
                 disconnection_reason = %s, recording_url = %s WHERE call_id = %s""",
            ts(call.get("end_timestamp")), call.get("duration_ms"), call.get("disconnection_reason"),
            call.get("recording_url"), call_id,
        )
        background.add_task(after_call, call_id, call)
    elif event == "call_analyzed":
        background.add_task(after_analysis, call_id, call)
    return Response(status_code=204)


async def after_call(call_id: str, call: dict) -> None:
    # If the live monitor missed the call, fill the transcript from the final one.
    has_items = await db.fetchrow("SELECT 1 FROM transcript_items WHERE call_id = %s LIMIT 1", call_id)
    if not has_items:
        for i, u in enumerate(call.get("transcript_object") or []):
            await db.execute(
                "INSERT INTO transcript_items (call_id, item_id, role, content, time_sec) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                call_id, f"final-{i}", u.get("role"), u.get("content"), (u.get("words") or [{}])[0].get("start"),
            )
    await classify_and_store(call_id, "post_call", use_jev=True)
    await handoff.finish(call_id)


async def after_analysis(call_id: str, call: dict) -> None:
    analysis = call.get("call_analysis") or {}
    data = analysis.get("custom_analysis_data") or {}
    await db.execute(
        """UPDATE calls SET status = 'analyzed', summary = %s,
             cluster = coalesce(cluster, %s), intent = coalesce(intent, %s),
             needs_review = needs_review OR coalesce(%s, false),
             recording_url = coalesce(recording_url, %s)
           WHERE call_id = %s""",
        analysis.get("call_summary"), data.get("cluster"), data.get("intent"), data.get("needs_review"),
        call.get("recording_url"), call_id,
    )
    await db.raise_lane(call_id, data.get("lane"), "retell post-call analysis")

    # Retell's analysis values are kept for comparison only; they never fill the official fields.
    for field in ("caller_name", "callback_number"):
        value = data.get(field)
        if value and value != "unknown":
            row = await db.fetchrow(
                """UPDATE calls SET details = jsonb_set(details, ARRAY[%s],
                     coalesce(details -> %s, '{}'::jsonb) || jsonb_build_object('analysis_value', %s::text), true)
                   WHERE call_id = %s RETURNING details -> %s ->> 'value' AS transcript_value""",
                field, field, value, call_id, field,
            )
            if row and row["transcript_value"] and not same_value(field, row["transcript_value"], value):
                await db.execute("UPDATE calls SET needs_review = true WHERE call_id = %s", call_id)
                await db.log_event(call_id, "analysis_mismatch", {"field": field, "transcript": row["transcript_value"], "analysis": value})
    await handoff.finish(call_id)  # again, in case the analysis raised the lane to red
    await recordings.download(call_id, call.get("recording_url"))
