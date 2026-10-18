"""Retell's inbound call webhook: before a call is answered, hand Retell this call's variables.

This is how the supervisor's choices reach the very next caller without a redeploy:
the active status message (spoken in the greeting), surge callback windows, and the nurse line.
Set it per phone number: dashboard -> Phone Numbers -> Inbound Webhook URL.
"""

from fastapi import APIRouter, Request

from . import db, handoff
from .retell_auth import retell_body

router = APIRouter()


async def call_variables() -> dict[str, str]:
    s = await db.fetchrow("SELECT * FROM surge_state WHERE id = 1")
    return {
        "surge_banner": s["status_message"] or "",
        "routine_callback_window": s["surge_routine_window"] if s["surge_on"] else s["routine_callback_window"],
        "priority_callback_window": s["surge_priority_window"] if s["surge_on"] else s["priority_callback_window"],
        "nurse_line": await handoff.current_nurse_line(),
    }


@router.post("/retell/inbound")
async def inbound(request: Request):
    body = await retell_body(request)
    info = body.get("call_inbound") or {}
    variables = await call_variables()
    if call_id := info.get("call_id"):
        await db.execute(
            """INSERT INTO calls (call_id, from_number, transfer_target) VALUES (%s, %s, %s)
               ON CONFLICT (call_id) DO UPDATE SET transfer_target = EXCLUDED.transfer_target""",
            call_id, info.get("from_number"), variables["nurse_line"],
        )
        await db.log_event(call_id, "inbound_variables", variables)
    return {"call_inbound": {"dynamic_variables": variables}}
