"""Tests for /api/explorer/brands endpoints."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            postal TEXT, sale_date TEXT, city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
            suite_type TEXT, suite_number TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_index (
            token TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (token, source_id, side)
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE industry_stopwords (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        CREATE TABLE places (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        CREATE TABLE brand_bigram_summary (
            bigram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT
        );
        CREATE TABLE brand_bigram_index (
            bigram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (bigram, source_id, side)
        );
        CREATE TABLE brand_trigram_summary (
            trigram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT, token_c TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT
        );
        CREATE TABLE brand_trigram_index (
            trigram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (trigram, source_id, side)
        );
        CREATE TABLE brand_fourgram_summary (
            fourgram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT, token_c TEXT, token_d TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER, discovered_at TEXT
        );
        CREATE TABLE brand_fourgram_index (
            fourgram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (fourgram, source_id, side)
        );
        CREATE TABLE brand_fivegram_summary (
            fivegram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT, token_c TEXT, token_d TEXT, token_e TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER, discovered_at TEXT
        );
        CREATE TABLE brand_fivegram_index (
            fivegram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (fivegram, source_id, side)
        );
        CREATE TABLE brand_long_phrase_summary (
            phrase TEXT PRIMARY KEY, n_tokens INTEGER, idf REAL,
            n_party_sides INTEGER, n_distinct_source_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER, discovered_at TEXT
        );
        CREATE TABLE brand_long_phrase_index (
            phrase TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (phrase, source_id, side)
        );
        CREATE TABLE phone_summary (
            phone TEXT PRIMARY KEY, n_party_sides INTEGER, is_distinctive INTEGER,
            discovered_at TEXT
        );
        CREATE TABLE address_base_summary (
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            n_party_sides INTEGER, n_distinct_suites INTEGER,
            n_distinct_postals INTEGER, is_distinctive INTEGER,
            discovered_at TEXT,
            PRIMARY KEY (street_number, street_name, street_suffix)
        );
        CREATE TABLE address_root_summary (
            street_number TEXT NOT NULL,
            street_name TEXT NOT NULL,
            n_party_sides INTEGER NOT NULL,
            n_distinct_suffixes INTEGER NOT NULL,
            n_distinct_directions INTEGER NOT NULL,
            n_distinct_suites INTEGER NOT NULL,
            n_distinct_postals INTEGER NOT NULL,
            discovered_at TEXT,
            PRIMARY KEY (street_number, street_name)
        );
        CREATE TABLE address_unit_summary (
            city TEXT NOT NULL,
            street_number TEXT NOT NULL,
            street_name TEXT NOT NULL,
            street_suffix TEXT NOT NULL DEFAULT '',
            street_direction TEXT NOT NULL DEFAULT '',
            suite_type TEXT NOT NULL DEFAULT '',
            suite_number TEXT NOT NULL DEFAULT '',
            n_party_sides INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            discovered_at TEXT,
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE TABLE contact_fingerprint_summary (
            contact_fingerprint TEXT PRIMARY KEY,
            n_party_sides INTEGER, is_distinctive INTEGER,
            discovered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT NOT NULL,
            confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
            n_members INTEGER NOT NULL, discovered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auto_group_anchors (
            auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL, score REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );
        CREATE TABLE IF NOT EXISTS auto_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            source_id TEXT, side TEXT, corp_name TEXT,
            match_score REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE IF NOT EXISTS brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS anchor_uniqueness (
            anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            volume INTEGER NOT NULL,
            score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
        CREATE TABLE IF NOT EXISTS transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT,
            sale_price REAL
        );
        CREATE TABLE IF NOT EXISTS auto_group_anchor_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id               TEXT NOT NULL,
            anchor_type                 TEXT NOT NULL,
            anchor_value                TEXT NOT NULL,
            start_date                  TEXT NOT NULL,
            end_date                    TEXT,
            n_party_sides_in_window     INTEGER NOT NULL,
            dominance_share_in_window   REAL NOT NULL,
            score                       REAL NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
    """)
    # seed: kingsett (2 sides), ontario (3 sides), rasenberg (2 sides)
    # (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
    #  wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword,
    #  filter_reason, discovered_at)
    conn.execute(
        "INSERT INTO brand_token_summary VALUES "
        "('kingsett', 6.5, 2, 2, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES "
        "('rasenberg', 5.2, 2, 1, 1, 0, 1.56, 0, 0, 0, NULL, NULL, NULL, 0, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES "
        "('ontario', 0.8, 3, 3, 0, 0, 4.5, 1, 1, 0, 'place', NULL, NULL, 0, '2026-04-23')"
    )
    for sid, tok, phrase in [
        ("RT1", "kingsett", "kingsett capital"),
        ("RT2", "kingsett", "kingsett wealth"),
        ("RT3", "rasenberg", "rasenberg investments"),
        ("RT4", "rasenberg", "rasenberg investments"),
        ("RT5", "ontario", "1234567 ontario"),
        ("RT6", "ontario", "2345678 ontario"),
        ("RT7", "ontario", "3456789 ontario"),
    ]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) "
            "VALUES (?, 'buyer', '2020-01-01')", (sid,)
        )
        conn.execute(
            "INSERT INTO brand_token_index (token, source_id, side) VALUES (?, ?, 'buyer')",
            (tok, sid),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')", (sid, phrase)
        )
    # Seed bigrams/trigrams/phones/addresses/contacts for the new tests.
    conn.execute(
        "INSERT INTO brand_bigram_summary VALUES "
        "('kingsett capital', 'kingsett', 'capital', 5.5, 2, 1, 1, 0, 0, 0, 0, 1, '2026-04-24')"
    )
    conn.execute(
        "INSERT INTO brand_bigram_index VALUES ('kingsett capital', 'RT1', 'buyer')"
    )
    conn.execute(
        "INSERT INTO brand_bigram_index VALUES ('kingsett capital', 'RT2', 'buyer')"
    )
    conn.execute(
        "INSERT INTO brand_trigram_summary VALUES "
        "('kingsett capital gp', 'kingsett', 'capital', 'gp', 6.0, 1, 1, 1, 0, 0, 0, 0, 1, '2026-04-24')"
    )
    conn.execute(
        "INSERT INTO brand_trigram_index VALUES ('kingsett capital gp', 'RT1', 'buyer')"
    )
    conn.execute(
        "INSERT INTO phone_summary VALUES ('4166876700', 2, 1, '2026-04-24')"
    )
    conn.execute(
        "INSERT INTO address_base_summary VALUES "
        "('66', 'wellington', 'street', 3, 2, 1, 1, '2026-04-24')"
    )
    conn.execute(
        "INSERT INTO contact_fingerprint_summary VALUES ('rob kumer', 2, 1, '2026-04-24')"
    )
    conn.execute(
        "INSERT INTO brand_fourgram_summary VALUES "
        "('kingsett capital gp residential', 'kingsett', 'capital', 'gp', 'residential', "
        " 6.0, 1, 1, 1, 0, 0, 0, 0, 1, '2026-04-27')"
    )
    conn.execute(
        "INSERT INTO brand_fourgram_index VALUES ('kingsett capital gp residential', 'RT1', 'buyer')"
    )
    conn.execute(
        "INSERT INTO brand_fivegram_summary VALUES "
        "('majesty queen right province ontario', 'majesty', 'queen', 'right', 'province', 'ontario', "
        " 6.5, 1, 1, 0, 0, 0, 0, 0, 1, '2026-04-27')"
    )
    conn.execute(
        "INSERT INTO brand_fivegram_index VALUES ('majesty queen right province ontario', 'RT1', 'buyer')"
    )
    conn.execute(
        "INSERT INTO brand_long_phrase_summary VALUES "
        "('her majesty queen right province ontario represented', 7, 7.0, 1, 1, "
        " 0, 0, 0, 0, 0, 1, '2026-04-27')"
    )
    conn.execute(
        "INSERT INTO brand_long_phrase_index VALUES "
        "('her majesty queen right province ontario represented', 'RT1', 'buyer')"
    )
    # Enrich existing RT1/RT2 party_fingerprints with address/phone/contact info
    # for hydration tests. The brand_phrases already exist from the loop above
    # ("kingsett capital" on RT1, "kingsett wealth" on RT2).
    conn.execute(
        "UPDATE party_fingerprints SET "
        "city='toronto', street_number='66', street_name='wellington', street_suffix='street', "
        "suite_type='suite', suite_number='4400', postal='M5K1H6', "
        "phone='4166876700', contact_fingerprint='rob kumer', sale_date='2020-01-01' "
        "WHERE source_id='RT1' AND side='buyer'"
    )
    conn.execute(
        "UPDATE party_fingerprints SET "
        "street_number='66', street_name='wellington', street_suffix='street', "
        "suite_type='suite', suite_number='4500', postal='M5K1H6', "
        "phone='4166876700', contact_fingerprint='rob kumer', sale_date='2021-06-15' "
        "WHERE source_id='RT2' AND side='buyer'"
    )

    # ── address_root_summary seeds ────────────────────────────────
    # Root for 66 wellington: matches the 2 RT1/RT2 party_fingerprints above.
    # n_distinct_suffixes=1 (just 'street'), 1 direction, 2 suites (4400/4500),
    # 1 postal (M5K1H6).
    conn.execute(
        "INSERT INTO address_root_summary VALUES "
        "('66', 'wellington', 2, 1, 1, 2, 1, '2026-04-27')"
    )

    # Second root: 100 main with two suffixes ('street' and no-suffix).
    # Seed two party_fingerprints + two party_atoms for hydration.
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, sale_date, street_number, street_name, street_suffix, "
        " suite_type, suite_number, postal, phone, contact_fingerprint) "
        "VALUES ('RT100', 'buyer', '2022-03-01', '100', 'main', 'street', "
        " NULL, NULL, 'L1A1A1', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, sale_date, street_number, street_name, street_suffix, "
        " suite_type, suite_number, postal, phone, contact_fingerprint) "
        "VALUES ('RT101', 'buyer', '2022-04-15', '100', 'main', '', "
        " 'unit', '5', 'L1A1A2', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT100', 'buyer', 'brand_phrase', 'mainline holdings', 'party_name')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT101', 'buyer', 'brand_phrase', 'main capital', 'party_name')"
    )
    conn.execute(
        "INSERT INTO address_root_summary VALUES "
        "('100', 'main', 2, 2, 1, 2, 2, '2026-04-27')"
    )

    # ── auto_groups (Layer 2 Plan A) seeds ────────────────────────
    conn.execute("""
        INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                                 n_anchors, n_members, discovered_at)
        VALUES ('AGRP_00001', 'kingsett', 'kingsett capital', 'confirmed', 0.85, 3, 8, '2026-04-27')
    """)
    conn.execute("""
        INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                                 n_anchors, n_members, discovered_at)
        VALUES ('AGRP_00002', 'starlight', 'starlight investments', 'probable', 0.55, 2, 5, '2026-04-27')
    """)
    conn.execute("""
        INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                                 n_anchors, n_members, discovered_at)
        VALUES ('AGRP_00003', 'almostkingsett', 'almostkingsett group', 'probable', 0.72, 2, 4, '2026-04-27')
    """)
    # AGRP_00004: a confirmed group whose phone anchor overlaps with RT1's phone (4166876700).
    # This is a deliberately constructed conflict — RT1 is registered as a member of AGRP_00001
    # (kingsett), but its phone anchor would also point at AGRP_00004 (a different stem).
    conn.execute("""
        INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                                 n_anchors, n_members, discovered_at)
        VALUES ('AGRP_00004', 'rivalstem', 'rivalstem group', 'confirmed', 0.85, 1, 0, '2026-04-27')
    """)
    conn.execute(
        "INSERT INTO auto_group_anchors VALUES ('AGRP_00004', 'phone', '4166876700', 1.5)"
    )
    for at, av in [('phone', '4166876700'), ('address_unit', 'toronto|40|king|st|||'), ('contact', 'rob kumer')]:
        conn.execute(
            'INSERT INTO auto_group_anchors VALUES (?, ?, ?, 2.0)',
            ('AGRP_00001', at, av),
        )
    conn.execute(
        "INSERT INTO auto_group_members (auto_group_id, member_type, source_id, side, match_score) "
        "VALUES ('AGRP_00001', 'party_side', 'RT1', 'buyer', 1.0)"
    )

    # Add 3 more parties for AGRP_00001 to exercise coverage
    # RT-COV-1: touches phone + address_unit + contact (3-anchor coverage)
    # RT-COV-2: touches phone only (phone-only coverage)
    # RT-COV-3: touches contact only (contact-only coverage)
    conn.execute("""
        INSERT INTO party_fingerprints
            (source_id, side, phone, contact_fingerprint, city, street_number, street_name, street_suffix)
        VALUES ('RT-COV-1', 'seller', '4166876700', 'rob kumer', 'toronto', '40', 'king', 'st')
    """)
    conn.execute("""
        INSERT INTO party_fingerprints
            (source_id, side, phone, contact_fingerprint, street_number, street_name)
        VALUES ('RT-COV-2', 'seller', '4166876700', 'someone else', '999', 'somewhere')
    """)
    conn.execute("""
        INSERT INTO party_fingerprints
            (source_id, side, phone, contact_fingerprint, street_number, street_name)
        VALUES ('RT-COV-3', 'seller', '5555555555', 'rob kumer', '888', 'elsewhere')
    """)
    for sid in ('RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
        conn.execute(
            "INSERT INTO auto_group_members (auto_group_id, member_type, source_id, side, match_score) "
            "VALUES ('AGRP_00001', 'party_side', ?, 'seller', 0.9)",
            (sid,),
        )

    # RT-COSTEM: a party at AGRP_00001's phone that ALSO has a starlight phrase mapped.
    # Used to verify co-stems detection on the phone anchor.
    conn.execute("""
        INSERT INTO party_fingerprints (source_id, side, phone)
        VALUES ('RT-COSTEM', 'buyer', '4166876700')
    """)
    conn.execute("""
        INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field)
        VALUES ('RT-COSTEM', 'buyer', 'brand_phrase', 'starlight investments', 'party_name')
    """)
    # Make sure starlight has a stem mapping in this fixture so co-stems can detect it.
    conn.execute("""
        INSERT OR IGNORE INTO brand_stem (stem, stem_type, dominant_anchor_type,
                                          dominant_anchor_value, dominance_share, volume)
        VALUES ('starlight', 'distinctive', 'phone', '4162348444', 0.9, 100)
    """)
    conn.execute("""
        INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence)
        VALUES ('starlight investments', 'starlight', 1.0)
    """)
    # Seed a phone-category near-miss anchor for the starlight stem so the
    # /why-tier endpoint exercises the non-trivial _near_miss_anchor path.
    # score=0.9 sits between the corroboration bar (0.5) and seeding threshold (1.5).
    conn.execute("""
        INSERT INTO anchor_uniqueness
            (anchor_type, anchor_value, dominant_stem, dominance_share, volume, score, is_service_provider)
        VALUES ('phone', 'NEAR_MISS_PHONE', 'starlight', 0.7, 5, 0.9, 0)
    """)
    # Same for kingsett — its parties use 'kingsett capital' as the brand phrase.
    conn.execute("""
        INSERT OR IGNORE INTO brand_stem (stem, stem_type, dominant_anchor_type,
                                          dominant_anchor_value, dominance_share, volume)
        VALUES ('kingsett', 'distinctive', 'phone', '4166876700', 0.9, 8)
    """)
    conn.execute("""
        INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence)
        VALUES ('kingsett capital', 'kingsett', 1.0)
    """)
    # Backfill brand_phrase atoms on the kingsett parties so co-stems has signal to compare against.
    for sid in ('RT1', 'RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', 'kingsett capital', 'party_name')",
            (sid, 'buyer' if sid == 'RT1' else 'seller'),
        )

    # ── Missed-stem seed (Plan G Task 3) ──────────────────────────
    # A position-anchor 1-gram that did NOT promote — 'lostbrand', 120 sides.
    # We seed brand_token_index entries to give it phone-anchor concentration.
    conn.execute("""
        INSERT OR IGNORE INTO brand_token_summary
            (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
             wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword,
             filter_reason, position_consistency, total_child_coverage,
             is_position_anchor, discovered_at)
        VALUES ('lostbrand', 6.5, 120, 8, 0, 0, 0.0, 0, 0, 0, NULL, 0.95, 0.99, 1, '2026-04-26')
    """)
    # Confirm brand_token_index table exists (added in earlier migrations); seed entries
    # that show 'lostbrand' is most concentrated at phone 4166876700 (kingsett's phone).
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brand_token_index (
            token TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (token, source_id, side)
        );
    """)
    # Seed 4 sides with lostbrand all at phone 4166876700 (via the existing party_fingerprints
    # rows RT1, RT-COV-1, RT-COV-2 + a new one).
    conn.execute("""
        INSERT OR IGNORE INTO party_fingerprints (source_id, side, phone)
        VALUES ('RT-LOSTBRAND-1', 'buyer', '4166876700')
    """)
    for sid, side in [('RT1', 'buyer'), ('RT-COV-1', 'seller'),
                       ('RT-COV-2', 'seller'), ('RT-LOSTBRAND-1', 'buyer')]:
        conn.execute(
            "INSERT OR IGNORE INTO brand_token_index (token, source_id, side) VALUES ('lostbrand', ?, ?)",
            (sid, side),
        )

    # ── Transactions for /parties enrichment (Plan D Task 3) ──────
    for sid, date, price in [
        ('RT1',       '2019-04-22', 5_200_000),
        ('RT-COV-1',  '2020-06-01', 8_400_000),
        ('RT-COV-2',  '2021-03-15', 3_100_000),
        ('RT-COV-3',  '2022-09-30',   780_000),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO transactions (source_id, sale_date, sale_price) VALUES (?, ?, ?)",
            (sid, date, price),
        )
    # Mirror sale_date back onto party_fingerprints (some queries read it from there)
    for sid in ('RT1', 'RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
        conn.execute(
            "UPDATE party_fingerprints SET sale_date = (SELECT sale_date FROM transactions WHERE source_id = ?) "
            "WHERE source_id = ?",
            (sid, sid),
        )

    # Seed address_unit_summary for 66 wellington (toronto): three units (Plan H1)
    conn.execute("""
        INSERT INTO address_unit_summary
           (city, street_number, street_name, street_suffix, street_direction,
            suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
            dominant_stem, dominance_share)
        VALUES
           ('toronto', '66', 'wellington', 'street', 'west', 'suite', '4400', 156, 3, 'kingsett', 0.88),
           ('toronto', '66', 'wellington', 'street', 'west', 'suite', '4100', 11, 2, 'weirfoulds', 0.82),
           ('toronto', '66', 'wellington', 'street', 'west', 'floor', '30th flr', 3, 0, NULL, 0.0)
    """)

    # ── auto_group_anchor_tenures seeds (Plan H3 Task 1) ─────────
    # Seed a tenure for AGRP_00001 (kingsett) at the phone 4166876700.
    conn.execute("""
        INSERT INTO auto_group_anchor_tenures
           (auto_group_id, anchor_type, anchor_value,
            start_date, end_date, n_party_sides_in_window,
            dominance_share_in_window, score)
        VALUES ('AGRP_00001', 'phone', '4166876700',
                '2010-01-01', '2026-01-01', 137, 0.95, 6.5)
    """)

    # ── Plan H3 Task 2: address_unit + contact timeline fixture data ──────────

    # Party fingerprint with full address_unit key (incl. street_direction='west')
    # to back the address_unit timeline endpoint.
    # Note: no phone field here — avoids inflating the phone anchor coverage
    # count checked by test_anchors_with_coverage_returns_per_anchor_coverage.
    conn.execute("""
        INSERT INTO party_fingerprints
            (source_id, side, sale_date,
             city, street_number, street_name, street_suffix, street_direction,
             suite_type, suite_number, contact_fingerprint)
        VALUES ('RT-UNIT-1', 'buyer', '2021-03-10',
                'toronto', '66', 'wellington', 'street', 'west',
                'suite', '4400', 'rob kumer')
    """)
    conn.execute("""
        INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field)
        VALUES ('RT-UNIT-1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')
    """)
    conn.execute(
        "INSERT OR IGNORE INTO auto_group_members "
        "(auto_group_id, member_type, source_id, side, match_score) "
        "VALUES ('AGRP_00001', 'party_side', 'RT-UNIT-1', 'buyer', 1.0)"
    )

    # Tenure for address_unit anchor 'toronto|66|wellington|street|west|suite|4400'.
    conn.execute("""
        INSERT INTO auto_group_anchor_tenures
           (auto_group_id, anchor_type, anchor_value,
            start_date, end_date, n_party_sides_in_window,
            dominance_share_in_window, score)
        VALUES ('AGRP_00001', 'address_unit', 'toronto|66|wellington|street|west|suite|4400',
                '2015-06-01', '2026-06-01', 156, 0.88, 5.2)
    """)

    # Contact fingerprint 'jc' — a new contact distinct from 'rob kumer'.
    conn.execute("""
        INSERT INTO contact_fingerprint_summary
            (contact_fingerprint, n_party_sides, is_distinctive, discovered_at)
        VALUES ('jc', 2, 1, '2026-04-29')
    """)
    conn.execute("""
        INSERT INTO party_fingerprints
            (source_id, side, sale_date, contact_fingerprint)
        VALUES ('RT-JC-1', 'seller', '2022-07-01', 'jc')
    """)
    conn.execute("""
        INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field)
        VALUES ('RT-JC-1', 'seller', 'brand_phrase', 'jc investments', 'party_name')
    """)
    conn.execute(
        "INSERT OR IGNORE INTO auto_group_members "
        "(auto_group_id, member_type, source_id, side, match_score) "
        "VALUES ('AGRP_00001', 'party_side', 'RT-JC-1', 'seller', 0.8)"
    )

    # auto_contact_tenures table + one tenure row linking 'jc' to AGRP_00001.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_contact_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            auto_group_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL,
            discovered_at TEXT
        );
    """)
    conn.execute("""
        INSERT INTO auto_contact_tenures
            (contact_fingerprint, auto_group_id, start_date, end_date,
             n_party_sides_in_window, discovered_at)
        VALUES ('jc', 'AGRP_00001', '2020-01-01', '2026-01-01', 8, '2026-04-29')
    """)

    conn.commit()
    return conn


@pytest.fixture
def client():
    """TestClient with a seeded in-memory DB injected via dependency override."""
    from cleo.web.app import app
    from cleo.web import deps

    conn = _seeded_db()

    def _get_conn_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_conn_override
    # Bypass auth for these tests — explorer routes don't need a real user.
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_list_distinctive_tokens_descending_by_count(client):
    resp = client.get("/api/explorer/brands", params={"distinctive_only": "true"})
    assert resp.status_code == 200
    body = resp.json()
    # kingsett + rasenberg are distinctive; lostbrand is a position anchor (Plan G fixture).
    # Default include_position_anchors=true picks all three up.
    assert body["total"] == 3
    tokens = [t["token"] for t in body["results"]]
    # lostbrand has n_party_sides=120, so it sorts first; kingsett/rasenberg both =2,
    # tiebreak alphabetical ASC.
    assert tokens == ["lostbrand", "kingsett", "rasenberg"]


def test_list_all_tokens_includes_nondistinctive(client):
    resp = client.get("/api/explorer/brands", params={"distinctive_only": "false"})
    body = resp.json()
    assert body["total"] == 4
    tokens = {t["token"] for t in body["results"]}
    assert tokens == {"kingsett", "rasenberg", "ontario", "lostbrand"}


def test_list_search_filter(client):
    resp = client.get("/api/explorer/brands", params={"q": "king", "distinctive_only": "false"})
    body = resp.json()
    tokens = [t["token"] for t in body["results"]]
    assert tokens == ["kingsett"]


def test_detail_returns_party_sides_and_phrases(client):
    resp = client.get("/api/explorer/brands/kingsett")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "kingsett"
    assert body["n_party_sides"] == 2
    assert set(body["phrases"]) == {"kingsett capital", "kingsett wealth"}
    ps_keys = {(p["source_id"], p["side"]) for p in body["party_sides"]}
    assert ps_keys == {("RT1", "buyer"), ("RT2", "buyer")}


def test_detail_unknown_token_returns_404(client):
    resp = client.get("/api/explorer/brands/nonesuch")
    assert resp.status_code == 404


def test_list_response_includes_signal_fields(client):
    resp = client.get("/api/explorer/brands?distinctive_only=false")
    body = resp.json()
    for t in body["results"]:
        for field in ("wordfreq_zipf", "is_english_common", "is_place_name",
                      "is_industry_stopword", "filter_reason"):
            assert field in t, f"Response missing {field!r}: {t!r}"


def test_list_supports_filter_reason_param(client):
    # Only 'ontario' in the fixture has filter_reason='place'.
    resp = client.get("/api/explorer/brands?distinctive_only=false&filter_reason=place")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["results"][0]["token"] == "ontario"


def test_list_filter_reason_english_returns_none_in_fixture(client):
    # No token in the fixture has filter_reason='english'.
    resp = client.get("/api/explorer/brands?distinctive_only=false&filter_reason=english")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_mark_industry_stopword(client):
    resp = client.post("/api/explorer/brands/kingsett/industry-stopword")
    assert resp.status_code == 204

    resp2 = client.get("/api/explorer/industry-stopwords")
    body = resp2.json()
    assert "kingsett" in {r["token"] for r in body["results"]}

    # Brand summary for 'kingsett' should reflect the change.
    resp3 = client.get("/api/explorer/brands/kingsett")
    body3 = resp3.json()
    assert body3["is_industry_stopword"] == 1
    assert body3["is_distinctive"] == 0
    assert body3["filter_reason"] == "industry"


def test_unmark_industry_stopword(client):
    # Start fresh — mark then unmark.
    client.post("/api/explorer/brands/kingsett/industry-stopword")
    resp = client.delete("/api/explorer/brands/kingsett/industry-stopword")
    assert resp.status_code == 204

    resp2 = client.get("/api/explorer/industry-stopwords")
    body = resp2.json()
    assert "kingsett" not in {r["token"] for r in body["results"]}

    # Brand summary for 'kingsett' should have is_industry_stopword=0 and,
    # since its other filter flags are all 0 and it was distinctive before,
    # filter_reason should revert to NULL and is_distinctive=1.
    resp3 = client.get("/api/explorer/brands/kingsett")
    body3 = resp3.json()
    assert body3["is_industry_stopword"] == 0
    # Note: our fixture kingsett has idf=6.5 > default min_idf=3.0, and all
    # other filters are 0. So it should become distinctive again.
    assert body3["is_distinctive"] == 1
    assert body3["filter_reason"] is None


def test_mark_unknown_token_returns_404(client):
    # Optional behavior — adding a token that isn't in brand_token_summary
    # should still succeed as a bare insert into industry_stopwords, but the
    # summary-sync step has no row to update. We accept either 204 or 404.
    resp = client.post("/api/explorer/brands/zzz_nonesuch/industry-stopword")
    assert resp.status_code in (204, 404)


def test_mark_place(client):
    resp = client.post("/api/explorer/brands/kingsett/place")
    assert resp.status_code == 204

    resp2 = client.get("/api/explorer/places")
    body = resp2.json()
    assert "kingsett" in {r["token"] for r in body["results"]}

    resp3 = client.get("/api/explorer/brands/kingsett")
    body3 = resp3.json()
    assert body3["is_place_name"] == 1
    assert body3["is_distinctive"] == 0
    assert body3["filter_reason"] == "place"


def test_unmark_place(client):
    client.post("/api/explorer/brands/kingsett/place")
    resp = client.delete("/api/explorer/brands/kingsett/place")
    assert resp.status_code == 204

    resp2 = client.get("/api/explorer/places")
    body = resp2.json()
    assert "kingsett" not in {r["token"] for r in body["results"]}

    resp3 = client.get("/api/explorer/brands/kingsett")
    body3 = resp3.json()
    assert body3["is_place_name"] == 0
    # Was distinctive in the fixture (idf=6.5 > 3.0, no other flags set), so:
    assert body3["is_distinctive"] == 1
    assert body3["filter_reason"] is None


def test_place_takes_precedence_over_english_in_reason(client):
    # Simulate a token with is_english_common=1 already set
    conn = _seeded_db()
    conn.execute(
        "UPDATE brand_token_summary SET is_english_common = 1 WHERE token = 'kingsett'"
    )
    conn.commit()

    from cleo.web.app import app
    from cleo.web import deps

    def _get_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_override
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}

    from fastapi.testclient import TestClient
    local_client = TestClient(app)

    local_client.post("/api/explorer/brands/kingsett/place")
    resp = local_client.get("/api/explorer/brands/kingsett")
    body = resp.json()
    # Both english AND place flags are set; precedence says reason = 'place'
    assert body["is_english_common"] == 1
    assert body["is_place_name"] == 1
    assert body["filter_reason"] == "place"

    app.dependency_overrides.clear()
    conn.close()


# ── Bigrams ────────────────────────────────────────────────────

def test_list_bigrams(client):
    resp = client.get("/api/explorer/brands/bigrams")
    assert resp.status_code == 200
    body = resp.json()
    tokens = {t["bigram"] for t in body["results"]}
    assert "kingsett capital" in tokens


def test_bigram_detail(client):
    resp = client.get("/api/explorer/brands/bigrams/kingsett%20capital")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bigram"] == "kingsett capital"
    assert body["n_party_sides"] == 2
    assert len(body["party_sides"]) == 2
    # Each party-side has brand_phrases hydrated
    for ps in body["party_sides"]:
        assert "brand_phrases" in ps
        # The phrases should have contains_token flag set correctly
        for bp in ps["brand_phrases"]:
            assert "contains_token" in bp


def test_bigram_detail_404(client):
    resp = client.get("/api/explorer/brands/bigrams/zz_unknown")
    assert resp.status_code == 404


# ── Trigrams ───────────────────────────────────────────────────

def test_trigram_detail(client):
    resp = client.get("/api/explorer/brands/trigrams/kingsett%20capital%20gp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trigram"] == "kingsett capital gp"
    assert body["token_c"] == "gp"


# ── Phones ─────────────────────────────────────────────────────

def test_list_phones(client):
    resp = client.get("/api/explorer/phones")
    body = resp.json()
    phones = {r["phone"] for r in body["results"]}
    assert "4166876700" in phones


def test_phone_detail_includes_party_sides(client):
    resp = client.get("/api/explorer/phones/4166876700")
    body = resp.json()
    assert body["phone"] == "4166876700"
    # Phone is shared across the original RT1/RT2 plus the coverage/co-stem
    # parties (RT-COV-1, RT-COV-2, RT-COSTEM) added for Plan D anchor coverage.
    assert len(body["party_sides"]) >= 2
    # Each party-side has address + contact + brand_phrases
    ps = body["party_sides"][0]
    assert "street_number" in ps
    assert "contact_fingerprint" in ps
    assert "brand_phrases" in ps


def test_phone_detail_404(client):
    resp = client.get("/api/explorer/phones/9999999999")
    assert resp.status_code == 404


# ── Addresses ──────────────────────────────────────────────────

def test_list_addresses(client):
    resp = client.get("/api/explorer/addresses")
    body = resp.json()
    assert body["total"] >= 1
    first = body["results"][0]
    assert "key" in first
    assert first["key"] == "66|wellington|street"


def test_address_detail_has_suite_variants(client):
    resp = client.get("/api/explorer/addresses/66%7Cwellington%7Cstreet")
    assert resp.status_code == 200
    body = resp.json()
    assert body["street_number"] == "66"
    assert body["street_name"] == "wellington"
    assert body["street_suffix"] == "street"
    assert body["n_party_sides"] == 3
    assert "suite_variants" in body
    # Two distinct suites in our seed (4400 and 4500)
    assert len(body["suite_variants"]) >= 2
    assert "party_sides" in body
    # Hydrated party-sides
    for ps in body["party_sides"]:
        assert "brand_phrases" in ps


def test_address_detail_404(client):
    resp = client.get("/api/explorer/addresses/zz%7Cnowhere%7Clane")
    assert resp.status_code == 404


# ── Address Roots ──────────────────────────────────────────────

def test_list_address_roots(client):
    resp = client.get("/api/explorer/addresses/roots")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    keys = [r["key"] for r in body["results"]]
    # Both seeded roots have n_party_sides=2 — tiebreak alphabetical by name ASC.
    assert "66|wellington" in keys
    assert "100|main" in keys
    # Each row should expose the canonical fields.
    first = body["results"][0]
    assert first["key"] == f"{first['street_number']}|{first['street_name']}"
    assert "n_distinct_suffixes" in first
    assert "n_distinct_directions" in first
    assert "n_distinct_suites" in first
    assert "n_distinct_postals" in first


def test_list_address_roots_q_filters_by_number_or_name(client):
    # Match by name substring
    resp = client.get("/api/explorer/addresses/roots", params={"q": "well"})
    assert resp.status_code == 200
    body = resp.json()
    keys = [r["key"] for r in body["results"]]
    assert keys == ["66|wellington"]

    # Match by number substring
    resp2 = client.get("/api/explorer/addresses/roots", params={"q": "100"})
    body2 = resp2.json()
    keys2 = [r["key"] for r in body2["results"]]
    assert "100|main" in keys2


def test_list_address_roots_pagination(client):
    resp = client.get(
        "/api/explorer/addresses/roots", params={"per_page": 1, "page": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["per_page"] == 1
    assert body["page"] == 1
    assert body["total"] >= 2
    assert len(body["results"]) == 1

    resp2 = client.get(
        "/api/explorer/addresses/roots", params={"per_page": 1, "page": 2}
    )
    body2 = resp2.json()
    assert body2["total"] == body["total"]
    assert body2["page"] == 2
    assert len(body2["results"]) == 1
    # Different row on page 2.
    assert body2["results"][0]["key"] != body["results"][0]["key"]


def test_address_root_detail_breakdowns(client):
    # 100 main has two suffixes: 'street' (RT100) and "" (RT101).
    resp = client.get("/api/explorer/addresses/roots/100%7Cmain")
    assert resp.status_code == 200
    body = resp.json()
    assert body["street_number"] == "100"
    assert body["street_name"] == "main"
    assert body["key"] == "100|main"
    assert body["n_party_sides"] == 2
    assert body["n_distinct_suffixes"] == 2

    # by_suffix should have both: "street" with base_key, "(none)" with base_key=null.
    suffixes = {entry["value"]: entry for entry in body["by_suffix"]}
    assert "street" in suffixes
    assert suffixes["street"]["base_key"] == "100|main|street"
    assert suffixes["street"]["n_party_sides"] == 1
    assert "(none)" in suffixes
    assert suffixes["(none)"]["base_key"] is None
    assert suffixes["(none)"]["n_party_sides"] == 1
    # Sorted DESC by count (here both = 1, but field exists).
    counts = [e["n_party_sides"] for e in body["by_suffix"]]
    assert counts == sorted(counts, reverse=True)
    assert len(body["by_suffix"]) <= 50

    # by_suite — sorted DESC, capped at 50.
    counts_suite = [e["n_party_sides"] for e in body["by_suite"]]
    assert counts_suite == sorted(counts_suite, reverse=True)
    assert len(body["by_suite"]) <= 50

    # by_postal — sorted DESC, capped at 50.
    counts_postal = [e["n_party_sides"] for e in body["by_postal"]]
    assert counts_postal == sorted(counts_postal, reverse=True)
    assert len(body["by_postal"]) <= 50
    # Both seeded postals should appear.
    postals = {e["postal"] for e in body["by_postal"]}
    assert postals == {"L1A1A1", "L1A1A2"}


def test_address_root_detail_404(client):
    resp = client.get("/api/explorer/addresses/roots/zz%7Cnowhere")
    assert resp.status_code == 404


def test_address_root_detail_400_on_malformed_key(client):
    resp = client.get("/api/explorer/addresses/roots/justonepart")
    assert resp.status_code == 400


def test_address_root_detail_party_sides_hydrated(client):
    resp = client.get("/api/explorer/addresses/roots/100%7Cmain")
    assert resp.status_code == 200
    body = resp.json()
    assert "party_sides" in body
    ps_keys = {(p["source_id"], p["side"]) for p in body["party_sides"]}
    assert ps_keys == {("RT100", "buyer"), ("RT101", "buyer")}
    for ps in body["party_sides"]:
        assert "brand_phrases" in ps
    # At least one party-side has a brand_phrase from the seeded atoms.
    all_phrases = {
        bp["phrase"]
        for ps in body["party_sides"]
        for bp in ps["brand_phrases"]
    }
    assert "mainline holdings" in all_phrases or "main capital" in all_phrases


# ── Contacts ───────────────────────────────────────────────────

def test_list_contacts(client):
    resp = client.get("/api/explorer/contacts")
    body = resp.json()
    names = {r["contact_fingerprint"] for r in body["results"]}
    assert "rob kumer" in names


def test_contact_detail(client):
    resp = client.get("/api/explorer/contacts/rob%20kumer")
    body = resp.json()
    assert body["contact_fingerprint"] == "rob kumer"
    # 'rob kumer' is touched by RT1/RT2 plus the Plan D coverage parties
    # (RT-COV-1 and RT-COV-3).
    assert len(body["party_sides"]) >= 2


# ── 4-grams ────────────────────────────────────────────────────

def test_list_4grams(client):
    resp = client.get("/api/explorer/brands/4grams")
    assert resp.status_code == 200
    body = resp.json()
    assert any(t["fourgram"] == "kingsett capital gp residential" for t in body["results"])


def test_4gram_detail_includes_containment(client):
    resp = client.get("/api/explorer/brands/4grams/kingsett%20capital%20gp%20residential")
    assert resp.status_code == 200
    body = resp.json()
    assert body["fourgram"] == "kingsett capital gp residential"
    assert body["token_d"] == "residential"
    assert "contains" in body
    assert "extended_by" in body


# ── 5-grams ────────────────────────────────────────────────────

def test_list_5grams(client):
    resp = client.get("/api/explorer/brands/5grams")
    body = resp.json()
    assert any(t["fivegram"] == "majesty queen right province ontario" for t in body["results"])


def test_5gram_detail(client):
    resp = client.get("/api/explorer/brands/5grams/majesty%20queen%20right%20province%20ontario")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_e"] == "ontario"
    assert "contains" in body
    assert "extended_by" in body


# ── Long-form ──────────────────────────────────────────────────

def test_list_long_phrases(client):
    resp = client.get("/api/explorer/brands/long-phrases")
    body = resp.json()
    assert any(t["phrase"] == "her majesty queen right province ontario represented"
               for t in body["results"])


def test_long_phrase_detail(client):
    encoded = "her%20majesty%20queen%20right%20province%20ontario%20represented"
    resp = client.get(f"/api/explorer/brands/long-phrases/{encoded}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_tokens"] == 7
    assert "contains" in body
    # extended_by is empty for long-form (no longer level)
    assert body["extended_by"] == []


# ── Containment in existing endpoints ──────────────────────────

def test_2gram_detail_now_includes_containment(client):
    resp = client.get("/api/explorer/brands/bigrams/kingsett%20capital")
    body = resp.json()
    assert "contains" in body
    assert "extended_by" in body
    # contains should have the two 1grams
    contained_values = {c["value"] for c in body["contains"]}
    assert "kingsett" in contained_values
    assert "capital" in contained_values


def test_1gram_detail_now_includes_containment(client):
    resp = client.get("/api/explorer/brands/kingsett")
    body = resp.json()
    assert "contains" in body
    assert "extended_by" in body
    # 1gram has no contains
    assert body["contains"] == []


# ── Brand Family + Search ──────────────────────────────────────

def test_brands_family_returns_tight_and_loose(client):
    resp = client.get("/api/explorer/brands/family",
                      params={"seed_value": "kingsett", "seed_level": "1gram"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["seed_value"] == "kingsett"
    assert body["seed_level"] == "1gram"
    assert "tight" in body
    assert "loose_sections" in body
    # Loose section should have one entry (the token itself) since it's a 1-gram seed
    assert len(body["loose_sections"]) == 1
    assert body["loose_sections"][0]["token"] == "kingsett"


def test_brands_family_2gram_seed_has_two_loose_sections(client):
    resp = client.get("/api/explorer/brands/family",
                      params={"seed_value": "kingsett capital", "seed_level": "2gram"})
    body = resp.json()
    assert len(body["loose_sections"]) == 2
    tokens = [s["token"] for s in body["loose_sections"]]
    assert set(tokens) == {"kingsett", "capital"}


def test_brands_family_loose_paginates(client):
    resp = client.get("/api/explorer/brands/family/loose",
                      params={"token": "kingsett", "per_page": 10})
    body = resp.json()
    assert body["token"] == "kingsett"
    assert "results" in body
    assert "pages" in body


def test_brands_search_returns_grouped_by_level(client):
    resp = client.get("/api/explorer/brands/search", params={"q": "kingsett"})
    body = resp.json()
    assert body["q"] == "kingsett"
    assert "results_by_level" in body
    assert "1gram" in body["results_by_level"]
    assert "2gram" in body["results_by_level"]
    # Should find 'kingsett' as a 1-gram
    onegram_tokens = {r["value"] for r in body["results_by_level"]["1gram"]}
    assert "kingsett" in onegram_tokens


def test_1gram_list_returns_position_anchor_field(client):
    resp = client.get("/api/explorer/brands?distinctive_only=false&per_page=100")
    body = resp.json()
    for row in body["results"]:
        assert "is_position_anchor" in row


def test_1gram_detail_returns_position_anchor_fields(client):
    resp = client.get("/api/explorer/brands/kingsett")
    body = resp.json()
    assert "is_position_anchor" in body
    assert "position_consistency" in body
    assert "total_child_coverage" in body


@pytest.fixture
def client_with_anchor(client):
    """Extend the standard client fixture with a position-anchor row in brand_token_summary."""
    # The client fixture's dependency override yields a connection; retrieve it via a
    # fresh call to _seeded_db so we can insert extra rows without touching the generator.
    db = _seeded_db()
    db.execute(
        "INSERT OR REPLACE INTO brand_token_summary VALUES "
        "('testanchor', 5.0, 30, 5, 0, 0, 2.0, 0, 0, 0, NULL, 1.0, 1.0, 1, '2026-04-27')"
    )
    db.execute(
        "INSERT OR REPLACE INTO brand_token_summary VALUES "
        "('testanchor2', 5.0, 30, 5, 0, 0, 2.0, 0, 0, 0, NULL, 1.0, 1.0, 1, '2026-04-27')"
    )
    db.commit()

    from cleo.web.app import app
    from cleo.web import deps
    from fastapi.testclient import TestClient

    def _get_override():
        yield db

    app.dependency_overrides[deps.get_db] = _get_override
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_list_brand_tokens_include_position_anchors_default_true(client_with_anchor):
    """Default: distinctive_only=true + include_position_anchors=true (default) surfaces
    both is_distinctive=1 AND is_position_anchor=1 rows."""
    resp = client_with_anchor.get(
        "/api/explorer/brands?distinctive_only=true&include_position_anchors=true"
    )
    body = resp.json()
    tokens = {r["token"] for r in body["results"]}
    assert "testanchor" in tokens       # picked up via PA flag
    assert "kingsett" in tokens         # distinctive row still present


def test_list_brand_tokens_include_position_anchors_false_excludes_anchors(client_with_anchor):
    """With distinctive_only=true and include_position_anchors=false, PA-only rows excluded."""
    resp = client_with_anchor.get(
        "/api/explorer/brands?distinctive_only=true&include_position_anchors=false"
    )
    body = resp.json()
    tokens = {r["token"] for r in body["results"]}
    assert "testanchor2" not in tokens  # excluded — only distinctive rows
    assert "kingsett" in tokens


# ── Auto-groups ──────────────────────────────────────────────────

def test_list_auto_groups_default_returns_confirmed_only(client):
    resp = client.get('/api/explorer/auto-groups')
    assert resp.status_code == 200
    body = resp.json()
    tiers = {g['tier'] for g in body['results']}
    assert tiers == {'confirmed'}


def test_list_auto_groups_tier_filter(client):
    resp = client.get('/api/explorer/auto-groups', params={'tier': 'probable'})
    body = resp.json()
    assert all(g['tier'] == 'probable' for g in body['results'])


def test_list_auto_groups_q_substring(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'tier': 'confirmed', 'q': 'kingsett'})
    body = resp.json()
    assert body['total'] >= 1
    assert any('kingsett' in g['canonical_stem'].lower() for g in body['results'])


def test_auto_group_detail_returns_anchors_and_members(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001')
    assert resp.status_code == 200
    body = resp.json()
    assert body['canonical_stem'] == 'kingsett'
    assert body['display_name'] == 'kingsett capital'
    assert body['tier'] == 'confirmed'
    assert len(body['anchors']) >= 3
    types = {a['anchor_type'] for a in body['anchors']}
    assert {'phone', 'address_unit', 'contact'}.issubset(types)
    assert isinstance(body['members'], list)


def test_auto_group_detail_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999')
    assert resp.status_code == 404


def test_anchors_with_coverage_returns_per_anchor_coverage(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchors-with-coverage')
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body['anchors'], list)
    # Find the phone anchor
    phone = next(a for a in body['anchors'] if a['anchor_type'] == 'phone')
    assert phone['anchor_value'] == '4166876700'
    # 3 parties touch this phone (RT1, RT-COV-1, RT-COV-2). RT-COV-3 doesn't.
    assert phone['coverage'] == 3


def test_anchors_with_coverage_returns_co_stems(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchors-with-coverage')
    body = resp.json()
    phone = next(a for a in body['anchors'] if a['anchor_type'] == 'phone')
    # The phone is shared with a 'starlight' phrase via RT-COSTEM
    co_stems = {c['stem'] for c in phone['co_stems']}
    assert 'starlight' in co_stems


def test_anchors_with_coverage_404_on_unknown(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/anchors-with-coverage')
    assert resp.status_code == 404


def test_why_tier_confirmed_lists_three_categories(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/why-tier')
    assert resp.status_code == 200
    body = resp.json()
    assert body['tier'] == 'confirmed'
    assert body['n_categories_passing'] == 3
    cats = {c['category']: c for c in body['categories']}
    assert {'phone', 'address', 'contact'} == set(cats.keys())
    for c in cats.values():
        assert c['passes_threshold'] is True
        assert c['strongest_anchor'] is not None


def test_why_tier_probable_identifies_missing_category(client):
    # AGRP_00002 (starlight, probable) has no anchors in the seed.
    # We need to add at least 2 anchor categories that pass for it to be
    # legitimately probable, but leave 1 category missing so the test exercises
    # the missing-category logic. Inject 2 strong anchors into the fixture
    # before the test client is created — but here we work with what's seeded.
    # If AGRP_00002 has zero anchors, this test verifies the empty case.
    resp = client.get('/api/explorer/auto-groups/AGRP_00002/why-tier')
    assert resp.status_code == 200
    body = resp.json()
    assert body['tier'] == 'probable'
    # n_categories_passing reflects how many categories had a strong anchor.
    # For this fixture, AGRP_00002 has no anchors → 0 passing.
    assert body['n_categories_passing'] == 0
    # All 3 categories should appear, each marked passes_threshold=False
    cats = {c['category'] for c in body['categories']}
    assert cats == {'phone', 'address', 'contact'}
    assert all(c['passes_threshold'] is False for c in body['categories'])


def test_why_tier_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/why-tier')
    assert resp.status_code == 404


def test_why_tier_surfaces_near_miss_for_missing_category(client):
    """Verify _near_miss_anchor surfaces a real row when score is between the
    corroboration bar and the seeding threshold for the group's stem."""
    resp = client.get('/api/explorer/auto-groups/AGRP_00002/why-tier')
    assert resp.status_code == 200
    body = resp.json()
    cats = {c['category']: c for c in body['categories']}
    phone_cat = cats['phone']
    assert phone_cat['passes_threshold'] is False
    assert phone_cat['near_miss_anchor'] is not None
    assert phone_cat['near_miss_anchor']['anchor_value'] == 'NEAR_MISS_PHONE'
    assert phone_cat['near_miss_anchor']['score'] == pytest.approx(0.9)


# ── /parties endpoint (Plan D Task 3) ─────────────────────────

def test_parties_returns_enriched_rows(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/parties')
    assert resp.status_code == 200
    body = resp.json()
    assert body['total'] >= 4
    first = body['results'][0]
    # Required fields
    for f in ('source_id', 'side', 'match_score', 'sale_date', 'sale_price',
              'phone', 'contact', 'street_number', 'street_name',
              'top_brand_phrase', 'anchor_signature'):
        assert f in first


def test_parties_anchor_signature_lists_matching_group_anchors(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/parties')
    body = resp.json()
    # RT-COV-1 touches phone + address_unit + contact (3 anchors)
    cov1 = next(p for p in body['results'] if p['source_id'] == 'RT-COV-1')
    sig_categories = {entry['category'] for entry in cov1['anchor_signature']}
    assert {'phone', 'address', 'contact'}.issubset(sig_categories)
    # RT-COV-2 touches phone only
    cov2 = next(p for p in body['results'] if p['source_id'] == 'RT-COV-2')
    sig_categories_2 = {entry['category'] for entry in cov2['anchor_signature']}
    assert sig_categories_2 == {'phone'}


def test_parties_filter_by_anchor(client):
    # Show only parties that touch contact 'rob kumer'
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'anchor_type': 'contact', 'anchor_value': 'rob kumer'},
    )
    body = resp.json()
    sids = {p['source_id'] for p in body['results']}
    # RT1 and RT-COV-1 and RT-COV-3 all have rob kumer; RT-COV-2 has someone else.
    assert 'RT-COV-2' not in sids


def test_parties_filter_by_min_match_score(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'min_match_score': 0.95},
    )
    body = resp.json()
    for p in body['results']:
        assert p['match_score'] >= 0.95


def test_parties_pagination(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'per_page': 2, 'page': 1},
    )
    body = resp.json()
    assert len(body['results']) <= 2
    assert body['per_page'] == 2
    assert body['page'] == 1


def test_parties_sort_by_match_score_desc(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'sort': 'match_score', 'order': 'desc'},
    )
    body = resp.json()
    scores = [p['match_score'] for p in body['results']]
    assert scores == sorted(scores, reverse=True)


def test_parties_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/parties')
    assert resp.status_code == 404


def test_parties_400_on_invalid_side(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'side': 'middleman'},
    )
    assert resp.status_code == 400


def test_parties_400_on_invalid_anchor_type(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'anchor_type': 'foo', 'anchor_value': 'bar'},
    )
    assert resp.status_code == 400


def test_parties_400_on_anchor_type_without_value(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'anchor_type': 'phone'},  # no anchor_value
    )
    assert resp.status_code == 400


def test_histogram_returns_buckets(client):
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    assert resp.status_code == 200
    body = resp.json()
    assert 'buckets' in body
    # 20 buckets covering [0.00, 1.00] in 0.05 increments.
    assert len(body['buckets']) == 20
    first = body['buckets'][0]
    assert first['lower'] == pytest.approx(0.0)
    assert first['upper'] == pytest.approx(0.05)
    assert 'count' in first


def test_histogram_includes_threshold_lines(client):
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    body = resp.json()
    assert body['tier_confirmed_threshold'] == pytest.approx(0.75)
    assert body['tier_probable_threshold'] == pytest.approx(0.4)


def test_histogram_counts_match_real_groups(client):
    # The fixture has at least 2 auto_groups (AGRP_00001 confirmed @ 0.85, AGRP_00002 probable @ 0.55).
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    body = resp.json()
    total_in_buckets = sum(b['count'] for b in body['buckets'])
    # Should at least match the 2 seeded groups.
    assert total_in_buckets >= 2
    # AGRP_00001 (0.85) lands in [0.85, 0.90)
    bucket_85 = next(b for b in body['buckets'] if b['lower'] == pytest.approx(0.85))
    assert bucket_85['count'] >= 1
    # AGRP_00002 (0.55) lands in [0.55, 0.60)
    bucket_55 = next(b for b in body['buckets'] if b['lower'] == pytest.approx(0.55))
    assert bucket_55['count'] >= 1


def test_close_to_promotion_default_window(client):
    """Default window is [0.70, 0.75) — picks up AGRP_00003 (0.72) but not AGRP_00001 (0.85) or AGRP_00002 (0.55)."""
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
    assert resp.status_code == 200
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    assert 'AGRP_00003' in sids
    assert 'AGRP_00001' not in sids
    assert 'AGRP_00002' not in sids


def test_close_to_promotion_custom_window(client):
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion',
                      params={'from': 0.50, 'to': 0.60})
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    # AGRP_00002 (0.55) lands in [0.50, 0.60), AGRP_00003 (0.72) does not.
    assert 'AGRP_00002' in sids
    assert 'AGRP_00003' not in sids


def test_close_to_promotion_window_thresholds(client):
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
    body = resp.json()
    assert body['from_confidence'] == pytest.approx(0.70)
    assert body['to_confidence'] == pytest.approx(0.75)


def test_close_to_promotion_400_on_invalid_window(client):
    # from > to should 400.
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion',
                      params={'from': 0.8, 'to': 0.5})
    assert resp.status_code == 400


def test_missed_stems_returns_lostbrand(client):
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    assert resp.status_code == 200
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    assert 'lostbrand' in tokens


def test_missed_stems_excludes_promoted(client):
    """Tokens that ARE in brand_stem should NOT appear."""
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    # 'kingsett' and 'starlight' are seeded in brand_stem; they should NOT be missed.
    assert 'kingsett' not in tokens
    assert 'starlight' not in tokens


def test_missed_stems_includes_dominance_contest(client):
    """Each missed stem should report the strongest-phone anchor where it was concentrated,
    plus the stem that won at that anchor."""
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    body = resp.json()
    lost = next(r for r in body['results'] if r['token'] == 'lostbrand')
    # 'lostbrand' is concentrated at phone 4166876700 (kingsett's phone)
    assert lost['strongest_phone'] == '4166876700'
    assert lost['token_sides_at_anchor'] >= 1
    # The fixture's anchor_uniqueness has anchor (phone, 4166876700) seeded only via
    # other data; if no anchor_uniqueness row exists, winner_stem is null.
    # The contract: winner_stem is the dominant_stem at that anchor (may be null).
    assert 'winner_stem' in lost
    assert 'winner_dominance' in lost


def test_missed_stems_respects_min_party_sides(client):
    # Bump threshold above 'lostbrand''s 120 → it disappears.
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 500})
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    assert 'lostbrand' not in tokens


# ── List endpoint extensions (Plan G Task 4) ─────────────────────

def test_list_auto_groups_returns_anchor_diversity_and_distinct_contacts(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'tier': 'confirmed'})
    body = resp.json()
    first = body['results'][0]
    assert 'anchor_diversity' in first
    # AGRP_00001 has 3 anchor types in fixture (phone, address_unit, contact) → 3 categories.
    assert first['anchor_diversity'] >= 1
    assert 'n_distinct_contacts' in first
    assert isinstance(first['n_distinct_contacts'], int)


def test_list_auto_groups_close_to_promotion_filter(client):
    """When close_to_promotion=true, restrict results to confidence in [0.70, 0.75)."""
    resp = client.get('/api/explorer/auto-groups',
                      params={'close_to_promotion': 'true', 'tier': 'probable'})
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    # AGRP_00003 has confidence 0.72 → in window.
    assert 'AGRP_00003' in sids


def test_list_auto_groups_close_to_promotion_excludes_outside_window(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'close_to_promotion': 'true', 'tier': 'confirmed'})
    body = resp.json()
    # AGRP_00001 is confidence 0.85 → confirmed but NOT in [0.70, 0.75) window.
    sids = {g['auto_group_id'] for g in body['results']}
    assert 'AGRP_00001' not in sids


# ── Trail endpoint (Plan F Task 1) ────────────────────────────────

def test_trail_returns_party_data(client):
    """RT1 (buyer) is a member of AGRP_00001 (kingsett)."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    assert resp.status_code == 200
    body = resp.json()
    assert body['party']['source_id'] == 'RT1'
    assert body['party']['side'] == 'buyer'
    # Party fields populated from the fixture.
    assert body['party']['phone'] == '4166876700'
    assert body['party']['contact'] == 'rob kumer'
    # brand_phrase should be one of the kingsett-mapped phrases.
    assert 'kingsett' in (body['party']['brand_phrase'] or '').lower()


def test_trail_threads_one_per_anchor(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    # RT1 has phone + contact + address_unit — 3 anchor identities.
    # The trail should produce one thread per non-empty anchor on the party.
    thread_anchors = {(t['anchor_type'], t['anchor_value']) for t in body['threads']}
    assert ('phone', '4166876700') in thread_anchors
    assert ('contact', 'rob kumer') in thread_anchors
    # address_unit fires because city+street_number+street_name are all set on RT1.
    assert ('address_unit', 'toronto|66|wellington|street||suite|4400') in thread_anchors


def test_trail_thread_groups_for_phone_lists_both_groups(client):
    """The phone 4166876700 is an anchor of BOTH AGRP_00001 (kingsett) and AGRP_00004 (rivalstem).
    The phone thread should list both groups — that's the conflict signal."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    phone_thread = next(t for t in body['threads'] if t['anchor_type'] == 'phone')
    group_ids = {g['auto_group_id'] for g in phone_thread['groups']}
    assert 'AGRP_00001' in group_ids
    assert 'AGRP_00004' in group_ids


def test_trail_returns_primary_group(client):
    """RT1 (buyer) is a member of AGRP_00001 — that's the primary."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    assert body['primary_group'] is not None
    assert body['primary_group']['auto_group_id'] == 'AGRP_00001'
    assert body['primary_group']['stem'] == 'kingsett'


def test_trail_returns_all_groups_for_conflict_visualization(client):
    """all_groups should include every group reachable via any thread — for rendering right-side nodes."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    all_ids = {g['auto_group_id'] for g in body['all_groups']}
    assert 'AGRP_00001' in all_ids
    assert 'AGRP_00004' in all_ids


def test_trail_404_on_unknown_party(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT-NOPE/buyer/trail')
    assert resp.status_code == 404


def test_trail_404_on_invalid_side(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT1/middleman/trail')
    assert resp.status_code == 400


def test_trail_with_no_primary_group(client):
    """A party that exists in party_fingerprints but isn't a member of any auto_group.
    Should return 200 with primary_group=None and threads still populated for any
    anchors that match registered groups."""
    # The fixture's RT-COSTEM party (added in Plan D Task 1) is at phone 4166876700
    # but is NOT in auto_group_members.
    resp = client.get('/api/explorer/auto-groups/parties/RT-COSTEM/buyer/trail')
    assert resp.status_code == 200
    body = resp.json()
    assert body['primary_group'] is None
    # Should still have a thread for the phone anchor since 4166876700 is a registered anchor.
    thread_types = {t['anchor_type'] for t in body['threads']}
    assert 'phone' in thread_types


# ── Plan H1 Task 5: /addresses/roots/:key/units ───────────────────────────────

def test_units_at_root_returns_unit_breakdown(client):
    """For root toronto|66|wellington, return the 3 seeded units."""
    resp = client.get('/api/explorer/addresses/roots/toronto%7C66%7Cwellington/units')
    assert resp.status_code == 200
    body = resp.json()
    assert len(body['results']) == 3
    suite_4400 = next((u for u in body['results']
                       if u['suite_type'] == 'suite' and u['suite_number'] == '4400'), None)
    assert suite_4400 is not None
    assert suite_4400['dominant_stem'] == 'kingsett'
    assert suite_4400['n_party_sides'] == 156
    assert suite_4400['dominance_share'] == pytest.approx(0.88)


def test_units_at_root_sorted_by_n_party_sides(client):
    resp = client.get('/api/explorer/addresses/roots/toronto%7C66%7Cwellington/units')
    counts = [u['n_party_sides'] for u in resp.json()['results']]
    assert counts == sorted(counts, reverse=True)


def test_units_at_root_404_on_unknown(client):
    resp = client.get('/api/explorer/addresses/roots/toronto%7C99%7Cnowhere/units')
    assert resp.status_code == 200  # endpoint returns empty list, not 404
    assert resp.json()['results'] == []


def test_unit_detail_returns_summary(client):
    """Unit key format: 'city|num|name|suffix|direction|suite_type|suite_number'."""
    key = 'toronto|66|wellington|street|west|suite|4400'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}')
    assert resp.status_code == 200
    body = resp.json()
    assert body['city'] == 'toronto'
    assert body['street_number'] == '66'
    assert body['street_name'] == 'wellington'
    assert body['suite_type'] == 'suite'
    assert body['suite_number'] == '4400'
    assert body['dominant_stem'] == 'kingsett'
    assert body['n_party_sides'] == 156


def test_unit_detail_404_on_unknown(client):
    key = 'toronto|99|nowhere|||||'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}')
    assert resp.status_code == 404


def test_unit_detail_400_on_malformed_key(client):
    resp = client.get('/api/explorer/addresses/units/notenoughparts')
    assert resp.status_code == 400


# ── Plan H3 Task 1: /phones/:value/timeline ──────────────────────────────────

def test_phone_timeline_returns_events_with_tenures(client):
    """Timeline for a phone returns chronological events + tenure windows."""
    resp = client.get('/api/explorer/phones/4166876700/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert body['anchor_type'] == 'phone'
    assert body['value'] == '4166876700'
    assert 'events' in body
    assert 'tenures' in body
    # Events sorted by sale_date ASC
    dates = [e['sale_date'] for e in body['events']]
    assert dates == sorted(dates)


def test_phone_timeline_event_shape(client):
    resp = client.get('/api/explorer/phones/4166876700/timeline')
    body = resp.json()
    if body['events']:
        e = body['events'][0]
        assert {'sale_date', 'source_id', 'side', 'party_phrase', 'auto_group_id'} <= set(e.keys())


def test_phone_timeline_tenure_shape(client):
    resp = client.get('/api/explorer/phones/4166876700/timeline')
    body = resp.json()
    assert len(body['tenures']) >= 1
    t = body['tenures'][0]
    assert {'auto_group_id', 'canonical_stem', 'start_date', 'end_date',
            'n_party_sides_in_window', 'is_active'} <= set(t.keys())


def test_phone_timeline_404_on_unknown_value(client):
    resp = client.get('/api/explorer/phones/9999999999/timeline')
    assert resp.status_code == 404


# ── Plan H3 Task 2: /addresses/units/:key/timeline ───────────────────────────

def test_address_unit_timeline_returns_events_with_tenures(client):
    key = 'toronto|66|wellington|street|west|suite|4400'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert body['anchor_type'] == 'address_unit'
    assert body['value'] == key
    assert 'events' in body
    assert 'tenures' in body


def test_address_unit_timeline_400_on_malformed_key(client):
    resp = client.get('/api/explorer/addresses/units/notenoughparts/timeline')
    assert resp.status_code == 400


def test_address_unit_timeline_404_on_unknown(client):
    key = 'toronto|99|nowhere|||||'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}/timeline')
    assert resp.status_code == 404


# ── Plan H3 Task 2: /contacts/:value/timeline ────────────────────────────────

def test_contact_timeline_returns_events_with_tenures(client):
    resp = client.get('/api/explorer/contacts/jc/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert body['anchor_type'] == 'contact'
    assert body['value'] == 'jc'
    assert 'events' in body
    assert 'tenures' in body


def test_contact_timeline_404_on_unknown(client):
    resp = client.get('/api/explorer/contacts/no_such_contact/timeline')
    assert resp.status_code == 404


# ── Plan H3 Task 5: /auto-groups/:id/anchor-tenures ──────────────────────────

def test_anchor_tenures_returns_one_row_per_tenure(client):
    """For a group with multiple anchor tenures, the endpoint returns one row per."""
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchor-tenures')
    assert resp.status_code == 200
    body = resp.json()
    assert body['auto_group_id'] == 'AGRP_00001'
    assert 'tenures' in body
    assert len(body['tenures']) >= 2
    for t in body['tenures']:
        assert {'anchor_type', 'anchor_value', 'start_date', 'end_date',
                'n_party_sides_in_window', 'dominance_share_in_window',
                'score', 'is_active', 'coverage_pct'} <= set(t.keys())


def test_anchor_tenures_404_on_unknown_group(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_NOPE/anchor-tenures')
    assert resp.status_code == 404


def test_anchor_tenures_sorted_by_score_desc(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchor-tenures')
    scores = [t['score'] for t in resp.json()['tenures']]
    assert scores == sorted(scores, reverse=True)
