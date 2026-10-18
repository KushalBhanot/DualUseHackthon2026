#!/usr/bin/env bash
# Create or update the Night Ledger agent with the Retell CLI.
#   ./deploy.sh            build + create (first run) or update (later runs)
#   ./deploy.sh --dry-run  print the requests without sending them
# IDs are saved to .ids.env so later runs update in place.
set -euo pipefail
cd "$(dirname "$0")"

DRY=()
[[ "${1:-}" == "--dry-run" ]] && DRY=(--dry-run)

# Use a global `retell` if it's on PATH, else run the official package via npx.
# (Plain `npx retell` can resolve to an unrelated npm package named "retell".)
if command -v retell >/dev/null 2>&1; then
  retell() { command retell "$@"; }
else
  retell() { npx --yes @retell-ai/retell-cli "$@"; }
fi
retell auth whoami >/dev/null || { echo "Not logged in: run 'npx @retell-ai/retell-cli auth login'" >&2; exit 1; }

[[ -f .ids.env ]] && source .ids.env
export LLM_ID="${LLM_ID:-}" AGENT_ID="${AGENT_ID:-}"

json_field() { node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s)[process.argv[1]]))' "$1"; }
quiet_unless_dry() { if [[ ${#DRY[@]} -gt 0 ]]; then cat; else cat >/dev/null; fi; }

# A published version (and its LLM) is locked, and publishing doesn't open a new draft.
# So after connect.sh publishes, start a new draft from the latest version before updating.
if [[ -n "$AGENT_ID" && ${#DRY[@]} -eq 0 ]]; then
  latest=$(retell get-agent "$AGENT_ID")
  if [[ "$(echo "$latest" | json_field is_published)" == true ]]; then
    base=$(echo "$latest" | json_field version)
    retell create-agent-version "$AGENT_ID" --base-version "$base" >/dev/null
    echo "agent version $base is published; started a new draft from it"
  fi
fi

if [[ -z "$LLM_ID" ]]; then
  node ladder.mjs
  out=$(retell create-retell-llm --body build/llm.json "${DRY[@]}")
  [[ ${#DRY[@]} -gt 0 ]] && { echo "$out"; LLM_ID=__LLM_ID__; } || LLM_ID=$(echo "$out" | json_field llm_id)
  echo "created LLM $LLM_ID"
else
  node ladder.mjs
  retell update-retell-llm "$LLM_ID" --body build/llm.json "${DRY[@]}" | quiet_unless_dry
  echo "updated LLM $LLM_ID"
fi

export LLM_ID
node ladder.mjs  # rebuild agent.json with the real llm_id

if [[ -z "$AGENT_ID" ]]; then
  out=$(retell create-agent --body build/agent.json "${DRY[@]}")
  [[ ${#DRY[@]} -gt 0 ]] && { echo "$out"; AGENT_ID=__AGENT_ID__; } || AGENT_ID=$(echo "$out" | json_field agent_id)
  echo "created agent $AGENT_ID"
else
  retell update-agent "$AGENT_ID" --body build/agent.json "${DRY[@]}" | quiet_unless_dry
  echo "updated agent $AGENT_ID (draft; run: retell publish-agent-version --help)"
fi

if [[ ${#DRY[@]} -eq 0 ]]; then
  printf 'LLM_ID=%s\nAGENT_ID=%s\n' "$LLM_ID" "$AGENT_ID" > .ids.env
  echo "saved ids to .ids.env"
fi
