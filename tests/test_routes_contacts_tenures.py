"""Tests for the new tenure-related fields on /api/contacts/:id."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    """In-memory DB seeded with one contact, two tenures, three transactions."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Schema — only the tables the contact_detail endpoint reads.
    conn.executescript("""
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            name_fingerprint TEXT NOT NULL,
            first_name TEXT, last_name TEXT, display_name TEXT NOT NULL,
            phone TEXT, email TEXT, mobile TEXT, job_title TEXT,
            company_name TEXT, current_group_id TEXT, contact_type TEXT,
            status TEXT NOT NULL DEFAULT 'lead',
            source TEXT, transaction_count INTEGER DEFAULT 0,
            first_seen_date TEXT, last_seen_date TEXT,
            hubspot_id TEXT, last_engaged_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE contact_field_overrides (
            contact_id TEXT PRIMARY KEY,
            email TEXT, phone TEXT, mobile TEXT, job_title TEXT,
            contact_type TEXT, linkedin_url TEXT, linkedin_headline TEXT,
            linkedin_photo_url TEXT, linkedin_enriched_at TEXT,
            datanyze_raw TEXT
        );
        CREATE TABLE contact_work_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            company TEXT, title TEXT, start_date TEXT, end_date TEXT,
            is_current INTEGER, location TEXT, company_logo_url TEXT
        );
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT, sale_price REAL,
            display_address TEXT, city TEXT, region TEXT, property_id TEXT
        );
        CREATE TABLE transaction_parties (
            source_id TEXT, side TEXT, contact_id TEXT, group_id TEXT,
            party_name TEXT, contact_title TEXT, phone TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT, display TEXT, geocode_string TEXT
        );
        CREATE TABLE pois (
            property_id TEXT, brand TEXT, category TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT, status TEXT, hq_address TEXT
        );
        CREATE TABLE party_fingerprints (
            source_id TEXT NOT NULL, side TEXT NOT NULL,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, phone TEXT,
            contact_fingerprint TEXT, sale_date TEXT,
            party_address_canonical TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE contact_brand_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            brand_stem TEXT NOT NULL,
            strict_start_date TEXT, strict_end_date TEXT,
            inferred_start_date TEXT, inferred_end_date TEXT,
            n_party_sides_strict INTEGER, n_party_sides_inferred INTEGER,
            top_phrases_json TEXT, source_field_breakdown_json TEXT,
            dominant_address_unit TEXT, auto_group_id TEXT,
            is_active INTEGER, discovered_at TEXT
        );
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT, confidence REAL,
            n_anchors INTEGER, n_members INTEGER
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
    """)
    # Seed one contact.
    conn.execute(
        "INSERT INTO contacts (id, name_fingerprint, display_name, status, "
        "transaction_count, phone) VALUES "
        "('CON_07049', 'PAUL BRAUN', 'Paul Braun', 'lead', 80, '4169249009')"
    )
    # Two tenures.
    conn.execute(
        "INSERT INTO contact_brand_tenures (contact_fingerprint, brand_stem, "
        "strict_start_date, strict_end_date, inferred_start_date, "
        "inferred_end_date, n_party_sides_strict, n_party_sides_inferred, "
        "top_phrases_json, source_field_breakdown_json, "
        "dominant_address_unit, auto_group_id, is_active) VALUES "
        "('paul braun', 'canfirst', '2004-07-02', '2022-12-13', "
        " '2002-04-29', '2022-12-13', 60, 80, "
        " '[{\"phrase\":\"canfirst capital management\",\"n\":60}]', "
        " '{\"trade_name\":41,\"companies_json\":15,\"care_of\":4}', "
        " 'toronto|30|st clair|ave|w|suite|', 'AGRP_01392', 1),"
        "('paul braun', 'dundee', '1999-01-27', '2001-06-12', "
        " '1999-01-27', '2001-06-12', 8, 8, "
        " '[{\"phrase\":\"dundee realty\",\"n\":8}]', "
        " '{\"care_of\":5,\"companies_json\":3}', "
        " 'toronto|390|bay|st|||', NULL, 0)"
    )
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) VALUES "
        "('AGRP_01392', 'canfirst', 'CanFirst Capital Management', "
        " 'confirmed', 0.85, 5, 58)"
    )
    # 3 transactions, with their party-side rows so transactions[].tenure is computable.
    conn.execute(
        "INSERT INTO transactions (source_id, sale_date, sale_price, "
        "display_address, city, region, property_id) VALUES "
        "('RT_C1', '2010-06-01', 5000000, '50 King St', 'toronto', '01', 'P1'),"
        "('RT_D1', '2000-03-15', 1000000, '100 Bay St', 'toronto', '01', 'P2'),"
        "('RT_INF', '2003-08-20', 2000000, '200 Yonge St', 'toronto', '01', 'P3')"
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, contact_id, "
        "party_name) VALUES "
        "('RT_C1', 'buyer', 'CON_07049', 'CF Vaughan Portfolio Inc'),"
        "('RT_D1', 'buyer', 'CON_07049', 'Some SPV'),"
        "('RT_INF', 'buyer', 'CON_07049', 'Another SPV')"
    )
    # party_fingerprints for the three sides — they all use 30 St Clair (canfirst dominant)
    # except RT_D1 which uses 390 Bay (dundee dominant).
    # Canonical addresses: toronto|30|st clair|ave|w|suite| and toronto|390|bay|st|||
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, contact_fingerprint, "
        "sale_date, city, street_number, street_name, street_suffix, "
        "street_direction, suite_type, suite_number, phone, party_address_canonical) VALUES "
        "('RT_C1','buyer','paul braun','2010-06-01','toronto','30','st clair','ave','w','','','4169249009','toronto|30|st clair|ave|w|suite|'),"
        "('RT_D1','buyer','paul braun','2000-03-15','toronto','390','bay','st','','','','','toronto|390|bay|st|||'),"
        "('RT_INF','buyer','paul braun','2003-08-20','toronto','30','st clair','ave','w','','','','toronto|30|st clair|ave|w|suite|'),"
        "('RT_RECENT','buyer','paul braun','2025-12-01','toronto','30','st clair','ave','w','','','4169249009','toronto|30|st clair|ave|w|suite|')"
    )
    # Recent transaction — puts the contact's phone within the 730-day cliff so
    # the active-phone test holds under strict spec §2g semantics.
    conn.execute(
        "INSERT INTO transactions (source_id, sale_date, sale_price, "
        "display_address, city, region, property_id) VALUES "
        "('RT_RECENT', '2025-12-01', 8000000, '30 St Clair Ave W', 'toronto', '01', 'P4')"
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, contact_id, party_name) VALUES "
        "('RT_RECENT', 'buyer', 'CON_07049', 'CanFirst Capital Management')"
    )
    # brand_stem_phrase_map: map qualifying phrases to stems.
    conn.execute(
        "INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES "
        "('canfirst capital management', 'canfirst', 0.95),"
        "('dundee realty', 'dundee', 0.95)"
    )
    # party_atoms: explicit qualifying-source-field atoms for RT_C1 (trade_name) and
    # RT_D1 (care_of). RT_INF gets a party_name atom (NOT a qualifying source field)
    # so it remains address-inferred.
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) VALUES "
        "('RT_C1', 'buyer', 'brand_phrase', 'canfirst capital management', 'trade_name'),"
        "('RT_D1', 'buyer', 'brand_phrase', 'dundee realty', 'care_of'),"
        "('RT_INF', 'buyer', 'brand_phrase', 'another spv', 'party_name')"
    )
    conn.commit()
    return conn


@pytest.fixture
def client():
    from cleo.web.app import app
    from cleo.web import deps
    conn = _seeded_db()

    def _get_conn_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_conn_override
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_contact_detail_returns_career_history(client):
    """career_history field lists tenures sorted by inferred_end_date DESC."""
    resp = client.get("/api/contacts/CON_07049")
    assert resp.status_code == 200
    body = resp.json()
    assert "career_history" in body
    assert len(body["career_history"]) == 2
    # canfirst (ends 2022) ranks before dundee (ends 2001)
    assert body["career_history"][0]["brand_stem"] == "canfirst"
    assert body["career_history"][1]["brand_stem"] == "dundee"
    cf = body["career_history"][0]
    assert cf["is_active"] == 1
    assert cf["display_name"] == "canfirst capital management"  # top phrase
    assert cf["n_transactions_credited"] >= 1
    assert cf["auto_group_id"] == "AGRP_01392"


def test_contact_detail_current_employer_realtrack_derived(client):
    """current_employer is the active tenure with most n_party_sides_inferred."""
    resp = client.get("/api/contacts/CON_07049")
    body = resp.json()
    ce = body["current_employer"]
    assert ce is not None
    assert ce["source"] == "realtrack"  # no LinkedIn rows seeded
    assert ce["brand_stem"] == "canfirst"
    assert ce["display_name"] == "canfirst capital management"


def test_contact_detail_transactions_carry_tenure_attribution(client):
    """Each transaction row gets a `tenure` field with stem + inferred flag."""
    resp = client.get("/api/contacts/CON_07049")
    txns = resp.json()["transactions"]
    by_id = {t["source_id"]: t for t in txns}
    # RT_C1: explicit canfirst atom on trade_name → inferred=False.
    assert by_id["RT_C1"]["tenure"]["brand_stem"] == "canfirst"
    assert by_id["RT_C1"]["tenure"]["inferred"] is False
    # RT_D1: explicit dundee atom on care_of → inferred=False.
    assert by_id["RT_D1"]["tenure"]["brand_stem"] == "dundee"
    assert by_id["RT_D1"]["tenure"]["inferred"] is False
    # RT_INF: SPV atom on party_name (not a qualifying source field), but the
    # side's address (30 St Clair) matches canfirst's dominant_address_unit →
    # attributed to canfirst via address bracket → inferred=True.
    assert by_id["RT_INF"]["tenure"]["brand_stem"] == "canfirst"
    assert by_id["RT_INF"]["tenure"]["inferred"] is True


def test_contact_detail_phone_tenure_tag_active(client):
    """Phone matching an active tenure's window gets an `active` tag with the stem."""
    resp = client.get("/api/contacts/CON_07049")
    body = resp.json()
    assert body["phone_tenure_tag"] is not None
    assert body["phone_tenure_tag"]["state"] == "active"
    assert body["phone_tenure_tag"]["stem"] == "canfirst"


def test_tenure_detail_returns_full_payload(client):
    """GET /api/contacts/:id/tenures/:stem returns top phrases, breakdown, dates, transactions."""
    resp = client.get("/api/contacts/CON_07049/tenures/canfirst")
    assert resp.status_code == 200
    body = resp.json()
    assert body["brand_stem"] == "canfirst"
    assert body["display_name"] == "canfirst capital management"
    assert body["strict_start_date"] == "2004-07-02"
    assert body["inferred_start_date"] == "2002-04-29"
    assert body["auto_group_id"] == "AGRP_01392"
    assert body["auto_group_display_name"] == "CanFirst Capital Management"
    assert body["top_phrases"][0] == {"phrase": "canfirst capital management", "n": 60}
    assert body["source_field_breakdown"] == {
        "trade_name": 41, "companies_json": 15, "care_of": 4
    }
    assert "credited_transactions" in body
    assert isinstance(body["credited_transactions"], list)
    sample = body["credited_transactions"][0]
    assert {"source_id", "sale_date", "display_address", "sale_price", "inferred"} <= set(sample.keys())


def test_tenure_detail_404_on_unknown_contact(client):
    resp = client.get("/api/contacts/CON_99999/tenures/canfirst")
    assert resp.status_code == 404


def test_tenure_detail_404_on_unknown_stem(client):
    resp = client.get("/api/contacts/CON_07049/tenures/unknownstem")
    assert resp.status_code == 404


def test_uppercase_name_fingerprint_still_finds_lowercase_tenures(client):
    """Regression: contacts.name_fingerprint is UPPERCASE in production but
    contact_brand_tenures.contact_fingerprint is lowercase. The endpoint must
    normalize before joining."""
    resp = client.get("/api/contacts/CON_07049")
    body = resp.json()
    # The fixture has UPPERCASE 'PAUL BRAUN' in contacts but lowercase
    # 'paul braun' in contact_brand_tenures + party_fingerprints. The endpoint
    # must find both tenures despite the case mismatch.
    assert len(body["career_history"]) == 2
    stems = {t["brand_stem"] for t in body["career_history"]}
    assert stems == {"canfirst", "dundee"}
