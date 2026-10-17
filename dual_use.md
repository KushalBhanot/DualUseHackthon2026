# Night Ledger: Dual Use

A dual-use tool earns its keep on an ordinary day, so it is already in place and trusted when the crisis comes. Night Ledger is an after-hours answering line every night, and the surge line on the worst night of the year.

## Two lives, one system

| | Ordinary Tuesday | The worst night |
|---|---|---|
| **Who uses it** | The on-call nurse at a small hospital or clinic network's after-hours line | The overnight house supervisor at a hospital under surge |
| **Who pays** | The hospital or clinic network | The same hospital |
| **Volume** | A call every few minutes | Calls every few seconds |
| **Mode** | Surge mode off | Surge mode on, switched on by the supervisor |
| **Main rungs** | Ask, Hold, Hand | All five: Watch, Ask, Slow, Hold, Hand |
| **Decision the person makes most** | Who to call back first | Whether to switch on surge mode, then who to call back first |

Nothing is installed or switched over during the crisis. The red-flag screen, the lanes, the Handoff Card and the callback queue are the same on both nights. Surge mode is one switch.

## The second customer

**The on-call nurse at a small hospital or clinic network's after-hours line, on any Tuesday night.** The hospital is the buyer and the nurse is the user.

**Today.** Many of these places pay an answering service at night. It takes messages with a callback number and little else. The nurse works through them in arrival order, with no idea which one is urgent until they call back.

**With Night Ledger, 9:40 PM on a Tuesday.**
- A refill request, a reschedule and a visiting-hours question are handled by the AI on its own.
- A patient discharged yesterday who is unsure about a new blood thinner dose goes to *A person soon*, with a callback within 15 minutes.
- A post-op patient whose wound is bleeding through the dressing goes straight to the on-call nurse, with a Handoff Card.

The nurse makes the same decision every night that the supervisor makes on a surge night: who needs a person first. The "Ordinary Tuesday" toggle in the demo UI shows this.

## Why it earns its keep on an ordinary day

- **Fewer missed calls.** Unanswered calls are a known problem for hospital lines. Tampa General reported that daily call abandonment fell from 34% to 14.9% within two weeks of adding an AI voice agent (Hyro case study, a vendor figure).
- **Context at handoff.** Most answering services pass on a callback number, not a summary. The Handoff Card means the nurse doesn't re-ask the basics.
- **Safer sorting.** The red-flag screen runs on every call, so an urgent caller isn't stuck behind routine messages.
- **Lower cost than staffing the phones overnight**, for places that can't justify a 24/7 nurse line.

## Why ordinary-day use makes the crisis use work

- **The rules are already tuned.** Months of Tuesday nights show where the red-flag screen over- or under-triages, before it matters most.
- **Staff already trust it.** The nurse and supervisor know what a Handoff Card looks like and what the lanes mean. Nobody is learning a new tool at 2 AM.
- **It is already connected.** Phone routing, the escalation list and the status-message templates are in place.
- **It runs separately from the EHR**, so it keeps working when the main hospital systems are down (as in the July 2024 CrowdStrike outage).

## Other ordinary-day uses

- **Monday-morning scheduling peak** at a patient access center: the same lanes and callbacks smooth out the busiest hours.
- **Visitor information line**: hours, parking and directions, a large, low-risk share of switchboard calls.
- **Planned IT downtime**: a status message and callbacks while systems are offline.

## One line for the pitch

"Every night it's the after-hours answering line. On the worst night of the year it's the surge line, already running."
