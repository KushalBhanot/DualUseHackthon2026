"""Optional TypeSafe Jev classifier (backend_plan.md). Runs only when TYPESAFE_API_KEY is set.

Any failure returns None so the call falls back to the rules, which already set the minimum lane.
"""
import os

import httpx

from .rules import RED_FLAGS, PERSON_SOON, CLUSTERS

URL = "https://api.typesafe.ai/v1/systemone"


def enabled() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


def _questions():
    return {
        "lane": {"type": "choice", "choices": {
            "red": "A red flag: someone may be in danger right now and needs a nurse immediately.",
            "amber": "Needs a human callback soon: family locating, child under 2, mental health, confused, recent discharge, asked for a person.",
            "green": "Routine or status question that can wait or be answered by a status message.",
        }},
        "red_flag": {"type": "choice", "choices": {k: k.replace("_", " ") for k in [*RED_FLAGS, "none"]}},
        "red_flag_present": {"type": "noul", "question": "Does the caller describe any medical emergency or danger, even indirectly?"},
        "person_soon_reason": {"type": "choice", "choices": {k: k.replace("_", " ") for k in [*PERSON_SOON, "none"]}},
        "cluster": {"type": "choice", "choices": {k: k.replace("_", " ") for k in [*CLUSTERS, "other"]}},
        "urgency": {"type": "score", "min": 1, "max": 5},
    }


def classify(transcript_text: str, timeout: float = 4.0) -> dict | None:
    if not enabled() or not transcript_text.strip():
        return None
    body = {"model": os.environ.get("JEV_MODEL", "jev-1.13.0"), "state": transcript_text, "questions": _questions()}
    try:
        r = httpx.post(URL, json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}"})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    answers = data.get("answers", data)
    lane = answers.get("lane", {})
    return {
        "source": "jev",
        "lane": lane.get("answer") if isinstance(lane, dict) else lane,
        "confidence": (lane.get("probability") if isinstance(lane, dict) else None) or 0.0,
        "red_flag_present": (answers.get("red_flag_present") or {}).get("probability", 0.0),
        "red_flag": (answers.get("red_flag") or {}).get("answer"),
        "cluster": (answers.get("cluster") or {}).get("answer"),
        "urgency": (answers.get("urgency") or {}).get("answer"),
    }
