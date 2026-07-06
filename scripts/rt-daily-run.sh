#!/bin/bash
# RT daily collection: scrape new transactions, then process them through
# the pipeline (extract -> classify -> normalize -> resolve -> compile).
# Run by launchd (com.cleo.rt-daily-scraper) at 7:30am and at login.
# Both steps are idempotent; overlapping runs are prevented by the
# orchestrator's lockfile awareness.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
PY="$REPO/.venv/bin/python"

echo "=== rt-daily-run $(date '+%Y-%m-%d %H:%M:%S') ==="
"$PY" -m engines.rt.scraper.daily_scraper --daily
SCRAPE_RC=$?
echo "--- scraper exit: $SCRAPE_RC ---"

"$PY" engines/rt/watcher.py --once
WATCH_RC=$?
echo "--- watcher exit: $WATCH_RC ---"
echo "=== done $(date '+%Y-%m-%d %H:%M:%S') ==="
exit $(( SCRAPE_RC > WATCH_RC ? SCRAPE_RC : WATCH_RC ))
