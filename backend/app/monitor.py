"""One task per live call: read Retell's Monitor Call WebSocket, store the transcript, classify,
and steer the agent to handoff_now when a red flag shows up.

wss://api.retellai.com/v2/monitor-call/{call_id} sends transcript_snapshot once, then
transcript_updated for every change (a growing turn is re-sent under the same id), then call_ended.
"""

import asyncio
import json
import logging

from retell import AsyncRetell
from websockets.asyncio.client import connect

from . import db, handoff
from .classify.labels import STATE_LANE
from .classify.service import classify_and_store
from .settings import RETELL_API_KEY

log = logging.getLogger(__name__)
MONITOR_URL = "wss://api.retellai.com/v2/monitor-call/{call_id}"
_tasks: dict[str, asyncio.Task] = {}
_retell: AsyncRetell | None = None


def retell() -> AsyncRetell:
    global _retell
    if _retell is None:
        _retell = AsyncRetell(api_key=RETELL_API_KEY)
    return _retell


def start(call_id: str) -> None:
    if call_id not in _tasks or _tasks[call_id].done():
        _tasks[call_id] = asyncio.create_task(LiveCall(call_id).run())


class LiveCall:
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.state = "ask"              # Retell LLM state, from transition_to_* tool calls
        self.last_role = None           # to spot a finished caller turn
        self.transfer_tool_ids: set[str] = set()
        self.steered: set[str] = set()  # red flags we already steered on
        self.jev_running = False

    async def run(self) -> None:
        for attempt in range(2):  # reconnect once; the snapshot resends everything
            try:
                async with connect(MONITOR_URL.format(call_id=self.call_id),
                                   additional_headers={"Authorization": f"Bearer {RETELL_API_KEY}"}) as ws:
                    await db.log_event(self.call_id, "monitor_connected", {"attempt": attempt})
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "call_ended":
                            return
                        for item in msg.get("transcripts") or []:
                            await self.on_item(item)
                return
            except Exception as e:  # noqa: BLE001 - keep the call alive, log and retry once
                log.warning("monitor %s: %s", self.call_id, e)
                await db.log_event(self.call_id, "monitor_error", {"error": str(e)[:300], "attempt": attempt})
                await asyncio.sleep(1)

    async def on_item(self, item: dict) -> None:
        role = item.get("role")
        content = item.get("content")
        if not isinstance(content, str):
            content = json.dumps({k: v for k, v in item.items() if k not in ("id", "role", "time_sec")})
        await db.execute(
            """INSERT INTO transcript_items (call_id, item_id, role, content, time_sec) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (call_id, item_id) DO UPDATE SET content = EXCLUDED.content, updated_at = now()""",
            self.call_id, str(item.get("id")), role, content, item.get("time_sec"),
        )

        if role == "user":
            # Rules on every update: instant, so a red flag mid-sentence is caught right away.
            out = await classify_and_store(self.call_id, "live", use_jev=False)
            await self.steer(out.get("new_red_flags") or [])
        elif role == "agent" and self.last_role == "user":
            # The caller's turn just finished: ask Jev about the conversation so far.
            if not self.jev_running:
                asyncio.create_task(self.jev_check())
        elif role == "tool_call_invocation":
            await self.on_tool_call(item)
        elif role == "tool_call_result" and item.get("tool_call_id") in self.transfer_tool_ids:
            await handoff.transfer_result(self.call_id, item)
        elif role == "node_transition":
            await self.on_state(item.get("new_node_name") or item.get("node_name") or "")
        if role in ("user", "agent"):
            self.last_role = role

    async def on_tool_call(self, item: dict) -> None:
        name = item.get("name") or ""
        if name.startswith("transition_to_"):
            await self.on_state(name.removeprefix("transition_to_"))
        elif name == "transfer_to_nurse":
            self.transfer_tool_ids.add(item.get("tool_call_id") or item.get("id"))
            await handoff.transfer_started(self.call_id)

    async def on_state(self, state: str) -> None:
        if state not in STATE_LANE:
            return
        self.state = state
        await db.raise_lane(self.call_id, STATE_LANE[state], f"agent moved to {state}")
        if state == "handoff_now":
            await db.execute("UPDATE calls SET red_flag_at = coalesce(red_flag_at, now()) WHERE call_id = %s", self.call_id)

    async def jev_check(self) -> None:
        self.jev_running = True
        try:
            out = await classify_and_store(self.call_id, "live", use_jev=True)
            await self.steer(out.get("new_red_flags") or [])
        finally:
            self.jev_running = False

    async def steer(self, flags: list[str]) -> None:
        flags = [f for f in flags if f not in self.steered]
        if not flags:
            return
        self.steered |= set(flags)
        await db.log_event(self.call_id, "red_flag_detected", {"flags": flags, "agent_state": self.state})
        if self.state == "handoff_now" or self.transfer_tool_ids:
            return  # already on the way to a nurse
        context = f"Safety system: the caller mentioned {', '.join(f.replace('_', ' ') for f in flags)}. Transition to handoff_now now."
        try:
            await retell().call.update_live(
                self.call_id, call_control={"additional_context": context, "trigger_response": True},
            )
            await db.log_event(self.call_id, "context_injected", {"flags": flags, "context": context})
        except Exception as e:  # noqa: BLE001
            await db.log_event(self.call_id, "context_inject_failed", {"flags": flags, "error": str(e)[:300]})
