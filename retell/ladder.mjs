// Night Ledger surge-line agent, defined as the response ladder in solution_ladder.md.
// Run `node ladder.mjs` to write build/llm.json and build/agent.json for the Retell CLI.
//
// Each rung is a Retell LLM *state*. Edges only point up the ladder, so the
// "one-way trigger" rule is structural: the AI has no edge that lowers a lane.

import { mkdirSync, writeFileSync } from "node:fs";

const NURSE_LINE = process.env.NURSE_LINE || "+12139940320"; // E.164; your phone for demos
const VOICE_ID = process.env.VOICE_ID || "11labs-Adrian";
const LLM_ID = process.env.LLM_ID || "__LLM_ID__";
const WEBHOOK_URL = process.env.WEBHOOK_URL || null;

// Supervisor-approved wording. Changing these is the "approve before it goes live" step:
// edit, rebuild, `retell update-retell-llm`. The agent may not add facts beyond them.
const approved = {
  hospital_name: "Harbor General Hospital",
  incident_status:
    "A strong earthquake hit at about 2 AM and parts of the city have lost power. " +
    "Harbor General's emergency room is open and running on backup power. " +
    "Appointments tomorrow morning are still on unless we call you. " +
    "We cannot share any patient information by phone.",
  status_url: "https://example.org/harbor/status",
  volunteer_url: "https://example.org/harbor/help",
  pio_contact: "our public information office at 555-0100",
  routine_callback_window: "tomorrow morning between 8 and 11",
  priority_callback_window: "within 30 minutes",
};

const RED_FLAGS = [
  "chest_pain", "breathing", "bleeding", "stroke", "unresponsive", "seizure",
  "self_harm_or_violence", "overdose_poisoning", "severe_allergy",
  "pregnancy_bleeding_or_pain", "infant_fever", "caller_in_danger",
];

const PERSON_SOON_REASONS = [
  "asked_for_person", "confused_or_unclear", "family_locating", "mental_health",
  "child_under_2", "hospice", "recent_discharge", "vulnerable_caller",
  "repeat_caller", "info_did_not_help_and_vulnerable",
];

// ---------------------------------------------------------------- prompts

const general_prompt = `
## Who you are
You answer overflow calls for {{hospital_name}} at night during an emergency surge. You are an automated assistant, not a nurse or doctor. Your job is to sort each caller to the right help fast. You never diagnose or treat.

## Situation (supervisor-approved, use ONLY these facts)
{{incident_status}}
Never add, guess or stretch facts about the incident, wait times, or the hospital. If asked something not covered here, say you don't know and that staff can call back.

## Rules that hold in every step
1. RED FLAGS BEAT EVERYTHING. If at any moment the caller mentions any of these, for anyone, transition to handoff_now immediately, even mid-question:
   chest pain or pressure; trouble breathing or choking; bleeding that won't stop; stroke signs (face drooping, arm weakness, slurred speech); someone unconscious, unresponsive or who fainted; a seizure; thoughts of suicide, self-harm or hurting someone; overdose or poisoning; severe allergic reaction or throat swelling; pregnant with bleeding or severe pain; a baby under 3 months with a fever; the caller is in danger or can't talk freely.
   If you are unsure whether something is a red flag, treat it as one.
2. ONLY MOVE UP. Once a caller has been moved to a more urgent step, never go back down, even if they say it's fine now. Only staff can lower urgency.
3. NEVER GIVE PATIENT INFORMATION. Do not confirm or deny whether anyone is or was at the hospital, their condition or location, even to family. Say: "I can't share patient information by phone, but a staff member will call you back."
4. NEVER give medical advice, a diagnosis, or reassurance like "that's probably fine". The only instructions you may give are the safety lines in handoff_now.
5. NEVER promise a time you were not given. Callback times: routine is {{routine_callback_window}}; priority is {{priority_callback_window}}.
6. If you can't understand the caller after one clarifying question, or they sound confused, disoriented or impaired, move them to person_soon.
7. If the caller asks for a person, human, nurse or operator, honor it: move to person_soon (or handoff_now if any red flag).
8. When more than one route applies, the more urgent wins: handoff_now > person_soon > callback_routine > info_status.

## How you speak
Calm, warm, plain. One or two short sentences per turn. One question at a time. No lists, no jargon, no filler sympathy. If the caller speaks another language, answer in that language if you can.
`.trim();

const ask_prompt = `
## Step 1: Ask (every caller)
Your greeting already said you are an automated assistant and asked safety question 1.

Ask the safety questions in order, one per turn. Skip any the caller already clearly answered.
- Q1 (in greeting): anyone with chest pain, trouble breathing, or bleeding that won't stop?
- Q2: "Is anyone passed out, having a seizure, or showing stroke signs like a drooping face or slurred speech?"
- Q3: "Is anyone in danger, or thinking about hurting themselves or someone else?"

Any "yes", "maybe", "I think so", or a hesitant answer that might be yes: transition to handoff_now right away.
If the caller jumps to their reason before you finish: if it contains a red flag, go to handoff_now; otherwise say "Got it, I'll help with that in a moment. One more safety question first." and continue.

After clear "no"s to all three, ask: "Thank you. What are you calling about tonight?"
Then route on the reason (the more urgent route wins):
- person_soon: looking for a family member or someone who may have been brought in; emotional distress, panic or a mental health concern (no danger); a child under 2 with any symptom; a hospice or end-of-life patient; discharged in the last 2 weeks with a symptom or medication question; elderly or alone and struggling; asks for a person; confused or hard to understand.
- callback_routine: scheduling, refills, billing, records, or other non-urgent business.
- info_status: questions about the incident or the hospital's status (is the ER open, power, parking, visiting), patient portal trouble, offers of help (blood, volunteering), or media.
`.trim();

const info_prompt = `
## Step 2: Slow (status message)
Give the approved status in a few short sentences, using only the facts in the Situation section. Then offer: "I can text you a link with live updates. Would that help?" If yes, call send_status_link.
- Blood donors or volunteers: thank them and call send_volunteer_link.
- Off-duty clinical staff offering to come in: thank them, then go to callback_routine so we can take their name, role and number for the staffing desk.
- Media: "Please contact ${approved.pio_contact}." Give no statement, numbers or details.

Then ask: "Did that answer your question?"
- Yes: thank them, remind them to call 911 if anyone gets worse, and call end_call.
- No, wants more, or needs something you can't answer: go to callback_routine.
Any red flag: handoff_now. Asks for a person, sounds distressed, or a vulnerability comes up: person_soon.
`.trim();

const callback_prompt = `
## Step 3: Hold, can wait
Say: "That's not something we can handle tonight, but I can book a callback for {{routine_callback_window}}."
Collect one at a time: their name; the best callback number (if {{user_number}} looks like a phone number, ask "Is the number you're calling from the best one?"); and one sentence on what they need.
Read back the name, number and window. Call send_callback_confirmation, then say "If anything gets worse before then, call 911," and call end_call.

Keep listening for vulnerability. Go to person_soon if: the caller or the patient is 75 or older or frail; discharged in the last 2 weeks; pregnant; a child under 2 is involved; they live alone and are struggling; they say they already called tonight and no one called back; or their worry is rising.
Any red flag: handoff_now.
`.trim();

const person_soon_prompt = `
## Step 4: Hold, a person soon
Tell them a staff member, such as a nurse, supervisor or social worker, will call them back {{priority_callback_window}}. You only collect details. You do not solve the problem.

Collect one at a time, skipping what you already know:
1. FIRST, their name and best callback number. Read the number back. This matters most.
2. Then, by reason:
   - Family locating: the person's full name, approximate age, what they look like or were wearing, and where they were last. If pressed, repeat: "I can't share patient information, but staff will call you back."
   - Child under 2: the child's age and main symptom. Ask: "Is the baby breathing hard, hard to wake, or turning blue or gray?" If yes: handoff_now.
   - Distress or mental health: slow down and stay with them. Ask: "Are you having any thoughts of hurting yourself?" If yes: handoff_now. Also say: "You can call or text 988 any time, day or night."
   - Recent discharge or medication question: what they were treated for and the medication name.
   - Confused caller: keep it very simple. Get a callback number or where they are, and whether someone is with them.
3. Close: "Staff will call you back at [number] {{priority_callback_window}}. If anything gets worse before then, call 911." Then call end_call.

Any red flag or rising distress: handoff_now. Never move this caller to a gentler step.
`.trim();

const handoff_prompt = `
## Step 5: Hand to a person, NOW
Your only job is to get this caller to a nurse within seconds.
Say one short line: "I'm connecting you to a nurse right now. Please stay on the line." Then immediately call transfer_to_nurse. Do not ask any other question first.

While connecting, you may say at most ONE of these lines, word for word, if it matches:
- Bleeding: "Press firmly on the wound with a clean cloth and don't let go."
- Smoke or trouble breathing: "If you can, get to fresh air."
- Someone not breathing, or the caller is in danger: "If they're not breathing or you're in danger, hang up and call 911 now."

If the transfer fails or no one answers, say: "No one could pick up. Please hang up and call 911 now." Then call end_call.
Never move this caller back to a lower step.
`.trim();

// ---------------------------------------------------------------- edges (up only)

const toHandoff = {
  destination_state_name: "handoff_now",
  description:
    "STEP 5. Use immediately when any red flag is mentioned or a safety question is answered yes or maybe. Takes priority over every other transition.",
  parameters: {
    type: "object",
    properties: {
      red_flag: { type: "string", enum: RED_FLAGS, description: "The red flag that fired." },
      summary: { type: "string", description: "One sentence: who, what, since when." },
    },
    required: ["red_flag", "summary"],
  },
};

const toPersonSoon = {
  destination_state_name: "person_soon",
  description:
    "STEP 4. The caller needs a human callback soon: asked for a person, confused/unclear, family locating, mental health, child under 2, hospice, recent discharge, vulnerable or repeat caller. Do not use if there is a red flag (use handoff_now).",
  parameters: {
    type: "object",
    properties: {
      reason: { type: "string", enum: PERSON_SOON_REASONS },
    },
    required: ["reason"],
  },
};

const toCallback = {
  destination_state_name: "callback_routine",
  description:
    "STEP 3. Routine business that can wait for a scheduled callback, or a status answer that didn't help. Not for red flags or vulnerable callers.",
};

const toInfo = {
  destination_state_name: "info_status",
  description:
    "STEP 2. Questions about the incident or hospital status, portal problems, offers of help, or media, with all safety questions answered no.",
};

// ---------------------------------------------------------------- tools

const end_call = {
  type: "end_call",
  name: "end_call",
  description: "End the call after you have said your closing line.",
};

const sms = (name, description, sms_content) => ({
  type: "send_sms",
  name,
  description,
  sms_content,
  sms_destination: { type: "customer_number" },
  speak_after_execution: true,
});

const send_status_link = sms(
  "send_status_link",
  "Text the caller the supervisor-approved live status link.",
  { type: "predefined", text: `{{hospital_name}} update: the ER is open. Live status: {{status_url}}. If someone is getting worse, call 911.` },
);

const send_volunteer_link = sms(
  "send_volunteer_link",
  "Text a blood donor or volunteer the sign-up link.",
  { type: "predefined", text: `Thank you for offering to help {{hospital_name}}. Sign up here: {{volunteer_url}}` },
);

const send_callback_confirmation = sms(
  "send_callback_confirmation",
  "Text the caller a confirmation of their routine callback.",
  {
    type: "inferred",
    prompt:
      "Write one SMS under 300 characters from {{hospital_name}} confirming a callback {{routine_callback_window}} about the caller's request (one short phrase, no medical details). End with: If anything gets worse, call 911.",
  },
);

const transfer_to_nurse = {
  type: "transfer_call",
  name: "transfer_to_nurse",
  description: "Warm-transfer the caller to the on-duty nurse or house supervisor. Use immediately in handoff_now.",
  transfer_destination: { type: "predefined", number: "{{nurse_line}}" },
  transfer_option: {
    type: "warm_transfer",
    transfer_ring_duration_ms: 20000,
    on_hold_music: "ringtone",
    // The Handoff Card: spoken privately to the nurse before the caller is bridged in.
    private_handoff_option: {
      type: "prompt",
      prompt:
        "Brief the nurse in under 15 seconds, in this order: 'Night Ledger red handoff.' The red flag. Who the patient is and their age if known. The caller's name if known and callback number {{user_number}}. One sentence on what happened and when. Then say 'Connecting you now.'",
    },
  },
  speak_during_execution: false,
};

// ---------------------------------------------------------------- Retell LLM

const llm = {
  model: process.env.LLM_MODEL || "gpt-5.6-terra",
  model_temperature: 0,
  tool_call_strict_mode: true,
  start_speaker: "agent",
  begin_message:
    "{{hospital_name}}. I'm an automated assistant, not a person, and you can ask for a person at any time. {{surge_banner}} " +
    "First, a quick safety check: is anyone with you having chest pain, trouble breathing, or bleeding that won't stop?",
  general_prompt,
  general_tools: [],
  // surge_banner and nurse_line are replaced per call by the backend's inbound webhook (backend/app/webhooks.py).
  default_dynamic_variables: { ...approved, surge_banner: "", nurse_line: NURSE_LINE },
  starting_state: "ask",
  states: [
    { name: "ask", state_prompt: ask_prompt, edges: [toHandoff, toPersonSoon, toCallback, toInfo], tools: [] },
    { name: "info_status", state_prompt: info_prompt, edges: [toHandoff, toPersonSoon, toCallback], tools: [send_status_link, send_volunteer_link, end_call] },
    { name: "callback_routine", state_prompt: callback_prompt, edges: [toHandoff, toPersonSoon], tools: [send_callback_confirmation, end_call] },
    { name: "person_soon", state_prompt: person_soon_prompt, edges: [toHandoff], tools: [end_call] },
    { name: "handoff_now", state_prompt: handoff_prompt, edges: [], tools: [transfer_to_nurse, end_call] },
  ],
};

// ---------------------------------------------------------------- agent

// Post-call analysis is the feed for Step 0 (Watch): one structured row per call
// that the supervisor board clusters and ranks.
const post_call_analysis_data = [
  { type: "enum", name: "lane", description: "Highest lane reached. red = handed to a person now (step 5); amber = person callback soon (step 4); green = status message or routine callback (steps 2-3).", choices: ["red", "amber", "green"], required: true },
  { type: "enum", name: "ladder_step", description: "Highest ladder step the call reached.", choices: ["1_ask", "2_slow", "3_hold_can_wait", "4_hold_person_soon", "5_hand_to_person"], required: true },
  { type: "string", name: "red_flags", description: `Comma-separated red flags mentioned, from: ${RED_FLAGS.join(", ")}. "none" if none.`, required: true },
  { type: "enum", name: "cluster", description: "Topic for grouping similar calls on the supervisor board.", choices: ["outage", "family", "help", "media", "scheduling", "billing", "medication", "mental_health", "child", "injury_or_illness", "other"], required: true },
  { type: "string", name: "intent", description: "One short sentence: why they called, in plain words.", examples: ["Asking if the ER is open with the power out", "Looking for brother after the building collapse"], required: true },
  { type: "string", name: "escalation_reason", description: "Why the call was moved above step 2, or 'none'.", required: true },
  { type: "enum", name: "language", description: "Main language the caller spoke.", choices: ["en", "es", "ko", "hy", "zh", "vi", "tl", "other"] },
  { type: "string", name: "caller_name", description: "Caller's name if given, else 'unknown'." },
  { type: "string", name: "callback_number", description: "Callback number confirmed by the caller, else 'unknown'." },
  { type: "string", name: "callback_window", description: "Callback window promised to the caller, or 'none'." },
  { type: "string", name: "missing_person", description: "For family-locating calls: name, age, description, last known location. Else 'none'." },
  { type: "boolean", name: "needs_review", description: "True if the agent seemed unsure about routing, the caller was hard to understand, or the agent broke a rule (gave patient info, medical advice, or lowered a lane)." },
];

const agent = {
  agent_name: "Night Ledger Surge Line",
  response_engine: { type: "retell-llm", llm_id: LLM_ID },
  voice_id: VOICE_ID,
  language: "en-US",
  interruption_sensitivity: 0.9, // callers in panic must be able to cut in with a red flag
  enable_backchannel: true,
  backchannel_frequency: 0.3,
  reminder_trigger_ms: 8000,
  reminder_max_count: 2,
  end_call_after_silence_ms: 60000,
  max_call_duration_ms: 900000,
  boosted_keywords: ["chest", "breathing", "bleeding", "seizure", "stroke", "overdose", "unconscious", "fainted", "Harbor General", "MyChart"],
  post_call_analysis_data,
  ...(WEBHOOK_URL && { webhook_url: WEBHOOK_URL }),
};

mkdirSync(new URL("./build/", import.meta.url), { recursive: true });
writeFileSync(new URL("./build/llm.json", import.meta.url), JSON.stringify(llm, null, 2));
writeFileSync(new URL("./build/agent.json", import.meta.url), JSON.stringify(agent, null, 2));
console.error(`wrote build/llm.json and build/agent.json (llm_id=${LLM_ID}, nurse_line=${NURSE_LINE})`);
