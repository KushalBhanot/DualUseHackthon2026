import pytest

from app.details import readback
from app.details.extract import extract, parse_dob, parse_name, parse_phone, parse_spelled


@pytest.mark.parametrize("text, digits", [
    ("four one five five five five zero one four two", "4155550142"),
    ("it's four one five, double five five, oh one four two", "4155550142"),
    ("415-555-0142", "4155550142"),
    ("1 415 555 0142", "4155550142"),
    ("my number is 4 1 5 5 5 5 0 1 4 2 thanks", "4155550142"),
])
def test_phone(text, digits):
    assert parse_phone(text) == digits


def test_phone_needs_ten_digits():
    assert parse_phone("five five five zero one four two") is None
    assert parse_phone("my dad is seventy one") is None


def test_spelling():
    assert parse_spelled("R as in Robert, E, Y, E, S") == "REYES"
    assert parse_spelled("R-E-Y-E-S") == "REYES"
    assert parse_spelled("I am a nurse") is None


def test_name_from_phrase_and_spelling():
    assert parse_name("my name is Daniel Raise, R E Y E S")[0] == "Daniel Reyes"
    assert parse_name("this is Priya Shah calling about my appointment")[0] == "Priya Shah"
    assert parse_name("Priya Shah.")[0] == "Priya Shah"


def test_dob():
    assert parse_dob("March fourth, nineteen fifty-two") == "1952-03-04"
    assert parse_dob("born on 3/4/1952") == "1952-03-04"


async def test_directory_match():
    assert (await extract("insurance_provider", ["I have blue cross"]))["value"] == "Blue Cross Blue Shield"
    assert (await extract("doctor_name", ["my doctor is doctor okafor"]))["value"] == "Dr. Okafor"
    assert (await extract("hospital_name", ["I was at saint brigid last week"]))["value"] == "St. Brigid Medical Center"


async def test_unknown_doctor_falls_back_to_spelling():
    assert (await extract("doctor_name", ["it's doctor B A R T O N"]))["value"] == "Dr. Barton"


async def test_callback_uses_caller_id_when_caller_says_yes():
    got = await extract("callback_number", ["yes, this number is fine"], from_number="+14155550142")
    assert got == {"value": "4155550142", "method": "caller_id", "stt_text": "yes, this number is fine"}


def test_readback():
    assert readback.phone("4155550142") == "four one five, five five five, zero one four two"
    assert readback.make("caller_name", {"value": "Daniel Reyes", "spelled": "REYES", "method": "spelling"}) == "Daniel Reyes. That's R-E-Y-E-S."
    assert readback.make("date_of_birth", {"value": "1952-03-04"}) == "March 4, 1952"
