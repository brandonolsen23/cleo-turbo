"""Tests for the party view aggregator."""

import json
import sqlite3
import pytest
from cleo.labeling.party_view import get_party_view


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
            source_id TEXT, side TEXT,
            party_name TEXT, phone TEXT, contact_id TEXT
        );
        -- Mirrors the production schema (no 'street' column — it's decomposed
        -- into street_number/street_name/etc., none of which party_view uses).
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            display TEXT, city TEXT, province TEXT, postal TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            display_name TEXT, phone TEXT, job_title TEXT
        );
    """)
    return conn


def test_party_view_aggregates_all_fields():
    conn = _make_db()
    conn.execute(
        "INSERT INTO transactions (source_id, sale_date, buyer_trade_name, buyer_care_of, "
        "buyer_law_firms_json, buyer_companies_json) VALUES (?, ?, ?, ?, ?, ?)",
        ("RT148276", "2005-04-18", "DH Management Inc", "",
         json.dumps(["Smith LLP"]), json.dumps(["DH Properties"]))
    )
    conn.execute(
        "INSERT INTO contacts (id, display_name, phone, job_title) VALUES (?, ?, ?, ?)",
        ("CON_00001", "Dan Hagler", "416-265-5055", "Pres")
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone, contact_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "buyer", "Niagara Falls Shopping Centre Inc", "416-265-5055", None)
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone, contact_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "buyer", None, None, "CON_00001")
    )
    conn.execute(
        "INSERT INTO transaction_mailing_addresses "
        "(source_id, side, display, city, province, postal) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("RT148276", "buyer", "180 Shorting Rd, Toronto M1S 3S7",
         "Toronto", "Ontario", "M1S 3S7")
    )

    view = get_party_view(conn, "RT148276", "buyer")

    assert view["source_id"] == "RT148276"
    assert view["side"] == "buyer"
    assert view["trade_name"] == "DH Management Inc"
    assert view["law_firms"] == ["Smith LLP"]
    assert view["companies_other"] == ["DH Properties"]
    assert view["mailing"]["display"] == "180 Shorting Rd, Toronto M1S 3S7"
    assert "Niagara Falls Shopping Centre Inc" in [r["party_name"] for r in view["party_rows"]]
    assert view["contacts"][0]["name"] == "Dan Hagler"
    assert "416-265-5055" in view["phones"]
    assert view["sale_date"] == "2005-04-18"


def test_party_view_returns_none_for_missing():
    conn = _make_db()
    assert get_party_view(conn, "RT999999", "buyer") is None
