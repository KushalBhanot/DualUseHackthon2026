from app.classify.combine import combine

NO_RULES = {"lane": None, "red_flags": [], "reason": None, "cluster": None}


def jev(**kw):
    return {"lane": "green", "confidence": 0.9, "red_flag_present": 0.05, "caller_confused": 0.05} | kw


def test_higher_lane_wins():
    assert combine({**NO_RULES, "lane": "red", "red_flags": ["chest_pain"]}, jev(lane="green"))["lane"] == "red"
    assert combine(NO_RULES, jev(lane="amber"))["lane"] == "amber"


def test_lane_never_goes_down():
    assert combine(NO_RULES, jev(lane="green"), current_lane="red")["lane"] == "red"


def test_low_confidence_jev_is_ignored_and_flagged():
    out = combine(NO_RULES, jev(lane="red", confidence=0.4))
    assert out["lane"] is None and out["needs_review"]


def test_jev_catches_what_rules_miss():
    out = combine(NO_RULES, jev(red_flag_present=0.92, red_flag="unresponsive"))
    assert out["lane"] == "red" and out["red_flags"] == ["unresponsive"] and out["rules_miss"]


def test_confused_caller_goes_amber():
    out = combine(NO_RULES, jev(caller_confused=0.8))
    assert out["lane"] == "amber" and out["reason"] == "confused_or_unclear"


def test_rules_only_without_jev():
    out = combine({**NO_RULES, "lane": "amber", "reason": "family_locating"}, None)
    assert out["lane"] == "amber" and not out["needs_review"]
