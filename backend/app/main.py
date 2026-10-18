"""Night Ledger backend: FastAPI app."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import api, db, inbound, sim, webhooks
from .details import tools
from .settings import SUPERVISOR_ENGINE
from .supervisor import engine
from .supervisor import routes as supervisor_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_db()
    loop = asyncio.create_task(engine.run_forever()) if SUPERVISOR_ENGINE else None
    # Public demo: a fresh instance starts with a recent surge already on the board.
    demo = os.getenv("DEMO_SEED")
    if demo and not await db.fetchrow("SELECT 1 FROM calls LIMIT 1"):
        await sim.start(sim.Start(scenario=demo, mode="instant", seed=7))
    yield
    await sim.stop()
    if loop:
        loop.cancel()
        with suppress(asyncio.CancelledError):
            await loop
    await db.close_db()


app = FastAPI(title="Night Ledger backend", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)  # the board is polled every few seconds
app.include_router(webhooks.router)
app.include_router(inbound.router)
app.include_router(tools.router)
app.include_router(supervisor_routes.router)
app.include_router(api.router)
app.include_router(sim.router)


@app.get("/health")
async def health():
    await db.fetchrow("SELECT 1")
    return {"ok": True}


# The built Next.js board (frontend/, `STATIC_EXPORT=1 next build`), served on the same origin as /api.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
