"""
Bank of Canada fixed policy-rate announcement dates.

Eight scheduled announcements per year, published about a year ahead. The
dashboard uses these to compute "change since the last rate decision" — how
far the market has repriced since the Bank last acted.

MAINTENANCE: extend ANNOUNCEMENT_DATES when the Bank publishes the next year's
schedule (search "Bank of Canada publishes its <YEAR> schedule"). Dates are ISO
strings in ascending order. Source: bankofcanada.ca press releases.
"""

from __future__ import annotations

ANNOUNCEMENT_DATES = [
    # 2025
    "2025-01-29", "2025-03-12", "2025-04-16", "2025-06-04",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-10",
    "2026-07-15", "2026-09-02", "2026-10-28", "2026-12-09",
]


def last_announcement_on_or_before(as_of: str) -> str | None:
    """Most recent BoC announcement date on or before `as_of` (ISO)."""
    prior = [d for d in ANNOUNCEMENT_DATES if d <= as_of]
    return prior[-1] if prior else None


def next_announcement_after(as_of: str) -> str | None:
    """Next scheduled BoC announcement strictly after `as_of` (ISO)."""
    upcoming = [d for d in ANNOUNCEMENT_DATES if d > as_of]
    return upcoming[0] if upcoming else None
