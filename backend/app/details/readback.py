"""The exact words the agent reads back. Spelled out so the speech model can't reshape them."""

import datetime as dt

DIGIT_NAMES = "zero one two three four five six seven eight nine".split()


def spell_digits(digits: str) -> str:
    return " ".join(DIGIT_NAMES[int(d)] for d in digits)


def phone(digits: str) -> str:
    """'4155550142' -> 'four one five, five five five, zero one four two'"""
    return ", ".join(spell_digits(g) for g in (digits[:3], digits[3:6], digits[6:]))


def spell(word: str) -> str:
    return "-".join(word.upper())


def name(value: str, spelled: str | None = None) -> str:
    """'Daniel Reyes' -> 'Daniel Reyes. That's R-E-Y-E-S.' Spells the spelled part, else the last word."""
    target = spelled or value.split()[-1]
    return f"{value}. That's {spell(target)}."


def date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def make(field: str, detail: dict) -> str:
    v = detail["value"]
    if field == "callback_number":
        return phone(v)
    if field == "date_of_birth":
        return date(v)
    if detail.get("method") == "spelling" or field.endswith("_name") and field not in {"hospital_name"}:
        return name(v.replace("Dr. ", "Doctor "), detail.get("spelled"))
    return v
