#!/usr/bin/env bash
#
# Restart the Budget Buddy app process only (not the machine). Used by
# deploy.sh and the Settings "Restart app" button. Under launchd it asks
# launchd to restart the job; otherwise it stops uvicorn and starts it again
# in the background.
#
main() {
  set -euo pipefail
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$REPO_DIR"
  # launchd starts jobs with a minimal PATH; add the usual Homebrew locations.
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
  HOST="${BUDGET_BUDDY_HOST:-0.0.0.0}"
  PORT="${BUDGET_BUDDY_PORT:-8000}"

  echo "==> Restarting Budget Buddy (app only)"
  if launchctl list 2>/dev/null | grep -q com.budgetbuddy; then
    launchctl kickstart -k "gui/$(id -u)/com.budgetbuddy"
    echo "    (restarted via launchd)"
  else
    pkill -f "uvicorn app.main:app" || true
    sleep 1
    nohup "$REPO_DIR/.venv/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" \
      > "$REPO_DIR/server.log" 2>&1 &
    echo "    (restarted in the background, see server.log)"
  fi
  echo "==> Restart requested."
}
# Everything is inside main() so bash reads the whole file before running it.
main "$@"
exit
