"""Night Ledger backend: FastAPI app."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from . import api, db, inbound, sim, webhooks
from .details import tools
from .settings import SUPERVISOR_ENGINE
from .supervisor import engine
from .supervisor import routes as supervisor_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_db()
    loop = asyncio.create_task(engine.run_forever()) if SUPERVISOR_ENGINE else None
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
