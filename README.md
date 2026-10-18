# Night Ledger

**The after-hours answering line every night. The surge line on the worst night of the year, already running.**

InnovateLA × Dual-Use Hackathon 2026 · Communication track (Retell AI) · "On the Line"

When an earthquake, fire or outage hits at night, a hospital's phone line floods. Most callers want to know if the ER is open; a few are in real danger. A two-person night crew can't tell them apart until someone picks up. Night Ledger answers every call with a Retell voice agent, runs the same red-flag screen on every caller, sorts each one into a lane, and gives the overnight house supervisor one board where the only decisions left are the ones that need a person.

## The ladder

| Step | What happens | Who acts |
| --- | --- | --- |
| 0 Watch | Every call is logged and clustered ("61 callers mention the outage, 0 red flags") | AI clusters, supervisor decides |
| 1 Ask | AI says it's an AI, offers a person, asks 3 fixed red-flag questions | AI; rules and model both classify, higher lane wins |
| 2 Slow | Approved status message plus an SMS link | AI delivers, supervisor approves wording |
| 3 Hold: can wait | Scheduled callback with a promised window | AI books, staff call back |
| 4 Hold: a person soon | Ranked callback queue: family locating, child under 2, mental health, confused callers | A human makes every callback |
| 5 Hand to a person | Warm transfer to a nurse in under 10 s with a Handoff Card | Nurse takes the call |

The AI can move a caller **up**, never down. Surge mode, broadcasts and staff call-ins always need a supervisor click.

## What's in the repo

| Path | What it is |
| --- | --- |
| `retell/` | The Retell voice agent: one LLM state per rung, edges only point up (`ladder.mjs`, `deploy.sh`) |
| `backend/` | FastAPI + SQLite: Retell webhooks, inbound webhook, rules classifier, optional Jev classifier, supervisor engine, simulator, REST API |
| `backend/app/static/` | The supervisor board (no build step) |
| `ui/night-ledger.html` | The first static prototype |
| `*.md` | Problem, ladder, scenarios, dual-use case, supervisor decisions, research, backend plan |

## Run it

```bash
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000, go to **Demo controls** and start **Serious earthquake**. Within a couple of minutes the surge prompt, the outage status-message suggestion, staffing suggestions and a red-caller-not-connected alert appear on their own.

Tests: `uv run --group dev pytest`

### Live phone calls (optional)

1. Expose the backend: `cloudflared tunnel --url http://localhost:8000`
2. Deploy the agent with the webhook: `cd retell && WEBHOOK_URL=https://<tunnel>/retell/webhook ./deploy.sh`, then publish it in the Retell dashboard.
3. On the phone number, set the **Inbound Webhook URL** to `https://<tunnel>/retell/inbound`. Each call then gets the active status message (`{{surge_banner}}`) and the top on-duty nurse line (`{{nurse_line}}`).

Real calls appear on the board with a purple **Live call** chip.

## How a call is classified

1. **Rules** (`backend/app/classify/rules.py`): keyword and regex lists for the 12 red flags, the person-soon reasons and topic clusters. Instant and predictable.
2. **Model**: Retell's post-call analysis, plus TypeSafe Jev when `TYPESAFE_API_KEY` is set (`classify/jev.py`).
3. **Combine** (`classify/combine.py`): the higher lane always wins, and a stored lane never drops. In the demo, the "dad's chest feels tight" caller is labelled a status question by the model (52%) and still lands in red because the rules catch it.

## What's simulated

The demo uses scripted calls (`backend/app/scenarios.py`) inserted directly into the database, so the board fills like a real night without a phone. They run through the real rules classifier and the real supervisor engine. Call volumes are illustrative, not measured.

## Responsible use

Night Ledger could be misused to deflect callers who need a person, or to give medical advice by phone. We limit this structurally: every call gets the same red-flag screen first, red flags go straight to a nurse, the AI can never lower a lane or share patient information, and every broadcast and staffing decision needs a named supervisor click recorded in the log.

## Not built yet

- Detail capture and read-back tools (`capture_detail` / `confirm_detail`, backend plan section "Capturing key details")
- Live transcript sidecar over Retell's monitor socket (`update_live` steering on a red flag)
- Downloading call recordings into the database
