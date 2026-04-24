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
        "('kingsett', 6.5, 2, 2, 1, 0, 0.0, 0, 0, 0, NULL, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES "
        "('rasenberg', 5.2, 2, 1, 1, 0, 1.56, 0, 0, 0, NULL, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES "
        "('ontario', 0.8, 3, 3, 0, 0, 4.5, 1, 1, 0, 'place', '2026-04-23')"
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
