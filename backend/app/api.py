"""Read endpoints for the supervisor board (frontend/, a Next.js app)."""

from fastapi import APIRouter, HTTPException, Response

from . import db
from .supervisor import config as C

router = APIRouter(prefix="/api")

# A call is on the line until it has ended. Live calls get ended_at from Retell's call_ended webhook;
# simulated calls are inserted with their scripted end time, so they count until then too.
ON_LINE = "(status = 'ongoing' OR ended_at > now())"

# Everything on calls except the audio bytes and the raw webhook payload.
CALL_COLUMNS = f"""call_id, source, scenario, status, from_number, started_at, ended_at, duration_ms,
  disconnection_reason, lane, red_flags, cluster, intent, reason, urgency, caller_name, callback_number,
  callback_source, needs_review, rules_result, jev_result, details, red_flag_at, transfer_started_at,
  transfer_ended_at, transfer_target, transfer_status, summary, recording_url, recording IS NOT NULL AS has_recording,
  {ON_LINE} AS on_line"""

# The slim columns a board row needs. The board is polled every few seconds, so it skips
# transcripts, details and full classifier results (those are on GET /api/calls/{id}).
ROW_COLUMNS = f"""call_id, source, status, started_at, lane, red_flags, cluster, intent, reason, caller_name,
  callback_number, from_number, transfer_status, disconnection_reason, needs_review,
  rules_result ->> 'lane' AS rules_lane, jev_result ->> 'lane' AS jev_lane, {ON_LINE} AS on_line"""

# Who in 'A person soon' gets called back first (decision 3), most urgent first.
AMBER_ORDER = ["child_under_2", "confused_or_unclear", "mental_health", "hospice", "recent_discharge",
               "vulnerable_caller", "family_locating", "repeat_caller", "asked_for_person"]


@router.get("/board")
async def board(minutes: int = 180):
    since = f"now() - make_interval(mins => {int(minutes)})"
    lanes = await db.fetch(f"SELECT coalesce(lane, 'unsorted') AS lane, count(*) AS n FROM calls WHERE started_at > {since} GROUP BY 1")
    clusters = await db.fetch(
        f"""SELECT cluster, count(*) AS calls, count(*) FILTER (WHERE lane = 'red') AS red_flags
            FROM calls WHERE started_at > {since} AND cluster IS NOT NULL
            GROUP BY cluster ORDER BY calls DESC"""
    )
    amber = await db.fetch(
        f"""SELECT {ROW_COLUMNS}, extract(epoch FROM now() - started_at)::int / 60 AS waiting_min
            FROM calls WHERE lane = 'amber' AND started_at > {since}
            ORDER BY coalesce(array_position(%s::text[], reason), 99), urgency DESC NULLS LAST, started_at""",
        AMBER_ORDER,
    )
    red = await db.fetch(f"SELECT {ROW_COLUMNS} FROM calls WHERE lane = 'red' AND started_at > {since} ORDER BY started_at DESC")
    green = await db.fetch(f"SELECT {ROW_COLUMNS} FROM calls WHERE lane = 'green' AND started_at > {since} ORDER BY started_at DESC LIMIT 100")
    # Live calls the classifiers haven't placed yet (no caller turn so far).
    unsorted = await db.fetch(f"SELECT {ROW_COLUMNS} FROM calls WHERE lane IS NULL AND status = 'ongoing' AND started_at > {since} ORDER BY started_at DESC")
    return {
        "lanes": {r["lane"]: r["n"] for r in lanes},
        "clusters": clusters,
        "cluster_series": await cluster_series(since),
        "red": red,
        "amber_queue": amber,
        "green": green,
        "unsorted": unsorted,
        "volume_1min": await volume_1min(),
        "kpis": await kpis(since),
        "surge": await db.fetchrow("SELECT * FROM surge_state WHERE id = 1"),
        "open_suggestions": (await db.fetchrow("SELECT count(*) AS n FROM suggestions WHERE status = 'open'"))["n"],
    }


async def kpis(since: str) -> dict:
    k = await db.fetchrow(
        f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE started_at > now() - interval '10 minutes') AS calls_10min,
                   count(*) FILTER (WHERE {ON_LINE}) AS on_line,
                   count(*) FILTER (WHERE disconnection_reason = 'user_hangup') AS hung_up,
                   count(*) FILTER (WHERE lane = 'green') AS handled_by_ai,
                   count(*) FILTER (WHERE lane IS NOT NULL) AS sorted,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM transfer_started_at - red_flag_at))
                         FILTER (WHERE lane = 'red' AND transfer_started_at IS NOT NULL AND red_flag_at IS NOT NULL))::numeric, 1)
                     AS red_median_handoff_s,
                   count(*) FILTER (WHERE lane = 'amber' AND started_at > now() - make_interval(mins => %s)) AS amber_waiting,
                   round(extract(epoch FROM now() - min(started_at) FILTER (
                     WHERE lane = 'amber' AND started_at > now() - make_interval(mins => %s))) / 60) AS oldest_amber_min
            FROM calls WHERE started_at > {since}""",
        C.AMBER_LOOKBACK_MIN, C.AMBER_LOOKBACK_MIN,
    )
    k["red_not_connected"] = (await db.fetchrow(
        "SELECT count(*) AS n FROM suggestions WHERE type = 'red_not_connected' AND status = 'open'"))["n"]
    k["amber_target_min"] = C.AMBER_TARGET_MIN
    k["ai_handled_share"] = round(k["handled_by_ai"] / k["sorted"], 2) if k["sorted"] else None
    return k


async def volume_1min(minutes: int = 20) -> list[dict]:
    """Calls per minute by lane over the last `minutes`, empty minutes included."""
    return await db.fetch(
        """SELECT m.bucket, count(c.call_id) AS calls,
                  count(*) FILTER (WHERE c.lane = 'red') AS red, count(*) FILTER (WHERE c.lane = 'amber') AS amber,
                  count(*) FILTER (WHERE c.lane = 'green') AS green
           FROM generate_series(date_trunc('minute', now()) - make_interval(mins => %s), date_trunc('minute', now()), interval '1 minute') m(bucket)
           LEFT JOIN calls c ON date_trunc('minute', c.started_at) = m.bucket
           GROUP BY 1 ORDER BY 1""",
        minutes - 1,
    )


async def cluster_series(since: str, minutes: int = 10) -> dict[str, list[int]]:
    """Per cluster, calls per minute over the last `minutes` (the sparklines on the Watch card)."""
    rows = await db.fetch(
        f"""SELECT s.cluster, array_agg(s.n ORDER BY s.bucket) AS series FROM (
              SELECT cl.cluster, m.bucket, count(c.call_id) AS n
              FROM (SELECT DISTINCT cluster FROM calls WHERE started_at > {since} AND cluster IS NOT NULL) cl
              CROSS JOIN generate_series(date_trunc('minute', now()) - make_interval(mins => %s), date_trunc('minute', now()), interval '1 minute') m(bucket)
              LEFT JOIN calls c ON c.cluster = cl.cluster AND date_trunc('minute', c.started_at) = m.bucket
              GROUP BY 1, 2) s
            GROUP BY 1""",
        minutes - 1,
    )
    return {r["cluster"]: r["series"] for r in rows}


@router.get("/calls")
async def list_calls(lane: str | None = None, source: str | None = None, status: str | None = None, limit: int = 100):
    return await db.fetch(
        f"""SELECT {CALL_COLUMNS} FROM calls
            WHERE (%s::text IS NULL OR lane = %s) AND (%s::text IS NULL OR source = %s) AND (%s::text IS NULL OR status = %s)
            ORDER BY started_at DESC LIMIT %s""",
        lane, lane, source, source, status, status, min(limit, 500),
    )


@router.get("/calls/{call_id}")
async def get_call(call_id: str):
    """The Handoff Card: who, which red flags, callback number (and whether it's confirmed), transcript."""
    call = await db.fetchrow(f"SELECT {CALL_COLUMNS} FROM calls WHERE call_id = %s", call_id)
    if not call:
        raise HTTPException(404, "no such call")
    call["transcript"] = await db.fetch(
        "SELECT item_id, role, content, time_sec FROM transcript_items WHERE call_id = %s ORDER BY time_sec NULLS LAST, updated_at", call_id,
    )
    call["events"] = await db.fetch("SELECT actor, type, payload, created_at FROM events WHERE call_id = %s ORDER BY id", call_id)
    call["alerts"] = await db.fetch("SELECT * FROM suggestions WHERE call_id = %s ORDER BY id", call_id)
    return call


@router.get("/calls/{call_id}/recording")
async def get_recording(call_id: str):
    row = await db.fetchrow("SELECT recording FROM calls WHERE call_id = %s", call_id)
    if not row or row["recording"] is None:
        raise HTTPException(404, "no recording")
    return Response(content=bytes(row["recording"]), media_type="audio/wav")


@router.get("/analytics")
async def analytics(minutes: int = 60):
    since = f"now() - make_interval(mins => {int(minutes)})"
    volume = await db.fetch(
        f"""SELECT date_bin('5 minutes', started_at, '2000-01-01') AS bucket, count(*) AS calls,
                   count(*) FILTER (WHERE lane = 'red') AS red, count(*) FILTER (WHERE lane = 'amber') AS amber,
                   count(*) FILTER (WHERE lane = 'green') AS green
            FROM calls WHERE started_at > {since} GROUP BY 1 ORDER BY 1"""
    )
    classifiers = await db.fetchrow(
        f"""SELECT count(*) FILTER (WHERE jev_result IS NOT NULL) AS jev_classified,
                   count(*) FILTER (WHERE jev_result ->> 'lane' = coalesce(rules_result ->> 'lane', 'green')) AS rules_jev_agree,
                   round(avg((jev_result ->> 'confidence')::numeric), 2) AS mean_jev_confidence,
                   round(avg((jev_result ->> 'latency_ms')::numeric)) AS mean_jev_latency_ms
            FROM calls WHERE started_at > {since}"""
    )
    events = await db.fetch(
        f"""SELECT type, count(*) AS n FROM events
            WHERE created_at > {since} AND type IN ('rules_miss', 'stt_model_mismatch', 'detail_confirmed',
                  'detail_rejected', 'confirm_disagreement', 'red_flag_detected', 'context_injected', 'analysis_mismatch')
            GROUP BY type"""
    )
    details = await db.fetch(
        f"""SELECT d.value ->> 'status' AS status, count(*) AS n
            FROM calls, jsonb_each(details) d WHERE started_at > {since} GROUP BY 1"""
    )
    handoff = await db.fetchrow(
        f"""SELECT count(*) AS red_calls,
                   round(avg(extract(epoch FROM transfer_started_at - red_flag_at))::numeric, 1) AS mean_sec_flag_to_transfer,
                   round(avg(extract(epoch FROM transfer_ended_at - transfer_started_at))
                         FILTER (WHERE transfer_status = 'connected')::numeric, 1) AS mean_sec_to_nurse_answer,
                   count(*) FILTER (WHERE transfer_status = 'connected') AS connected,
                   count(*) FILTER (WHERE transfer_status = 'no_answer') AS told_to_call_911,
                   count(*) FILTER (WHERE transfer_status IN ('caller_hung_up', 'never_started')) AS other_not_connected
            FROM calls WHERE lane = 'red' AND started_at > {since}"""
    )
    detail_counts = {r["status"]: r["n"] for r in details}
    captured = sum(detail_counts.values())
    return {
        "window_min": minutes,
        "volume_5min": volume,
        "lane_mix": {k: sum(b[k] for b in volume) for k in ("red", "amber", "green")},
        "classifiers": classifiers,
        "events": {r["type"]: r["n"] for r in events},
        "details": detail_counts | {"confirmation_rate": round(detail_counts.get("confirmed", 0) / captured, 2) if captured else None},
        "handoff": handoff | {"share_told_to_call_911": round(handoff["told_to_call_911"] / handoff["red_calls"], 2) if handoff["red_calls"] else None},
    }
