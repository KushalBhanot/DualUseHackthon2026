"""Supervisor actions: decide suggestions, switch surge mode, set the status message, edit nurse lines.

Every action is one click and is logged as an event with actor='supervisor'.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from . import config as C
from . import messages

router = APIRouter(prefix="/api")


async def act(type_: str, payload: dict, call_id: str | None = None) -> None:
    await db.log_event(call_id, type_, payload, actor="supervisor")


# ---------------------------------------------------------------- suggestions

@router.get("/suggestions")
async def list_suggestions(status: str = "open"):
    return await db.fetch(
        """SELECT * FROM suggestions WHERE status = %s
           ORDER BY (type = 'red_not_connected') DESC, created_at DESC""",
        status,
    )


async def get_suggestion(sid: int) -> dict:
    s = await db.fetchrow("SELECT * FROM suggestions WHERE id = %s", sid)
    if not s:
        raise HTTPException(404, "no such suggestion")
    if s["status"] not in ("open", "snoozed"):
        raise HTTPException(409, f"suggestion is already {s['status']}")
    return s


async def decide(s: dict, status: str, **extra) -> dict:
    await db.execute(
        "UPDATE suggestions SET status = %s, decided_at = now(), snooze_until = %s WHERE id = %s",
        status, extra.get("snooze_until"), s["id"],
    )
    await act(f"suggestion_{status}", {"suggestion_id": s["id"], "type": s["type"]} | extra.get("payload", {}), s["call_id"])
    return await db.fetchrow("SELECT * FROM suggestions WHERE id = %s", s["id"])


class Accept(BaseModel):
    message: str | None = None  # status_message only: the supervisor's edited wording


@router.post("/suggestions/{sid}/accept")
async def accept(sid: int, body: Accept | None = None):
    s = await get_suggestion(sid)
    if s["type"] == "red_not_connected":
        raise HTTPException(409, "red alerts can only be resolved")
    if s["type"] == "surge_mode":
        await set_surge(Surge(on=True))
    elif s["type"] == "status_message":
        await set_message(Message(text=(body and body.message) or s["recommendation"]["message"],
                                  template_id=s["recommendation"].get("template_id")))
    # Staffing: accepting only records the decision. Paging staff is out of scope for v1.
    return await decide(s, "accepted")


@router.post("/suggestions/{sid}/snooze")
async def snooze(sid: int):
    s = await get_suggestion(sid)
    if s["type"] == "red_not_connected":
        raise HTTPException(409, "red alerts can't be snoozed")
    until = (await db.fetchrow(f"SELECT now() + interval '{C.SNOOZE_MIN} minutes' AS t"))["t"]
    return await decide(s, "snoozed", snooze_until=until)


@router.post("/suggestions/{sid}/dismiss")
async def dismiss(sid: int):
    s = await get_suggestion(sid)
    if s["type"] == "red_not_connected":
        raise HTTPException(409, "red alerts can't be dismissed, only resolved")
    return await decide(s, "dismissed")


class Resolve(BaseModel):
    outcome: str  # called_back | reached_911 | unreachable


@router.post("/suggestions/{sid}/resolve")
async def resolve(sid: int, body: Resolve):
    s = await get_suggestion(sid)
    if s["type"] != "red_not_connected":
        raise HTTPException(409, "only red alerts are resolved")
    if body.outcome not in ("called_back", "reached_911", "unreachable"):
        raise HTTPException(422, "outcome must be called_back, reached_911 or unreachable")
    return await decide(s, "resolved", payload={"outcome": body.outcome})


# ---------------------------------------------------------------- surge mode

class Surge(BaseModel):
    on: bool


@router.get("/surge")
async def get_surge():
    return await db.fetchrow("SELECT * FROM surge_state WHERE id = 1")


@router.post("/surge")
async def set_surge(body: Surge):
    await db.execute(
        "UPDATE surge_state SET surge_on = %s, switched_at = now() WHERE id = 1 AND surge_on <> %s", body.on, body.on,
    )
    await act("surge_on" if body.on else "surge_off", {})
    if body.on:  # a manual switch answers any open prompt
        await db.execute("UPDATE suggestions SET status = 'accepted', decided_at = now() WHERE type = 'surge_mode' AND status IN ('open', 'snoozed')")
    return await get_surge()


# ---------------------------------------------------------------- status message

class Message(BaseModel):
    text: str | None  # null stops the message
    template_id: str | None = None


@router.get("/status-messages")
async def list_messages():
    active = (await db.fetchrow("SELECT status_message FROM surge_state WHERE id = 1"))["status_message"]
    return {"active": active, "templates": messages.TEMPLATES}


@router.post("/status-message")
async def set_message(body: Message):
    text = (body.text or "").strip() or None
    await db.execute("UPDATE surge_state SET status_message = %s WHERE id = 1", text)
    edited = bool(text and body.template_id and text != next((t["text"] for t in messages.TEMPLATES if t["id"] == body.template_id), None))
    await act("status_message_set" if text else "status_message_stopped", {"text": text, "template_id": body.template_id, "edited": edited})
    return await list_messages()


# ---------------------------------------------------------------- nurse lines

class NurseLine(BaseModel):
    label: str | None = None
    number: str | None = None
    role: str | None = None
    on_duty: bool | None = None
    priority: int | None = None


@router.get("/nurse-lines")
async def list_nurse_lines():
    return await db.fetch("SELECT * FROM nurse_lines ORDER BY on_duty DESC, priority, id")


def check_number(number: str | None) -> None:
    if number is not None and not (number.startswith("+") and number[1:].isdigit() and 8 <= len(number) <= 16):
        raise HTTPException(422, "number must be E.164, e.g. +14155550142")


@router.post("/nurse-lines")
async def add_nurse_line(body: NurseLine):
    if not body.label or not body.number:
        raise HTTPException(422, "label and number are required")
    check_number(body.number)
    row = await db.fetchrow(
        "INSERT INTO nurse_lines (label, number, role, on_duty, priority) VALUES (%s, %s, %s, %s, %s) RETURNING *",
        body.label, body.number, body.role or "nurse", True if body.on_duty is None else body.on_duty, body.priority or 1,
    )
    await act("nurse_line_added", {"id": row["id"], "label": row["label"], "number": row["number"]})
    return row


@router.patch("/nurse-lines/{line_id}")
async def update_nurse_line(line_id: int, body: NurseLine):
    check_number(body.number)
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "nothing to change")
    sets = ", ".join(f"{k} = %s" for k in changes)
    row = await db.fetchrow(
        f"UPDATE nurse_lines SET {sets}, updated_at = now() WHERE id = %s RETURNING *", *changes.values(), line_id,
    )
    if not row:
        raise HTTPException(404, "no such nurse line")
    await act("nurse_line_changed", {"id": line_id} | changes)
    return row
