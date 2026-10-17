# Night Ledger: Response Ladder

Steps run from gentlest (0) to most urgent (5). A trigger only ever moves a caller up. Only a person can lower a lane.

| Step | What happens | What moves you up a step | Who acts |
|---|---|---|---|
| **0. Watch** (always on) | Every call is logged and grouped into clusters ("61 callers mention the outage, 0 red flags"). The supervisor sees one card instead of 140 calls. | A cluster gets bigger, or a red flag appears inside one, so the card rises to the top of the board and a broadcast action is suggested. | **AI** spots clusters. **Supervisor** decides whether to act. |
| **1. Ask** (every caller) | The AI says it's an AI and offers a human. It asks 2–3 fixed red-flag questions, then why the person is calling. | Any red-flag "yes" → straight to **5**. The caller asks for a human, sounds confused or impaired, or the AI can't hear them clearly → **4**. Otherwise the call goes to the lane for its reason. | **AI** asks. Rules and the LLM both classify, and the higher tier wins. |
| **2. Slow** (🟢 info callers) | An honest status message ("ER is open, we know about the outage") plus an SMS link. Many callers get their answer and hang up. | The caller says the answer didn't help or wants more → **3**. A red-flag word comes up mid-call → **5**. | **AI** delivers the message. **Supervisor** approves the wording before it goes live. |
| **3. Hold: can wait** (🟢 routine) | Scheduled callback with a promised time window. Confirmed by SMS. | Callback window missed, caller calls again, or a vulnerability signal appears (elderly, recently discharged) → **4**. | **AI** schedules and calls back. **Staff** handle the callbacks once the surge eases. |
| **4. Hold: a person soon** (🟠) | Callback queue visible on the supervisor board: family reunification, mental health (non-acute), child under 2, hospice, confused callers. The AI never gives out patient status. | Caller unreachable twice → supervisor alert. Distress or a red flag on callback → **5**. Queue time runs past its target → flagged at the top. | **Human** (nurse, supervisor, social work) makes every callback. The AI only collects details and keeps the queue. |
| **5. Hand to a person** (🔴 now) | Warm transfer in under 10 seconds with a Handoff Card: who, which red flags, callback number, transcript. | No human answers within the timeout → the AI tells the caller to hang up and call 911, then retries and alerts the supervisor. That is the top of the ladder. | **Nurse or supervisor** takes the call. The AI only connects the call and passes on the context. |

## Rules that hold across every step

- **One-way trigger.** The AI can move a caller up but never down. Only a person can lower a lane.
- **Broadcasts are human-only.** Mass alerts, outbound texts and declaring an incident always need a supervisor tap.
