# Night Ledger

**The after-hours answering line every night. The surge line on the worst night of the year, already running.**

InnovateLA × Dual-Use Hackathon 2026 · Communication track (Retell AI) · "On the Line"

**Try it live: https://night-ledger-neon.onrender.com** (free hosting: the first load after idle takes about a minute). Open **Demo controls** in the sidebar and start a scenario.

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

### Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/KushalBhanot/DualUseHackthon2026)

`render.yaml` builds `backend/Dockerfile` on Render's free plan. A fresh instance starts with a seeded earthquake surge (`DEMO_SEED`), so visitors land on a live board. The free plan sleeps after 15 idle minutes and takes about a minute to wake, and the SQLite data resets on each restart. The same Dockerfile runs on Fly.io, Railway or any container host.

### Live phone calls (optional)

1. Expose the backend: `cloudflared tunnel --url http://localhost:8000`
2. Deploy the agent with the webhook: `cd retell && WEBHOOK_URL=https://<tunnel>/retell/webhook ./deploy.sh`, then publish it in the Retell dashboard.
3. On the phone number, set the **Inbound Webhook URL** to `https://<tunnel>/retell/inbound`. Each call then gets the active status message (`{{surge_banner}}`) and the top on-duty nurse line (`{{nurse_line}}`).

Real calls appear on the board with a purple **Live call** chip.

## What the board does

- **Surge prompt, status message, staffing:** suggestions with the numbers behind them; every action is one supervisor click, logged.
- **Lanes and Handoff Cards:** Now / A person soon / Can wait, with rules-vs-model reasoning, transcript and transfer timing.
- **AI callbacks to hang-ups:** every caller who hangs up within 30 s gets an AI callback that says it's an AI and asks "Do you need help?". A red flag on the callback goes straight to a nurse; two unanswered callbacks open an alert only a person can close. Live outbound calls need `RETELL_API_KEY`, `RETELL_FROM_NUMBER` and `RETELL_CALLBACK_AGENT_ID`.
- **Hotspots and a brief for incident command:** calls grouped by place and topic over the last 15 minutes, written up as a facts-only brief the supervisor copies and marks as sent. This is the gap the Eaton fire review found: what callers reported didn't reach incident command.
- **Language access:** callers are answered in their language; the Handoff Card shows the original and the live English translation, and the rules classify the English.
- **After-action report:** `/api/report` writes the night up from the log: decisions with names, red handoff times, callbacks, hotspots and languages. Print or save as PDF.

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
