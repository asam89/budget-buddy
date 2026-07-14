#!/usr/bin/env bash
#
# Budget Buddy deploy script.
#
# Pulls the latest code from main, updates dependencies, rebuilds the
# frontend, and restarts the server. Run this on the host machine (e.g. the
# Mac Mini) after merging changes on GitHub:
#
#     ~/budget-buddy/deploy.sh
#
set -euo pipefail

# Resolve the repo root (the directory this script lives in) so it works
# regardless of where it's invoked from.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

HOST="${BUDGET_BUDDY_HOST:-0.0.0.0}"
PORT="${BUDGET_BUDDY_PORT:-8000}"

echo "==> Pulling latest code (main)"
git pull origin main

echo "==> Activating virtualenv"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Updating backend dependencies"
pip install -r requirements.txt

echo "==> Building frontend"
(cd frontend && npm install && npm run build)

echo "==> Restarting server"
if launchctl list 2>/dev/null | grep -q com.budgetbuddy; then
  # Managed by launchd — let it restart the process.
  launchctl kickstart -k "gui/$(id -u)/com.budgetbuddy"
  echo "    (restarted via launchd)"
else
  pkill -f "uvicorn app.main:app" || true
  sleep 1
  nohup uvicorn app.main:app --host "$HOST" --port "$PORT" \
    > "$REPO_DIR/server.log" 2>&1 &
  echo "    (restarted via nohup — see server.log)"
fi

echo "==> Done. Budget Buddy is running on port $PORT."
