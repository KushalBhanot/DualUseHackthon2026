"""TypeSafe Jev client. Jev returns typed answers with probabilities, never text.

API: POST https://api.typesafe.ai/v1/systemone  {state, model, questions} -> {model, answers, usage}
Question types: noul (yes/no probability), choice (pick one option), score (ordered levels).
Without TYPESAFE_API_KEY every call returns None and the backend runs on rules alone.
"""

import logging
import time

import httpx

from ..settings import JEV_MODEL, TYPESAFE_API_KEY
from .labels import CLUSTERS, PERSON_SOON_REASONS, RED_FLAGS

log = logging.getLogger(__name__)
URL = "https://api.typesafe.ai/v1/systemone"
_client: httpx.AsyncClient | None = None


def enabled() -> bool:
    return bool(TYPESAFE_API_KEY)


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=5.0, headers={"Authorization": f"Bearer {TYPESAFE_API_KEY}"})
    return _client


async def ask(state, questions: dict) -> dict | None:
    """Send one Jev request. Returns {"answers": {...}, "model": ..., "latency_ms": ...} or None."""
    if not enabled():
        return None
    t0 = time.monotonic()
    try:
        r = await _http().post(URL, json={"state": state, "model": JEV_MODEL, "questions": questions})
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("jev request failed: %s", e)
        return None
    return {"answers": body.get("answers", {}), "model": body.get("model"), "latency_ms": int((time.monotonic() - t0) * 1000)}


def _choice(instructions: str, options: dict[str, str | None]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


CALL_QUESTIONS = {
    "lane": _choice(
        "How urgently does this hospital caller need a person?",
        {
            "red": "Someone may be in immediate danger: a red-flag symptom or safety risk. Needs a nurse now.",
            "amber": "Needs a staff callback soon: family looking for someone, distress, a child under 2, recent discharge, confused, or asked for a person.",
            "green": "Routine: status questions, scheduling, billing, refills, offers of help, media.",
        },
    ),
    "red_flag": _choice(
        "Which red-flag emergency, if any, does the caller describe for anyone?",
        {flag: None for flag in RED_FLAGS} | {"none": "No red-flag emergency described."},
    ),
    "red_flag_present": {
        "type": "noul",
        "instructions": "Does the caller describe a possible medical emergency or safety risk for anyone, even in vague words?",
    },
    "person_soon_reason": _choice(
        "Why might this caller need a human callback soon?",
        {r: None for r in PERSON_SOON_REASONS} | {"none": "No reason for a priority callback."},
    ),
    "cluster": _choice("What is the call mainly about?", {c: None for c in CLUSTERS}),
    "caller_confused": {"type": "noul", "instructions": "Does the caller sound confused, disoriented, impaired, or very hard to understand?"},
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this call?",
        "criteria": ["Routine, can wait days", "Can wait until morning", "Needs a callback within hours",
                     "Needs a callback within 30 minutes", "Needs a person right now"],
    },
}


async def classify_call(transcript: str) -> dict | None:
    """Ask the call questions about a transcript. Returns a flat result dict, or None."""
    res = await ask(transcript, CALL_QUESTIONS)
    if not res:
        return None
    a = res["answers"]

    def choice(key):
        x = a.get(key) or {}
        return x.get("choice"), x.get("confidence"), x.get("probabilities")

    lane, lane_conf, lane_probs = choice("lane")
    red_flag, _, _ = choice("red_flag")
    reason, _, _ = choice("person_soon_reason")
    cluster, cluster_conf, _ = choice("cluster")
    return {
        "lane": lane,
        "confidence": lane_conf,
        "lane_probabilities": lane_probs,
        "red_flag": None if red_flag == "none" else red_flag,
        "red_flag_present": (a.get("red_flag_present") or {}).get("noul"),
        "reason": None if reason == "none" else reason,
        "cluster": cluster,
        "cluster_confidence": cluster_conf,
        "caller_confused": (a.get("caller_confused") or {}).get("noul"),
        "urgency": (a.get("urgency") or {}).get("score"),  # probability-weighted level, for ranking only
        "model": res["model"],
        "latency_ms": res["latency_ms"],
    }


async def pick(text: str, instructions: str, options: list[str]) -> tuple[str | None, float | None]:
    """Choose one of `options` (plus 'other') for a short piece of caller speech."""
    res = await ask(text, {"pick": _choice(instructions, {o: None for o in options} | {"other": "None of these."})})
    if not res:
        return None, None
    x = res["answers"].get("pick") or {}
    return (None if x.get("choice") == "other" else x.get("choice")), x.get("confidence")


async def yes_no(state, instructions: str) -> float | None:
    """Probability (0-1) that the answer to `instructions` is yes."""
    res = await ask(state, {"q": {"type": "noul", "instructions": instructions}})
    return None if not res else (res["answers"].get("q") or {}).get("noul")
