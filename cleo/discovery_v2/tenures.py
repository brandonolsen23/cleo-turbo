"""Pure-Python tenure summarizer. Groups events by (dominant stem) and emits
one tenure per stem covering the first to last observed event.

No gap splitting, no inferring "shut down" from silence — just first to last.
"""
from __future__ import annotations
import math


def _dominant_stem(stem_counts: dict) -> tuple[str | None, int]:
    """Return (stem_name, count). Deterministic alphabetical tiebreak."""
    if not stem_counts:
        return None, 0
    return sorted(stem_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def detect_tenures(timeline: list[dict], *, now: str | None = None) -> list[dict]:
    """Walk a chronological timeline and emit one tenure per stem.

    timeline: list of {sale_date, source_id, side, stem} dicts in date order.
              `stem` is None for unmapped sides.
    now: ignored (kept for backward compat with the old signature).

    Returns a list of tenure dicts:
        {dominant_stem, start_date, end_date, n_party_sides,
         dominance_share, score}

    Where:
      - dominant_stem: the stem this tenure covers (never None — sides with
        stem=None contribute to volume but don't seed a tenure on their own)
      - start_date, end_date: MIN, MAX sale_date of events for this stem
      - n_party_sides: count of events for this stem
      - dominance_share: this stem's events / all events at the anchor
      - score: dominance_share * log(n_anchor_events + 1)  (matches old A2 formula)
    """
    if not timeline:
        return []

    # Group events by their stem.
    by_stem: dict[str, list[dict]] = {}
    for ev in timeline:
        if ev['stem'] is None:
            continue
        by_stem.setdefault(ev['stem'], []).append(ev)

    if not by_stem:
        return []

    total_events_at_anchor = len(timeline)

    tenures: list[dict] = []
    for stem, events in by_stem.items():
        # Already sorted (caller sorts the timeline).
        # If you can't trust caller's sort, uncomment: events.sort(key=lambda e: e['sale_date'])
        n = len(events)
        share = n / total_events_at_anchor
        score = share * math.log(total_events_at_anchor + 1)
        tenures.append({
            'dominant_stem':   stem,
            'start_date':      events[0]['sale_date'],
            'end_date':        events[-1]['sale_date'],
            'n_party_sides':   n,
            'dominance_share': share,
            'score':           score,
        })

    # Sort tenures by start_date for deterministic output order.
    tenures.sort(key=lambda t: (t['start_date'], t['dominant_stem']))
    return tenures
