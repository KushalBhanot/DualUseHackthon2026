# Night Ledger: Scenarios

The same system handles very different nights. What changes is how far up the ladder calls go and which decisions reach the supervisor. The gentlest response that works is different for a kitchen fire and for a building collapse, and the system should not treat them the same.

Call volumes below are illustrative, for the demo and pitch. They are not measured figures.

## At a glance

| | Small fire | Big fire | Small earthquake | Serious earthquake |
|---|---|---|---|---|
| **Example** | Apartment fire two blocks away, 3 people treated for smoke | Wind-driven wildfire, evacuations, smoke across the city | Short, strong shaking, no damage, no power loss | Collapsed buildings, regional power outage, many injured |
| **Extra call volume** | 2–3× normal for an hour | 10×+ for many hours, in waves | 5–10× for 20–30 min, then drops fast | 10×+ for hours |
| **Who's calling** | Neighbors, families of the 3 patients, media | Evacuees, families, people with breathing problems, staff who can't get in | Worried public, "was that an earthquake?", patients asking about appointments | Families looking for people, injured callers, offers of help, outage questions |
| **Share of red-flag calls** | Very low | Low but steady (smoke, breathing) | Very low | Highest of the four |
| **Surge mode?** | Usually not needed | Yes, for the whole event | Maybe, briefly | Yes, immediately |
| **Rungs doing the work** | Ask, Hold | Watch, Slow, Hand | Watch, Slow | All five |
| **Key supervisor decision** | Who calls the 3 families back | Which status message to play, and updating it as evacuations change | Whether to switch surge mode on at all | Surge mode in the first 5 minutes, then reunification staffing |

## 1. Small fire

**Setting.** 11:40 PM. An apartment fire two blocks away. Three residents are brought to the ER with smoke inhalation, none critical. The power stays on.

**What callers ask.**
- Families: "Is my mother there? She lives in that building."
- Neighbors: "Is the smoke dangerous? My kid is coughing."
- Local reporters asking how many patients came in.

**What Night Ledger does.**
- **Ask:** every caller still gets the red-flag screen. A coughing child under 2 goes to *A person soon*. A caller with trouble breathing goes to *Now*.
- **Hold:** family callers go into the *A person soon* callback queue. The AI never confirms whether someone is a patient.
- **Watch:** a small "fire on Alder Street" cluster appears, but it is too small to suggest surge mode.
- Media calls go to the public information officer's queue.

**Supervisor decisions.**
- Who calls the three families back, and when (decision 3).
- Usually nothing else. Surge mode is not suggested, and nobody waits on hold for long.

**Why this matters.** The system should *not* escalate a small event into a big response. No mass alert, no surge mode, no extra staff called in. This is the gentlest rung working as intended.

## 2. Big fire

**Setting.** A wind-driven wildfire on the edge of the city. Evacuation orders change through the night. Smoke covers a wide area. 911 is overloaded, so people call the hospital directly.

**What callers ask.**
- "Is the hospital being evacuated? My father is a patient."
- "I have COPD and the smoke is making it hard to breathe."
- "Is the ER open? Which entrance?"
- Staff: "My road is closed, I can't get to my shift."
- Offers of help and donations.

**What Night Ledger does.**
- **Watch:** clusters form and change over hours ("evacuation questions", "smoke and breathing", "is the ER open").
- **Slow:** a status message carries most of the load. The supervisor updates it as the situation changes, for example when the ER entrance changes because of a road closure.
- **Ask and Hand:** breathing complaints are red flags. They go straight to a nurse with a Handoff Card, even while hundreds of status questions are coming in.
- **Hold:** families of inpatients go into the *A person soon* queue. Staff calls are routed to the staffing desk.

**Supervisor decisions.**
- Switch surge mode on (decision 1) early, and keep it on for the whole event.
- Approve and update the status message (decision 2) as evacuations change. A stale message is worse than none.
- Call in staff who can still get in (decision 6).

**Risk and safeguard.** Smoke-related breathing problems can sound routine ("I'm just a bit short of breath"). The rules catch "breathing" as a red flag even when the model labels the call a status question, and the higher lane always wins.

## 3. Small earthquake

**Setting.** 3:15 AM. Short, strong shaking. No buildings damaged, power stays on, a few people with minor falls. Phones light up for about 20 minutes, then go quiet.

**What callers ask.**
- "Was that an earthquake? Is the hospital OK?"
- "Is my 8 AM appointment still on?"
- "I'm anxious and can't sleep." (mental health, goes to a person)
- A few minor injuries: "I fell and hurt my wrist."

**What Night Ledger does.**
- **Watch:** one big "earthquake / are you OK?" cluster, with almost no red flags.
- **Slow:** one status message ("The hospital is not damaged and all services are running. Appointments go ahead as planned.") answers most callers.
- **Ask:** the rare real injury still gets screened and placed in the right lane.

**Supervisor decisions.**
- **Whether to switch surge mode on at all** (decision 1). The prompt appears, but the supervisor may reasonably say *Not yet*, play the status message, and wait for the spike to pass.
- If the volume drops, the system stops asking. If it doesn't, it asks again in two minutes with updated numbers.

**Why this matters.** This is where the *Not yet, ask in 2 min* option earns its place. The supervisor keeps control, and a short spike doesn't force a big response.

## 4. Serious earthquake

**Setting.** 2:06 AM. Strong earthquake. Several buildings collapse and the regional power is out. The hospital runs on backup power. Within minutes, call volume is far above normal. This is the scenario the demo UI simulates.

**What callers ask.**
- Families: "My brother lives in the building that collapsed. Is he there?"
- Injured callers: chest pain, heavy bleeding, people trapped with injuries.
- Outage questions: "Is the ER open?", "Is my appointment still on?"
- People offering blood or help, off-duty nurses offering to come in.
- Confused or distressed callers, Spanish speakers, people who can't be understood clearly.

**What Night Ledger does.**
- **Watch:** volume far above normal triggers the surge-mode prompt within minutes.
- **Ask:** every caller gets the red-flag screen first. A caller who starts with "Are you open?" and then mentions chest pressure is caught by the rules even though the model labeled it a status question.
- **Slow:** a status message about the outage answers many callers without them waiting.
- **Hold:** family reunification, children under 2, mental health and confused callers go to *A person soon*. Routine callers get a callback time.
- **Hand:** red-flag callers reach a nurse in under 10 seconds with a Handoff Card. In a first-come queue they could have dozens of callers ahead of them.

**Supervisor decisions.**
- Switch surge mode on in the first five minutes (decision 1). Switching on takes held callers off hold and schedules callbacks for those who already hung up.
- Play the outage status message (decision 2).
- Decide reunification callback order, and how many staff to put on it (decisions 3 and 6).
- Handle callers who don't pick up twice: retry, or ask police for a welfare check (decision 4).

**Why this matters.** This is the night the system exists for. Every piece runs at once, and the supervisor's attention goes only to decisions that need a person.

## What stays the same in every scenario

- Every caller hears that they are talking to an AI and can ask for a person.
- Every caller gets the same red-flag screen first.
- The AI can move a caller up a lane, never down.
- The AI never shares patient information.
- Broadcasts, surge mode and declaring an incident always need the supervisor.
