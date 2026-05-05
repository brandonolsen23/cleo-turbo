"""Builder for the contact_brand_tenures derived table.

Source-of-truth for "where a contact worked, when". Reads party_atoms
brand_phrase rows from trade_name / care_of / companies_json (party_name
intentionally excluded — SPV names live there), aggregates per
(contact_fingerprint, brand_stem), applies threshold and address-
bracketed window expansion.

Idempotent: deletes all rows on each run, then re-inserts.
"""
from __future__ import annotations
import json
import sqlite3
from collections import defaultdict, Counter

QUALIFYING_SOURCE_FIELDS = ("trade_name", "care_of", "companies_json")
THRESHOLD_PARTY_SIDES = 2
ACTIVE_CLIFF_DAYS = 730  # 2-year recency cliff for is_active


def build_contact_brand_tenures(
    conn: sqlite3.Connection, *, today: str | None = None, verbose: bool = True
) -> dict:
    """Rebuild contact_brand_tenures.

    Args:
        conn: open SQLite connection.
        today: ISO date string used as the "now" reference for is_active.
            Pass an explicit value in tests; production passes None to use
            datetime('now').
        verbose: print progress.

    Returns:
        {'n_tenure_rows': int}.
    """
    conn.execute("DELETE FROM contact_brand_tenures")

    # Step 1 — load qualifying brand-phrase events for every contact.
    # Joins party_atoms → party_fingerprints → brand_stem_phrase_map.
    placeholders = ",".join("?" * len(QUALIFYING_SOURCE_FIELDS))
    rows = conn.execute(
        f"""
        SELECT pf.contact_fingerprint   AS cf,
               m.stem                    AS stem,
               pa.atom_value             AS phrase,
               pa.source_field           AS source_field,
               pf.sale_date              AS sale_date,
               pf.source_id              AS source_id,
               pf.side                   AS side,
               pf.city                   AS city,
               COALESCE(pf.street_number,'')   AS sn,
               COALESCE(pf.street_name,'')     AS st,
               COALESCE(pf.street_suffix,'')   AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'')      AS suite_t,
               COALESCE(pf.suite_number,'')    AS suite_n
        FROM party_atoms pa
        JOIN party_fingerprints pf
          ON pf.source_id = pa.source_id AND pf.side = pa.side
        JOIN brand_stem_phrase_map m
          ON m.phrase = pa.atom_value
        WHERE pa.atom_type = 'brand_phrase'
          AND pa.source_field IN ({placeholders})
          AND pf.contact_fingerprint IS NOT NULL
          AND pf.contact_fingerprint != ''
          AND pf.sale_date IS NOT NULL
          AND pf.sale_date != ''
        """,
        QUALIFYING_SOURCE_FIELDS,
    ).fetchall()

    # Step 2 — group by (contact_fingerprint, stem) and aggregate.
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_pair[(r["cf"], r["stem"])].append({
            "phrase": r["phrase"],
            "source_field": r["source_field"],
            "sale_date": r["sale_date"],
            "source_id": r["source_id"],
            "side": r["side"],
            "address_unit": _address_unit_key(
                r["city"], r["sn"], r["st"], r["sx"], r["sd"], r["suite_t"], r["suite_n"]
            ),
        })

    # Step 3 — for each pair, decide if it survives the threshold and write.
    inserts: list[tuple] = []
    for (cf, stem), events in by_pair.items():
        # Distinct party-sides count (one per (source_id, side)).
        distinct_sides = {(e["source_id"], e["side"]) for e in events}
        if len(distinct_sides) < THRESHOLD_PARTY_SIDES:
            continue

        # Strict window: MIN/MAX sale_date of these events.
        sale_dates = sorted(e["sale_date"] for e in events)
        strict_start = sale_dates[0]
        strict_end = sale_dates[-1]

        # Phrase + source-field aggregations.
        phrase_counts = Counter(e["phrase"] for e in events)
        sf_counts = Counter(e["source_field"] for e in events)
        top_phrases = [
            {"phrase": p, "n": n}
            for p, n in phrase_counts.most_common()
        ]
        # source_field_breakdown is a dict; emit deterministic key order
        # by sorting alphabetically.
        sf_breakdown = {k: sf_counts[k] for k in sorted(sf_counts)}

        # Inferred window placeholder: in this task the inferred window
        # equals the strict window. Task 3 extends it via dominant address.
        inferred_start = strict_start
        inferred_end = strict_end
        n_strict = len(distinct_sides)
        n_inferred = n_strict

        # is_active placeholder: computed in Task 5 with the today arg.
        # For now, set 0 — Task 5 overwrites this column.
        is_active = 0

        inserts.append((
            cf, stem, strict_start, strict_end,
            inferred_start, inferred_end,
            n_strict, n_inferred,
            json.dumps(top_phrases),
            json.dumps(sf_breakdown),
            None,  # dominant_address_unit — Task 3
            None,  # auto_group_id — Task 4
            is_active,
        ))

    if inserts:
        conn.executemany(
            """INSERT INTO contact_brand_tenures
               (contact_fingerprint, brand_stem,
                strict_start_date, strict_end_date,
                inferred_start_date, inferred_end_date,
                n_party_sides_strict, n_party_sides_inferred,
                top_phrases_json, source_field_breakdown_json,
                dominant_address_unit, auto_group_id, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            inserts,
        )
    conn.commit()
    if verbose:
        print(f"  contact_brand_tenures: {len(inserts):,} rows.", flush=True)
    return {"n_tenure_rows": len(inserts)}


def _address_unit_key(city, sn, st, sx, sd, suite_t, suite_n) -> str:
    """Build the canonical pipe-joined address_unit string.

    Empty components stay as empty strings (never None) — matches the
    primary-key shape of address_unit_summary.
    """
    return "|".join([
        (city or "").lower(),
        sn or "", (st or "").lower(),
        (sx or "").lower(), (sd or "").lower(),
        (suite_t or "").lower(), suite_n or "",
    ])
