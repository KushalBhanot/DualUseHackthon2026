"""Check that a request really came from Retell (x-retell-signature over the raw body)."""

import json

from fastapi import HTTPException, Request
from retell.lib.webhook_auth import verify

from .settings import RETELL_API_KEY, VERIFY_RETELL_SIGNATURE


async def retell_body(request: Request) -> dict:
    raw = (await request.body()).decode()
    if VERIFY_RETELL_SIGNATURE:
        sig = request.headers.get("x-retell-signature", "")
        if not RETELL_API_KEY or not verify(raw, RETELL_API_KEY, sig):
            raise HTTPException(401, "bad Retell signature")
    return json.loads(raw or "{}")
