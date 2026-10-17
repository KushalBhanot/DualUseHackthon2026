# Night Ledger surge line (Retell agent)

The Retell voice agent for rungs 1–5 of `../solution_ladder.md`. Each rung is a Retell LLM state, and edges only point up the ladder:

```
ask ──▶ info_status ──▶ callback_routine ──▶ person_soon ──▶ handoff_now
 │            │                 │                  ▲              ▲
 └────────────┴─────────────────┴──────────────────┴──────────────┘
           (every state has a direct edge to person_soon and handoff_now)
```

| Ladder step | State | What the agent does |
|---|---|---|
| 1 Ask | `ask` | Discloses that it is an AI and offers a person. Asks 3 fixed red-flag questions, then the reason for the call. |
| 2 Slow | `info_status` | Reads the approved `{{incident_status}}` and texts the status link. |
| 3 Hold: can wait | `callback_routine` | Books a callback in `{{routine_callback_window}}` and texts a confirmation. |
| 4 Hold: person soon | `person_soon` | Takes the details for a staff callback in `{{priority_callback_window}}`. Never gives patient status. |
| 5 Hand to a person | `handoff_now` | Warm-transfers to `NURSE_LINE`, briefing the nurse privately first (the Handoff Card). If the transfer fails, tells the caller to call 911. |
| 0 Watch | post-call analysis | Fills in `lane`, `ladder_step`, `red_flags`, `cluster` and `intent` on every call, for the supervisor board. |

## Setup

```bash
npm install -g @retell-ai/retell-cli   # official CLI, Node 22+
# If `retell` is still "command not found", alias it (deploy.sh already falls back to npx):
alias retell='npx --yes @retell-ai/retell-cli'
retell auth login                      # paste an API key from dashboard.retellai.com → API Keys
retell list-voices --output table      # pick a voice_id if you don't want the default
```

## Deploy

```bash
export NURSE_LINE=+1XXXXXXXXXX   # the phone a teammate holds as "the nurse"
export VOICE_ID=11labs-Adrian    # optional
./deploy.sh --dry-run            # check the requests first
./deploy.sh                      # creates the LLM and agent, saves the ids to .ids.env
```

Re-run `./deploy.sh` after you edit `ladder.mjs`. It updates both in place.

**Supervisor-approved wording.** Change `approved` in `ladder.mjs` and re-deploy. Or, for a single call, override it with `--retell-llm-dynamic-variables`.

## Talk to it

- **Browser:** dashboard → Agents → *Night Ledger Surge Line* → Test. This is a web call, so it can't do the transfer or send texts, but the transition and transfer tool calls still show up in the transcript.
- **Real phone** (transfer and SMS work):
  ```bash
  source .ids.env
  retell create-phone-number --area-code 415 --nickname night-ledger \
    --inbound-agents "[{\"agent_id\":\"$AGENT_ID\",\"weight\":1}]"
  ```

## Simulated callers (no phone needed)

```bash
source .ids.env && node scenarios.mjs
ids=$(for f in build/tests/*.json; do retell create-test-case-definition --body "$f" | node -pe 'JSON.parse(require("fs").readFileSync(0)).test_case_definition_id'; done | node -pe 'JSON.stringify(require("fs").readFileSync(0,"utf8").trim().split("\n"))')
retell create-batch-test --test-case-definition-ids "$ids" --response-engine "{\"type\":\"retell-llm\",\"llm_id\":\"$LLM_ID\"}"
retell list-test-runs <batch_job_id> --output table
```

## Inspect calls (Watch feed)

```bash
retell list-calls --output table
retell get-call <call_id>    # see call_analysis.custom_analysis_data
```
