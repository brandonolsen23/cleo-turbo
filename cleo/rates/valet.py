"""
Bank of Canada Valet API client for Government of Canada benchmark bond yields.

Free, no API key. One HTTP call fetches all four benchmark terms over a date
range. Values are business-day observations published with a short lag.
Docs: https://www.bankofcanada.ca/valet/docs
"""

from __future__ import annotations

import httpx

# Term label -> Valet series name. 5yr is the workhorse for commercial term
# debt; 2yr tracks policy expectations; 10yr/long read longer-run growth.
SERIES = {
    "2yr": "BD.CDN.2YR.DQ.YLD",
    "5yr": "BD.CDN.5YR.DQ.YLD",
    "10yr": "BD.CDN.10YR.DQ.YLD",
    "long": "BD.CDN.LONG.DQ.YLD",
}
_SERIES_TO_TERM = {v: k for k, v in SERIES.items()}
_BASE = "https://www.bankofcanada.ca/valet/observations"


def fetch_observations(start_date: str, timeout: float = 10.0) -> list[dict]:
    """Fetch all benchmark yields from start_date (ISO) through the latest
    available business day.

    Returns a list of {"date", "term", "yield_pct"} dicts, one per
    (business day, term) that has a populated value. Observations with an
    empty value (holidays / no print) are skipped. Raises httpx.HTTPError on
    a network or HTTP failure — callers on the startup path swallow it.
    """
    names = ",".join(SERIES.values())
    url = f"{_BASE}/{names}/json"
    resp = httpx.get(
        url,
        params={"start_date": start_date},
        timeout=timeout,
        headers={"User-Agent": "cleo-turbo/1.0"},
    )
    resp.raise_for_status()
    data = resp.json()

    out: list[dict] = []
    for obs in data.get("observations", []):
        date = obs.get("d")
        if not date:
            continue
        for series_name, term in _SERIES_TO_TERM.items():
            cell = obs.get(series_name)
            if not cell:
                continue
            raw = cell.get("v")
            if raw is None or raw == "":
                continue  # holiday / no observation for this series
            try:
                out.append({"date": date, "term": term, "yield_pct": float(raw)})
            except (TypeError, ValueError):
                continue
    return out
