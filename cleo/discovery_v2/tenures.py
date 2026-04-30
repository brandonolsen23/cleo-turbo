"""Pure-Python tenure detector. Walks a chronological timeline and emits
one tenure per stable run of events.

Tenures are emitted with: dominant_stem, start_date, end_date (None if
ongoing), n_party_sides, dominance_share, score. The score uses Stage A2's
existing formula (dominance_share * log(volume + 1)) computed within the
tenure window.
"""
from __future__ import annotations
import math
from datetime import date

from cleo.discovery_v2.constants import (
    MAX_TENURE_GAP_DAYS,
    RECENT_TENURE_DAYS,
    RUN_GRACE_EVENTS,
)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _days_between(a: str, b: str) -> int:
    return (_parse_date(b) - _parse_date(a)).days


def _dominant_stem(stem_counts: dict) -> tuple[str | None, int]:
    """Return (stem_name, count). Deterministic alphabetical tiebreak."""
    if not stem_counts:
        return None, 0
    return sorted(stem_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _emit_tenure(events: list[dict], now: str | None) -> dict | None:
    """Build one tenure record from a list of events. Returns None if no
    event in the run had a mapped stem."""
    stem_counts: dict[str, int] = {}
    for e in events:
        if e['stem']:
            stem_counts[e['stem']] = stem_counts.get(e['stem'], 0) + 1
    dominant_stem, dom_n = _dominant_stem(stem_counts)
    if dominant_stem is None:
        return None
    n = len(events)
    dom_share = dom_n / n
    score = dom_share * math.log(n + 1)
    last_event_date = events[-1]['sale_date']
    end_date: str | None = last_event_date
    if now is not None:
        days_since = _days_between(last_event_date, now)
        if days_since <= RECENT_TENURE_DAYS:
            end_date = None  # ongoing
    return {
        'dominant_stem':   dominant_stem,
        'start_date':      events[0]['sale_date'],
        'end_date':        end_date,
        'n_party_sides':   n,
        'dominance_share': dom_share,
        'score':           score,
    }


def detect_tenures(timeline: list[dict], *, now: str | None = None) -> list[dict]:
    """Walk a chronological timeline and emit one tenure per stable run.

    timeline: list of {sale_date, source_id, side, stem} dicts in date order.
              `stem` is None for unmapped sides.
    now: ISO date string. If the latest event is within RECENT_TENURE_DAYS of
         `now`, the tenure is emitted with end_date=None (ongoing).

    Returns a list of tenure dicts (see _emit_tenure for shape).
    """
    if not timeline:
        return []

    tenures: list[dict] = []
    run: list[dict] = []
    off_buffer: list[dict] = []
    run_dominant_stem: str | None = None

    def close_run(end_with: str | None = None):
        """Close current run, emit tenure, reset state."""
        nonlocal run, off_buffer, run_dominant_stem
        if run:
            t = _emit_tenure(run, now=now if end_with is None else None)
            if t is not None:
                if end_with is not None:
                    t['end_date'] = end_with
                tenures.append(t)
        run = []
        off_buffer = []
        run_dominant_stem = None

    for ev in timeline:
        # Gap-based split.
        if run:
            last_date = (off_buffer[-1] if off_buffer else run[-1])['sale_date']
            if _days_between(last_date, ev['sale_date']) > MAX_TENURE_GAP_DAYS:
                close_run(end_with=run[-1]['sale_date'])
                run = [ev]
                off_buffer = []
                run_dominant_stem = ev['stem']
                continue

        # No run yet — initialize.
        if not run:
            run = [ev]
            off_buffer = []
            run_dominant_stem = ev['stem']
            continue

        # If the run's dominant stem is still None (we haven't seen a mapped
        # event yet), upgrade as soon as we do.
        if run_dominant_stem is None and ev['stem'] is not None:
            run.append(ev)
            run_dominant_stem = ev['stem']
            continue

        # Off-stem event handling.
        if ev['stem'] is not None and run_dominant_stem is not None and \
                ev['stem'] != run_dominant_stem:
            off_buffer.append(ev)
            if len(off_buffer) > RUN_GRACE_EVENTS:
                # Capture buffer before close_run resets it (close_run uses nonlocal).
                saved_buffer = list(off_buffer)
                last_on_stem_date = run[-1]['sale_date']
                # Split. Tenure ends at last on-stem event.
                close_run(end_with=last_on_stem_date)
                # New run starts from the buffer's first event.
                run = saved_buffer
                stems = [e['stem'] for e in saved_buffer if e['stem']]
                run_dominant_stem = max(set(stems), key=stems.count) if stems else None
                off_buffer = []
        else:
            # Same stem (or unmapped) — drain buffer back into run, then extend.
            run.extend(off_buffer)
            run.append(ev)
            off_buffer = []

    # End of timeline — drain buffer back into run, then close.
    run.extend(off_buffer)
    close_run()
    return tenures
