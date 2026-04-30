"""Stage A0: per-anchor timeline builder.

Given an anchor (phone, address_unit, or contact), returns a chronological
list of party events with their dominant stem (or None if the side has no
stem-mapped brand phrases).

Used by Stage A2 (windowed dominance) to detect tenure boundaries and by
Stage A6 (conflict detection) to scan for reassignments. Not stored — the
timeline is rebuilt per-run.
"""
from __future__ import annotations
import sqlite3
from typing import Iterator


def _anchor_pf_clause(anchor_type: str) -> str:
    """SQL fragment that filters party_fingerprints (aliased pf) for the given
    anchor_type. Expects exactly one bind param: the anchor_value."""
    if anchor_type == 'phone':
        return "pf.phone = ?"
    if anchor_type == 'contact':
        return "pf.contact_fingerprint = ?"
    if anchor_type == 'address_unit':
        return (
            "(COALESCE(pf.city,'') || '|' || COALESCE(pf.street_number,'') || '|' || "
            "COALESCE(pf.street_name,'') || '|' || COALESCE(pf.street_suffix,'') || '|' || "
            "COALESCE(pf.street_direction,'') || '|' || COALESCE(pf.suite_type,'') || '|' || "
            "COALESCE(pf.suite_number,'')) = ?"
        )
    raise ValueError(f"Unknown anchor_type: {anchor_type!r}")


def build_anchor_timeline(
    conn: sqlite3.Connection, anchor_type: str, anchor_value: str,
) -> list[dict]:
    """Return chronologically-ordered events for the given anchor.

    Each event is a dict: {sale_date, source_id, side, stem}. The stem is
    the most-common stem across the side's brand_phrase atoms; None if the
    side has no stem-mapped phrases. Ties broken alphabetically.
    """
    pf_clause = _anchor_pf_clause(anchor_type)
    rows = conn.execute(
        f"""
        SELECT pf.source_id, pf.side, pf.sale_date,
               (SELECT m.stem
                  FROM party_atoms pa
                  JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
                 WHERE pa.source_id = pf.source_id
                   AND pa.side      = pf.side
                   AND pa.atom_type = 'brand_phrase'
                 GROUP BY m.stem
                 ORDER BY COUNT(*) DESC, m.stem ASC
                 LIMIT 1) AS stem
        FROM party_fingerprints pf
        WHERE {pf_clause}
          AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
        ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC
        """,
        (anchor_value,),
    ).fetchall()
    return [
        {
            'sale_date': r['sale_date'],
            'source_id': r['source_id'],
            'side':      r['side'],
            'stem':      r['stem'],
        }
        for r in rows
    ]


def iter_all_anchor_timelines(
    conn: sqlite3.Connection,
) -> Iterator[tuple[str, str, list[dict]]]:
    """Yield (anchor_type, anchor_value, timeline) for every anchor with at
    least one dated event.

    Bulk-loads all events and stems in 4 queries (one for stems, one per anchor
    type) instead of one correlated-subquery SQL call per anchor (was 220K+).
    """
    # Pre-load: (source_id, side) → dominant stem across all party_atoms.
    # Window function picks the most-common stem per side (ties: alphabetical).
    side_dominant_stem: dict[tuple[str, str], str] = {}
    for r in conn.execute(
        """
        SELECT source_id, side, stem
        FROM (
            SELECT pa.source_id, pa.side, m.stem,
                   ROW_NUMBER() OVER (
                       PARTITION BY pa.source_id, pa.side
                       ORDER BY COUNT(*) DESC, m.stem ASC
                   ) AS rk
            FROM party_atoms pa
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE pa.atom_type = 'brand_phrase'
            GROUP BY pa.source_id, pa.side, m.stem
        ) WHERE rk = 1
        """
    ):
        side_dominant_stem[(r['source_id'], r['side'])] = r['stem']

    # Pre-load all events grouped by anchor — one query per anchor type.
    events_by_anchor: dict[tuple[str, str], list[tuple[str, str, str]]] = {}

    # Phones
    for r in conn.execute(
        """
        SELECT phone AS av, source_id, side, sale_date
        FROM party_fingerprints
        WHERE phone IS NOT NULL AND phone != ''
          AND sale_date IS NOT NULL AND sale_date != ''
        ORDER BY sale_date, source_id, side
        """
    ):
        events_by_anchor.setdefault(('phone', r['av']), []).append(
            (r['sale_date'], r['source_id'], r['side'])
        )

    # Contacts
    for r in conn.execute(
        """
        SELECT contact_fingerprint AS av, source_id, side, sale_date
        FROM party_fingerprints
        WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
          AND sale_date IS NOT NULL AND sale_date != ''
        ORDER BY sale_date, source_id, side
        """
    ):
        events_by_anchor.setdefault(('contact', r['av']), []).append(
            (r['sale_date'], r['source_id'], r['side'])
        )

    # Address units
    for r in conn.execute(
        """
        SELECT (COALESCE(city,'') || '|' || COALESCE(street_number,'') || '|' ||
                COALESCE(street_name,'') || '|' || COALESCE(street_suffix,'') || '|' ||
                COALESCE(street_direction,'') || '|' || COALESCE(suite_type,'') || '|' ||
                COALESCE(suite_number,'')) AS av,
               source_id, side, sale_date
        FROM party_fingerprints
        WHERE city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
          AND sale_date IS NOT NULL AND sale_date != ''
        ORDER BY sale_date, source_id, side
        """
    ):
        events_by_anchor.setdefault(('address_unit', r['av']), []).append(
            (r['sale_date'], r['source_id'], r['side'])
        )

    # Yield timelines, zipping in pre-loaded stems
    for (atype, aval), evts in events_by_anchor.items():
        timeline = [
            {
                'sale_date': sd,
                'source_id': sid,
                'side':      side,
                'stem':      side_dominant_stem.get((sid, side)),
            }
            for (sd, sid, side) in evts
        ]
        yield (atype, aval, timeline)
