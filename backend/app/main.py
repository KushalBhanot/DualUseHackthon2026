import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import api, db, sim, webhooks  # noqa: E402
from .supervisor import engine  # noqa: E402

INTERVAL = float(os.environ.get("ENGINE_INTERVAL_S", "5"))


async def _engine_loop():
    while True:
        try:
            engine.run_once()
        except Exception as e:  # keep the board alive if one check fails
            print("engine error:", e)
        await asyncio.sleep(INTERVAL)


@asynccontextmanager
async def lifespan(app):
    db.conn()
    sim.seed_nurse_lines()
    # Public demo: a fresh instance starts with a recent surge night already on the board.
    demo = os.environ.get("DEMO_SEED")
    if demo and not db.one("SELECT call_id FROM calls LIMIT 1"):
        sim.backfill(demo, int(os.environ.get("DEMO_SEED_COUNT", "45")), minutes=12)
        # Show the scenario's night-time clock instead of the server's (UTC on most hosts).
        import time as _t
        from .scenarios import SCENARIOS
        sim.STATE.update({"scenario": demo, "running": False, "started_at": _t.time(),
                          "clock_start": SCENARIOS[demo]["clock"] + 12 * 60, "inserted": 0, "total": 0})
    task = asyncio.create_task(_engine_loop())
    yield
    task.cancel()
    sim.stop()


app = FastAPI(title="Night Ledger", lifespan=lifespan)
app.include_router(api.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
