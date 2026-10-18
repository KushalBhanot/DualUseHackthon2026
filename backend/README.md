# Night Ledger backend

FastAPI + Postgres. Stores every Retell call (live transcript, details, transfer outcome, summary, audio),
classifies calls with rules + Jev, steers the agent on red flags, and suggests supervisor decisions.
Design: [../backend_plan.md](../backend_plan.md).

## Run it

```bash
cd backend
cp .env.example .env            # add RETELL_API_KEY; TYPESAFE_API_KEY is optional (rules-only without it)

# Postgres 16 (either one)
docker run -d --name ledger-db -e POSTGRES_USER=ledger -e POSTGRES_PASSWORD=ledger -e POSTGRES_DB=ledger \
  -p 5432:5432 -v ledger_pgdata:/var/lib/postgresql/data postgres:16
# docker compose up -d          # if your Docker has Compose

uv sync
uv run uvicorn app.main:app --port 8000      # schema is applied on startup
```

## Simulated emergencies (no Retell needed)

```bash
uv run python -m app.seed serious_earthquake --count 40 --classify --reset   # a surge, instantly
uv run python -m app.seed serious_earthquake --drip 3 --reset                # one call every 3 s, for the demo
uv run python -m app.seed tuesday --reset                                    # a quiet night: no surge prompt
uv run python -m app.seed --reset                                            # clear simulated data
```

Scenarios: `serious_earthquake`, `big_fire`, `small_fire`, `small_earthquake`, `tuesday`. Add `--jev` (with `--classify`) to run Jev too.

## Connect Retell (live calls)

With the backend running, in a second terminal:

```bash
cd retell
./connect.sh               # speech-to-speech (gpt-realtime-2.1)
S2S_MODEL= ./connect.sh    # or the text model
```

It opens a public tunnel to port 8000. Then it redeploys and publishes the agent with the tunnel's webhook and tool URLs. Finally it sets the phone number **+12139283405** to answer with that agent, with its **inbound webhook** pointing at `/retell/inbound`. Keep it running during calls, and re-run it after any restart. Use `PHONE_NUMBER=+1... ./connect.sh` for a different number.

**Tunnel:** it tries cloudflared first, then falls back to localtunnel (`npx localtunnel`, no account). Some networks block `trycloudflare.com` and ngrok; venue and campus Wi-Fi often do, and that includes the one this was built on. localtunnel asks for the fixed name `night-ledger-<your user>.loca.lt`, so the URL usually stays the same between runs. Force one with `TUNNEL=localtunnel` or `TUNNEL=cloudflared`.

## Endpoints

| | |
|---|---|
| `GET /api/board` | lanes, clusters, red calls, ranked "person soon" queue, surge state |
| `GET /api/calls`, `GET /api/calls/{id}` | call list; one call with details, transcript, events, alerts (Handoff Card) |
| `GET /api/calls/{id}/recording` | audio |
| `GET /api/analytics?minutes=60` | volume, lane mix, rules vs Jev, details, handoff timing |
| `GET /api/suggestions` · `POST /api/suggestions/{id}/accept\|snooze\|dismiss\|resolve` | supervisor decisions |
| `GET/POST /api/surge`, `GET /api/status-messages`, `POST /api/status-message` | surge mode and the status message |
| `GET/POST /api/nurse-lines`, `PATCH /api/nurse-lines/{id}` | nurse lines for red transfers |
| `POST /retell/webhook`, `/retell/inbound`, `/retell/tools/capture_detail`, `/retell/tools/confirm_detail` | called by Retell (signature-checked) |

Interactive docs: http://localhost:8000/docs

## Tests

```bash
uv run pytest -q      # uses its own database, ledger_test, created automatically
```

## Layout

```
app/
  main.py  settings.py  db.py  retell_auth.py
  webhooks.py   call_started / call_ended / call_analyzed
  monitor.py    live transcript over Retell's monitor socket, classification, steering on red flags
  handoff.py    nurse line, transfer outcome, red_not_connected alerts
  inbound.py    per-call variables: status message, callback windows, nurse line
  recordings.py audio download
  api.py        read endpoints
  seed.py       simulated emergencies
  classify/     labels.py  rules.py  jev.py  combine.py  service.py
  details/      directory.json  extract.py  readback.py  confirm.py  tools.py
  supervisor/   config.py (thresholds)  messages.py (approved wording)  engine.py (15 s check)  routes.py
```
