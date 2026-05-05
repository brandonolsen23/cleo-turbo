"""Tests that the fingerprint pass populates the canonical address columns."""
import sqlite3

import pytest

from cleo.atoms.fingerprint import run_fingerprint_pass


def _seed_minimal_db() -> sqlite3.Connection:
    """Tiny DB with two transactions, two parties each, sharing an ARN.

    Both transactions resolve to the same property_id (PRO_00001) but the
    party-side mailing addresses use noisy variants:
      - source RT001 buyer side: scarborough / suite / 0212
      - source RT002 buyer side: toronto / unit / 212
    Both should canonicalize to the same party_address_canonical.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            property_id TEXT,
            arn TEXT,
            sale_date TEXT,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
        CREATE TABLE transaction_parties (
            source_id TEXT, side TEXT, party_name TEXT,
            phone TEXT, contact_id TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT, country TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, first_name TEXT, last_name TEXT
        );
        INSERT INTO transactions VALUES
            ('RT001', 'PRO_00001', '12345', '2024-01-01',
             '', '', '[]', '[]', '', '', '[]', '[]'),
            ('RT002', 'PRO_00001', '12345', '2024-06-01',
             '', '', '[]', '[]', '', '', '[]', '[]');
        INSERT INTO transaction_parties VALUES
            ('RT001', 'buyer', 'Acme Corp', '4165550001', NULL),
            ('RT002', 'buyer', 'Acme Corp', '4165550001', NULL);
        INSERT INTO transaction_mailing_addresses VALUES
            ('RT001', 'buyer', '2555', 'eglinton', 'avenue', 'east',
             'suite', '0212', 'scarborough', 'on', 'M1K0A0', 'ca'),
            ('RT002', 'buyer', '2555', 'eglinton', 'avenue', 'east',
             'unit', '212', 'toronto', 'on', 'M1K0A0', 'ca');
        """
    )
    conn.commit()
    return conn


def test_fingerprint_pass_writes_canonical_columns():
    conn = _seed_minimal_db()
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT source_id, party_address_canonical, property_canonical_id "
        "FROM party_fingerprints ORDER BY source_id"
    ).fetchall()
    assert len(rows) == 2
    # Both noisy inputs collapse to the same canonical key.
    assert rows[0]["party_address_canonical"] == rows[1]["party_address_canonical"]
    assert rows[0]["party_address_canonical"] == \
        "toronto|2555|eglinton|avenue|east|suite|212"
    # Both rows share property_canonical_id from transactions.property_id.
    assert rows[0]["property_canonical_id"] == "PRO_00001"
    assert rows[1]["property_canonical_id"] == "PRO_00001"


def test_fingerprint_pass_handles_unresolved_property_id():
    conn = _seed_minimal_db()
    conn.execute("UPDATE transactions SET property_id = NULL WHERE source_id='RT001'")
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT source_id, property_canonical_id FROM party_fingerprints ORDER BY source_id"
    ).fetchall()
    assert rows[0]["property_canonical_id"] is None
    assert rows[1]["property_canonical_id"] == "PRO_00001"


def test_fingerprint_pass_canonical_column_never_null():
    """Even an all-empty mailing address yields a non-NULL canonical key."""
    conn = _seed_minimal_db()
    conn.execute(
        """UPDATE transaction_mailing_addresses
           SET street_number='', street_name='', street_suffix='',
               street_direction='', suite_type='', suite_number='', city=''"""
    )
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT party_address_canonical FROM party_fingerprints"
    ).fetchall()
    for r in rows:
        assert r["party_address_canonical"] is not None
        # All-empty input → "|||||suite|" (empty suite_type maps to suite).
        assert r["party_address_canonical"] == "|||||suite|"
