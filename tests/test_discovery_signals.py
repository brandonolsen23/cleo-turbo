"""
Tests for cleo.discovery.signals — Signal Extraction (Step 0).

Uses an in-memory SQLite database populated with data mimicking the DH portfolio
(Dan Hagler / DH Management Inc / Niagara Falls Shopping Centre).

Run:
    cd /Users/brandonolsen23/cleo-turbo
    python -m pytest tests/test_discovery_signals.py -v
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from cleo.discovery.signals import extract_signals, _load_exclusions, _unify_fuzzy_contacts
from cleo.discovery.types import Signal


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_db():
    """Create an in-memory SQLite DB with minimal schema for signal extraction."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE groups (
            id TEXT PRIMARY KEY,
            display_name TEXT,
            normalized_name TEXT,
            status TEXT DEFAULT 'pool',
            property_count INTEGER DEFAULT 0,
            transaction_count INTEGER DEFAULT 0,
            contact_count INTEGER DEFAULT 0
        );

        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            property_id TEXT,
            arn TEXT,
            sale_date TEXT,
            sale_price INTEGER,
            display_address TEXT,
            city TEXT,
            region TEXT,
            postal TEXT,
            seller_trade_name TEXT,
            buyer_trade_name TEXT,
            seller_care_of TEXT,
            buyer_care_of TEXT,
            seller_law_firms_json TEXT,
            buyer_law_firms_json TEXT,
            seller_companies_json TEXT,
            buyer_companies_json TEXT
        );

        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            name_fingerprint TEXT UNIQUE,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT,
            phone TEXT,
            email TEXT,
            mobile TEXT,
            job_title TEXT,
            company_name TEXT,
            current_group_id TEXT,
            contact_type TEXT,
            status TEXT DEFAULT 'pool',
            source TEXT DEFAULT 'transaction',
            transaction_count INTEGER DEFAULT 0,
            first_seen_date TEXT,
            last_seen_date TEXT
        );

        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL REFERENCES transactions(source_id),
            contact_id TEXT REFERENCES contacts(id),
            group_id TEXT REFERENCES groups(id),
            side TEXT NOT NULL,
            party_name TEXT,
            contact_title TEXT,
            phone TEXT
        );

        CREATE TABLE transaction_mailing_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL REFERENCES transactions(source_id),
            side TEXT NOT NULL,
            display TEXT,
            street_number TEXT,
            street_name TEXT,
            street_suffix TEXT,
            street_direction TEXT,
            suite_type TEXT,
            suite_number TEXT,
            city TEXT,
            province TEXT,
            postal TEXT,
            country TEXT,
            geocode_string TEXT,
            UNIQUE(source_id, side)
        );

        CREATE TABLE group_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL REFERENCES groups(id),
            name TEXT NOT NULL,
            source TEXT
        );

        CREATE TABLE discovery_exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exclusion_type TEXT NOT NULL,
            exclusion_value TEXT NOT NULL,
            reason TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # ── Groups ───────────────────────────────────────────────────
    conn.executemany(
        "INSERT INTO groups (id, display_name, normalized_name) VALUES (?, ?, ?)",
        [
            ("GRP_00001", "DH Management Inc", "DH MANAGEMENT"),
            ("GRP_00002", "Dan Hagler Investments Ltd", "DAN HAGLER INVESTMENTS"),
            ("GRP_00003", "Niagara Falls Shopping Centre Inc", "NIAGARA FALLS SHOPPING CENTRE"),
        ]
    )

    # ── Contacts ─────────────────────────────────────────────────
    conn.execute("""
        INSERT INTO contacts (id, name_fingerprint, first_name, last_name, display_name,
            phone, current_group_id)
        VALUES ('CON_00001', 'DAN HAGLER', 'Dan', 'Hagler', 'Dan Hagler',
            '4162655055', 'GRP_00001')
    """)

    # ── Transactions ─────────────────────────────────────────────
    # TX1: DH Management sells to Dan Hagler Investments — shared address, shared contact
    conn.execute("""
        INSERT INTO transactions (source_id, sale_date, sale_price, display_address,
            seller_care_of, buyer_trade_name)
        VALUES ('RT_TX_001', '2023-05-15', 1500000, '555 King St, Toronto',
            'DH Property Holdings LP', 'DH Realty Trust')
    """)

    # TX2: Dan Hagler Investments and Niagara Falls SC both on buyer side — co-occurrence
    conn.execute("""
        INSERT INTO transactions (source_id, sale_date, sale_price, display_address)
        VALUES ('RT_TX_002', '2023-07-20', 3200000, '180 Shorting Rd, Scarborough')
    """)

    # ── Transaction Parties ───────────────────────────────────────
    # TX1: seller side — DH Management group + Dan Hagler contact
    conn.execute("""
        INSERT INTO transaction_parties (source_id, group_id, contact_id, side, party_name)
        VALUES ('RT_TX_001', 'GRP_00001', 'CON_00001', 'seller', 'DH Management Inc')
    """)
    # TX1: buyer side — Dan Hagler Investments group
    conn.execute("""
        INSERT INTO transaction_parties (source_id, group_id, contact_id, side, party_name)
        VALUES ('RT_TX_001', 'GRP_00002', NULL, 'buyer', 'Dan Hagler Investments Ltd')
    """)

    # TX2: buyer side — both Dan Hagler Investments and Niagara Falls SC (co-occurrence)
    conn.execute("""
        INSERT INTO transaction_parties (source_id, group_id, contact_id, side, party_name)
        VALUES ('RT_TX_002', 'GRP_00002', 'CON_00001', 'buyer', 'Dan Hagler Investments Ltd')
    """)
    conn.execute("""
        INSERT INTO transaction_parties (source_id, group_id, contact_id, side, party_name)
        VALUES ('RT_TX_002', 'GRP_00003', NULL, 'buyer', 'Niagara Falls Shopping Centre Inc')
    """)

    # ── Mailing Addresses ─────────────────────────────────────────
    # Both TX1 seller and TX2 buyer share 180 Shorting Rd
    conn.execute("""
        INSERT INTO transaction_mailing_addresses
            (source_id, side, display, street_number, street_name, street_suffix, city, province, postal)
        VALUES ('RT_TX_001', 'seller', '180 Shorting Rd, Scarborough ON M1S 3S2',
            '180', 'SHORTING', 'RD', 'SCARBOROUGH', 'ON', 'M1S3S2')
    """)
    conn.execute("""
        INSERT INTO transaction_mailing_addresses
            (source_id, side, display, street_number, street_name, street_suffix, city, province, postal)
        VALUES ('RT_TX_002', 'buyer', '180 Shorting Rd, Scarborough ON M1S 3S2',
            '180', 'SHORTING', 'RD', 'SCARBOROUGH', 'ON', 'M1S3S2')
    """)

    conn.commit()
    return conn


@pytest.fixture
def db():
    conn = make_db()
    yield conn
    conn.close()


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestExtractAddressSignals:
    def test_extracts_address_signals(self, db):
        """Groups with a shared mailing address should each yield an address signal."""
        signals = extract_signals(db)
        address_signals = [s for s in signals if s.signal_type == "address"]

        # We have two address records: RT_TX_001 seller (GRP_00001) and RT_TX_002 buyer
        # (GRP_00002 + GRP_00003).  That's 3 address signals total.
        assert len(address_signals) >= 3, (
            f"Expected at least 3 address signals, got {len(address_signals)}: "
            f"{[(s.group_id, s.source_id) for s in address_signals]}"
        )

    def test_address_signal_value_format(self, db):
        """Address signal_value must be 'STREET_NUM STREET_NAME SUFFIX|CITY|POSTAL'."""
        signals = extract_signals(db)
        addr = next(
            (s for s in signals if s.signal_type == "address" and s.group_id == "GRP_00001"),
            None
        )
        assert addr is not None, "No address signal for GRP_00001"
        # Normalized: '180 SHORTING RD|SCARBOROUGH|M1S3S2'
        assert addr.signal_value == "180 SHORTING RD|SCARBOROUGH|M1S3S2", (
            f"Got: {addr.signal_value!r}"
        )

    def test_address_signal_has_raw_value(self, db):
        """Address signals should preserve a raw_value."""
        signals = extract_signals(db)
        addr = next((s for s in signals if s.signal_type == "address"), None)
        assert addr is not None
        assert addr.raw_value != "", "raw_value should not be empty"

    def test_address_signal_side(self, db):
        """Address signal side should match the transaction_mailing_addresses.side."""
        signals = extract_signals(db)
        seller_addr = next(
            (s for s in signals if s.signal_type == "address" and s.group_id == "GRP_00001"),
            None
        )
        assert seller_addr is not None
        assert seller_addr.side == "seller"


class TestExtractContactSignals:
    def test_extracts_contact_signals(self, db):
        """A contact appearing with a group on a transaction yields a contact signal."""
        signals = extract_signals(db)
        contact_signals = [s for s in signals if s.signal_type == "contact"]
        assert len(contact_signals) >= 1, "Expected at least one contact signal"

    def test_contact_signal_value_is_fingerprint(self, db):
        """Contact signal_value should be the contact name_fingerprint."""
        signals = extract_signals(db)
        contact_signal = next(
            (s for s in signals if s.signal_type == "contact" and s.group_id == "GRP_00001"),
            None
        )
        assert contact_signal is not None, "No contact signal for GRP_00001"
        assert contact_signal.signal_value == "DAN HAGLER"

    def test_contact_signal_for_multiple_groups(self, db):
        """Dan Hagler appears with GRP_00001 (TX1) and GRP_00002 (TX2)."""
        signals = extract_signals(db)
        contact_signals = [s for s in signals if s.signal_type == "contact"]
        group_ids = {s.group_id for s in contact_signals}
        # GRP_00001 from TX1, GRP_00002 from TX2
        assert "GRP_00001" in group_ids
        assert "GRP_00002" in group_ids


class TestExtractPhoneSignals:
    def test_extracts_phone_signals(self, db):
        """Contacts with a phone number yield phone signals."""
        signals = extract_signals(db)
        phone_signals = [s for s in signals if s.signal_type == "phone"]
        assert len(phone_signals) >= 1, "Expected at least one phone signal"

    def test_phone_normalized_to_10_digits(self, db):
        """Phone signal_value must be exactly 10 digits."""
        signals = extract_signals(db)
        phone_signal = next(
            (s for s in signals if s.signal_type == "phone"),
            None
        )
        assert phone_signal is not None
        assert phone_signal.signal_value.isdigit(), "Phone value should be all digits"
        assert len(phone_signal.signal_value) == 10, (
            f"Expected 10 digits, got {len(phone_signal.signal_value)}: "
            f"{phone_signal.signal_value!r}"
        )

    def test_phone_attributed_to_current_group(self, db):
        """Phone signal should be attributed to the contact's current_group_id."""
        signals = extract_signals(db)
        phone_signal = next(
            (s for s in signals if s.signal_type == "phone"),
            None
        )
        assert phone_signal is not None
        assert phone_signal.group_id == "GRP_00001"

    def test_phone_strips_leading_1(self, db):
        """An 11-digit phone starting with 1 should strip it down to 10 digits."""
        conn = make_db()
        # Insert a contact with 11-digit phone starting with 1
        conn.execute("""
            UPDATE contacts SET phone = '14162655055' WHERE id = 'CON_00001'
        """)
        conn.commit()
        signals = extract_signals(conn)
        phone_signal = next(
            (s for s in signals if s.signal_type == "phone"),
            None
        )
        conn.close()
        assert phone_signal is not None
        assert phone_signal.signal_value == "4162655055"


class TestExtractCareOfSignals:
    def test_extracts_care_of_signals(self, db):
        """seller_care_of / buyer_care_of on transactions yield care_of signals."""
        signals = extract_signals(db)
        care_of_signals = [s for s in signals if s.signal_type == "care_of"]
        assert len(care_of_signals) >= 1, (
            f"Expected at least one care_of signal; got {len(care_of_signals)}"
        )

    def test_care_of_value_normalized(self, db):
        """care_of signal_value should be normalized via normalize_group_name."""
        signals = extract_signals(db)
        care_of = next(
            (s for s in signals if s.signal_type == "care_of"),
            None
        )
        assert care_of is not None
        # 'DH Property Holdings LP' → normalize_group_name strips 'LP' → 'DH PROPERTY HOLDINGS'
        assert care_of.signal_value == "DH PROPERTY HOLDINGS", (
            f"Got: {care_of.signal_value!r}"
        )

    def test_care_of_attributed_to_first_group_on_side(self, db):
        """care_of signals are attributed to the first group on that side."""
        signals = extract_signals(db)
        care_of = next(
            (s for s in signals if s.signal_type == "care_of"),
            None
        )
        assert care_of is not None
        assert care_of.group_id == "GRP_00001"
        assert care_of.side == "seller"


class TestExtractTradeNameSignals:
    def test_extracts_trade_name_signals(self, db):
        """buyer_trade_name on transactions yield trade_name signals."""
        signals = extract_signals(db)
        trade_signals = [s for s in signals if s.signal_type == "trade_name"]
        assert len(trade_signals) >= 1, (
            f"Expected at least one trade_name signal; got {len(trade_signals)}"
        )

    def test_trade_name_value_normalized(self, db):
        """trade_name signal_value is normalized via normalize_group_name."""
        signals = extract_signals(db)
        trade = next(
            (s for s in signals if s.signal_type == "trade_name"),
            None
        )
        assert trade is not None
        # 'DH Realty Trust' → 'DH REALTY TRUST' (no legal suffix to strip)
        assert trade.signal_value == "DH REALTY TRUST", (
            f"Got: {trade.signal_value!r}"
        )


class TestExclusions:
    def test_excludes_excluded_addresses(self, db):
        """If an address is in discovery_exclusions it should not appear in signals."""
        # Add exclusion for the shared address
        db.execute("""
            INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason)
            VALUES ('address', '180 SHORTING RD|SCARBOROUGH|M1S3S2', 'common mailing address')
        """)
        db.commit()

        signals = extract_signals(db)
        address_signals = [s for s in signals if s.signal_type == "address"]
        excluded_values = {s.signal_value for s in address_signals}
        assert "180 SHORTING RD|SCARBOROUGH|M1S3S2" not in excluded_values, (
            "Excluded address should not appear in signals"
        )

    def test_excludes_excluded_contact(self, db):
        """If a contact fingerprint is in discovery_exclusions it should be filtered."""
        db.execute("""
            INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason)
            VALUES ('contact', 'DAN HAGLER', 'ubiquitous contact')
        """)
        db.commit()

        signals = extract_signals(db)
        contact_signals = [s for s in signals if s.signal_type == "contact"]
        contact_values = {s.signal_value for s in contact_signals}
        assert "DAN HAGLER" not in contact_values

    def test_non_excluded_signals_still_present(self, db):
        """Excluding one address shouldn't remove other signal types."""
        db.execute("""
            INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason)
            VALUES ('address', '180 SHORTING RD|SCARBOROUGH|M1S3S2', 'test')
        """)
        db.commit()

        signals = extract_signals(db)
        # Other signal types (contact, phone, care_of, trade_name) should still be present
        non_address = [s for s in signals if s.signal_type != "address"]
        assert len(non_address) > 0, "Non-address signals should still be present after exclusion"

    def test_load_exclusions_returns_set(self, db):
        """_load_exclusions should return a set of (type, value) tuples."""
        db.execute("""
            INSERT INTO discovery_exclusions (exclusion_type, exclusion_value)
            VALUES ('address', '180 SHORTING RD|SCARBOROUGH|M1S3S2')
        """)
        db.commit()

        exclusions = _load_exclusions(db)
        assert isinstance(exclusions, set)
        assert ("address", "180 SHORTING RD|SCARBOROUGH|M1S3S2") in exclusions


class TestEntityCooccurrenceSignals:
    def test_extracts_entity_cooccurrence_signals(self, db):
        """When 2+ groups are on same side of a transaction, pairwise entity signals."""
        signals = extract_signals(db)
        entity_signals = [s for s in signals if s.signal_type == "entity"]
        assert len(entity_signals) >= 2, (
            f"Expected at least 2 entity co-occurrence signals (one per group in pair), "
            f"got {len(entity_signals)}: {[(s.group_id, s.signal_value) for s in entity_signals]}"
        )

    def test_cooccurrence_signal_value_is_other_group(self, db):
        """Entity signal_value should be the co-occurring group's ID."""
        signals = extract_signals(db)
        entity_signals = [s for s in signals if s.signal_type == "entity"]

        # GRP_00002 and GRP_00003 both appeared as buyer on TX2
        grp2_signals = [s for s in entity_signals if s.group_id == "GRP_00002"]
        grp3_signals = [s for s in entity_signals if s.group_id == "GRP_00003"]

        assert any(s.signal_value == "GRP_00003" for s in grp2_signals), (
            "GRP_00002 should have entity signal pointing to GRP_00003"
        )
        assert any(s.signal_value == "GRP_00002" for s in grp3_signals), (
            "GRP_00003 should have entity signal pointing to GRP_00002"
        )

    def test_cooccurrence_signals_on_correct_side(self, db):
        """Entity signals should reflect the side they co-occurred on."""
        signals = extract_signals(db)
        entity_signals = [s for s in signals if s.signal_type == "entity"]
        buyer_entity = next(
            (s for s in entity_signals if s.group_id == "GRP_00002"),
            None
        )
        assert buyer_entity is not None
        assert buyer_entity.side == "buyer"

    def test_no_cooccurrence_for_single_group(self, db):
        """A side with only one group should not generate entity signals."""
        # TX1 seller side only has GRP_00001 — no co-occurrence expected for seller
        signals = extract_signals(db)
        entity_signals = [s for s in signals if s.signal_type == "entity"]
        # GRP_00001 only appears on seller side of TX1 (alone), so no entity signal
        grp1_entity = [s for s in entity_signals if s.group_id == "GRP_00001"]
        assert len(grp1_entity) == 0, (
            f"GRP_00001 should have no entity signals, got: "
            f"{[(s.signal_value, s.source_id) for s in grp1_entity]}"
        )


class TestFuzzyContactUnification:
    def test_fuzzy_contact_unification(self, db):
        """NINA WINE and NINA HAGLER WINE should unify to same contact signal."""
        # Add a second contact with a longer name variant
        db.execute(
            "INSERT INTO contacts (id, name_fingerprint, display_name, current_group_id) "
            "VALUES ('CON_00002', 'NINA HAGLER WINE', 'Nina Hagler Wine', 'GRP_00003')"
        )
        # Add a contact with the shorter form
        db.execute(
            "INSERT INTO contacts (id, name_fingerprint, display_name, current_group_id) "
            "VALUES ('CON_00003', 'NINA WINE', 'Nina Wine', 'GRP_00002')"
        )
        # Add transaction parties so both appear in signals
        db.execute(
            "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, party_name) "
            "VALUES ('RT_TX_001', 'CON_00002', 'GRP_00003', 'buyer', 'Nina Hagler Wine')"
        )
        db.execute(
            "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, party_name) "
            "VALUES ('RT_TX_002', 'CON_00003', 'GRP_00002', 'buyer', 'Nina Wine')"
        )
        db.commit()

        signals = extract_signals(db)
        contact_signals = [s for s in signals if s.signal_type == "contact"]
        contact_values = {s.signal_value for s in contact_signals}

        # The longer form should have been unified away
        assert "NINA HAGLER WINE" not in contact_values, (
            "NINA HAGLER WINE should have been unified into NINA WINE"
        )
        # The shorter form should be present
        assert "NINA WINE" in contact_values, (
            "NINA WINE should remain as the canonical form"
        )

    def test_unify_returns_merge_map(self):
        """_unify_fuzzy_contacts returns a mapping of long → short fingerprints."""
        signals = [
            Signal("contact", "NINA HAGLER WINE", "GRP_00001", "TX1", "seller"),
            Signal("contact", "NINA WINE", "GRP_00002", "TX2", "buyer"),
            Signal("address", "180 SHORTING RD|TORONTO|M1S3S2", "GRP_00001", "TX1", "seller"),
        ]
        updated, merge_map = _unify_fuzzy_contacts(signals)

        assert merge_map == {"NINA HAGLER WINE": "NINA WINE"}
        # The longer form should be replaced in the updated list
        contact_values = [s.signal_value for s in updated if s.signal_type == "contact"]
        assert "NINA HAGLER WINE" not in contact_values
        assert contact_values.count("NINA WINE") == 2  # both rows now canonical

    def test_no_match_when_disjoint_tokens(self):
        """NINA WINE and NINA SMITH should NOT unify (different last name)."""
        signals = [
            Signal("contact", "NINA SMITH", "GRP_00001", "TX1", "seller"),
            Signal("contact", "NINA WINE", "GRP_00002", "TX2", "buyer"),
        ]
        _, merge_map = _unify_fuzzy_contacts(signals)
        assert merge_map == {}, "Disjoint names should not be merged"

    def test_single_token_names_skipped(self):
        """Single-token fingerprints are too ambiguous and should never unify."""
        signals = [
            Signal("contact", "NINA", "GRP_00001", "TX1", "seller"),
            Signal("contact", "NINA WINE", "GRP_00002", "TX2", "buyer"),
        ]
        _, merge_map = _unify_fuzzy_contacts(signals)
        assert merge_map == {}, "Single-token names should not trigger unification"

    def test_non_contact_signals_unchanged(self):
        """Address/phone signals must pass through _unify_fuzzy_contacts untouched."""
        signals = [
            Signal("address", "180 SHORTING RD|TORONTO|M1S3S2", "GRP_00001", "TX1", "seller"),
            Signal("contact", "NINA HAGLER WINE", "GRP_00001", "TX1", "seller"),
            Signal("contact", "NINA WINE", "GRP_00002", "TX2", "buyer"),
        ]
        updated, _ = _unify_fuzzy_contacts(signals)
        addr_signals = [s for s in updated if s.signal_type == "address"]
        assert len(addr_signals) == 1
        assert addr_signals[0].signal_value == "180 SHORTING RD|TORONTO|M1S3S2"


class TestSignalStructure:
    def test_all_signals_have_required_fields(self, db):
        """Every signal must have non-empty signal_type, signal_value, group_id, source_id, side."""
        signals = extract_signals(db)
        assert len(signals) > 0, "extract_signals must return at least one signal"
        for s in signals:
            assert s.signal_type, f"Empty signal_type: {s}"
            assert s.signal_value, f"Empty signal_value: {s}"
            assert s.group_id, f"Empty group_id: {s}"
            # source_id is allowed to be empty for phone signals (not transaction-derived)
            assert s.side in ("seller", "buyer", ""), f"Invalid side: {s.side!r}"

    def test_returns_list_of_signal_instances(self, db):
        """extract_signals must return a list of Signal dataclass instances."""
        signals = extract_signals(db)
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, Signal), f"Expected Signal, got {type(s)}"
