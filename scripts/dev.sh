#!/usr/bin/env bash
# Run the pacelab API + web stack locally.
# Stops cleanly on Ctrl-C.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# Activate venv if present.
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Make sure ports are free.
for port in 8200 4400; do
  if lsof -iTCP:$port -sTCP:LISTEN -t 2>/dev/null | head -1 >/dev/null; then
    echo "port $port already in use; aborting"
    exit 1
  fi
done

# Start API.
mkdir -p logs
echo "starting pacelab API on http://127.0.0.1:8200"
pacelab serve api --host 127.0.0.1 --port 8200 > logs/api.log 2>&1 &
API_PID=$!

# Start web.
cd web
echo "starting pacelab web on http://127.0.0.1:4400"
bun --bun next dev -p 4400 -H 127.0.0.1 --turbopack > ../logs/web.log 2>&1 &
WEB_PID=$!

cleanup() {
  echo
  echo "shutting down..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "pacelab is up:"
echo "  api:  http://127.0.0.1:8200   (logs/api.log)"
echo "  web:  http://127.0.0.1:4400   (logs/web.log)"
echo
echo "press Ctrl-C to stop both."
wait
