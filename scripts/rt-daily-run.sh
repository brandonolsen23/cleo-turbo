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

# Top up Government of Canada bond yields from the Bank of Canada Valet API.
# The web app only ingests these on startup, but the backend runs for weeks
# at a time, so the dashboard tile goes stale. Refreshing here guarantees a
# daily top-up regardless of backend restarts. Non-fatal: a network hiccup
# must never fail the daily run (the scraper is what matters), so this step's
# exit code is deliberately not folded into the run's exit status.
echo "--- bond yields top-up ---"
"$PY" -c "
from cleo.database.connection import get_connection
from cleo.rates.ingest import backfill_bond_yields
conn = get_connection()
try:
    n = backfill_bond_yields(conn)
    print(f'bond_yields: upserted {n} observation(s)')
except Exception as exc:
    print(f'bond_yields top-up skipped: {exc}')
finally:
    conn.close()
"

echo "=== done $(date '+%Y-%m-%d %H:%M:%S') ==="
exit $(( SCRAPE_RC > WATCH_RC ? SCRAPE_RC : WATCH_RC ))
