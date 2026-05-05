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
               pf.party_address_canonical AS address_unit
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
            "address_unit": r["address_unit"] or "",
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

        # Pick dominant_address_unit: address_unit appearing on the most
        # distinct party-sides among the strict events. Deterministic
        # alphabetical tiebreak.
        addr_to_sides: dict[str, set] = defaultdict(set)
        for e in events:
            addr_to_sides[e["address_unit"]].add((e["source_id"], e["side"]))
        # Filter empty-key (city missing entirely) — those don't make a useful
        # bracket. If everything is empty, dominant is None.
        addr_to_sides = {k: v for k, v in addr_to_sides.items() if k.strip("|")}
        if addr_to_sides:
            dominant_addr = sorted(
                addr_to_sides.items(),
                key=lambda kv: (-len(kv[1]), kv[0]),
            )[0][0]
        else:
            dominant_addr = None

        # Expand inferred window: include any party-side for the same contact
        # at dominant_addr, regardless of whether it carries this stem's
        # qualifying brand_phrase.
        inferred_start = strict_start
        inferred_end = strict_end
        inferred_sides = set(distinct_sides)
        if dominant_addr is not None:
            ext_rows = conn.execute(
                """
                SELECT pf.source_id, pf.side, pf.sale_date,
                       pf.party_address_canonical AS address_unit
                FROM party_fingerprints pf
                WHERE pf.contact_fingerprint = ?
                  AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
                """,
                (cf,),
            ).fetchall()
            for er in ext_rows:
                if (er["address_unit"] or "") != dominant_addr:
                    continue
                if er["sale_date"] < inferred_start:
                    inferred_start = er["sale_date"]
                if er["sale_date"] > inferred_end:
                    inferred_end = er["sale_date"]
                inferred_sides.add((er["source_id"], er["side"]))

        n_strict = len(distinct_sides)
        n_inferred = len(inferred_sides)

        # is_active: 1 iff inferred_end_date >= today - 730 days.
        is_active = 1 if _is_active(inferred_end, today) else 0

        inserts.append((
            cf, stem, strict_start, strict_end,
            inferred_start, inferred_end,
            n_strict, n_inferred,
            json.dumps(top_phrases),
            json.dumps(sf_breakdown),
            dominant_addr,
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

    # Soft corroboration: link tenure → auto_group when canonical_stem matches.
    # When multiple auto_groups share canonical_stem, the highest-membership
    # one wins (deterministic, matches user's "drill into the biggest cluster"
    # intent).
    conn.execute("""
        UPDATE contact_brand_tenures
        SET auto_group_id = (
            SELECT g.auto_group_id
            FROM auto_groups g
            WHERE g.canonical_stem = contact_brand_tenures.brand_stem
            ORDER BY g.n_members DESC, g.auto_group_id ASC
            LIMIT 1
        )
    """)

    conn.commit()
    if verbose:
        print(f"  contact_brand_tenures: {len(inserts):,} rows.", flush=True)
    return {"n_tenure_rows": len(inserts)}


def _address_unit_key(city, sn, st, sx, sd, suite_t, suite_n) -> str:
    """LEGACY: pre-canonicalization 7-tuple builder. Kept for reference and
    in case any external test fixture still calls it. Prefer reading
    party_fingerprints.party_address_canonical instead.
    """
    return "|".join([
        (city or "").lower(),
        sn or "", (st or "").lower(),
        (sx or "").lower(), (sd or "").lower(),
        (suite_t or "").lower(), suite_n or "",
    ])


def _is_active(inferred_end_date: str, today: str | None) -> bool:
    """Return True iff the tenure ends within ACTIVE_CLIFF_DAYS of today."""
    import datetime
    if today is None:
        today_dt = datetime.date.today()
    else:
        today_dt = datetime.date.fromisoformat(today)
    end_dt = datetime.date.fromisoformat(inferred_end_date)
    delta_days = (today_dt - end_dt).days
    return delta_days <= ACTIVE_CLIFF_DAYS
