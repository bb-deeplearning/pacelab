#!/usr/bin/env bash
# pull-data-from-vm.sh — rsync pacelab's parquet + derived data from the GCP VM
# to a local clone. Run this on Rohan's Mac (or anywhere with tailscale + clone).
#
# Usage:
#   ./scripts/pull-data-from-vm.sh
#
# Prereqs:
#   - tailscale running and authenticated, with `iris-vm` reachable
#   - this script run from inside a local pacelab clone

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

REMOTE_HOST="${PACELAB_REMOTE_HOST:-iris-vm}"
REMOTE_USER="${PACELAB_REMOTE_USER:-rohan}"
REMOTE_PATH="${PACELAB_REMOTE_PATH:-/home/rohan/.openclaw/workspace/projects/pacelab}"

echo "pulling from ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/data/"
echo "(takes <1 min on tailnet)"
echo

mkdir -p data
rsync -avh --delete --no-perms --no-owner --no-group \
  --exclude='data/cache/' \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/data/parquet/" \
  data/parquet/

rsync -avh --no-perms --no-owner --no-group \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/data/derived/" \
  data/derived/

echo
echo "done. local size:"
du -sh data/parquet/ data/derived/ 2>/dev/null

echo
echo "next:"
echo "  uv venv --python 3.11"
echo "  source .venv/bin/activate"
echo "  uv pip install -e \".[bayes]\""
echo
echo "then fit the model (5-10 min on apple silicon, 4 chains):"
echo "  pacelab bayes fit --seasons 2018,2019,2020,2021,2024,2025 \\"
echo "    --warmup 1500 --samples 2000 --chains 4 --subsample 50"
echo
echo "then serve locally:"
echo "  pacelab serve api --host 127.0.0.1 --port 8200 &"
echo "  cd web && bun install && bun --bun next dev -p 4400"
echo "  open http://127.0.0.1:4400/"
