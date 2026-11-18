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
# The Settings "Update" button runs this too. Everything is inside main() so
# bash reads the whole file before running it: `git pull` may replace this
# file mid-run.
#
main() {
  set -euo pipefail
  trap 'echo "==> FAILED at line $LINENO (exit $?). The app was NOT restarted; it is still running the previous version."' ERR

  # Resolve the repo root (the directory this script lives in) so it works
  # regardless of where it's invoked from.
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$REPO_DIR"

  # When started from the app under launchd, PATH is minimal and misses
  # Homebrew (npm, node, git). Add the usual locations.
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

  echo "==> Pulling latest code (main)"
  # Older builds rewrote this tracked file; discard that so it can't block the
  # pull or show the install as modified. Builds now write it to node_modules.
  git checkout -- frontend/tsconfig.tsbuildinfo 2>/dev/null || true
  git pull origin main

  echo "==> Activating virtualenv"
  # shellcheck disable=SC1091
  source .venv/bin/activate

  echo "==> Updating backend dependencies"
  pip install -r requirements.txt

  echo "==> Building frontend"
  (cd frontend && npm install && npm run build)

  bash "$REPO_DIR/scripts/restart.sh"

  echo "==> Done. Budget Buddy is restarting on port ${BUDGET_BUDDY_PORT:-8000}."
}
main "$@"
exit
