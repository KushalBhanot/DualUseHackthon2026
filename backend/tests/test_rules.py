from app.classify.rules import classify
from app.classify.combine import combine


def test_chest_pain_is_red():
    r = classify("I was calling to ask if you're open... my dad's chest feels tight and he's sweaty.")
    assert r["lane"] == "red" and "chest_pain" in r["red_flags"]


def test_parking_is_green_with_no_flags():
    r = classify("Where do I park tonight?")
    assert r["lane"] == "green" and r["red_flags"] == []


def test_breathing_and_bleeding():
    assert "breathing" in classify("He can't catch his breath, there's smoke")["red_flags"]
    assert "bleeding" in classify("it's bleeding and it won't stop")["red_flags"]
    assert "bleeding" in classify("My incision is soaking through the bandage.")["red_flags"]


def test_fainted_is_unresponsive():
    assert "unresponsive" in classify("my wife just fainted")["red_flags"]


def test_person_soon_reasons():
    assert classify("I'm looking for my brother, is he there?")["reason"] == "family_locating"
    assert classify("My 14-month-old baby keeps coughing")["reason"] == "child_under_2"
    assert classify("Just put me through to a real person please")["reason"] == "asked_for_person"
    assert classify("I was discharged yesterday with a new blood thinner")["reason"] == "recent_discharge"


def test_toddler_cough_is_not_infant_fever():
    r = classify("My 14-month-old baby keeps coughing, there was dust everywhere.")
    assert r["lane"] == "amber" and "infant_fever" not in r["red_flags"]


def test_low_transcription_confidence_goes_to_person():
    r = classify("...mi mamá... el oxígeno no...", transcription_confidence=0.31)
    assert r["lane"] == "amber" and r["reason"] == "confused_or_unclear"


def test_higher_lane_wins_and_never_drops():
    rules = classify("my dad says his chest feels tight")
    out = combine(rules, {"lane": "green", "confidence": 0.9})
    assert out["lane"] == "red" and out["model_under_triage"]
    # A stored red lane never goes down, even if both classifiers say green
    assert combine({"lane": "green"}, {"lane": "green", "confidence": 0.99}, stored_lane="red")["lane"] == "red"


def test_model_red_flag_rules_missed():
    out = combine({"lane": "green", "red_flags": []}, {"lane": "green", "confidence": 0.7, "red_flag_present": 0.86})
    assert out["lane"] == "red" and out["rules_miss"]


def test_low_confidence_model_is_ignored_but_flagged():
    out = combine({"lane": "green"}, {"lane": "red", "confidence": 0.3})
    assert out["lane"] == "green" and out["needs_review"]
