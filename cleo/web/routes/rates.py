"""
Market data API — Government of Canada benchmark bond yields for the dashboard.

Yields are ingested from the Bank of Canada Valet API on app startup
(see cleo/rates/). This route reads the stored series and computes the
day/week/month and since-last-BoC-decision deltas the dashboard tile renders,
plus a short history for the 5yr sparkline.
"""

import datetime as _dt

from fastapi import APIRouter, Depends

from ...web.deps import get_db, get_current_user
from ...rates.boc_calendar import (
    last_announcement_on_or_before,
    next_announcement_after,
)

router = APIRouter()

TERMS = ["2yr", "5yr", "10yr", "long"]
_DELTA_WINDOWS = {"change_1d": 1, "change_1w": 7, "change_1m": 30}
_SPARK_DAYS = 90


def _latest(db, term):
    return db.execute(
        "SELECT date, yield_pct FROM bond_yields WHERE term=? "
        "ORDER BY date DESC LIMIT 1",
        (term,),
    ).fetchone()


def _on_or_before(db, term, target):
    return db.execute(
        "SELECT date, yield_pct FROM bond_yields WHERE term=? AND date<=? "
        "ORDER BY date DESC LIMIT 1",
        (term, target),
    ).fetchone()


@router.get("/goc")
def goc_yields(db=Depends(get_db), user=Depends(get_current_user)):
    """Latest GoC benchmark yields per term with 1d/1w/1m and since-last-BoC
    deltas (in yield points), plus a 90-day 5yr history for the sparkline and
    the last/next Bank of Canada decision dates.

    Deltas are null when there isn't enough history yet. Values round to 2
    decimals; the frontend converts to basis points for display.
    """
    # Latest observation date (business day) shared across all terms.
    anchor = None
    for term in TERMS:
        r = _latest(db, term)
        if r and (anchor is None or r["date"] > anchor):
            anchor = r["date"]
    if anchor is None:
        return {"as_of": None, "terms": {}, "history": [],
                "last_boc": None, "next_boc": None}

    last_boc = last_announcement_on_or_before(anchor)
    next_boc = next_announcement_after(anchor)

    terms_out: dict = {}
    for term in TERMS:
        latest = _latest(db, term)
        if not latest:
            continue
        latest_date = latest["date"]
        latest_yield = latest["yield_pct"]
        entry = {"yield": round(latest_yield, 2)}

        base_date = _dt.date.fromisoformat(latest_date)
        for key, days in _DELTA_WINDOWS.items():
            target = (base_date - _dt.timedelta(days=days)).isoformat()
            prior = _on_or_before(db, term, target)
            entry[key] = (round(latest_yield - prior["yield_pct"], 2)
                          if prior and prior["date"] != latest_date else None)

        # Change since the last BoC rate decision (how far the market has
        # repriced since the Bank last acted).
        if last_boc:
            base = _on_or_before(db, term, last_boc)
            entry["change_since_boc"] = (
                round(latest_yield - base["yield_pct"], 2)
                if base and base["date"] != latest_date else None)
        else:
            entry["change_since_boc"] = None

        terms_out[term] = entry

    floor = (_dt.date.fromisoformat(anchor) - _dt.timedelta(days=_SPARK_DAYS)).isoformat()
    rows = db.execute(
        "SELECT date, yield_pct FROM bond_yields WHERE term='5yr' AND date>=? "
        "ORDER BY date",
        (floor,),
    ).fetchall()
    history = [{"date": r["date"], "yield": round(r["yield_pct"], 2)} for r in rows]

    return {"as_of": anchor, "terms": terms_out, "history": history,
            "last_boc": last_boc, "next_boc": next_boc}
