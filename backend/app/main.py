"""Night Ledger backend: FastAPI app."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from . import api, db, inbound, webhooks
from .details import tools
from .settings import SUPERVISOR_ENGINE
from .supervisor import engine
from .supervisor import routes as supervisor_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_db()
    loop = asyncio.create_task(engine.run_forever()) if SUPERVISOR_ENGINE else None
    yield
    if loop:
        loop.cancel()
        with suppress(asyncio.CancelledError):
            await loop
    await db.close_db()


app = FastAPI(title="Night Ledger backend", lifespan=lifespan)
app.include_router(webhooks.router)
app.include_router(inbound.router)
app.include_router(tools.router)
app.include_router(supervisor_routes.router)
app.include_router(api.router)


@app.get("/health")
async def health():
    await db.fetchrow("SELECT 1")
    return {"ok": True}
