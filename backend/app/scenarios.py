"""Scripted caller situations, ported from ui/night-ledger.html and solution_scenarios.md.

`model` is what the language model labelled the call (label, confidence). The rules run on the caller's
words, and the higher lane wins, so a mislabelled chest-pain call still lands in red.
"""

MODEL_LANE = {
    "status question": "green", "scheduling": "green", "offer of help": "green", "media": "green", "portal help": "green",
    "refill": "green", "billing": "green", "visitor info": "green", "evacuation question": "green", "staff can't get in": "green",
    "family locating": "amber", "unclear": "amber", "emotional distress": "amber", "child symptom": "amber",
    "request human": "amber", "medication question": "amber", "post-op question": "amber", "minor injury": "green",
    "injury": "red", "breathing problem": "red",
}

SERIOUS_EARTHQUAKE = [
    {"w": 12, "cl": "outage", "intent": "Asking if the ER is open", "model": ("status question", .94),
     "q": ["Is the emergency room still open with the power out?", "Yes, the ER is open and running on backup power."]},
    {"w": 7, "cl": "outage", "intent": "Power out, asking if tomorrow's appointment is still on", "model": ("scheduling", .91),
     "q": ["The power's out here. My MRI is at 8 tomorrow, is that still happening?", "I'll book a callback to confirm once the schedule is set."]},
    {"w": 6, "intent": "Looking for brother, may have been brought in after the building collapse", "model": ("family locating", .89),
     "q": ["I'm looking for my brother, he lives on Alder Street and the building came down. Is he there?", "I can't share patient information, but a staff member will call you back. Can I take his name and what he looks like?"]},
    {"w": 5, "cl": "help", "intent": "Offering to donate blood", "model": ("offer of help", .96),
     "q": ["Do you need blood donors tonight? I want to donate.", "Thank you. I'll send you a text with the donation sign-up link."]},
    {"w": 4, "cl": "help", "intent": "Off-duty nurse offering to come in", "model": ("offer of help", .90),
     "q": ["I'm an ICU nurse, off-duty tonight. Should I come in?", "I'll pass your name and number to the staffing desk right now."]},
    {"w": 3, "intent": "Wife was in the ER waiting room, not answering her phone", "model": ("family locating", .87),
     "q": ["Is my wife there? She texted me she was in your ER, now nothing.", "A staff member will call you back. What's her name and date of birth?"]},
    {"w": 3, "intent": "Caller repeats questions, seems confused about where they are", "model": ("unclear", .41), "stt": .38,
     "q": ["Which... what is this? I need the bus.", "I want to get you to a person. Can you tell me your name?"]},
    {"w": 2, "intent": "Can't stop shaking since the quake, scared to stay home alone", "model": ("emotional distress", .83),
     "q": ["I can't stop shaking. I don't want to be alone.", "You're not alone on this call. Are you having any thoughts of hurting yourself?"]},
    {"w": 2, "intent": "14-month-old coughing, no fever, parent worried about dust", "model": ("child symptom", .80),
     "q": ["My 14-month-old baby keeps coughing, there was dust everywhere.", "A nurse will call you back within 15 minutes. Is she breathing hard or turning blue?"]},
    {"w": 2, "intent": "Asked for a human", "model": ("request human", .97),
     "q": ["Just put me through to a real person please.", "Of course. A staff member will call you back. Can I confirm your number?"]},
    {"w": 1, "intent": "Spanish speaker, transcription unclear", "model": ("unclear", .35), "stt": .31,
     "q": ["...mi mamá... el oxígeno no...", "Le comunico con una persona. ¿Me puede dar su número?"]},
    {"w": 2, "cl": "media", "intent": "Reporter asking for a statement", "model": ("media", .95),
     "q": ["Channel 4 news, how many patients have you received?", "I'll pass your request to our public information officer."]},
    {"w": 2, "cl": "outage", "intent": "Patient portal down, can't see test results", "model": ("portal help", .92),
     "q": ["MyChart isn't loading since the power went out.", "The portal is down with the outage. I'll text you when it's back."]},
    {"w": 2, "intent": "Neighbor cut by glass, bleeding won't stop", "model": ("injury", .88),
     "q": ["My neighbor got cut by glass, it's bleeding and it won't stop.", "I'm connecting you to a nurse now. Press firmly on the wound."]},
    {"w": 2, "intent": "Smoke in the apartment, father wheezing", "model": ("breathing problem", .90),
     "q": ["My father is wheezing, he can't catch his breath, there's smoke.", "I'm connecting you to a nurse now. Get him to fresh air if you can."]},
]

# The star call: the model thinks it's a status question; the rules catch the chest pain.
CHEST = {"intent": "Father has chest pressure and is sweating, 71 years old", "model": ("status question", .52), "star": True,
         "q": ["I was calling to ask if you're open... my dad says his chest feels tight and he's sweaty.", "I'm connecting you to a nurse right now. Stay on the line."]}

BIG_FIRE = [
    {"w": 8, "cl": "outage", "intent": "Asking if the hospital is being evacuated", "model": ("evacuation question", .93),
     "q": ["Is the hospital being evacuated? Is the ER open?", "The hospital is open and is not being evacuated."]},
    {"w": 5, "intent": "Father is an inpatient, family wants to know if he's safe", "model": ("family locating", .88),
     "q": ["My father is a patient there, is he being moved? Is my dad safe?", "I can't share patient information, but staff will call you back."]},
    {"w": 3, "intent": "COPD patient, smoke making it hard to breathe", "model": ("status question", .58),
     "q": ["I have COPD and the smoke is making it hard to breathe. Are you open?", "I'm connecting you to a nurse now. If you can, get to fresh air."]},
    {"w": 4, "cl": "help", "intent": "Nurse can't reach shift, road closed", "model": ("staff can't get in", .90),
     "q": ["I'm a nurse, my road is closed, I can't get to my shift.", "I'll pass this to the staffing desk."]},
    {"w": 4, "cl": "help", "intent": "Offering donations for evacuees", "model": ("offer of help", .95),
     "q": ["We want to donate water and blankets, where do we bring them?", "Thank you, I'll text you the donation link."]},
    {"w": 2, "intent": "Anxious about evacuation, alone at home", "model": ("emotional distress", .82),
     "q": ["I'm alone and I panic every time the evacuation alert goes off.", "You're not alone on this call. A staff member will call you back soon."]},
]

SMALL_FIRE = [
    {"w": 4, "intent": "Mother lives in the burned building", "model": ("family locating", .90),
     "q": ["Is my mother there? She lives in the building on Alder that caught fire.", "A staff member will call you back. What's her name?"]},
    {"w": 3, "intent": "Neighbor asking if smoke is dangerous", "model": ("status question", .86),
     "q": ["Is the smoke from the fire dangerous? I'm two blocks away.", "Keep windows closed. If anyone has trouble breathing, tell me right away."]},
    {"w": 1, "intent": "Toddler coughing from smoke", "model": ("child symptom", .84),
     "q": ["My 18-month-old is coughing from the smoke.", "A nurse will call you back within 15 minutes. Is he breathing hard?"]},
    {"w": 2, "cl": "media", "intent": "Reporter asking how many patients came in", "model": ("media", .94),
     "q": ["This is the Daily Breeze, how many fire patients did you get?", "I'll pass your request to our public information officer."]},
]

SMALL_EARTHQUAKE = [
    {"w": 8, "cl": "outage", "intent": "Was that an earthquake, is the hospital OK", "model": ("status question", .95),
     "q": ["Was that an earthquake? Is the hospital OK and open?", "The hospital is not damaged and all services are running."]},
    {"w": 5, "cl": "scheduling", "intent": "Asking if the 8 AM appointment is still on", "model": ("scheduling", .93),
     "q": ["Is my 8 AM appointment still on after the quake?", "Appointments go ahead as planned."]},
    {"w": 2, "intent": "Anxious and can't sleep after the shaking", "model": ("emotional distress", .80),
     "q": ["I'm anxious and I can't sleep after the shaking.", "A staff member will call you back soon. You can also call or text 988."]},
    {"w": 2, "intent": "Fell during the shaking, wrist hurts", "model": ("minor injury", .85),
     "q": ["I fell during the shaking and hurt my wrist.", "I'll book a callback. If it gets worse or swells badly, call 911."]},
]

TUESDAY = [
    {"w": 6, "cl": "medication", "intent": "Prescription refill question", "model": ("refill", .95),
     "q": ["Can I get my lisinopril prescription refilled?", "I'll send a refill request. The pharmacy team will confirm in the morning."]},
    {"w": 5, "cl": "scheduling", "intent": "Reschedule Thursday appointment", "model": ("scheduling", .97),
     "q": ["I need to reschedule my Thursday appointment.", "I can offer Friday at 10:20 or Monday at 9."]},
    {"w": 4, "cl": "billing", "intent": "Billing question about a statement", "model": ("billing", .93),
     "q": ["My bill says I owe $340, I thought insurance covered it.", "I'll schedule a callback from billing tomorrow between 9 and 11."]},
    {"w": 3, "cl": "other", "intent": "Visiting hours and parking", "model": ("visitor info", .98),
     "q": ["Can I visit my mom tonight, and where do I park?", "Visiting ends at 9 pm. Overnight, one adult can stay with ICU patients."]},
    {"w": 2, "intent": "Discharged yesterday, unsure about new medication dose", "model": ("medication question", .86),
     "q": ["I was discharged yesterday with a new blood thinner, I can't remember if it's one or two.", "A nurse will call you back within 15 minutes. Please don't take another dose until then."]},
    {"w": 1, "intent": "Post-op wound bleeding through the dressing", "model": ("post-op question", .70),
     "q": ["My incision is soaking through the bandage.", "I'm connecting you to the on-call nurse now."]},
]

SCENARIOS = {
    "serious_earthquake": {"label": "Serious earthquake", "templates": SERIOUS_EARTHQUAKE, "clock": 2 * 3600 + 6 * 60,
                           "interval": (3.5, 0.8), "star_at": 10, "abandon": 0.35},
    "big_fire": {"label": "Big fire", "templates": BIG_FIRE, "clock": 23 * 3600 + 20 * 60, "interval": (5.0, 1.5), "abandon": 0.3},
    "small_fire": {"label": "Small fire", "templates": SMALL_FIRE, "clock": 23 * 3600 + 40 * 60, "interval": (12.0, 10.0), "abandon": 0.05},
    "small_earthquake": {"label": "Small earthquake", "templates": SMALL_EARTHQUAKE, "clock": 3 * 3600 + 15 * 60, "interval": (4.0, 3.0), "abandon": 0.2},
    "tuesday": {"label": "Ordinary Tuesday", "templates": TUESDAY, "clock": 21 * 3600 + 42 * 60, "interval": (10.0, 10.0), "abandon": 0.02},
}

FIRST = ["Maria", "James", "Aisha", "Daniel", "Priya", "Luis", "Hannah", "Omar", "Grace", "Tomás", "Mei", "Samuel", "Fatima",
         "Noah", "Rosa", "Ethan", "Yara", "Victor", "Leah", "Kwame", "Ana", "Ben", "Sofia", "Imran", "Chloe", "Diego", "Nadia",
         "Owen", "Rina", "Marcus"]
LAST = ["Reyes", "Okafor", "Nguyen", "Patel", "Kim", "Garcia", "Cohen", "Mensah", "Silva", "Haddad", "Novak", "Tanaka",
        "Brooks", "Alvarez", "Osei", "Ivanova", "Moreno", "Chen", "Walsh", "Rossi"]
