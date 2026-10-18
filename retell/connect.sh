#!/usr/bin/env bash
# Point the live Retell agent and phone number at the local backend, through a public tunnel.
#   ./connect.sh                     start a tunnel, deploy + publish the agent with its URLs, set the number's inbound webhook
#   ./connect.sh https://...         reuse a tunnel that's already running
#   S2S_MODEL= ./connect.sh          use the text model instead of speech-to-speech
#   TUNNEL=localtunnel ./connect.sh  skip cloudflared (blocked on some networks)
# A free tunnel can get a new URL every start, so re-run this whenever the tunnel restarts.
# Needs: the backend running on :8000 (cd ../backend && uv run uvicorn app.main:app --port 8000)
#        RETELL_API_KEY in ../backend/.env (or in the environment).
set -euo pipefail
cd "$(dirname "$0")"

PHONE_NUMBER="${PHONE_NUMBER:-+12139283405}"
export S2S_MODEL="${S2S_MODEL-gpt-realtime-2.1}"

if [[ -z "${RETELL_API_KEY:-}" && -f ../backend/.env ]]; then
  RETELL_API_KEY="$(grep -E '^RETELL_API_KEY=' ../backend/.env | cut -d= -f2- || true)"
fi
[[ -n "${RETELL_API_KEY:-}" ]] || { echo "Put RETELL_API_KEY in backend/.env first." >&2; exit 1; }
export RETELL_API_KEY

retell() { npx --yes @retell-ai/retell-cli "$@"; }
json_field() { node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s)[process.argv[1]]))' "$1"; }

curl -sf localhost:8000/health >/dev/null || { echo "Backend isn't running on localhost:8000." >&2; exit 1; }

# Start a tunnel process and wait for its public URL. Sets URL and TUNNEL_PID, or returns 1.
#   $1: name, $2: url regex, rest: the command
start_tunnel() {
  local name="$1" pattern="$2"; shift 2
  LOG="$(mktemp)"
  "$@" >"$LOG" 2>&1 &
  TUNNEL_PID=$!
  for _ in $(seq 1 60); do
    URL="$(grep -oE "$pattern" "$LOG" | head -1 || true)"
    [[ -n "$URL" ]] && return 0
    kill -0 "$TUNNEL_PID" 2>/dev/null || break  # the tunnel process died
    sleep 0.5
  done
  echo "  $name failed: $(grep -iE 'error|fail' "$LOG" | tail -1 | cut -c1-200)" >&2
  kill "$TUNNEL_PID" 2>/dev/null || true
  TUNNEL_PID="" URL=""
  return 1
}

# TUNNEL=auto (default) tries cloudflared, then localtunnel. Some networks (venue/campus Wi-Fi)
# block trycloudflare.com and ngrok; localtunnel usually gets through. TUNNEL=cloudflared|localtunnel forces one.
# LT_SUBDOMAIN asks localtunnel for a fixed name, so the URL survives restarts when it's free.
TUNNEL="${TUNNEL:-auto}"
LT_SUBDOMAIN="${LT_SUBDOMAIN:-night-ledger-$(whoami)}"
URL="${1:-}"
TUNNEL_PID=""
trap '[[ -n "$TUNNEL_PID" ]] && kill "$TUNNEL_PID" 2>/dev/null' EXIT
if [[ -z "$URL" ]]; then
  if [[ "$TUNNEL" != localtunnel ]]; then
    echo "starting cloudflared tunnel..."
    start_tunnel cloudflared 'https://[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com' \
      cloudflared tunnel --url http://localhost:8000 --no-autoupdate || true
  fi
  if [[ -z "$URL" && "$TUNNEL" != cloudflared ]]; then
    echo "starting localtunnel..."
    start_tunnel localtunnel 'https://[a-z0-9-]+\.loca\.lt' \
      npx --yes localtunnel --port 8000 --subdomain "$LT_SUBDOMAIN" || true
  fi
  [[ -n "$URL" ]] || { echo "No tunnel could start on this network. Try a phone hotspot, or pass a URL: ./connect.sh https://..." >&2; exit 1; }
fi
echo "tunnel: $URL"
for _ in $(seq 1 30); do curl -sf "$URL/health" >/dev/null && break; sleep 1; done
curl -sf "$URL/health" >/dev/null || { echo "Tunnel URL doesn't reach the backend yet; try again." >&2; exit 1; }

# 1. Agent: webhook + detail tools point at the tunnel. deploy.sh updates the draft.
WEBHOOK_URL="$URL/retell/webhook" TOOLS_URL="$URL/retell/tools" ./deploy.sh
source .ids.env

# 2. Publish the draft so the phone number uses it.
VERSION="$(retell get-agent "$AGENT_ID" | json_field version)"
retell publish-agent-version "$AGENT_ID" --version "$VERSION" >/dev/null
echo "published agent $AGENT_ID version $VERSION"

# 3. Phone number: answer with this agent; ask the backend for per-call variables first.
retell update-phone-number "$PHONE_NUMBER" \
  --inbound-agents "[{\"agent_id\":\"$AGENT_ID\",\"weight\":1}]" \
  --inbound-webhook-url "$URL/retell/inbound" >/dev/null
echo "phone $PHONE_NUMBER -> agent $AGENT_ID, inbound webhook $URL/retell/inbound"
echo "model: ${S2S_MODEL:-text model}"

if [[ -n "$TUNNEL_PID" ]]; then
  echo "Ready: call $PHONE_NUMBER. Keep this running; Ctrl+C stops the tunnel."
  wait "$TUNNEL_PID"
fi
