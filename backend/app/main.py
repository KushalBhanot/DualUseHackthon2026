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
