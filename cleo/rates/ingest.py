"""
Backfill-on-startup ingestion of Government of Canada bond yields.

The app has no always-on component, so instead of a cron we top up on boot:
read the latest stored date and pull every business day since then from the
Bank of Canada Valet API. Open the app after a gap and it fills the gap; in
steady state it's a one-row-per-series fetch. Safe to call on every startup.
"""

from __future__ import annotations

import datetime as _dt
import logging

from ..database.schema import MARKET_DATA_TABLES
from .valet import fetch_observations

logger = logging.getLogger(__name__)

# On a cold table, backfill far enough that 1d/1w/1m deltas all have history.
_COLD_START_DAYS = 400


def _ensure_table(conn) -> None:
    """Create bond_yields if it doesn't exist (idempotent)."""
    conn.executescript(MARKET_DATA_TABLES)


def _latest_date(conn):
    row = conn.execute("SELECT MAX(date) AS d FROM bond_yields").fetchone()
    if row is None:
        return None
    # sqlite3.Row supports index access; MAX() is column 0.
    return row[0]


def _start_date(conn, today: _dt.date) -> str:
    latest = _latest_date(conn)
    if latest:
        # Re-fetch from the last stored day so same-day revisions are picked up.
        return latest
    return (today - _dt.timedelta(days=_COLD_START_DAYS)).isoformat()


def backfill_bond_yields(conn, today: _dt.date | None = None,
                         timeout: float = 10.0) -> int:
    """Fetch missing observations and upsert them. Returns rows written.

    Raises on network/HTTP failure — use ingest_bond_yields() on the startup
    path, which swallows errors.
    """
    _ensure_table(conn)
    today = today or _dt.date.today()
    start = _start_date(conn, today)
    rows = fetch_observations(start, timeout=timeout)
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO bond_yields "
        "(date, term, yield_pct, source, fetched_at) "
        "VALUES (?, ?, ?, 'boc_valet', datetime('now'))",
        [(r["date"], r["term"], r["yield_pct"]) for r in rows],
    )
    conn.commit()
    return len(rows)


def ingest_bond_yields(conn, timeout: float = 10.0) -> None:
    """Startup entry point. Never raises: a network hiccup or offline boot
    logs a warning and returns so it can't stop the app from starting."""
    try:
        n = backfill_bond_yields(conn, timeout=timeout)
        logger.info("bond_yields: upserted %d observation(s)", n)
    except Exception as exc:  # noqa: BLE001 - startup must not fail on data fetch
        logger.warning("bond_yields ingest skipped: %s", exc)
