"""Stage A3: Auto-seed groups from anchor convergence."""
from __future__ import annotations
import sqlite3

from cleo.discovery_v2.constants import (
    ANCHOR_SEEDING_SCORE_THRESHOLD,
    ANCHOR_CORROBORATION_SCORE_THRESHOLD,
    TIER_CONFIRMED_MIN_CONFIDENCE,
    TIER_PROBABLE_MIN_CONFIDENCE,
    ANCHOR_SCORE_CEILING,
)


def _next_group_id(n: int) -> str:
    return f'AGRP_{n:05d}'


def _category_of(anchor_type: str) -> str:
    """Collapse the (sole) address anchor type into 'address' category for tiering."""
    if anchor_type == 'address_unit':
        return 'address'
    return anchor_type


def _compute_tier_and_confidence(anchors: list[dict]) -> tuple[str | None, float]:
    """Decide tier (confirmed / probable / candidate) and confidence per the spec.

    Tier is based on the number of distinct anchor categories among anchors
    that meet ANCHOR_SEEDING_SCORE_THRESHOLD. Confidence is a continuous score.
    """
    strong = [a for a in anchors if a['score'] >= ANCHOR_SEEDING_SCORE_THRESHOLD]
    corroborating = [a for a in anchors if a['score'] >= ANCHOR_CORROBORATION_SCORE_THRESHOLD]
    strong_categories = {_category_of(a['anchor_type']) for a in strong}
    n_cats = len(strong_categories)

    avg_score = sum(a['score'] for a in anchors) / len(anchors)
    confidence = (
        (n_cats / 3.0) * 0.4
        + min(avg_score / ANCHOR_SCORE_CEILING, 1.0) * 0.4
        + 0.2  # placeholder; replaced by (1 - anti_evidence_ratio) * 0.2 in Plan B
    )

    if confidence >= TIER_CONFIRMED_MIN_CONFIDENCE and n_cats >= 3:
        tier = 'confirmed'
    elif confidence >= TIER_PROBABLE_MIN_CONFIDENCE and n_cats >= 2:
        tier = 'probable'
    elif n_cats >= 1 and len(corroborating) >= 2:
        tier = 'candidate'
    else:
        tier = None  # don't seed
    return tier, confidence


def _apply_crm_overrides(conn: sqlite3.Connection) -> None:
    """Apply auto_group_overrides (confirm/reject/split) and auto_group_merges.

    Plan A only handles confirm + reject; merge/split are stubs until Plan C.
    """
    # confirm: force tier='confirmed' on the named group (if it still exists)
    for r in conn.execute(
        "SELECT auto_group_id FROM auto_group_overrides WHERE action='confirm'"
    ).fetchall():
        conn.execute(
            "UPDATE auto_groups SET tier='confirmed' WHERE auto_group_id=?",
            (r['auto_group_id'],),
        )
    # reject: remove the group
    for r in conn.execute(
        "SELECT auto_group_id FROM auto_group_overrides WHERE action='reject'"
    ).fetchall():
        conn.execute('DELETE FROM auto_group_anchors WHERE auto_group_id=?', (r['auto_group_id'],))
        conn.execute('DELETE FROM auto_groups WHERE auto_group_id=?', (r['auto_group_id'],))


def build_seeds(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A3. Idempotent — drops prior derived rows first."""
    conn.execute('DELETE FROM auto_group_anchors')
    conn.execute('DELETE FROM auto_groups')

    # Apply auto_anchor_overrides up front (override_stem reroutes a dominant stem;
    # override_service_provider removes the anchor from seeding eligibility).
    overrides = {
        (r['anchor_type'], r['anchor_value']): r
        for r in conn.execute('SELECT * FROM auto_anchor_overrides').fetchall()
    }

    # Group anchors by stem, applying overrides
    by_stem: dict[str, list[dict]] = {}
    for r in conn.execute(
        f"""SELECT * FROM anchor_uniqueness
             WHERE dominant_stem IS NOT NULL
               AND score >= {ANCHOR_CORROBORATION_SCORE_THRESHOLD}
               AND is_service_provider = 0"""
    ).fetchall():
        a = dict(r)
        ov = overrides.get((a['anchor_type'], a['anchor_value']))
        if ov is not None:
            if ov['override_service_provider']:
                continue  # drop anchor from seeding
            if ov['override_stem']:
                a['dominant_stem'] = ov['override_stem']
        by_stem.setdefault(a['dominant_stem'], []).append(a)

    # Seed one group per stem
    n = 1
    seeded: list[tuple] = []  # (group_id, stem, display_name, tier, confidence, n_anchors, n_members)
    anchor_rows: list[tuple] = []  # (group_id, anchor_type, anchor_value, score)
    for stem, anchors in by_stem.items():
        tier, confidence = _compute_tier_and_confidence(anchors)
        if tier is None:
            continue
        group_id = _next_group_id(n)
        n += 1
        # display_name placeholder — Stage A5 fills it in.
        seeded.append((group_id, stem, stem, tier, confidence, len(anchors), 0))
        for a in anchors:
            anchor_rows.append((group_id, a['anchor_type'], a['anchor_value'], a['score']))

    if seeded:
        conn.executemany(
            """INSERT INTO auto_groups
                 (auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            seeded,
        )
    if anchor_rows:
        conn.executemany(
            "INSERT INTO auto_group_anchors (auto_group_id, anchor_type, anchor_value, score) VALUES (?,?,?,?)",
            anchor_rows,
        )

    _apply_crm_overrides(conn)
    conn.commit()

    if verbose:
        print(f'  Stage A3 (seeds): {len(seeded):,} groups.', flush=True)
    return {'n_groups': len(seeded)}
