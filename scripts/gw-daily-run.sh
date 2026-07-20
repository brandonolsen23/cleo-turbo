#!/bin/bash
# GeoWarehouse daily ingest.
#
# Processes any new GeoWarehouse HTML the user has downloaded to
# ~/Downloads/GeoWarehouse/gw-ingest-data/ and folds it into the database
# incrementally (parcels, assessments, sales history, property enrichment,
# PIN-bridge linking of orphan RT transactions). The watcher only touches
# files it hasn't seen before, so this is a no-op when nothing new landed.
#
# Run by launchd (com.cleo.gw-daily-scraper) at 7:35am and at login. GW
# enrichment does not feed the transaction-derived groups/analytics, so a new
# GW file does not require the RT master rebuild — the watcher's own
# incremental DB update is sufficient.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
PY="$REPO/.venv/bin/python"

echo "=== gw-daily-run $(date '+%Y-%m-%d %H:%M:%S') ==="
"$PY" engines/gw/watcher.py --once
RC=$?
echo "--- gw watcher exit: $RC ---"
echo "=== done $(date '+%Y-%m-%d %H:%M:%S') ==="
exit $RC
