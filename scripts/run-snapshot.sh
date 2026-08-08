#!/usr/bin/env bash
# Launcher for the WRF news snapshot — safe to double-click from a KDE desktop
# entry (Terminal=true). Resolves the repo root from its own location, so it
# works no matter where it's invoked from. Any extra args pass through to
# snapshot.py (e.g. --latest 5, --date 2026-08-08).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd -- "$REPO_ROOT"

python3 scripts/snapshot.py "$@"
status=$?

# Keep the terminal window open when launched from a desktop entry, so the
# output stays readable. Skipped when not attached to a TTY (e.g. cron).
if [ -t 0 ]; then
    echo
    read -n1 -r -p "Done (exit $status). Press any key to close..."
    echo
fi
exit "$status"
