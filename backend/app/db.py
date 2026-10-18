"""Postgres access: one async pool, plain SQL, rows as dicts."""

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import JsonbDumper
from psycopg_pool import AsyncConnectionPool

from .settings import BACKEND_DIR, DATABASE_URL

# Python dicts go in as jsonb; lists stay Postgres arrays (red_flags text[]).
psycopg.adapters.register_dumper(dict, JsonbDumper)

pool: AsyncConnectionPool = None  # type: ignore[assignment]  # created by open_db() in the running loop


async def open_db() -> None:
    global pool
    pool = AsyncConnectionPool(
        DATABASE_URL, open=False, min_size=1, max_size=10,
        kwargs={"row_factory": dict_row, "autocommit": True},
    )
    await pool.open(wait=True)
    async with pool.connection() as conn:
        await conn.execute((BACKEND_DIR / "schema.sql").read_text())


async def close_db() -> None:
    await pool.close()


async def fetch(sql: str, *args: Any) -> list[dict]:
    async with pool.connection() as conn:
        return await (await conn.execute(sql, args)).fetchall()


async def fetchrow(sql: str, *args: Any) -> dict | None:
    async with pool.connection() as conn:
        return await (await conn.execute(sql, args)).fetchone()


async def execute(sql: str, *args: Any) -> None:
    async with pool.connection() as conn:
        await conn.execute(sql, args)


async def log_event(call_id: str | None, type_: str, payload: dict | None = None, actor: str = "system") -> None:
    await execute(
        "INSERT INTO events (call_id, actor, type, payload) VALUES (%s, %s, %s, %s)",
        call_id, actor, type_, payload or {},
    )


async def raise_lane(call_id: str, lane: str | None, why: str) -> None:
    """Raise a call's lane (never lowers it) and log when it actually changed."""
    if not lane:
        return
    row = await fetchrow(
        """UPDATE calls c SET lane = lane_max(c.lane, %s)
           FROM (SELECT lane AS old FROM calls WHERE call_id = %s) prev
           WHERE c.call_id = %s RETURNING prev.old, c.lane""",
        lane, call_id, call_id,
    )
    if row and row["old"] != row["lane"]:
        await log_event(call_id, "lane_raised", {"from": row["old"], "to": row["lane"], "why": why})
