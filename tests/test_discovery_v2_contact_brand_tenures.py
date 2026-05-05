"""Tests for the contact_brand_tenures builder."""
import json
import sqlite3
import pytest


def _make_db():
    """In-memory DB seeded with the schema this builder reads/writes."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL,
            street_number       TEXT,
            street_name         TEXT,
            street_suffix       TEXT,
            street_direction    TEXT,
            suite_type          TEXT,
            suite_number        TEXT,
            city                TEXT,
            phone               TEXT,
            contact_fingerprint TEXT,
            sale_date           TEXT,
            party_address_canonical TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL, side TEXT NOT NULL,
            atom_type TEXT NOT NULL, atom_value TEXT NOT NULL,
            source_field TEXT NOT NULL
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY,
            stem TEXT NOT NULL,
            confidence REAL NOT NULL
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
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE TABLE auto_groups (
            auto_group_id  TEXT PRIMARY KEY,
            canonical_stem TEXT NOT NULL,
            display_name   TEXT NOT NULL,
            tier           TEXT NOT NULL,
            confidence     REAL NOT NULL,
            n_anchors      INTEGER NOT NULL,
            n_members      INTEGER NOT NULL
        );
        CREATE TABLE contact_brand_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            brand_stem TEXT NOT NULL,
            strict_start_date TEXT NOT NULL,
            strict_end_date TEXT NOT NULL,
            inferred_start_date TEXT NOT NULL,
            inferred_end_date TEXT NOT NULL,
            n_party_sides_strict INTEGER NOT NULL,
            n_party_sides_inferred INTEGER NOT NULL,
            top_phrases_json TEXT NOT NULL,
            source_field_breakdown_json TEXT NOT NULL,
            dominant_address_unit TEXT,
            auto_group_id TEXT,
            is_active INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES
            ('canfirst capital management', 'canfirst', 0.95),
            ('canfirst capital', 'canfirst', 0.90),
            ('dundee realty', 'dundee', 0.95);
    """)
    return conn


def _add_party(conn, source_id, side, contact_fp, sale_date,
               city="toronto", street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w",
               suite_type="", suite_number=""):
    addr_canonical = "|".join([
        (city or "").lower(),
        street_number or "",
        (street_name or "").lower(),
        (street_suffix or "").lower(),
        (street_direction or "").lower(),
        (suite_type or "").lower(),
        suite_number or "",
    ])
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, contact_fingerprint, sale_date, "
        " city, street_number, street_name, street_suffix, street_direction, "
        " suite_type, suite_number, party_address_canonical) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (source_id, side, contact_fp, sale_date, city,
         street_number, street_name, street_suffix, street_direction,
         suite_type, suite_number, addr_canonical),
    )


def _add_brand_phrase(conn, source_id, side, phrase, source_field):
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, ?)",
        (source_id, side, phrase, source_field),
    )


def test_strict_window_basic_aggregation():
    """Two qualifying party-sides for canfirst → one tenure row, MIN/MAX dates."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    rows = conn.execute(
        "SELECT contact_fingerprint, brand_stem, strict_start_date, "
        "strict_end_date, n_party_sides_strict "
        "FROM contact_brand_tenures"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["contact_fingerprint"] == "paul braun"
    assert rows[0]["brand_stem"] == "canfirst"
    assert rows[0]["strict_start_date"] == "2004-07-02"
    assert rows[0]["strict_end_date"] == "2022-12-13"
    assert rows[0]["n_party_sides_strict"] == 2


def test_threshold_filters_one_shot_mentions():
    """A single qualifying party-side for a stem is dropped (threshold ≥ 2)."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    # Only ONE side carries dundee — should be filtered.
    _add_party(conn, "RT99", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT99", "buyer", "dundee realty", "care_of")
    # Add a second canfirst row so canfirst survives.
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    stems = {r["brand_stem"] for r in conn.execute(
        "SELECT brand_stem FROM contact_brand_tenures"
    )}
    assert "canfirst" in stems
    assert "dundee" not in stems  # filtered by threshold


def test_party_name_source_field_excluded():
    """party_name source_field is excluded — SPV names should not produce tenures."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # 5 party-sides where the brand_phrase is on party_name (SPV-style)
    for i in range(5):
        _add_party(conn, f"RT{i}", "buyer", "paul braun", f"200{i}-01-01")
        _add_brand_phrase(conn, f"RT{i}", "buyer",
                          "canfirst capital management", "party_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    n = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    assert n == 0, "party_name source_field must not yield tenure rows"


def test_top_phrases_and_source_field_breakdown_json():
    """top_phrases_json and source_field_breakdown_json reflect the input mix."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # Three trade_name + one care_of + one companies_json — five total.
    for i in range(3):
        _add_party(conn, f"RT_T{i}", "buyer", "paul braun", f"20{10+i}-01-01")
        _add_brand_phrase(conn, f"RT_T{i}", "buyer",
                          "canfirst capital management", "trade_name")
    _add_party(conn, "RT_C", "buyer", "paul braun", "2015-01-01")
    _add_brand_phrase(conn, "RT_C", "buyer", "canfirst capital", "care_of")
    _add_party(conn, "RT_J", "buyer", "paul braun", "2016-01-01")
    _add_brand_phrase(conn, "RT_J", "buyer",
                      "canfirst capital management", "companies_json")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT top_phrases_json, source_field_breakdown_json "
        "FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    phrases = json.loads(row["top_phrases_json"])
    breakdown = json.loads(row["source_field_breakdown_json"])
    # Top phrase is canfirst capital management, n=4
    assert phrases[0] == {"phrase": "canfirst capital management", "n": 4}
    assert {"phrase": "canfirst capital", "n": 1} in phrases
    assert breakdown == {"trade_name": 3, "care_of": 1, "companies_json": 1}


def test_idempotent_rebuild():
    """Running the builder twice yields the same row count."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")
    n1 = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    build_contact_brand_tenures(conn, today="2026-05-04")
    n2 = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    assert n1 == n2 == 1


def test_dominant_address_unit_picked():
    """When two addresses appear in the strict window, the more-frequent one wins."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # 3 sides at 30 St Clair, 1 side at 100 Bloor — 30 St Clair wins.
    for i in range(3):
        _add_party(conn, f"RT_S{i}", "buyer", "paul braun", f"20{10+i}-01-01",
                   street_number="30", street_name="st clair",
                   street_suffix="ave", street_direction="w")
        _add_brand_phrase(conn, f"RT_S{i}", "buyer",
                          "canfirst capital management", "trade_name")
    _add_party(conn, "RT_B", "buyer", "paul braun", "2014-01-01",
               street_number="100", street_name="bloor",
               street_suffix="st", street_direction="w")
    _add_brand_phrase(conn, "RT_B", "buyer",
                      "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT dominant_address_unit FROM contact_brand_tenures "
        "WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["dominant_address_unit"] == "toronto|30|st clair|ave|w||"


def test_inferred_window_extends_via_dominant_address():
    """The inferred window extends backward+forward via address bracketing."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # Two strict canfirst sides at 30 St Clair, 2010 + 2020.
    _add_party(conn, "RT_S1", "buyer", "paul braun", "2010-01-01",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_S1", "buyer",
                      "canfirst capital management", "trade_name")
    _add_party(conn, "RT_S2", "buyer", "paul braun", "2020-01-01",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_S2", "buyer",
                      "canfirst capital management", "trade_name")
    # An SPV-only side at 30 St Clair in 2002 (before strict start) and 2022 (after).
    # No qualifying brand_phrase, but party_name SPV does exist.
    _add_party(conn, "RT_SPV1", "buyer", "paul braun", "2002-04-29",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_SPV1", "buyer", "cf vaughan portfolio inc", "party_name")
    _add_party(conn, "RT_SPV2", "buyer", "paul braun", "2022-12-13",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_SPV2", "buyer", "cf vaughan portfolio inc", "party_name")
    # Add an irrelevant brand_phrase mapping for cf vaughan portfolio inc so it
    # doesn't fail the join — actually, we want it to NOT appear in tenures.
    # Don't add it to brand_stem_phrase_map; it's just an SPV name on party_name.
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT strict_start_date, strict_end_date, "
        "inferred_start_date, inferred_end_date, "
        "n_party_sides_strict, n_party_sides_inferred "
        "FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["strict_start_date"] == "2010-01-01"
    assert row["strict_end_date"] == "2020-01-01"
    assert row["inferred_start_date"] == "2002-04-29"
    assert row["inferred_end_date"] == "2022-12-13"
    assert row["n_party_sides_strict"] == 2
    assert row["n_party_sides_inferred"] == 4


def test_inferred_window_does_not_extend_when_no_other_sides():
    """If no SPV-only sides exist at the dominant address outside the strict
    window, inferred = strict (the Paul × Dundee case)."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay",
               street_suffix="st", street_direction="")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay",
               street_suffix="st", street_direction="")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT strict_start_date, strict_end_date, "
        "inferred_start_date, inferred_end_date "
        "FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["strict_start_date"] == row["inferred_start_date"] == "1999-01-27"
    assert row["strict_end_date"] == row["inferred_end_date"] == "2001-06-12"


def test_auto_group_id_link_when_canonical_stem_matches():
    """When an auto_group exists with matching canonical_stem, link it."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) "
        "VALUES ('AGRP_01392', 'canfirst', 'CanFirst Capital Management', "
        "'confirmed', 0.85, 5, 58)"
    )
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2020-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["auto_group_id"] == "AGRP_01392"


def test_auto_group_id_null_when_no_matching_stem():
    """When no auto_group has canonical_stem='dundee', auto_group_id is NULL."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["auto_group_id"] is None


def test_auto_group_id_picks_highest_membership_on_tie():
    """When multiple auto_groups share canonical_stem, pick the one with most members."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) VALUES "
        "('AGRP_00001', 'canfirst', 'A', 'confirmed', 0.8, 1, 5),"
        "('AGRP_00002', 'canfirst', 'B', 'confirmed', 0.8, 1, 50)"
    )
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2020-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["auto_group_id"] == "AGRP_00002"  # higher n_members wins


def test_is_active_when_inferred_end_within_730_days():
    """Tenure ending within 730 days of today → is_active=1."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    # End within 730 days of today=2026-05-04 → 2024-05-05+ qualifies.
    _add_party(conn, "RT2", "buyer", "paul braun", "2025-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT is_active, inferred_end_date FROM contact_brand_tenures "
        "WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["is_active"] == 1


def test_is_active_zero_when_too_old():
    """Tenure ending more than 730 days ago → is_active=0."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT is_active FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["is_active"] == 0


def test_is_active_uses_today_default_when_arg_omitted():
    """When today=None, builder uses datetime('now')."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # End yesterday → must be active under today=None.
    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    _add_party(conn, "RT1", "buyer", "alice smith", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "alice smith", yesterday)
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today=None)

    row = conn.execute(
        "SELECT is_active FROM contact_brand_tenures WHERE contact_fingerprint='alice smith'"
    ).fetchone()
    assert row["is_active"] == 1
