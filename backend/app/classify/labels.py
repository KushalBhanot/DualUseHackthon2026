"""Label sets shared by rules, Jev and the seed. Keep in sync with retell/ladder.mjs."""

LANES = ["green", "amber", "red"]

RED_FLAGS = [
    "chest_pain", "breathing", "bleeding", "stroke", "unresponsive", "seizure",
    "self_harm_or_violence", "overdose_poisoning", "severe_allergy",
    "pregnancy_bleeding_or_pain", "infant_fever", "caller_in_danger",
]

PERSON_SOON_REASONS = [
    "asked_for_person", "confused_or_unclear", "family_locating", "mental_health",
    "child_under_2", "hospice", "recent_discharge", "vulnerable_caller",
    "repeat_caller", "info_did_not_help_and_vulnerable",
]

CLUSTERS = [
    "outage", "family", "help", "media", "scheduling", "billing", "medication",
    "mental_health", "child", "injury_or_illness", "other",
]

# Retell LLM state -> lane, for node_transition items in the live transcript.
STATE_LANE = {
    "handoff_now": "red",
    "person_soon": "amber",
    "callback_routine": "green",
    "info_status": "green",
}


def lane_rank(lane: str | None) -> int:
    return LANES.index(lane) + 1 if lane in LANES else 0


def higher_lane(*lanes: str | None) -> str | None:
    best = max(lanes, key=lane_rank, default=None)
    return best if lane_rank(best) else None
