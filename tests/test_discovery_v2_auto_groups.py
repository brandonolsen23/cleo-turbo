import pytest
import sqlite3

from cleo.discovery_v2.auto_groups import build_auto_groups
from tests._helpers import seed_party_side


def test_full_pipeline_produces_skyline_group_with_display_name(discovery_v2_db):
    conn = discovery_v2_db
    # 8 sides converging on Skyline anchors with multiple phrase variants.
    phrases = [
        'skyline real estate holdings',
        'skyline retail real estate holdings',
        'skyline real estate holdings',
    ]
    for i in range(8):
        ph = phrases[i % len(phrases)]
        seed_party_side(conn, f'TX{i}', 'buyer', ph,
                        phone='P1', contact='jc',
                        street_number='5', street_name='douglas', street_suffix='st')

    build_auto_groups(conn, verbose=False)

    g = conn.execute(
        "SELECT * FROM auto_groups WHERE canonical_stem='skyline'"
    ).fetchone()
    assert g is not None
    # display_name picks the most-common skyline phrase among members.
    assert g['display_name'] == 'skyline real estate holdings'
    # n_members reflects expansion output.
    assert g['n_members'] >= 8


def test_multi_tenant_address_does_not_seed_alone(discovery_v2_db):
    conn = discovery_v2_db
    # 30 sides at the same address but with 30 different stem-mapped phrases
    # spanning two different operators. Should not produce a group from address alone.
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('kingsett', 6.50, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    for i in range(15):
        seed_party_side(conn, f'A{i}', 'buyer', 'skyline real estate holdings',
                        street_number='161', street_name='bay', street_suffix='st')
    for i in range(15):
        seed_party_side(conn, f'B{i}', 'buyer', 'kingsett capital',
                        street_number='161', street_name='bay', street_suffix='st')
    build_auto_groups(conn, verbose=False)
    # The address (161, bay, st) anchor should NOT dominate either stem — half/half split.
    # No group should be seeded from the address alone (would need more anchors).
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    for g in groups:
        n_anchors = conn.execute(
            'SELECT COUNT(*) AS n FROM auto_group_anchors WHERE auto_group_id=?',
            (g['auto_group_id'],),
        ).fetchone()['n']
        assert n_anchors >= 2, f'Group {g["auto_group_id"]} seeded with only one anchor'


def test_orchestrator_includes_contact_brand_tenures_step(discovery_v2_db):
    """Smoke test: build_auto_groups returns a summary that includes n_tenure_rows."""
    conn = discovery_v2_db
    # Ensure the contact_brand_tenures table exists (created by migration 018 in production).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_brand_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint         TEXT NOT NULL,
            brand_stem                  TEXT NOT NULL,
            strict_start_date           TEXT NOT NULL,
            strict_end_date             TEXT NOT NULL,
            inferred_start_date         TEXT NOT NULL,
            inferred_end_date           TEXT NOT NULL,
            n_party_sides_strict        INTEGER NOT NULL,
            n_party_sides_inferred      INTEGER NOT NULL,
            top_phrases_json            TEXT NOT NULL,
            source_field_breakdown_json TEXT NOT NULL,
            dominant_address_unit       TEXT,
            auto_group_id               TEXT,
            is_active                   INTEGER NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Empty DB — orchestrator should still run without erroring.
    summary = build_auto_groups(conn, verbose=False)
    assert "n_tenure_rows" in summary
    assert summary["n_tenure_rows"] == 0
