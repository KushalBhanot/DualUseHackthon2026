"""Combine classifier outputs. The higher lane always wins, and nothing here lowers a lane."""
import os

LANE_RANK = {None: -1, "green": 0, "amber": 1, "red": 2}
JEV_MIN_CONFIDENCE = float(os.environ.get("JEV_MIN_CONFIDENCE", "0.6"))


def highest(*lanes):
    return max(lanes, key=lambda l: LANE_RANK.get(l, -1))


def combine(rules: dict | None, model: dict | None, retell_lane: str | None = None, stored_lane: str | None = None) -> dict:
    """rules: output of rules.classify. model: {'lane','confidence','red_flag_present'} from Jev or the agent.

    Returns the final lane plus review flags. A low-confidence model result is ignored for the lane
    but still marks the call for review.
    """
    rules = rules or {}
    model = model or {}
    model_lane = model.get("lane") if model.get("confidence", 0) >= JEV_MIN_CONFIDENCE else None
    rules_miss = bool(model.get("red_flag_present", 0) >= 0.8 and not rules.get("red_flags"))
    lanes = [rules.get("lane"), model_lane, retell_lane, stored_lane]
    if rules_miss:
        lanes.append("red")
    final = highest(*lanes)
    rr, mr = LANE_RANK.get(rules.get("lane"), -1), LANE_RANK.get(model.get("lane"), -1)
    model_under_triage = rr > mr >= 0
    needs_review = bool(
        (model and model.get("confidence", 1) < JEV_MIN_CONFIDENCE)
        or (rr >= 0 and mr >= 0 and abs(rr - mr) > 1)
    )
    return {
        "lane": final,
        "rules_miss": rules_miss,
        "model_under_triage": model_under_triage,
        "needs_review": needs_review,
    }
