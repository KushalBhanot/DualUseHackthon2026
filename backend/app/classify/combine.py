"""Merge rules, Jev and the stored state into one result. The higher lane always wins."""

from ..settings import JEV_MIN_CONFIDENCE
from .labels import higher_lane, lane_rank

JEV_RED_FLAG_MIN = 0.8
JEV_CONFUSED_MIN = 0.7


def combine(rules: dict, jev: dict | None, current_lane: str | None = None, analysis_lane: str | None = None) -> dict:
    jev = jev or {}
    jev_ok = jev.get("lane") is not None and (jev.get("confidence") or 0) >= JEV_MIN_CONFIDENCE

    red_flags = list(rules.get("red_flags") or [])
    jev_red = (jev.get("red_flag_present") or 0) >= JEV_RED_FLAG_MIN
    if jev_red and jev.get("red_flag") and jev["red_flag"] not in red_flags:
        red_flags.append(jev["red_flag"])
    rules_miss = jev_red and not rules.get("red_flags")

    reason = rules.get("reason") or (jev.get("reason") if jev_ok else None)
    confused = (jev.get("caller_confused") or 0) >= JEV_CONFUSED_MIN
    if confused and not reason:
        reason = "confused_or_unclear"

    lane = higher_lane(
        current_lane,
        analysis_lane,
        rules.get("lane"),
        jev.get("lane") if jev_ok else None,
        "red" if jev_red else None,
        "amber" if confused else None,
    )

    needs_review = False
    if jev:
        if jev.get("lane") is not None and not jev_ok:
            needs_review = True
        if rules.get("lane") and jev.get("lane") and abs(lane_rank(rules["lane"]) - lane_rank(jev["lane"])) > 1:
            needs_review = True

    use_jev_cluster = jev.get("cluster") and (jev.get("cluster_confidence") or 0) >= 0.5
    return {
        "lane": lane,
        "red_flags": red_flags,
        "reason": reason,
        "cluster": jev["cluster"] if use_jev_cluster else rules.get("cluster"),
        "urgency": jev.get("urgency"),
        "needs_review": needs_review,
        "rules_miss": rules_miss,
    }
