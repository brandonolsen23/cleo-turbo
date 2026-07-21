#!/bin/bash
# Midday Bank of Canada bond-yield refresh.
#
# The GoC yields also top up inside rt-daily-run.sh at 7:30am, but the Bank
# sometimes publishes the prior business day's yields later in the morning, so
# the early run can miss a day. This second, BoC-only pass at noon catches those
# late publishes. Idempotent (INSERT OR REPLACE, re-fetches from the last stored
# day) and non-fatal: a network hiccup must never fail loudly.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
PY="$REPO/.venv/bin/python"

echo "=== boc-refresh-run $(date '+%Y-%m-%d %H:%M:%S') ==="
"$PY" -c "
from cleo.database.connection import get_connection
from cleo.rates.ingest import backfill_bond_yields
conn = get_connection()
try:
    n = backfill_bond_yields(conn)
    print(f'bond_yields: upserted {n} observation(s)')
except Exception as exc:
    print(f'bond_yields refresh skipped: {exc}')
finally:
    conn.close()
"
echo "=== done $(date '+%Y-%m-%d %H:%M:%S') ==="
