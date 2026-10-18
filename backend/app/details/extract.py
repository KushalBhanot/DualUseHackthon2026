"""Pull a detail out of what the caller said, using the speech-to-text transcript only.

Plain parsers, no text model: spoken digits for phone numbers, spelled letters for names,
a date parser for birthdays, and fuzzy matching against known lists (Jev breaks close ties).
"""

import json
import re
from pathlib import Path

import dateparser
from rapidfuzz import fuzz

DIRECTORY = json.loads((Path(__file__).parent / "directory.json").read_text())
FIELD_KIND = {"insurance_provider": "insurer", "doctor_name": "doctor", "hospital_name": "hospital", "medication_name": "medication"}
NAME_FIELDS = {"caller_name", "patient_name", "missing_person_name"}

DIGIT_WORDS = {"zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2", "too": "2", "three": "3", "four": "4",
               "for": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
REPEAT_WORDS = {"double": 2, "triple": 3}
TOKEN = re.compile(r"[a-z]+|\d+")


# ---------------------------------------------------------------- phone numbers

def parse_phone(text: str) -> str | None:
    """'four one five, double five five, zero one four two' -> '4155550142'. Needs exactly 10 digits."""
    runs, run, repeat = [], "", 1
    for tok in TOKEN.findall(text.lower()):
        if tok in REPEAT_WORDS:
            repeat = REPEAT_WORDS[tok]
            continue
        if tok.isdigit():
            run += tok * repeat if len(tok) == 1 else tok
        elif tok in DIGIT_WORDS and (run or tok not in {"o", "oh", "to", "too", "for"}):
            run += DIGIT_WORDS[tok] * repeat
        elif tok in {"dash", "and"} and run:
            pass
        else:
            if run:
                runs.append(run)
            run = ""
        repeat = 1
    if run:
        runs.append(run)
    for r in sorted(runs, key=len, reverse=True):
        if len(r) == 11 and r.startswith("1"):
            r = r[1:]
        if len(r) == 10:
            return r
    return None


def digits_of(number: str | None) -> str:
    d = re.sub(r"\D", "", number or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d


# ---------------------------------------------------------------- names

AS_IN = re.compile(r"\b([a-z])\s+(?:as in|like)\s+[a-z]+\b")
NAME_PHRASE = re.compile(
    r"\b(?:my name is|my name's|name is|this is|i am|i'm|it's|it is|his name is|her name is|their name is|"
    r"he's called|she's called|he is|she is)\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})"
)
NOT_NAME = {"and", "calling", "about", "from", "the", "a", "an", "my", "here", "trying", "just", "so", "um", "uh",
            "yes", "yeah", "no", "okay", "ok", "sorry", "looking", "worried", "at", "in", "on", "that", "it", "is"}


def parse_spelled(text: str) -> str | None:
    """'R as in Robert, E, Y, E, S' or 'R-E-Y-E-S' -> 'REYES'. Needs 3+ letters in a row."""
    text = AS_IN.sub(r"\1", text.lower())
    best, run = "", ""
    for tok in re.findall(r"[a-z]+", text):
        if len(tok) == 1:
            run += tok
        else:
            best, run = max(best, run, key=len), ""
    best = max(best, run, key=len)
    return best.upper() if len(best) >= 3 else None


def parse_phrase_name(text: str) -> str | None:
    m = NAME_PHRASE.search(text.lower())
    if m:
        words = []
        for w in m.group(1).split():
            if w in NOT_NAME:
                break
            words.append(w)
    else:
        # A short answer with no digits is probably just the name: "Daniel Reyes."
        words = re.findall(r"[a-z][a-z'\-]+", text.lower())
        if not (1 <= len(words) <= 3) or re.search(r"\d", text) or any(w in NOT_NAME for w in words):
            return None
    return " ".join(w.capitalize() for w in words) or None


def parse_name(text: str) -> tuple[str | None, str | None, str | None]:
    """Returns (name, spelled part, method). The spelled letters win over the heard word they match."""
    spelled = parse_spelled(text)
    # Strip the spelled letters before looking for a phrase name, so they aren't read as words.
    phrase = parse_phrase_name(re.sub(r"\b([a-z])\b(?:[\s,\-]+\b[a-z]\b)+", " ", AS_IN.sub(r"\1", text.lower())))
    if spelled and phrase:
        # The spelling replaces the heard word it resembles, else the last name
        # (speech-to-text often mishears it: "Raise" for Reyes), else it's added.
        words = phrase.split()
        i = max(range(len(words)), key=lambda k: fuzz.ratio(words[k].upper(), spelled))
        if fuzz.ratio(words[i].upper(), spelled) >= 50:
            words[i] = spelled.capitalize()
        elif len(words) >= 2:
            words[-1] = spelled.capitalize()
        else:
            words.append(spelled.capitalize())
        return " ".join(words), spelled, "spelling"
    if spelled:
        return spelled.capitalize(), spelled, "spelling"
    if phrase:
        return phrase, None, "phrase"
    return None, None, None


# ---------------------------------------------------------------- dates

ORDINALS = {w: str(i) for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
    "fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), start=1)}
ORDINALS |= {f"twenty {w}": str(20 + int(n)) for w, n in list(ORDINALS.items())[:9]}
ORDINALS |= {"thirtieth": "30", "thirty first": "31"}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine".split())}
SPOKEN_YEAR = re.compile(r"\b(nineteen|twenty)\s+(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s\-]+(one|two|three|four|five|six|seven|eight|nine))?\b")


def parse_dob(text: str) -> str | None:
    """'March fourth, nineteen fifty-two' -> '1952-03-04'."""
    t = text.lower()
    t = SPOKEN_YEAR.sub(lambda m: str((19 if m.group(1) == "nineteen" else 20) * 100 + TENS[m.group(2)] + UNITS.get(m.group(3) or "zero", 0)), t)
    for words in sorted(ORDINALS, key=len, reverse=True):
        t = re.sub(rf"\b{words}\b", ORDINALS[words], t)
    t = re.sub(r"\b(born on|born|my birthday is|birthday is|date of birth is|it's|it is|um|uh)\b", " ", t)
    d = dateparser.parse(t, languages=["en"], settings={"PREFER_DATES_FROM": "past", "DATE_ORDER": "MDY", "STRICT_PARSING": True})
    return d.date().isoformat() if d else None


# ---------------------------------------------------------------- known lists

def match_directory(kind: str, text: str) -> list[tuple[str, float]]:
    """Score every known name against 1-4 word chunks of the caller's speech. Best first."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    chunks = {" ".join(words[i:i + n]) for n in range(1, 5) for i in range(len(words) - n + 1)}
    scores = []
    for name, aliases in DIRECTORY[kind].items():
        forms = [name.lower().replace("dr. ", "")] + [a.lower() for a in aliases]
        best = max((fuzz.ratio(f, c) for f in forms for c in chunks if abs(len(f) - len(c)) <= max(3, len(f) // 3)), default=0)
        scores.append((name, best))
    return sorted(scores, key=lambda s: s[1], reverse=True)


async def pick_from_directory(kind: str, text: str, jev_pick=None) -> tuple[str | None, str | None, float]:
    """Returns (name, method, score). Clear winner -> fuzzy; close call -> Jev; nothing close -> None."""
    ranked = match_directory(kind, text)
    (top, s1), (_, s2) = ranked[0], ranked[1] if len(ranked) > 1 else ("", 0)
    if s1 >= 85 and s1 - s2 >= 8:
        return top, "fuzzy", s1
    close = [n for n, s in ranked if s >= 70 and s1 - s <= 10]
    if len(close) >= 2 and jev_pick:
        choice, conf = await jev_pick(text, f"Which {kind} did the caller name?", close)
        if choice:
            return choice, "jev", (conf or 0) * 100
    if s1 >= 85:
        return top, "fuzzy", s1
    return None, None, s1


# ---------------------------------------------------------------- entry point

YES_CALLER_ID = re.compile(r"\b(yes|yeah|yep|that one|this one|this number|same number|the one i'?m calling from|that's fine|that's the best)\b")


async def extract(field: str, caller_turns: list[str], from_number: str | None = None, jev_pick=None) -> dict | None:
    """Try the latest caller turn first, then the last two together. Returns {value, method, stt_text, score}."""
    tries = [caller_turns[-1]] if caller_turns else []
    if len(caller_turns) >= 2:
        tries.append(" ".join(caller_turns[-2:]))

    for text in tries:
        if field == "callback_number":
            if v := parse_phone(text):
                return {"value": v, "method": "digits", "stt_text": text}
        elif field in NAME_FIELDS:
            name, spelled, method = parse_name(text)
            if name:
                return {"value": name, "method": method, "spelled": spelled, "stt_text": text}
        elif field == "date_of_birth":
            if v := parse_dob(text):
                return {"value": v, "method": "date", "stt_text": text}
        elif field in FIELD_KIND:
            name, method, score = await pick_from_directory(FIELD_KIND[field], text, jev_pick)
            if name:
                return {"value": name, "method": method, "score": score, "stt_text": text}
            if field in {"doctor_name", "medication_name"} and (spelled := parse_spelled(text)):
                value = f"Dr. {spelled.capitalize()}" if field == "doctor_name" else spelled.lower()
                return {"value": value, "method": "spelling", "spelled": spelled, "stt_text": text}

    # "Is the number you're calling from the best one?" -> "Yes": use caller ID.
    if field == "callback_number" and caller_turns and from_number and YES_CALLER_ID.search(caller_turns[-1].lower()):
        if len(d := digits_of(from_number)) == 10:
            return {"value": d, "method": "caller_id", "stt_text": caller_turns[-1]}
    return None
