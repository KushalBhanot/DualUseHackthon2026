"""Rule-based classification of caller speech. Instant, free and predictable.

Rules only ever *raise* urgency: they return red or amber when they find a signal,
and no lane otherwise. Green comes from the agent's own routing or from Jev.
"""

import re

# A match is ignored when one of these comes earlier in the same clause, so the
# usual answer to the safety question ("no, nobody has chest pain") doesn't fire.
# Clauses split at commas too, so "oh no, my wife just fainted" still fires.
NEGATION = re.compile(r"\b(no|not|nobody|no one|none|nothing|never|without|isn't|aren't|doesn't|don't|didn't|wasn't|haven't|hasn't)\b|n't\b")
CLAUSE_SPLIT = re.compile(r"[.,;!?\n]|\bbut\b|\band then\b")


def _rx(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


RED_FLAG_RULES: dict[str, list[re.Pattern]] = {
    "chest_pain": _rx(
        r"\bchest\b.{0,30}\b(pain|pressure|tight|tightness|hurts?|heavy|heaviness|crushing|squeez)",
        r"\b(pain|pressure|tightness)\b.{0,15}\bchest\b",
        r"\bheart attack\b",
    ),
    "breathing": _rx(
        r"\b(can'?t|cannot|can not|couldn'?t|trouble|hard to|struggling to|difficulty)\s+(breathe|breathing|catch (his|her|my|their|a) breath)",
        r"\bshort(ness)? of breath\b", r"\bnot breathing\b", r"\bwheez", r"\bchok(e|ing)\b",
        r"\bgasping\b", r"\bturning (blue|gray|grey)\b",
    ),
    "bleeding": _rx(
        r"\bbleeding\b.{0,20}\b(won'?t|will not|doesn'?t|isn'?t going to)\s+stop",
        r"\bwon'?t stop bleeding\b", r"\bblood everywhere\b",
        r"\bbleeding\s+(a lot|heavily|badly|really bad)", r"\bsoak(ing|ed)? through\b",
    ),
    "stroke": _rx(
        r"\bstroke\b", r"\bface\b.{0,15}\bdroop", r"\bslurr", r"\barm\b.{0,15}\b(weak|numb|limp)",
        r"\bcan'?t (lift|move) (his|her|my|their) arm\b",
    ),
    "unresponsive": _rx(
        r"\bunconscious\b", r"\bunresponsive\b", r"\bpassed out\b", r"\bfaint(ed|ing)?\b",
        r"\bwon'?t wake\b", r"\bnot waking\b", r"\bcollapsed\b", r"\bnot responding\b",
    ),
    "seizure": _rx(r"\bseizure", r"\bconvuls"),
    "self_harm_or_violence": _rx(
        r"\bkill(ing)? (myself|himself|herself|themselves|someone|somebody)\b", r"\bsuicid",
        r"\bhurt(ing)? (myself|himself|herself|themselves|someone|somebody)\b", r"\bend (it all|my life)\b",
        r"\bself[- ]harm", r"\bdon'?t want to (live|be alive)\b",
    ),
    "overdose_poisoning": _rx(r"\boverdos", r"\btook too many\b", r"\bpoison", r"\bswallowed\b.{0,20}\b(pills|bleach|chemical)"),
    "severe_allergy": _rx(r"\ballergic reaction\b", r"\bthroat\b.{0,15}\b(swell|closing|tight)", r"\banaphyla", r"\bepi-?pen\b"),
    "pregnancy_bleeding_or_pain": _rx(r"\bpregnant\b.{0,40}\b(bleed|pain|cramp)", r"\b(bleed|pain|cramp)\w*\b.{0,40}\bpregnan"),
    "infant_fever": _rx(
        r"\b(newborn|infant|\d+[- ]weeks?[- ]old|[0-2][- ]months?[- ]old)\b.{0,40}\bfever",
        r"\bfever\b.{0,40}\b(newborn|infant|\d+[- ]weeks?[- ]old|[0-2][- ]months?[- ]old)\b",
    ),
    "caller_in_danger": _rx(
        r"\b(i'?m|we'?re|i am|we are) in danger\b", r"\bcan'?t talk (freely|right now)\b",
        r"\b(has|got) a (gun|knife)\b", r"\bbeing attacked\b", r"\b(is|are) (hurting|attacking) (me|us)\b",
        r"\btrapped\b",
    ),
}

PERSON_SOON_RULES: dict[str, list[re.Pattern]] = {
    "asked_for_person": _rx(
        r"\b(real|actual|live) (person|human)\b",
        r"\b(speak|talk) (to|with) (a |an |the )?(person|human|nurse|someone|somebody|operator|doctor)\b",
        r"\boperator\b", r"\bput me through\b",
    ),
    "family_locating": _rx(
        r"\blooking for (my|our)\b", r"\b(is|was) (he|she|my \w+) (there|brought in|at the hospital)\b",
        r"\bbrought in\b", r"\bcan'?t (find|reach) (my|him|her)\b", r"\bnot answering (her|his) phone\b",
    ),
    "child_under_2": _rx(
        r"\b(\d{1,2}|one|two|three|six|nine|eleven)[- ]months?[- ]old\b", r"\bmy baby\b", r"\bnewborn\b",
        r"\binfant\b", r"\btoddler\b",
    ),
    "recent_discharge": _rx(r"\bdischarged\b", r"\bjust got (out|home) (of|from) the hospital\b", r"\bsent home (yesterday|today|last week)\b"),
    "hospice": _rx(r"\bhospice\b", r"\bend of life\b", r"\bpalliative\b"),
    "mental_health": _rx(
        r"\bpanic", r"\banxi(ety|ous)\b", r"\bcan'?t stop (shaking|crying)\b", r"\b(scared|afraid) to be alone\b",
        r"\bdon'?t want to be alone\b", r"\bdepress",
    ),
    "repeat_caller": _rx(r"\bcalled (before|earlier|already|twice)\b", r"\bno one called (me )?back\b"),
}

CLUSTER_RULES: dict[str, list[re.Pattern]] = {
    "family": PERSON_SOON_RULES["family_locating"],
    "outage": _rx(r"\bpower\b", r"\boutage\b", r"\bbackup\b", r"\bgenerator\b", r"\belectricity\b", r"\b(er|emergency room)\b.{0,20}\bopen\b", r"\bare you open\b", r"\bportal\b", r"\bmychart\b"),
    "help": _rx(r"\bdonat", r"\bgive blood\b", r"\bvolunteer", r"\boff[- ]duty\b", r"\bcome in to help\b", r"\bshould i come in\b"),
    "media": _rx(r"\breporter\b", r"\bnews\b", r"\bchannel \d+\b", r"\bstatement\b", r"\bpress\b"),
    "scheduling": _rx(r"\bappointment\b", r"\breschedul", r"\bmri\b", r"\bvisiting hours\b", r"\bmove my\b"),
    "billing": _rx(r"\bbill(ing|ed)?\b", r"\binsurance\b.{0,20}\bcover", r"\bcharge[ds]?\b", r"\bpayment\b"),
    "medication": _rx(r"\brefill", r"\bprescription\b", r"\bmedication\b", r"\bpills?\b", r"\bdose\b"),
    "mental_health": PERSON_SOON_RULES["mental_health"],
    "child": PERSON_SOON_RULES["child_under_2"],
    "injury_or_illness": _rx(r"\bhurt\b", r"\binjur", r"\bcut\b", r"\bbroke(n)?\b", r"\bfell\b", r"\bpain\b", r"\bfever\b", r"\bcough"),
}


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in CLAUSE_SPLIT.split(text.lower()) if c.strip()]


def _hits(clause: str, patterns: list[re.Pattern]) -> bool:
    for p in patterns:
        m = p.search(clause)
        if m and not NEGATION.search(clause[: m.start()]):
            return True
    return False


def find_red_flags(text: str) -> list[str]:
    clauses = _clauses(text)
    return [flag for flag, pats in RED_FLAG_RULES.items() if any(_hits(c, pats) for c in clauses)]


def find_reason(text: str) -> str | None:
    clauses = _clauses(text)
    return next((r for r, pats in PERSON_SOON_RULES.items() if any(_hits(c, pats) for c in clauses)), None)


def find_cluster(text: str) -> str | None:
    clauses = _clauses(text)
    return next((k for k, pats in CLUSTER_RULES.items() if any(_hits(c, pats) for c in clauses)), None)


def classify(caller_text: str) -> dict:
    """Classify everything the caller has said so far."""
    red_flags = find_red_flags(caller_text)
    reason = find_reason(caller_text)
    return {
        "lane": "red" if red_flags else "amber" if reason else None,
        "red_flags": red_flags,
        "reason": reason,
        "cluster": find_cluster(caller_text),
    }
