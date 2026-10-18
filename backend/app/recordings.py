"""Download a call's audio from Retell's recording_url into calls.recording."""

import logging

import httpx

from . import db

log = logging.getLogger(__name__)


async def download(call_id: str, url: str | None) -> None:
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
    except httpx.HTTPError as e:
        await db.log_event(call_id, "recording_failed", {"error": str(e)[:300]})
        return
    await db.execute("UPDATE calls SET recording = %s WHERE call_id = %s", r.content, call_id)
    await db.log_event(call_id, "recording_saved", {"bytes": len(r.content), "content_type": r.headers.get("content-type")})
