"""Demo controls: run a simulated night from the board (the same calls as `python -m app.seed`).

Drip mode inserts one call at a time so the board fills like a real night; instant mode
backfills the whole scenario spread over its usual time span.
"""

import asyncio
import datetime as dt
import logging
import random
from contextlib import suppress
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import seed
from .classify.service import classify_and_store
from .supervisor import engine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sim")

LABELS = {
    "serious_earthquake": "Serious earthquake",
    "big_fire": "Big fire",
    "small_fire": "Small fire",
    "small_earthquake": "Small earthquake",
    "tuesday": "An ordinary Tuesday",
}
STATE: dict = {"scenario": None, "running": False, "inserted": 0, "total": 0}
_task: asyncio.Task | None = None


def state() -> dict:
    return STATE | {"scenarios": [{"id": k, "label": v, "default_count": seed.SCENARIOS[k][1]} for k, v in LABELS.items()]}


async def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
    _task = None
    STATE["running"] = False


async def run(scenario: str, count: int, drip: float, rng: random.Random) -> None:
    templates, _, span_min = seed.SCENARIOS[scenario]
    weights = [t["w"] for t in templates]
    now = dt.datetime.now(dt.timezone.utc)
    try:
        for i in range(count):
            t = rng.choices(templates, weights)[0]
            started = dt.datetime.now(dt.timezone.utc) if drip else now - dt.timedelta(minutes=rng.uniform(0, span_min))
            call_id = await seed.insert_call(scenario, t, started, rng)
            await classify_and_store(call_id, "post_call", use_jev=False)
            STATE["inserted"] = i + 1
            if drip:
                await engine.tick()
                # Ramp up: the first few calls come in slowly, then the surge hits.
                await asyncio.sleep(drip * (3 if i < 4 else 1))
        await engine.tick()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - surface in the log, keep the server up
        log.exception("simulation %s failed", scenario)
    finally:
        STATE["running"] = False


class Start(BaseModel):
    scenario: str
    count: int | None = None
    mode: Literal["drip", "instant"] = "drip"
    drip: float = 1.5  # seconds between calls in drip mode
    seed: int | None = None


@router.get("")
async def get_state():
    return state()


@router.post("/start")
async def start(body: Start):
    global _task
    if body.scenario not in seed.SCENARIOS:
        raise HTTPException(422, f"scenario must be one of {', '.join(LABELS)}")
    await stop()
    await seed.ensure_nurse_lines()
    count = max(1, min(body.count or seed.SCENARIOS[body.scenario][1], 200))
    STATE.update(scenario=body.scenario, running=True, inserted=0, total=count)
    drip = max(0.2, body.drip) if body.mode == "drip" else 0
    _task = asyncio.create_task(run(body.scenario, count, drip, random.Random(body.seed)))
    return state()


@router.post("/stop")
async def post_stop():
    await stop()
    return state()


@router.post("/reset")
async def reset():
    """Remove simulated calls and demo suggestions, and switch surge mode off."""
    await stop()
    await seed.reset()
    STATE.update(scenario=None, inserted=0, total=0)
    return state()
