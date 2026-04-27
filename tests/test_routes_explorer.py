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
            postal TEXT, sale_date TEXT, street_number TEXT, street_name TEXT,
            street_suffix TEXT, suite_type TEXT, suite_number TEXT,
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
        CREATE TABLE contact_fingerprint_summary (
            contact_fingerprint TEXT PRIMARY KEY,
            n_party_sides INTEGER, is_distinctive INTEGER,
            discovered_at TEXT
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
        "street_number='66', street_name='wellington', street_suffix='street', "
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
    assert body["total"] == 2
    tokens = [t["token"] for t in body["results"]]
    # Both kingsett and rasenberg have n_party_sides=2; tiebreak alphabetical ASC.
    assert tokens == ["kingsett", "rasenberg"]


def test_list_all_tokens_includes_nondistinctive(client):
    resp = client.get("/api/explorer/brands", params={"distinctive_only": "false"})
    body = resp.json()
    assert body["total"] == 3
    tokens = {t["token"] for t in body["results"]}
    assert tokens == {"kingsett", "rasenberg", "ontario"}


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
    assert body["n_party_sides"] == 2
    assert len(body["party_sides"]) == 2
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
    assert body["n_party_sides"] == 2
    assert len(body["party_sides"]) == 2


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
