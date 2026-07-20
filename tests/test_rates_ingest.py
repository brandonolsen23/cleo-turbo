"""Tests for the daily bond-yield top-up (cleo/rates/ingest.py).

The dashboard's GoC yields tile was going stale because the ingest only ran
on backend startup and the backend runs for weeks. rt-daily-run.sh now calls
backfill_bond_yields every morning; these tests lock in that it upserts new
observations, is idempotent, and re-fetches from the last stored day.
"""

import sqlite3

import pytest

from cleo.rates import ingest as rates_ingest


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _rows(*specs):
    """specs: (date, term, yield_pct) tuples -> list of dicts."""
    return [{"date": d, "term": t, "yield_pct": y} for d, t, y in specs]


def test_backfill_upserts_and_is_idempotent(db, monkeypatch):
    fetched = _rows(
        ("2026-07-17", "2yr", 3.10),
        ("2026-07-17", "5yr", 3.25),
    )
    monkeypatch.setattr(rates_ingest, "fetch_observations",
                        lambda start, timeout=10.0: fetched)

    n1 = rates_ingest.backfill_bond_yields(db, today=None)
    assert n1 == 2

    # Running again with the same data must not duplicate rows (INSERT OR
    # REPLACE on the (date, term) primary key).
    n2 = rates_ingest.backfill_bond_yields(db, today=None)
    assert n2 == 2
    total = db.execute("SELECT COUNT(*) FROM bond_yields").fetchone()[0]
    assert total == 2

    # A later revision of the same key overwrites in place.
    monkeypatch.setattr(rates_ingest, "fetch_observations",
                        lambda start, timeout=10.0: _rows(("2026-07-17", "2yr", 3.15)))
    rates_ingest.backfill_bond_yields(db, today=None)
    val = db.execute(
        "SELECT yield_pct FROM bond_yields WHERE date='2026-07-17' AND term='2yr'"
    ).fetchone()[0]
    assert val == 3.15


def test_backfill_refetches_from_last_stored_day(db, monkeypatch):
    seen_starts = []

    def fake_fetch(start, timeout=10.0):
        seen_starts.append(start)
        return _rows(("2026-07-16", "5yr", 3.20))

    monkeypatch.setattr(rates_ingest, "fetch_observations", fake_fetch)
    rates_ingest.backfill_bond_yields(db, today=None)

    # Next run should re-fetch starting from the latest stored date, not a
    # cold-start 400-day window.
    rates_ingest.backfill_bond_yields(db, today=None)
    assert seen_starts[-1] == "2026-07-16"


def test_ingest_never_raises_on_network_error(db, monkeypatch):
    def boom(start, timeout=10.0):
        raise ConnectionError("BoC unreachable")

    monkeypatch.setattr(rates_ingest, "fetch_observations", boom)
    # ingest_bond_yields is the non-fatal entry point; it must swallow errors.
    rates_ingest.ingest_bond_yields(db)  # should not raise
