"""Simulated emergency nights, inserted straight into Postgres (no Retell).

  uv run python -m app.seed serious_earthquake --count 40
  uv run python -m app.seed serious_earthquake --drip 3          # one call every 3 s, for the live demo
  uv run python -m app.seed tuesday --classify --jev             # also run rules + Jev on the fake transcripts
  uv run python -m app.seed --reset                              # remove simulated calls and demo suggestions

Caller templates come from ui/night-ledger.html (SURGE, CHEST, TUESDAY) and solution_scenarios.md.
Names and numbers are fictional.
"""

import argparse
import asyncio
import datetime as dt
import random
import uuid

from . import db, handoff
from .classify.service import classify_and_store
from .details import readback
from .supervisor import engine

GREETING = ("Harbor General Hospital. I'm an automated assistant, not a person, and you can ask for a person at any time. "
            "First, a quick safety check: is anyone with you having chest pain, trouble breathing, or bleeding that won't stop?")


def T(w, lane, cluster, intent, caller, agent, reason=None, flags=(), safety_no=True):
    return dict(w=w, lane=lane, cluster=cluster, intent=intent, caller=caller, agent=agent,
                reason=reason, flags=list(flags), safety_no=safety_no)


SURGE = [
    T(9, "green", "outage", "Asking if the ER is open", "Is the emergency room still open with the power out?", "Yes, the ER is open and running on backup power."),
    T(7, "green", "outage", "Power out, asking if tomorrow's appointment is still on", "My MRI is at 8 tomorrow, is that still happening?", "I'll book a callback to confirm once the schedule is set."),
    T(6, "amber", "family", "Looking for brother, may have been brought in after the building collapse", "My brother lives on Alder Street, the building came down. Is he there?", "I can't share patient information, but a staff member will call you back. Can I take his name and what he looks like?", "family_locating"),
    T(5, "green", "help", "Offering to donate blood", "Do you need blood donors tonight?", "Thank you. I'll send you a text with the donation sign-up link."),
    T(4, "green", "help", "Off-duty nurse offering to come in", "I'm an ICU nurse, off tonight. Should I come in?", "I'll pass your name and number to the staffing desk right now."),
    T(3, "amber", "family", "Wife was in the ER waiting room, not answering her phone", "She texted me she was in your ER, now she's not answering her phone.", "A staff member will call you back. What's her name and date of birth?", "family_locating"),
    T(3, "amber", "other", "Caller repeats questions, seems confused about where they are", "Which... what is this? I need the bus.", "I want to get you to a person. Can you tell me your name?", "confused_or_unclear"),
    T(2, "amber", "mental_health", "Can't stop shaking since the quake, scared to stay home alone", "I can't stop shaking. I don't want to be alone.", "You're not alone on this call. Are you having any thoughts of hurting yourself?", "mental_health"),
    T(2, "amber", "child", "14-month-old coughing, no fever, parent worried about dust", "My 14 month old baby keeps coughing, there was dust everywhere.", "A nurse will call you back within 30 minutes. Is she breathing hard or turning blue?", "child_under_2"),
    T(2, "amber", "other", "Asked for a human", "Just put me through to a real person please.", "Of course. A staff member will call you back. Can I confirm your number?", "asked_for_person"),
    T(1, "amber", "other", "Spanish speaker, transcription unclear", "...mi mamá... el oxígeno no...", "Le comunico con una persona. ¿Me puede dar su número?", "confused_or_unclear"),
    T(2, "green", "media", "Reporter asking for a statement", "Channel 4 news, how many patients have you received?", "I'll pass your request to our public information officer."),
    T(2, "green", "outage", "Patient portal down, can't see test results", "MyChart isn't loading.", "The portal is down with the outage. I'll text you when it's back."),
    T(1, "red", "injury_or_illness", "Neighbor cut by glass, bleeding won't stop", "There's blood everywhere, it won't stop.", "I'm connecting you to a nurse now. Press firmly on the wound.", flags=["bleeding"], safety_no=False),
    T(1, "red", "injury_or_illness", "Smoke in the apartment, father wheezing", "He can't catch his breath, there's smoke.", "I'm connecting you to a nurse now. Get him to fresh air if you can.", flags=["breathing"], safety_no=False),
    T(1, "red", "outage", "Father has chest pressure and is sweating, 71 years old", "I was calling to ask if you're open... my dad says his chest feels tight and he's sweaty.", "I'm connecting you to a nurse right now. Stay on the line.", flags=["chest_pain"]),
]

TUESDAY = [
    T(6, "green", "medication", "Prescription refill question", "Can I get my lisinopril refilled?", "I'll send a refill request. The pharmacy team will confirm in the morning."),
    T(5, "green", "scheduling", "Reschedule Thursday appointment", "I need to move my Thursday visit.", "I'll book a callback for tomorrow morning between 8 and 11."),
    T(4, "green", "billing", "Billing question about a statement", "My bill says I owe $340, I thought insurance covered it.", "I'll schedule a callback from billing tomorrow morning."),
    T(3, "green", "scheduling", "Visiting hours and parking", "Can I visit my mom tonight?", "Visiting ends at 9 pm. A staff member can call you about overnight stays."),
    T(2, "amber", "medication", "Discharged yesterday, unsure about new medication dose", "They discharged me yesterday with a new blood thinner, I can't remember if it's one or two.", "A nurse will call you back within 30 minutes. Please don't take another dose until then.", "recent_discharge"),
    T(1, "red", "injury_or_illness", "Post-op wound bleeding through the dressing", "My incision is soaking through the bandage.", "I'm connecting you to the on-call nurse now.", flags=["bleeding"], safety_no=False),
]

BIG_FIRE = [
    T(7, "green", "outage", "Asking if the hospital is being evacuated", "Is the hospital being evacuated? My father is a patient.", "The hospital is not being evacuated. A staff member can call you about your father.", "family_locating"),
    T(6, "green", "outage", "Asking which ER entrance is open", "Is the ER open? Which entrance do I use?", "Yes, the ER is open."),
    T(4, "red", "injury_or_illness", "COPD, smoke making it hard to breathe", "I have COPD and the smoke is making it hard to breathe.", "I'm connecting you to a nurse now. If you can, get to fresh air.", flags=["breathing"], safety_no=False),
    T(3, "green", "help", "Staff member can't reach their shift", "My road is closed, I can't get to my shift.", "I'll pass that to the staffing desk."),
    T(3, "amber", "family", "Family of an inpatient", "My mother is on the third floor, is she safe?", "I can't share patient information, but a staff member will call you back.", "family_locating"),
    T(2, "green", "help", "Offering donations", "Do you need water or supplies?", "Thank you. I'll text you a sign-up link."),
]

SMALL_FIRE = [
    T(4, "amber", "family", "Looking for mother from the burning building", "Is my mother there? She lives in that building on Alder.", "I can't share patient information, but a staff member will call you back.", "family_locating"),
    T(3, "amber", "child", "Neighbor's toddler coughing from smoke", "My 18 month old is coughing, we live next to the fire.", "A nurse will call you back within 30 minutes.", "child_under_2"),
    T(2, "green", "media", "Local reporter", "I'm a reporter, how many patients came in from the fire?", "I'll pass your request to our public information officer."),
    T(1, "green", "outage", "Asking if the smoke is dangerous", "Is the smoke dangerous to breathe if I stay inside?", "I can't give medical advice, but a staff member can call you back."),
]

SMALL_EARTHQUAKE = [
    T(8, "green", "outage", "Was that an earthquake, is the hospital OK", "Was that an earthquake? Is the hospital OK?", "The hospital is not damaged and all services are running."),
    T(5, "green", "scheduling", "Is my 8 AM appointment still on", "Is my 8 AM appointment still on after the quake?", "Appointments go ahead as planned."),
    T(2, "amber", "mental_health", "Anxious and can't sleep", "I'm so anxious after that I can't sleep.", "A staff member will call you back soon. You can call or text 988 any time.", "mental_health"),
    T(1, "green", "injury_or_illness", "Fell and hurt wrist", "I fell and hurt my wrist, it's swollen.", "I'll book a callback. If it gets worse, go to urgent care or the ER."),
]

SCENARIOS = {
    # templates, default count, minutes the calls are spread over (shorter = denser)
    "serious_earthquake": (SURGE, 40, 8),
    "big_fire": (BIG_FIRE, 30, 20),
    "small_fire": (SMALL_FIRE, 8, 60),
    "small_earthquake": (SMALL_EARTHQUAKE, 20, 6),
    "tuesday": (TUESDAY, 8, 120),
}

FIRST = ["Maria", "James", "Aisha", "Daniel", "Priya", "Luis", "Hannah", "Omar", "Grace", "Tomás", "Mei", "Samuel",
         "Fatima", "Noah", "Rosa", "Ethan", "Yara", "Victor", "Leah", "Kwame", "Ana", "Ben", "Sofia", "Imran"]
LAST = ["Reyes", "Okafor", "Shah", "Nguyen", "Lindqvist", "Haddad", "Mensah", "Kowalski", "Patel", "Ramirez",
        "Chen", "Abebe", "Moreau", "Sato", "Ortiz", "Novak"]


def fake_number(rng) -> str:
    return f"415555{rng.randint(1000, 9999)}"


def one_digit_off(number: str, rng) -> str:
    i = rng.randrange(6, 10)
    return number[:i] + str((int(number[i]) + rng.randint(1, 9)) % 10) + number[i + 1:]


def build_details(t: dict, name: str, number: str, rng) -> tuple[dict, str | None, str | None, str | None]:
    """Returns (details, official caller_name, official callback_number, callback_source)."""
    if t["lane"] == "red":
        return {}, None, number, "caller_id"  # red calls skip capture and use caller ID
    details = {}
    roll = rng.random()
    heard = one_digit_off(number, rng) if roll < 0.15 else number  # the speech model mishears now and then
    status = "unconfirmed" if roll > 0.9 else "confirmed"
    details["callback_number"] = {"value": number, "method": "digits", "status": status, "attempts": 2 if heard != number or status == "unconfirmed" else 1,
                                  "read_back": readback.phone(number), "model_heard": heard}
    last = name.split()[-1]
    details["caller_name"] = {"value": name, "method": "spelling", "spelled": last.upper(), "status": "confirmed", "attempts": 1,
                              "read_back": readback.name(name, last.upper()), "model_heard": name}
    return (details, name, number if status == "confirmed" else None, "confirmed" if status == "confirmed" else None)


async def insert_call(scenario: str, t: dict, started: dt.datetime, rng) -> str:
    call_id = f"sim_{uuid.uuid4().hex[:10]}"
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    number = fake_number(rng)
    details, caller_name, callback, callback_source = build_details(t, name, number, rng)
    duration = rng.randint(45, 180) if t["lane"] != "red" else rng.randint(25, 60)

    red = t["lane"] == "red"
    transfer_status = ("connected" if rng.random() < 0.8 else "no_answer") if red else None
    red_at = started + dt.timedelta(seconds=rng.randint(8, 20)) if red else None
    transfer_at = red_at + dt.timedelta(seconds=rng.randint(2, 6)) if red else None
    transfer_end = transfer_at + dt.timedelta(seconds=rng.randint(4, 12) if transfer_status == "connected" else 20) if red else None
    summary = f"{t['intent']}. " + ("Warm-transferred to the nurse line." if transfer_status == "connected"
                                    else "Nurse line didn't answer; caller told to call 911." if red
                                    else "Staff callback arranged." if t["lane"] == "amber" else "Handled by the agent.")

    await db.execute(
        """INSERT INTO calls (call_id, source, scenario, status, from_number, started_at, ended_at, duration_ms, disconnection_reason,
             lane, red_flags, cluster, intent, reason, caller_name, callback_number, callback_source, details,
             red_flag_at, transfer_started_at, transfer_ended_at, transfer_target, transfer_status, summary)
           VALUES (%s, 'simulated', %s, 'analyzed', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        call_id, scenario, "+1" + number, started, started + dt.timedelta(seconds=duration), duration * 1000,
        ("call_transfer" if transfer_status == "connected" else "agent_hangup") if red else "agent_hangup",
        t["lane"], t["flags"], t["cluster"], t["intent"], t["reason"], caller_name, callback, callback_source, details,
        red_at, transfer_at, transfer_end, "+12139940320" if red else None, transfer_status, summary,
    )

    lines = [("agent", GREETING)]
    if t["safety_no"]:
        lines += [("user", "No."), ("agent", "Thank you. What are you calling about tonight?")]
    lines += [("user", t["caller"]), ("agent", t["agent"])]
    for i, (role, content) in enumerate(lines):
        await db.execute(
            "INSERT INTO transcript_items (call_id, item_id, role, content, time_sec) VALUES (%s, %s, %s, %s, %s)",
            call_id, str(i), role, content, i * 5.0,
        )

    if red:
        await db.log_event(call_id, "red_flag_detected", {"flags": t["flags"], "simulated": True})
        await db.log_event(call_id, "transfer_started", {"simulated": True})
        if transfer_status != "connected":
            await handoff.open_red_alert(call_id, transfer_status)
    for field, d in details.items():
        if d["model_heard"] != d["value"]:
            await db.log_event(call_id, "stt_model_mismatch", {"field": field, "transcript": d["value"], "model_heard": d["model_heard"]})
        await db.log_event(call_id, "detail_confirmed" if d["status"] == "confirmed" else "detail_rejected", {"field": field})
    return call_id


async def reset() -> None:
    await db.execute("DELETE FROM calls WHERE source = 'simulated'")
    await db.execute("DELETE FROM suggestions WHERE call_id IS NULL")
    await db.execute("UPDATE surge_state SET surge_on = false, switched_at = NULL, status_message = NULL")
    print("removed simulated calls, demo suggestions, and reset surge mode")


async def ensure_nurse_lines() -> None:
    if not await db.fetchrow("SELECT 1 FROM nurse_lines LIMIT 1"):
        await db.execute(
            "INSERT INTO nurse_lines (label, number, role, priority) VALUES "
            "('ED charge nurse (demo)', '+12139940320', 'nurse', 1), ('House supervisor (demo)', '+14155550199', 'house_supervisor', 2)"
        )
        print("added 2 demo nurse lines")


async def main(args) -> None:
    await db.open_db()
    try:
        if args.reset:
            await reset()
        if not args.scenario:
            return
        templates, default_count, span_min = SCENARIOS[args.scenario]
        count = args.count or default_count
        rng = random.Random(args.seed)
        await ensure_nurse_lines()
        now = dt.datetime.now(dt.timezone.utc)
        weights = [t["w"] for t in templates]

        for i in range(count):
            t = rng.choices(templates, weights)[0]
            if args.drip:
                started = dt.datetime.now(dt.timezone.utc)
            else:
                started = now - dt.timedelta(minutes=rng.uniform(0, span_min))
            call_id = await insert_call(args.scenario, t, started, rng)
            if args.classify:
                await classify_and_store(call_id, "post_call", use_jev=args.jev)
            if args.drip:
                await engine.tick()
                print(f"[{i + 1}/{count}] {t['lane']:5} {t['intent']}")
                # Ramp up: the first few calls come in slowly, then the surge hits.
                await asyncio.sleep(args.drip * (3 if i < 4 else 1))
        await engine.tick()
        lanes = await db.fetch("SELECT lane, count(*) AS n FROM calls WHERE source = 'simulated' AND scenario = %s GROUP BY lane", args.scenario)
        open_s = await db.fetch("SELECT type, evidence ->> 'text' AS text FROM suggestions WHERE status = 'open' ORDER BY id")
        print(f"inserted {count} '{args.scenario}' calls. lanes: {', '.join(f'{r['lane']}={r['n']}' for r in lanes)}")
        for s in open_s:
            print(f"  open suggestion [{s['type']}]: {s['text']}")
    finally:
        await db.close_db()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Insert simulated emergency calls.")
    p.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS))
    p.add_argument("--count", type=int)
    p.add_argument("--drip", type=float, help="seconds between calls, inserted live")
    p.add_argument("--classify", action="store_true", help="run the rules on each fake transcript")
    p.add_argument("--jev", action="store_true", help="with --classify, also call Jev (needs TYPESAFE_API_KEY)")
    p.add_argument("--reset", action="store_true", help="remove simulated calls and demo suggestions first")
    p.add_argument("--seed", type=int, help="random seed, for a repeatable demo")
    asyncio.run(main(p.parse_args()))
