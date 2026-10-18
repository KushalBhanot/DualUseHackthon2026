"""The two Retell custom-function endpoints for capture-and-confirm.

Retell POSTs {name, call, args} and waits for our JSON reply, which the agent reads as the
tool result. `call` includes the transcript so far; we only ever read the caller's words.
"""

import asyncio
import re

from fastapi import APIRouter, Request
from rapidfuzz import fuzz

from .. import db
from ..classify import jev
from ..retell_auth import retell_body
from . import readback
from .confirm import judge_reply
from .extract import NAME_FIELDS, digits_of, extract

router = APIRouter(prefix="/retell/tools")
MAX_ATTEMPTS = 2
OFFICIAL_COLUMN = {"caller_name": "caller_name", "callback_number": "callback_number"}


def caller_turns(call: dict) -> list[str]:
    """The caller's utterances, oldest first, from Retell's speech-to-text."""
    obj = call.get("transcript_object")
    if obj:
        return [u.get("content", "") for u in obj if u.get("role") == "user" and u.get("content")]
    lines = (call.get("transcript") or "").splitlines()
    return [l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("user:")]


async def ensure_call(call: dict) -> str:
    call_id = call["call_id"]
    await db.execute(
        "INSERT INTO calls (call_id, from_number) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        call_id, call.get("from_number"),
    )
    return call_id


async def get_detail(call_id: str, field: str) -> dict:
    row = await db.fetchrow("SELECT details -> %s AS d FROM calls WHERE call_id = %s", field, call_id)
    return (row or {}).get("d") or {}


async def save_detail(call_id: str, field: str, detail: dict) -> None:
    await db.execute(
        "UPDATE calls SET details = jsonb_set(details, ARRAY[%s], %s, true) WHERE call_id = %s",
        field, detail, call_id,
    )


def same_value(field: str, a: str, b: str | None) -> bool:
    if not b:
        return True
    if field == "callback_number":
        return digits_of(a) == digits_of(b)
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    return fuzz.ratio(norm(a), norm(b)) >= 90


async def jev_pick_fast(text, instructions, options):
    try:
        return await asyncio.wait_for(jev.pick(text, instructions, options), timeout=1.5)
    except asyncio.TimeoutError:
        return None, None


@router.post("/capture_detail")
async def capture_detail(request: Request):
    body = await retell_body(request)
    call, args = body.get("call") or {}, body.get("args") or {}
    field, model_heard = args.get("field"), args.get("model_heard")
    call_id = await ensure_call(call)
    previous = await get_detail(call_id, field)
    attempts = previous.get("attempts", 0) + 1

    found = await extract(field, caller_turns(call), call.get("from_number"), jev_pick_fast)
    if not found:
        await db.log_event(call_id, "detail_not_found", {"field": field, "model_heard": model_heard})
        ask = "Ask the caller to say it again slowly"
        if field in NAME_FIELDS or field in {"doctor_name", "medication_name"}:
            ask += ", and to spell it letter by letter"
        return {"status": "not_found", "instruction": ask + ". Then call capture_detail again."}

    detail = found | {
        "status": "pending_confirmation",
        "attempts": attempts,
        "read_back": readback.make(field, found),
        "model_heard": model_heard,
    }
    await save_detail(call_id, field, detail)
    if not same_value(field, detail["value"], model_heard):
        await db.log_event(call_id, "stt_model_mismatch", {"field": field, "transcript": detail["value"], "model_heard": model_heard})
    return {
        "status": "captured",
        "read_back": detail["read_back"],
        "instruction": "Read back the read_back text word for word, then ask: Is that right?",
    }


@router.post("/confirm_detail")
async def confirm_detail(request: Request):
    body = await retell_body(request)
    call, args = body.get("call") or {}, body.get("args") or {}
    field, agent_says = args.get("field"), bool(args.get("confirmed"))
    call_id = await ensure_call(call)
    detail = await get_detail(call_id, field)
    if not detail:
        return {"status": "missing", "instruction": "Call capture_detail first."}

    turns = caller_turns(call)
    reply = turns[-1] if turns else ""
    heard = judge_reply(reply)
    if heard is None and reply:
        p = await jev.yes_no(f"Agent read back: {detail.get('read_back')}\nCaller replied: {reply}",
                             "Did the caller confirm the read-back is correct?")
        heard = None if p is None else "yes" if p >= 0.7 else "no" if p <= 0.3 else None

    if agent_says and heard == "yes":
        detail |= {"status": "confirmed", "confirm_reply": reply}
        await save_detail(call_id, field, detail)
        if col := OFFICIAL_COLUMN.get(field):
            extra = ", callback_source = 'confirmed'" if field == "callback_number" else ""
            await db.execute(f"UPDATE calls SET {col} = %s{extra} WHERE call_id = %s", detail["value"], call_id)
        await db.log_event(call_id, "detail_confirmed", {"field": field, "value": detail["value"], "attempts": detail["attempts"]})
        return {"status": "confirmed", "instruction": "Thank them briefly and continue."}

    if agent_says and heard != "yes":
        # The agent thought it was confirmed but the caller's words don't say so.
        await db.log_event(call_id, "confirm_disagreement", {"field": field, "reply": reply, "transcript_judged": heard})

    if detail.get("attempts", 1) >= MAX_ATTEMPTS:
        detail |= {"status": "unconfirmed", "confirm_reply": reply}
        await save_detail(call_id, field, detail)
        await db.execute("UPDATE calls SET needs_review = true WHERE call_id = %s", call_id)
        await db.log_event(call_id, "detail_rejected", {"field": field, "value": detail["value"], "final": True})
        return {"status": "unconfirmed", "instruction": "Say: Staff will confirm your details when they call back. Then continue."}

    detail |= {"status": "retry", "confirm_reply": reply}
    await save_detail(call_id, field, detail)
    await db.log_event(call_id, "detail_rejected", {"field": field, "value": detail["value"], "final": False})
    ask = "Apologize, ask them to say it again slowly"
    if field in NAME_FIELDS or field in {"doctor_name", "medication_name"}:
        ask += " and spell it letter by letter"
    return {"status": "retry", "instruction": ask + ". Then call capture_detail again."}
