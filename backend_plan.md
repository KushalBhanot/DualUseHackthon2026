# Night Ledger: Backend Plan (first iteration)

## Goal

The Retell agent already exists (`retell/ladder.mjs`, deployed with `retell/deploy.sh`), but nothing stores calls yet. This backend adds:

1. **Call recording.** Every real Retell call is saved in Postgres: the live transcript as it happens, the post-call summary and analysis, and the audio.
2. **Classification.** Fixed rules plus TypeSafe's **Jev** model label each call (lane, red flags, cluster, reason). This runs live during the call and again after it ends.
3. **Transcript sidecar.** When the rules or Jev catch a red flag, the backend steers the agent through Retell's Update Live Call API.
4. **Key details from the transcript.** Names, phone numbers, insurance, doctors and hospitals come from Retell's speech-to-text transcript, not from the speech-to-speech model. The agent reads each one back to the caller and the caller confirms it. Only confirmed transcript values become the call's official details.
5. **Red-flag handoff tracking.** Nurse lines are managed in the backend. Every red call's transfer outcome is stored, and a red caller who didn't reach a nurse raises an alert.
6. **Supervisor decisions.** The backend prompts the supervisor to switch on surge mode (or they switch it on themselves), suggests a pre-approved status message to play to every caller, and suggests how many nurses and doctors to call in. The AI only suggests; every decision is a supervisor click.
7. **Simulated emergencies.** Scenario calls are inserted straight into Postgres, without Retell, so the supervisor view has realistic data for the demo.

The frontend comes later. This iteration only exposes read endpoints for it.

**Stack:** Python (FastAPI), Postgres, Retell Python SDK, Jev over HTTP.

**Known limits:**
- Retell's live stream is text only, so audio is stored **after** the call: we download Retell's `recording_url` into Postgres.
- Retell's docs don't say whether Update Live Call works with speech-to-speech (`s2s_model`) agents. The live test answers that. If it doesn't work, we switch back to the text model and the backend stays the same.

## How data flows

```
Phone call ──► Retell agent (s2s_model) ──webhooks──► FastAPI /retell/webhook
                                                        │ call_started  → insert call, start monitor task
                                                        │ call_ended    → transfer outcome, recording_url, post-call Jev
                                                        │ call_analyzed → Retell summary + analysis, download audio
     monitor task: wss://api.retellai.com/v2/monitor-call/{call_id}
        transcript_updated ─► upsert transcript_items
                            ├─► lane from node_transition (up only)
                            ├─► rules on every user update ──────────┐
                            └─► Jev after each finished user turn ───┤
                                                                     ▼
                                       combine (higher lane wins) ─► calls.lane
                                                                     └─ red flag? → update_live(context, trigger_response)

Detail capture (agent tool calls → our backend, synchronous):
  agent asks for a detail ─► capture_detail(field, model_heard) ─► backend reads the speech-to-text transcript
                                                                   ─► extract + normalize ─► returns read_back text
  agent reads read_back word for word, "Is that right?"
  caller answers ─► confirm_detail(field, confirmed) ─► backend checks the caller's reply in the transcript
                                                       ─► calls.details[field].status = confirmed / retry / unconfirmed

Supervisor (every 15 s):
  calls table ─► engine.py: volume vs baseline, top cluster, queues ─► suggestions (surge / status message / staffing)
  supervisor clicks accept / not yet / dismiss ─► surge_state, events
  new call rings ─► Retell inbound webhook ─► backend returns {surge_banner, incident_status, callback windows, nurse_line}
  red call transfer ─► monitor + call_ended ─► calls.transfer_status ─► not connected? → red_not_connected alert

seed.py ─► same tables (source='simulated'), optionally runs rules + Jev on the fake transcripts
```

## Classification

Two classifiers run on the same transcript, and **the higher lane always wins**. That matches the ladder rule: the AI can raise a lane, never lower it.

### 1. Rules (`app/classify/rules.py`)

Rules are instant, free and predictable. They run on every live transcript update.

| Rule group | Example triggers | Result |
|---|---|---|
| Red flags (the 12 `RED_FLAGS` in `ladder.mjs`) | "chest feels tight", "can't breathe", "won't stop bleeding", "fainted", "overdose" | lane **red** + `red_flags` |
| Person-soon signals | "real person", "my baby" / child under 2, "discharged yesterday", "looking for my brother", "hospice" | lane **amber** + `reason` |
| Cluster keywords | "power", "open", "appointment", "bill", "donate", "news" | `cluster` hint |

These are plain keyword/regex lists, unit tested.

### 2. Jev (`app/classify/jev.py`)

[Jev](https://docs.typesafe.ai/api) is TypeSafe AI's classification model. It doesn't generate text: you send the transcript plus a set of questions, and it returns one typed answer per question with probabilities. We call it with one HTTP request, `POST https://api.typesafe.ai/v1/systemone` (`Authorization: Bearer $TYPESAFE_API_KEY`). The model is pinned to `jev-1.13.0` so tuned thresholds keep working.

Questions sent in each request (`state` = the transcript so far):

| Key | Jev type | Answer used for |
|---|---|---|
| `lane` | `choice`: red / amber / green, each with a one-line description | the call's lane |
| `red_flag` | `choice`: the 12 red flags + `none` | which red flag, if any |
| `red_flag_present` | `noul` (yes/no probability) | catches paraphrases the rules miss ("he's gone gray and won't answer me") |
| `person_soon_reason` | `choice`: the 10 `PERSON_SOON_REASONS` + `none` | amber reason |
| `cluster` | `choice`: the 11 clusters | Watch board grouping |
| `caller_confused` | `noul` | moves the call to amber (ladder rule 6) |
| `urgency` | `score`: 1–5 | ranking inside a lane |

**When Jev runs:**
- **Live:** after each finished user turn, meaning an `agent` item shows up after a `user` item, since Retell doesn't flag when a turn ends. At most one request per call is in flight at a time.
- **Post-call:** once on `call_ended`, using the final transcript.

### 3. Combining (`app/classify/combine.py`)

- `final lane` = the highest of: rules, Jev (only if `confidence ≥ JEV_MIN_CONFIDENCE`, default 0.6), Retell's post-call `lane`, and the lane already stored.
- If Jev's `red_flag_present ≥ 0.8` and the rules found nothing, treat it as a red flag. It goes to the sidecar and is logged as a `rules_miss` event.
- `needs_review = true` when:
  - Jev's confidence is low, or
  - Jev and the rules disagree by more than one lane, or
  - Retell's analysis sets `needs_review`.
- The latest result from each classifier is kept on the call (`calls.rules_result`, `calls.jev_result`), so rules and Jev can be compared.

**Safety note:** caller speech goes into Jev's `state`, so a caller could try to steer it. That can only *raise* a lane. The rules set a minimum Jev can't go below, because the higher lane always wins.

## Capturing key details from the transcript (`app/details/`)

**Why:** a speech-to-speech model hears audio directly, and it often gets exact details wrong: a digit in a phone number, the spelling of a name, which insurer. Retell also runs its own speech-to-text on the caller (mostly Deepgram). That gives us a written record we can parse, check and store. So the **transcript is the source of truth for details**, and the speech model's job is to ask, read back and confirm.

**Turning sentences into fields.** The transcript is whole sentences ("this is Daniel Reyes, call me at four one five…"), so plain code picks out each field. There is no extra AI service. Names have no fixed list, so **callers spell them**, the way nurses already do on the phone.

### Fields captured

| Field | How it's pulled from the transcript | How it's read back |
|---|---|---|
| `callback_number` | Spoken-digit parser ("four one five, double five…") + regex → 10 digits | Digit by digit in groups: "four one five, five five five, zero one four two" |
| `caller_name`, `patient_name`, `missing_person_name` | The caller spells it, and a letter parser joins the letters ("R E Y E S", "R as in Robert" → `REYES`). If they don't spell it, the backend takes the words after "my name is / this is / his name is", and the read-back asks them to spell it | Name, then spelled: "Reyes, R-E-Y-E-S" |
| `date_of_birth` | Date parser on the caller's turn | "March fourth, nineteen fifty-two" |
| `insurance_provider` | Fuzzy match against the list of insurers. If 2+ close matches, a Jev `choice` question picks one, with `other` as an option | The matched name: "Blue Cross Blue Shield" |
| `doctor_name` | Fuzzy match against the hospital's doctor list, then Jev for close calls. If nothing matches, the caller spells it | "Doctor Okafor, O-K-A-F-O-R" |
| `hospital_name` | Fuzzy match against the list of local hospitals and clinics | The matched name |
| `medication_name` | Fuzzy match against a short list of common medications. If nothing matches, the caller spells it | Name, then spelled |

The lists (insurers, Harbor General doctors, local hospitals, medications) live in a Python file, `app/details/directory.py`, with demo data. The same lists are added to the agent's `boosted_keywords` so Retell's speech-to-text hears them better.

### The capture-and-confirm loop

Two new **custom function tools** on the Retell agent. Retell calls our backend and waits for the answer. The request includes the transcript so far, which keeps the order of steps reliable.

1. **Agent asks** for the detail. For names it asks for spelling; for numbers it asks the caller to say them slowly.
2. **Agent calls `capture_detail(field, model_heard)`.** `model_heard` is the speech model's own version, kept only for comparison. → `POST /retell/tools/capture_detail`
   - The backend takes the caller's last 1–2 turns from `call.transcript`, which is the speech-to-text text.
   - It extracts and normalizes the value with the method in the table above.
   - It saves the value to `calls.details` with status `pending_confirmation`. If the value differs from `model_heard`, it also logs an `stt_model_mismatch` event.
   - It returns `{"read_back": "four one five, five five five, zero one four two"}`, or `{"status": "not_found", "say": "Ask the caller to repeat it slowly."}`.
3. **Agent reads `read_back` word for word** and asks "Is that right?" Reading digits from text is reliable for the model; hearing them is the error-prone part.
4. **Agent calls `confirm_detail(field, confirmed)`** after the caller answers. → `POST /retell/tools/confirm_detail`
   - The backend **double-checks against the caller's actual reply** in the transcript:
     - A "yes" phrase ("yes", "yeah", "that's right", "correct", "sí") counts as yes.
     - A "no" phrase, or a correction ("no, it's 0143"), counts as no.
     - If unclear, a Jev `noul` question decides: "Did the caller confirm the read-back is correct?" (≥ 0.7 counts as yes).
   - **Confirmed** only if the agent *and* the transcript both say yes. The status becomes `confirmed`, and the value is copied to the matching column on the call (`caller_name`, `callback_number`).
   - **Not confirmed:** the backend replies "Ask them to repeat or spell it", and the agent captures again. After 2 failed tries the status is `unconfirmed`, `needs_review = true`, and the agent says "Staff will confirm your details when they call back."

**Safety:** detail capture never delays a red-flag transfer. `handoff_now` has no capture tools; it uses caller ID (`{{user_number}}`) and moves straight to the nurse. Capture runs in `callback_routine` and `person_soon`.

**If a tool fails or times out** (timeout set to 3 s): the agent carries on with the call. The detail is saved as `unconfirmed`, so a person checks it later.

### How details are stored

All details for a call live in one jsonb column, `calls.details`, keyed by field:

```json
{"callback_number": {"value": "4155550142", "status": "confirmed", "attempts": 2,
                     "stt_text": "four one five five five five zero one four two",
                     "read_back": "four one five, five five five, zero one four two",
                     "model_heard": "4155550124", "analysis_value": "4155550142"}}
```

Trust order:
1. **Confirmed transcript value.** Only this fills the official `calls.caller_name` and `calls.callback_number` columns.
2. **Unconfirmed transcript value.** Shown with an "unconfirmed" badge.
3. **Retell's post-call analysis (`analysis_value`) and `model_heard`.** Kept **only for comparison**; they never fill the official fields. If they disagree with the transcript value, `needs_review` is set.

### Agent prompt changes (`retell/ladder.mjs`)

Add one rule to `general_prompt`:
> DETAILS COME FROM THE TRANSCRIPT. When you collect a name, phone number, date of birth, insurance, doctor, hospital or medication: ask for it (ask the caller to spell names), then call `capture_detail`. Read back only the `read_back` text it returns, word for word, and ask "Is that right?" Then call `confirm_detail`. Never read back a detail from memory.

Also add the two tools to `callback_routine` and `person_soon`, and replace each "read back the number" step in those prompts with this loop.

**Later option:** if spelling slows calls down too much, a small text model (e.g. Claude Haiku) could copy names out of the transcript, with a check that the name really appears there.

## Sidecar steering (`app/monitor.py`)

When a red flag is first detected (by the rules, or by Jev above the threshold):
1. Log a `red_flag_detected` event and set the lane to red.
2. If the agent isn't already in `handoff_now`, call `client.call.update_live(call_id, call_control={"additional_context": "Safety system: caller mentioned <flag>. Transition to handoff_now now.", "trigger_response": True})`. Fall back to a plain `PATCH /v2/update-live-call/{id}` if the SDK lacks the method.
3. Log `context_injected`.

Each flag fires once per call. If the monitor socket drops, it reconnects once; `transcript_snapshot` resends everything.

## Red-flag calls: nurse lines and transfer outcome (`app/handoff.py`)

The agent's behavior stays as written in `retell/ladder.mjs`:
1. It warm-transfers to the nurse line.
2. Retell rings that line for **20 s**. This is the `transfer_ring_duration_ms: 20000` setting on the transfer tool, not a prompt; change it there and redeploy.
3. If nobody answers, the agent says *"Please hang up and call 911 now"* and ends the call.

The agent does **not** transfer to 911: a caller who dials 911 themselves gives the dispatcher their real number and location. The backend adds the parts that are missing.

### Nurse lines, managed in the backend

- **Storage:** the `nurse_lines` table holds the phones that can take red transfers: `label` ("ED charge nurse"), `number` (E.164), `role` (nurse / house supervisor), `on_duty`, `priority`.
- **Who updates it:** the supervisor, through the API: add a line, change a number, take a line off duty. No redeploy needed.
- **How Retell gets the number:** the transfer tool's number becomes a variable, `{{nurse_line}}`.
  - The **inbound webhook** fills it for each call with the top on-duty line (lowest priority number).
  - A change applies from the next call.
  - Web test calls don't hit the inbound webhook, so they use the default (`NURSE_LINE` env, as today).

### Transfer outcome, stored on every red call

The monitor stream and the `call_ended` webhook tell the backend what happened. The backend writes it to the `calls` row:

| Column | Filled from |
|---|---|
| `red_flag_at` | First red-flag detection (rules, Jev or the agent's own move to `handoff_now`) |
| `transfer_started_at`, `transfer_target` | The `transfer_to_nurse` tool call item in the live transcript, plus the nurse line used |
| `transfer_ended_at`, `transfer_status` | The transfer tool's result item and `disconnection_reason` at call end. The exact Retell values get confirmed in the live test |
| `callback_number` | For red calls, caller ID (`from_number`), marked `caller_id`, since detail capture is skipped to save time |

`transfer_status` values:
- `connected`: the nurse answered.
- `no_answer`: the caller was told to call 911.
- `caller_hung_up`: the caller left before the transfer finished.
- `never_started`: the red flag was flagged, but no transfer began within 10 s.

### What the backend does with it

- **Alert when a red caller didn't reach a nurse.** Any status other than `connected` opens a `red_not_connected` alert at the top of the board.
  - It **can't be snoozed or dismissed**, only resolved by a person ("called back", "reached 911", "unreachable").
  - Example: *"Red caller not connected, told to call 911. Call back (415) 555-0142, chest pain, 2:14 AM."*
  - This is the "retry and alert the supervisor" step from `solution_ladder.md`, done by a human.
- **Handoff timing in `/api/analytics`:** time from red flag to transfer start, time to nurse answer, and the share of red callers who were told to call 911. The ladder's target is under 10 s.

## Supervisor decisions (`app/supervisor/`)

This is the backend half of `supervisor_decisions.md`. A background check runs every 15 s, reads the `calls` table, and opens **suggestions** with the numbers behind them. The supervisor accepts, snoozes ("Not yet") or dismisses each one. **The AI never acts on its own:** no surge mode, broadcast or staff call-in happens without a click.

Thresholds live in one config file (`app/supervisor/config.py`), so nursing leadership can agree on them ahead of time: baseline volume, multipliers, minutes per call, targets.

### 1. Surge mode: prompted and manual

- **Manual, any time:** `POST /api/surge {"on": true}` or `{"on": false}`. Only a person can switch it on or off.
- **Prompt:**
  - **When:** surge mode is off, calls in the last 3 min ≥ `SURGE_MULTIPLIER` (5×) the normal rate (`BASELINE_CALLS_PER_HOUR`, default 20), and there are at least 5 calls.
  - **Evidence shown:** *"18 calls in 3 min (normal ≈ 1). 5 about the outage. 0 red flags waiting."*
  - **Accept** turns surge mode on.
  - **Not yet** snoozes for 2 min. It then asks again with updated numbers, including callers who hung up early (`disconnection_reason = user_hangup` in under 30 s).
  - The prompt closes itself if the volume drops back under the threshold.
- **What surge mode changes:**
  - New calls get the surge callback windows and the active status message (see 2) through the inbound webhook.
  - The board switches to surge view.

### 2. Status message for every caller

- **Templates, not new wording.** Wording approved on a calm day for likely events (power outage, fire, earthquake, IT outage) lives in `app/supervisor/messages.py`. Each template is tied to a cluster (`outage`, …).
- **Suggestion:** when one cluster is ≥ 40% of calls in the last 10 min (at least 5 calls), the backend suggests the matching template, for example *"The ER is open on backup power. We can't share patient information by phone."* The supervisor activates it as is, or edits it first. The active text, edited or not, is saved in `surge_state.status_message`.
- **How every caller hears it:** through Retell's **inbound call webhook** (`POST /retell/inbound`).
  - Before each phone call is answered, Retell asks our backend for that call's variables. We return `surge_banner` (the active message, or `""`), `incident_status`, the callback windows, and `nurse_line` (see Red-flag calls).
  - It works from the very next call, with no redeploy.
  - If our backend is down, Retell falls back to the agent's default variables after 3 tries.
- **Where it plays:** in the greeting, as **one sentence** right after "I'm an automated assistant…" and before the safety questions. Outage callers hear the answer within seconds, and the safety screen still comes before any other question. *Check this placement with whoever owns the clinical rules.*

### 3. Staffing suggestions

The math is simple and visible. It uses the last 30 min of calls, and the supervisor sees the inputs as well as the result.

| Role | How it's estimated | Example suggestion |
|---|---|---|
| **Nurses** (phones and callbacks) | Nurse minutes needed per hour = red calls/h × `RED_MIN` (10) + amber callbacks/h × `AMBER_MIN` (8). Nurses needed = ceil(minutes ÷ 60 ÷ 0.8 utilization), minus `NURSES_ON_PHONES`. Also triggers if the oldest amber caller has waited past the 15-min target, or if 2+ red calls in 10 min ended `no_answer` | *"Call in 2 nurses: 14 callers in 'A person soon', oldest waiting 22 min (target 15)."* |
| **Doctors** (ER) | **Rough signal only.** Phone calls can't measure how full the ER is. Tiers are based on the rate of red-flag injury and illness calls: ≥ 6/h → "consider 1–2 ER doctors", ≥ 15/h → "consider 3+" | *"Consider calling in 1–2 ER doctors: 9 injury red-flag calls in 30 min (normal ≈ 0)."* |

Accepting a staffing suggestion only **records** the decision as an event. Actually paging staff is out of scope for v1. A new suggestion opens only when the number goes up, so the supervisor isn't asked the same thing every 15 s.

## Database (`schema.sql`): 6 tables

| Table | What it holds |
|---|---|
| `calls` | One row per call. **Identity:** `call_id`, `source` (`retell`/`simulated`), `scenario`, `status`, `from_number`, `started_at`, `ended_at`, `duration_ms`, `disconnection_reason`. **Supervisor fields:** `lane`, `red_flags[]`, `cluster`, `intent`, `reason`, `urgency`, `caller_name`, `callback_number`, `needs_review`. **Classifiers:** `rules_result` jsonb, `jev_result` jsonb. **Details:** `details` jsonb. **Red-flag handoff:** `red_flag_at`, `transfer_started_at`, `transfer_ended_at`, `transfer_target`, `transfer_status`. **Post-call:** `summary`, `recording_url`, `recording` (bytea audio), `raw` jsonb (latest webhook `call` object, which includes the final transcript and Retell's analysis) |
| `transcript_items` | Live transcript, upserted by `(call_id, item_id)`, since Retell re-sends a growing turn under the same id. Roles: user, agent, tool call, `node_transition`, `injected` |
| `events` | One log for everything: `id`, `call_id` (nullable), `actor` (`system`/`supervisor`), `type`, `payload` jsonb, `created_at`. System types: webhooks, `red_flag_detected`, `context_injected`, `lane_raised`, `rules_miss`, `stt_model_mismatch`, `detail_confirmed`, `detail_rejected`. Supervisor types: surge on/off, message activated, suggestion decided, red alert resolved, nurse line changed, lane lowered |
| `suggestions` | `id`, `type` (`surge_mode`/`status_message`/`staffing_nurses`/`staffing_doctors`/`red_not_connected`), `call_id` (for red alerts), `evidence` jsonb (the numbers shown), `recommendation` jsonb, `status` (`open`/`accepted`/`snoozed`/`dismissed`/`resolved`/`expired`), `snooze_until`, `created_at`, `decided_at` |
| `nurse_lines` | `id`, `label`, `number` (E.164), `role`, `on_duty`, `priority`, `updated_at` |
| `surge_state` | One row: `on`, `switched_at`, `status_message` (active text or null), surge callback windows |

**Lane rule:** a lane only ever goes up in SQL. During the call, node transitions set it: `handoff_now` → red, `person_soon` → amber, `info_status`/`callback_routine` → green. Nothing in the code lowers a lane.

## API for the future frontend (`app/api.py`)

| Endpoint | Returns |
|---|---|
| `GET /api/board` | Counts per lane, clusters (count, red-flag count), ranked amber queue |
| `GET /api/calls?lane=&source=&status=` | Call list, newest first |
| `GET /api/calls/{id}` | Call (with details and their confirmed/unconfirmed status) + transcript + events (the Handoff Card data) |
| `GET /api/calls/{id}/recording` | Audio |
| `GET /api/analytics?minutes=60` | Calls per 5 min (surge detection), lane mix, rules-vs-Jev agreement, rules misses, detail confirmation rate, how often the speech model and the transcript disagreed, red-flag handoff time and share told to call 911 |
| `GET /api/suggestions?status=open` | Open suggestions with evidence, red alerts first |
| `POST /api/suggestions/{id}/accept`, `/snooze`, `/dismiss`, `/resolve` | Supervisor decisions. `snooze` = "Not yet, ask in 2 min". `resolve` closes a red alert with an outcome (`called_back`/`reached_911`/`unreachable`) |
| `GET /api/surge`, `POST /api/surge` | Read or switch surge mode |
| `GET /api/status-messages`, `POST /api/status-message` | List the templates; set the active text (a template, edited or not, or `null` to stop) |
| `GET /api/nurse-lines`, `POST /api/nurse-lines`, `PATCH /api/nurse-lines/{id}` | List, add, or update nurse lines (number, on duty, priority) |
| `POST /retell/webhook`, `POST /retell/inbound`, `POST /retell/tools/capture_detail`, `POST /retell/tools/confirm_detail` | Called by Retell (signature-checked) |
| `GET /health` | OK |

## Simulated emergencies (`app/seed.py`)

```bash
uv run python -m app.seed serious_earthquake --count 40 [--drip 3] [--classify] [--jev] [--reset]
```

- **Scenarios:** `serious_earthquake`, `big_fire`, `small_fire`, `small_earthquake`, `tuesday`. Call templates are ported from `ui/night-ledger.html` (`SURGE`, `CHEST`, `TUESDAY`) and `solution_scenarios.md`.
- **`--drip 3`:** inserts one call every 3 s, so the board fills up live during the demo. With `serious_earthquake`, the volume ramps up, so the surge prompt, the outage status-message suggestion and the staffing suggestions all fire on their own within a few minutes. That's the 2:10 AM moment from `supervisor_decisions.md`.
- The seed also adds 2 demo `nurse_lines`.
- Simulated red calls get a `transfer_status`. Most are `connected`; a few are `no_answer`, so `red_not_connected` alerts show on the board.
- **Details:** each simulated call gets a `details` value. Most fields are `confirmed`; a few are `unconfirmed` or have a speech-model mismatch, so the board shows both states.
- **`--classify`:** runs the rules on each fake transcript. **`--jev`:** also calls Jev, so the demo shows real classifier output, not just pre-set labels.
- **`--reset`:** deletes only simulated rows.

## Files

**Changes to existing files:**
- `retell/ladder.mjs`:
  - If `S2S_MODEL` is set, write `s2s_model` instead of `model`, since Retell allows only one of the two.
  - Add the "details come from the transcript" rule and the `capture_detail` / `confirm_detail` custom tools (URL from `TOOLS_URL`, timeout 3 s), and change the read-back steps.
  - Add the directory names to `boosted_keywords`.
  - Add `{{surge_banner}}` to `begin_message`, right after the AI disclosure, and set `surge_banner: ""` in `default_dynamic_variables`.
  - Change `transfer_to_nurse`'s number from the hard-coded `NURSE_LINE` to `{{nurse_line}}`, with `nurse_line: NURSE_LINE` as the default. The 20 s ring time and the "hang up and call 911" line stay as they are.
- `.gitignore`: add `backend/.env` and `backend/.venv/`.

**New `backend/` folder:**
```
backend/
  pyproject.toml          fastapi, uvicorn, psycopg[binary,pool], retell-sdk, websockets, httpx, python-dotenv, rapidfuzz, dateparser, pytest
  docker-compose.yml      postgres:16
  .env.example            DATABASE_URL, RETELL_API_KEY, TYPESAFE_API_KEY, JEV_MODEL, JEV_MIN_CONFIDENCE, NURSE_LINE
  schema.sql
  app/
    main.py  db.py  webhooks.py  monitor.py  recordings.py  api.py  seed.py
    classify/    rules.py  jev.py  combine.py
    details/     extract.py (digits, spelling, dates, fuzzy+Jev)  readback.py  tools.py (the two tool endpoints)  directory.py (lists)
    supervisor/  config.py (thresholds)  messages.py (status templates)  engine.py (15 s check)  routes.py
    inbound.py   Retell inbound webhook → per-call variables (incl. top on-duty nurse line)
    handoff.py   transfer outcome tracking, red_not_connected alerts
  tests/
    test_rules.py  test_combine.py  test_extract.py  test_confirm.py  test_engine.py
```

## Run order

1. `cd backend && cp .env.example .env`, then fill in the keys.
2. `docker compose up -d`, then `uv sync`, then `uv run uvicorn app.main:app --reload`.
3. Open a public tunnel to port 8000: `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`.
4. `cd retell && WEBHOOK_URL=https://<tunnel>/retell/webhook TOOLS_URL=https://<tunnel>/retell/tools S2S_MODEL=gpt-realtime-2.1 ./deploy.sh`, then publish the agent version (deploy only updates the draft).
5. Buy a phone number if there isn't one yet (`retell/README.md`). A phone call is needed so transfer and SMS work.
6. On that number, set **Inbound Webhook URL** to `https://<tunnel>/retell/inbound` (dashboard → Phone Numbers). This is per number, not per agent.

## Testing

1. **Unit:** `uv run pytest`.
   - Rules: "my dad's chest feels tight" → `chest_pain`; "where do I park" → nothing.
   - Combine: higher lane wins, and the lane never goes down.
   - Extract:
     - "four one five five five five zero one four two" → `4155550142`; "double five" → `55`.
     - "R as in Robert, E, Y, E, S" → `REYES`.
     - "blue cross" → `Blue Cross Blue Shield`.
   - Confirm:
     - "yeah that's right" → yes; "no, it's zero one four three" → no.
     - Agent says confirmed but the caller said "no" → **not** confirmed.
   - Engine, using fake `calls` rows:
     - 18 calls in 3 min → one open `surge_mode` suggestion; "Not yet" → none for 2 min, then a new one with updated numbers.
     - 60% outage calls → outage status-message suggestion.
     - 14 amber callers, oldest 22 min → nurse suggestion > 0.
     - Same numbers again → no duplicate suggestion.
   - Handoff:
     - Red call with `transfer_status = no_answer` → one `red_not_connected` alert, which can't be snoozed or dismissed.
     - Nurse line choice returns the top on-duty line and skips off-duty ones.
2. **Jev smoke test:** classify 3 fixed transcripts (chest pain, family locating, outage question) and check the lanes come back red / amber / green.
3. **Simulation:** run `seed serious_earthquake --count 40 --classify --jev`. Check that `/api/board` and `/api/analytics` show lanes, clusters and rules-vs-Jev agreement.
   - **Surge demo:** run `seed serious_earthquake --drip 3`, then watch `GET /api/suggestions`. The surge prompt should appear first, then the status-message and staffing suggestions. Accept the surge prompt and activate the outage message. `GET /api/surge` shows surge mode on.
4. **Live call A (details):** ask to reschedule. Give your name, spell it, and give a callback number. Say "no" to the first read-back, then correct it. Check that:
   - the agent reads back the **transcript** version, digit by digit / spelled,
   - `calls.details.callback_number` has `attempts = 2` and status `confirmed`, `calls.callback_number` matches, and any `stt_model_mismatch` events show where the speech model heard it differently,
   - the tool request from Retell really contains the speech-to-text transcript on an s2s agent.
5. **Live call B (red flag, with surge mode on):** the greeting should include the active status message. Answer "no" to the safety questions, ask about billing, then say "my wife just fainted." Check that:
   - transcript rows and live classifications appear **during** the call,
   - `red_flag_detected` → `context_injected` is logged and the agent transfers,
   - the transfer rings the nurse line from `nurse_lines` (change it via the API first, to prove the backend picks the number),
   - after you answer the "nurse" phone: `transfer_status = connected` and the handoff times are filled in,
   - **repeat without answering the nurse phone:** after 20 s the agent says to call 911, `transfer_status = no_answer`, and a `red_not_connected` alert is open,
   - about 30 s after the call, the summary, `lane='red'`, `jev_result` and the recording are in the DB,
   - `node retell/lastcall.mjs` matches what's in the DB.
6. **If the live calls fail:** redeploy without `S2S_MODEL` and repeat. That separates an s2s problem from a backend problem.
