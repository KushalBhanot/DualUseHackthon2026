"""Fixed keyword rules: instant, free and predictable. They run on every caller turn.

Red flags mirror RED_FLAGS in retell/ladder.mjs. Any red flag puts the call in the red lane.
"""
import re

RED_FLAGS = {
    "chest_pain": [r"\bchest\b[^.?!]{0,40}\b(pain|tight|pressure|hurt|squeez)", r"\b(pain|pressure|tightness) in (my|his|her|their) chest", r"heart attack"],
    "breathing": [r"can'?t (catch (my|his|her|their) )?breath", r"(trouble|hard|difficulty|problems?) breathing", r"not breathing", r"\bchok(e|ing)\b", r"wheez", r"short(ness)? of breath"],
    "bleeding": [r"bleed\w*[^.?!]{0,30}(won'?t|will not|doesn'?t|can'?t) stop", r"won'?t stop bleeding", r"blood everywhere", r"soak(ing|ed)? through", r"(heavy|a lot of) bleeding"],
    "stroke": [r"face (is )?droop", r"slurr", r"arm (is |went )?(weak|numb)", r"\bstroke\b"],
    "unresponsive": [r"unconscious", r"unresponsive", r"passed out", r"\bfaint(ed)?\b", r"won'?t wake", r"not waking", r"collapsed and"],
    "seizure": [r"seiz", r"convuls"],
    "self_harm_or_violence": [r"kill (my|him|her)?self", r"suicid", r"hurt (my)?self", r"end (it all|my life)", r"hurt (someone|somebody)"],
    "overdose_poisoning": [r"overdos", r"poison", r"(took|swallowed) (too many|a (bunch|bottle) of) (pills|tablets)"],
    "severe_allergy": [r"throat (is )?(swelling|closing)", r"anaphyla", r"(bad|severe) allergic reaction"],
    "pregnancy_bleeding_or_pain": [r"pregnan\w*[^.?!]{0,40}(bleed|severe pain|cramp)", r"(bleed|cramp)\w*[^.?!]{0,30}pregnan"],
    "infant_fever": [r"\b([1-9]|1[0-2])[- ]?(week|wk)s?[- ]old\b[^.?!]{0,40}fever", r"\b[12][- ]?months?[- ]old\b[^.?!]{0,40}fever", r"newborn[^.?!]{0,40}fever"],
    "caller_in_danger": [r"can'?t talk (now|freely)", r"(he|she|they)'?s (coming back|outside the door)", r"i'?m not safe", r"(threatening|hurting) me"],
}

PERSON_SOON = {
    "asked_for_person": [r"(real|actual) person", r"\bhuman\b", r"\boperator\b", r"put me through", r"talk to (a|the) nurse"],
    "child_under_2": [r"\b(baby|infant|newborn)\b", r"\b([1-9]|1[0-9]|2[0-3])[- ]month[- ]old\b"],
    "mental_health": [r"can'?t stop shaking", r"\bpanic", r"anxious", r"don'?t want to be alone", r"scared to (be|stay) (home|alone)"],
    "family_locating": [r"(looking for|find|where is|is) my (brother|sister|mother|mom|father|dad|son|daughter|wife|husband|grand\w+|partner|aunt|uncle)", r"(was|been|got) brought in", r"is (he|she) (there|here)"],
    "hospice": [r"hospice", r"end of life"],
    "recent_discharge": [r"discharged (yesterday|today|last week|this week|\w+ days ago)", r"(just|recently) (got )?discharged"],
}

CLUSTERS = {
    "outage": [r"\bpower\b", r"outage", r"\bopen\b", r"backup", r"generator", r"portal", r"mychart", r"lights? (are|went) out"],
    "family": [r"(brother|sister|mother|mom|father|dad|son|daughter|wife|husband|grandma|grandpa)", r"brought in"],
    "help": [r"donat", r"\bblood donors?\b", r"volunteer", r"off[- ]duty", r"should i come in", r"help out"],
    "media": [r"\bnews\b", r"reporter", r"channel \d", r"statement", r"press"],
    "scheduling": [r"appointment", r"reschedul", r"\bschedule", r"\bmri\b", r"visit (on|this)"],
    "billing": [r"\bbill", r"insurance", r"\bowe\b", r"statement says"],
    "medication": [r"refill", r"medication", r"\bdose\b", r"prescription", r"blood thinner", r"\bpills?\b"],
    "mental_health": [r"anxious", r"panic", r"can'?t stop shaking", r"alone"],
    "child": [r"\bbaby\b", r"month[- ]old", r"\bkid\b", r"toddler"],
    "injury_or_illness": [r"\bcut\b", r"broke", r"hurt", r"fell", r"bleed", r"breath", r"chest", r"wound"],
}

REASON_WEIGHT = {
    "child_under_2": 5, "confused_or_unclear": 4, "mental_health": 4, "family_locating": 3,
    "recent_discharge": 3, "hospice": 3, "vulnerable_caller": 3, "repeat_caller": 3, "asked_for_person": 2,
}

_compiled = {name: {k: [re.compile(p, re.I) for p in pats] for k, pats in table.items()}
             for name, table in (("red", RED_FLAGS), ("soon", PERSON_SOON), ("cluster", CLUSTERS))}


def _hits(table, text):
    return [k for k, pats in _compiled[table].items() if any(p.search(text) for p in pats)]


def classify(caller_text: str, transcription_confidence: float | None = None) -> dict:
    """Classify everything the caller has said so far. Returns lane, red flags, reason and cluster."""
    text = caller_text or ""
    flags = _hits("red", text)
    soon = _hits("soon", text)
    clusters = _hits("cluster", text)
    if transcription_confidence is not None and transcription_confidence < 0.5:
        soon.append("confused_or_unclear")
    if flags:
        lane = "red"
    elif soon:
        lane = "amber"
    elif text.strip():
        lane = "green"
    else:
        lane = None
    reason = max(soon, key=lambda r: REASON_WEIGHT.get(r, 0)) if soon else None
    cluster = "injury_or_illness" if flags else (clusters[0] if clusters else "other")
    if reason == "family_locating":
        cluster = "family"
    elif reason == "child_under_2" and not flags:
        cluster = "child"
    elif reason == "mental_health" and not flags:
        cluster = "mental_health"
    return {"lane": lane, "red_flags": flags, "person_soon": soon, "reason": reason, "cluster": cluster}
