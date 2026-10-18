import pytest

from app.classify.rules import classify, find_red_flags


@pytest.mark.parametrize("text, flag", [
    ("actually my dad says his chest feels tight and he's sweaty", "chest_pain"),
    ("He can't catch his breath, there's smoke", "breathing"),
    ("There's blood everywhere, it won't stop", "bleeding"),
    ("oh no, my wife just fainted", "unresponsive"),
    ("her face is drooping and she's slurring", "stroke"),
    ("I think he took too many of his pills", "overdose_poisoning"),
    ("I've been thinking about killing myself", "self_harm_or_violence"),
    ("my 6 week old has a fever of 101", "infant_fever"),
    ("I'm pregnant and there's bleeding", "pregnancy_bleeding_or_pain"),
])
def test_red_flags_fire(text, flag):
    assert flag in find_red_flags(text)


@pytest.mark.parametrize("text", [
    "No, nobody has chest pain or trouble breathing.",
    "no one's bleeding",
    "Is the emergency room still open with the power out?",
    "where do I park",
    "I need to move my Thursday appointment",
])
def test_no_false_alarm(text):
    assert find_red_flags(text) == []


def test_negation_is_per_clause():
    # "No" answers the safety question; the next sentence is a real red flag.
    assert find_red_flags("No. But my chest feels really tight.") == ["chest_pain"]


def test_lanes():
    assert classify("Just put me through to a real person please")["lane"] == "amber"
    assert classify("Just put me through to a real person please")["reason"] == "asked_for_person"
    assert classify("Looking for my brother, the building on Alder came down")["reason"] == "family_locating"
    assert classify("Is the ER open with the power out?") == {"lane": None, "red_flags": [], "reason": None, "cluster": "outage"}
    assert classify("My MRI is at 8 tomorrow")["cluster"] == "scheduling"


def test_exclamation_is_not_negation():
    assert find_red_flags("oh no, my wife just fainted") == ["unresponsive"]
    assert find_red_flags("No, nothing like that.") == []
