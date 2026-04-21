"""Tests for labeling operations: create session, record verdict, search."""

import sqlite3
import pytest


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Core schema (minimal subset)
    conn.executescript("""
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, party_name TEXT, phone TEXT, contact_id TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            display TEXT, city TEXT, province TEXT, postal TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT, phone TEXT, job_title TEXT
        );
    """)
    # Labeling schema
    import pathlib
    mig = pathlib.Path(__file__).parent.parent / "cleo" / "database" / "migrations" / "006_labeling_tables.py"
    src = mig.read_text()
    # Extract the executescript block (between the triple-quoted sql string)
    start = src.index('conn.executescript("""') + len('conn.executescript("""')
    end = src.index('""")', start)
    conn.executescript(src[start:end])
    return conn


def _seed_tx(conn, source_id, side, party_name, trade_name, phone=None, mailing=None):
    conn.execute(
        f"INSERT INTO transactions (source_id, {side}_trade_name) VALUES (?, ?) "
        "ON CONFLICT(source_id) DO UPDATE SET " + f"{side}_trade_name = excluded.{side}_trade_name",
        (source_id, trade_name)
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone) VALUES (?, ?, ?, ?)",
        (source_id, side, party_name, phone)
    )
    if mailing:
        conn.execute(
            "INSERT INTO transaction_mailing_addresses (source_id, side, display) VALUES (?, ?, ?)",
            (source_id, side, mailing)
        )


def test_create_session_auto_harvests_anchor_seeds():
    from cleo.labeling.operations import create_session

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Dan Hagler Investments Ltd", "DH Management Inc",
             phone="416-265-5055", mailing="180 Shorting Rd")

    session_id = create_session(
        conn, anchor_source_id="RT1", anchor_side="buyer",
        name="DH Management", audit_slug="05-huntington", created_by="brandon"
    )

    terms = {(r["term"], r["field_type"]) for r in conn.execute(
        "SELECT term, field_type FROM labeling_seeds WHERE session_id = ?", (session_id,)
    )}
    assert ("Dan Hagler Investments Ltd", "party_name") in terms
    assert ("DH Management Inc", "trade_name") in terms
    assert ("416-265-5055", "phone") in terms
    assert ("180 Shorting Rd", "address") in terms


def test_record_confirmed_verdict_auto_harvests_and_dedups():
    from cleo.labeling.operations import create_session, record_verdict

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Party A", "DH Management Inc", phone="416-1")
    _seed_tx(conn, "RT2", "buyer", "Party B", "DH Management Inc", phone="416-2")

    session_id = create_session(
        conn, anchor_source_id="RT1", anchor_side="buyer",
        name="DH", audit_slug=None, created_by="brandon"
    )
    # RT1 anchor already contributed "DH Management Inc" as trade_name.
    # Confirming RT2 contributes it again — must not duplicate.
    verdict_id = record_verdict(
        conn, session_id=session_id,
        source_id="RT2", side="buyer",
        verdict="confirmed",
        left_source_id="RT1", left_side="buyer",
        seed_id=None, rationale="same trade_name",
        links=[{"from_field_type": "trade_name", "from_field_value": "DH Management Inc",
                "to_field_type": "trade_name", "to_field_value": "DH Management Inc",
                "kind": "exact"}],
        created_by="brandon",
    )
    assert verdict_id > 0

    dupes = conn.execute(
        "SELECT COUNT(*) FROM labeling_seeds WHERE session_id = ? "
        "AND term = ? AND field_type = ?",
        (session_id, "DH Management Inc", "trade_name")
    ).fetchone()[0]
    assert dupes == 1, "Seed should have been deduped, not re-inserted"

    # RT2's unique phone and party_name should be new seeds
    rt2_phone = conn.execute(
        "SELECT COUNT(*) FROM labeling_seeds WHERE session_id = ? "
        "AND term = ? AND field_type = 'phone'",
        (session_id, "416-2")
    ).fetchone()[0]
    assert rt2_phone == 1


def test_rejected_verdict_rejects_empty_links():
    from cleo.labeling.operations import create_session, record_verdict, VerdictValidationError

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "A", "X")
    _seed_tx(conn, "RT2", "buyer", "B", "Y")
    session_id = create_session(conn, "RT1", "buyer", "Session", None, "brandon")

    with pytest.raises(VerdictValidationError):
        record_verdict(
            conn, session_id=session_id, source_id="RT2", side="buyer",
            verdict="confirmed",  # confirmed with no links is invalid
            left_source_id="RT1", left_side="buyer",
            seed_id=None, rationale=None, links=[], created_by="brandon",
        )

    with pytest.raises(VerdictValidationError):
        record_verdict(
            conn, session_id=session_id, source_id="RT2", side="buyer",
            verdict="rejected",  # rejected with no rationale is invalid
            left_source_id="RT1", left_side="buyer",
            seed_id=None, rationale=None, links=[], created_by="brandon",
        )


def test_search_candidates_excludes_reviewed_and_matches_across_fields():
    from cleo.labeling.operations import create_session, search_candidates, mark_reviewed

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Anchor Co", "Anchor Trade", phone="111")
    _seed_tx(conn, "RT2", "buyer", "Hit One", "Anchor Trade", phone="222")
    _seed_tx(conn, "RT3", "seller", "Hit Two via address", "Other",
             phone="333", mailing="Anchor Trade Ave")
    _seed_tx(conn, "RT4", "buyer", "Reviewed Already", "Anchor Trade", phone="444")

    session_id = create_session(conn, "RT1", "buyer", "S", None, "brandon")
    mark_reviewed(conn, session_id, "RT4", "buyer")

    hits = search_candidates(conn, session_id, term="Anchor Trade")
    keys = {(h["source_id"], h["side"]) for h in hits}

    # RT1 is anchor — not excluded automatically (users sometimes anchor a confirmed party)
    # RT2: matches via trade_name
    # RT3: matches via address "Anchor Trade Ave"
    # RT4: excluded (reviewed)
    assert ("RT2", "buyer") in keys
    assert ("RT3", "seller") in keys
    assert ("RT4", "buyer") not in keys


def test_delete_verdict_reassigns_seed_when_alternate_contributor_exists():
    """Deleting a verdict should reassign seeds to another confirmed
    verdict whose party harvests the same (term, field_type)."""
    from cleo.labeling.operations import (
        create_session, record_verdict, delete_verdict,
    )

    conn = _make_db()
    # Two parties both have trade_name "KingSett" — so both harvest
    # ("KingSett", "trade_name") as a seed.
    _seed_tx(conn, "RT1", "buyer", "A", "KingSett", phone="111")
    _seed_tx(conn, "RT2", "buyer", "B", "KingSett", phone="222")
    _seed_tx(conn, "RT3", "buyer", "C", "KingSett", phone="333")

    session_id = create_session(conn, "RT1", "buyer", "S", None, "brandon")
    # Anchor RT1 contributed the initial seeds.
    seed = conn.execute(
        "SELECT id, first_contributed_by_source_id AS src FROM labeling_seeds "
        "WHERE session_id = ? AND term = 'KingSett' AND field_type = 'trade_name'",
        (session_id,),
    ).fetchone()
    assert seed["src"] == "RT1"

    # Confirm RT2 — RT1 stays the first contributor (OR IGNORE).
    verdict2 = record_verdict(
        conn, session_id=session_id, source_id="RT2", side="buyer",
        verdict="confirmed", left_source_id="RT1", left_side="buyer",
        seed_id=None, rationale=None,
        links=[{"from_field_type": "trade_name", "from_field_value": "KingSett",
                "to_field_type": "trade_name", "to_field_value": "KingSett",
                "kind": "exact"}],
        created_by="brandon",
    )

    # Now delete the RT1 ... wait, RT1 is the anchor with no verdict. Delete
    # a hypothetical RT3 verdict instead. Confirm RT3 first.
    verdict3 = record_verdict(
        conn, session_id=session_id, source_id="RT3", side="buyer",
        verdict="confirmed", left_source_id="RT1", left_side="buyer",
        seed_id=None, rationale=None,
        links=[{"from_field_type": "trade_name", "from_field_value": "KingSett",
                "to_field_type": "trade_name", "to_field_value": "KingSett",
                "kind": "exact"}],
        created_by="brandon",
    )
    # Manually reassign the seed's contributor to RT3 to simulate the case
    # where RT3 was first to contribute (can't happen in normal flow given
    # anchor always wins, but we test the reconciliation logic directly).
    conn.execute(
        "UPDATE labeling_seeds SET first_contributed_by_source_id = 'RT3' "
        "WHERE id = ?",
        (seed["id"],),
    )
    conn.commit()

    delete_verdict(conn, verdict3)
    # Seed should survive with a different contributor (RT2, also has
    # KingSett trade_name and is the only other confirmed).
    row = conn.execute(
        "SELECT first_contributed_by_source_id AS src FROM labeling_seeds "
        "WHERE id = ?", (seed["id"],),
    ).fetchone()
    assert row is not None, "Seed should not have been deleted — RT2 still contributes"
    assert row["src"] == "RT2"


def test_delete_verdict_removes_orphan_seed_when_no_alternate_exists():
    """Deleting a verdict should delete any seed whose sole contributor
    was the deleted party (the orphan-seed bug that previously let seeds
    linger in the queue pointing at a ghost RT)."""
    from cleo.labeling.operations import (
        create_session, record_verdict, delete_verdict,
    )

    conn = _make_db()
    # Anchor RT1 has unique fields. Confirmed RT2 has its own unique fields
    # (trade_name "Unique2"). If RT2 is deleted, "Unique2" seed should go.
    _seed_tx(conn, "RT1", "buyer", "A", "Anchor Trade")
    _seed_tx(conn, "RT2", "buyer", "B", "Unique2")

    session_id = create_session(conn, "RT1", "buyer", "S", None, "brandon")
    verdict_id = record_verdict(
        conn, session_id=session_id, source_id="RT2", side="buyer",
        verdict="confirmed", left_source_id="RT1", left_side="buyer",
        seed_id=None, rationale=None,
        links=[{"from_field_type": "party_name", "from_field_value": "A",
                "to_field_type": "party_name", "to_field_value": "B",
                "kind": "implied"}],
        created_by="brandon",
    )

    # "Unique2" seed should exist and be contributed by RT2.
    before = conn.execute(
        "SELECT id FROM labeling_seeds WHERE session_id = ? "
        "AND term = 'Unique2' AND field_type = 'trade_name'",
        (session_id,),
    ).fetchone()
    assert before is not None

    delete_verdict(conn, verdict_id)

    after = conn.execute(
        "SELECT id FROM labeling_seeds WHERE session_id = ? "
        "AND term = 'Unique2' AND field_type = 'trade_name'",
        (session_id,),
    ).fetchone()
    assert after is None, "Orphan seed should have been deleted"
