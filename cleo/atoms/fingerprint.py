"""Fingerprint every transaction party-side.

Reads raw transaction / party / mailing / contact data, atomizes via
cleo.atoms.normalize, writes party_fingerprints + party_atoms.

Called from the compiler's run_compiler() as the final pass. Idempotent:
the tables are dropped and recreated at the start so repeat runs produce
identical output.
"""

from __future__ import annotations
import json
from cleo.atoms.normalize import (
    normalize_brand, tokenize_brand, normalize_contact_name,
    normalize_phone, normalize_street_number, normalize_street_name,
    normalize_street_suffix, normalize_street_direction,
    normalize_suite_type, normalize_suite_number, normalize_city,
    normalize_province, normalize_postal, normalize_country,
)


def _parse_json_array(raw):
    """Safely parse a JSON array column. Returns [] on any issue."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val if x] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _emit_brand_atoms(rows, source_id, side, raw_value, source_field,
                      phrase_type, token_type):
    """Given a raw value (or single string), normalize + tokenize and append
    atom rows to the `rows` list. No-ops if the value normalizes to empty."""
    phrase = normalize_brand(raw_value)
    if not phrase:
        return
    rows.append((source_id, side, phrase_type, phrase, source_field))
    for tok in tokenize_brand(phrase):
        rows.append((source_id, side, token_type, tok, source_field))


def run_fingerprint_pass(conn):
    """Rebuild party_fingerprints and party_atoms from current DB state.

    Reads:
      transactions (for sale_date + 4 side-specific brand fields + law firms)
      transaction_parties (for party_name, phone, contact_id per side)
      transaction_mailing_addresses (for address components per side)
      contacts (for first_name, last_name)

    Writes:
      party_fingerprints: one row per distinct (source_id, side)
      party_atoms: multiple rows per party-side (brand phrase + tokens, law firm phrase + tokens)
    """
    print('Fingerprint pass: atomizing every party-side...')

    # Step 1: drop and recreate to ensure idempotency (even if schema.py was
    # also applied — we want a clean rebuild).
    conn.executescript("""
        DROP TABLE IF EXISTS party_atoms;
        DROP TABLE IF EXISTS party_fingerprints;
    """)

    # Step 2: recreate the two tables (schema.py's DERIVED_TABLES block already
    # defines them, but since we just dropped them we need them back).
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS party_fingerprints (
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            street_number       TEXT,
            street_name         TEXT,
            street_suffix       TEXT,
            street_direction    TEXT,
            suite_type          TEXT,
            suite_number        TEXT,
            city                TEXT,
            province            TEXT,
            postal              TEXT,
            postal_raw          TEXT,
            country             TEXT,
            phone               TEXT,
            contact_fingerprint TEXT,
            sale_date           TEXT,
            computed_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE IF NOT EXISTS party_atoms (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            atom_type    TEXT NOT NULL,
            atom_value   TEXT NOT NULL,
            source_field TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pfp_street_key ON party_fingerprints(street_number, street_name, street_suffix);
        CREATE INDEX IF NOT EXISTS idx_pfp_postal ON party_fingerprints(postal);
        CREATE INDEX IF NOT EXISTS idx_pfp_phone ON party_fingerprints(phone);
        CREATE INDEX IF NOT EXISTS idx_pfp_contact ON party_fingerprints(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_pa_lookup ON party_atoms(atom_type, atom_value);
        CREATE INDEX IF NOT EXISTS idx_pa_party ON party_atoms(source_id, side);
    """)

    # Step 3: bulk-load auxiliary lookups in one pass each
    # (party_name, phone, contact_id) per (source_id, side): multi-valued
    party_names_by_key = {}
    phones_by_key = {}
    contact_ids_by_key = {}
    for r in conn.execute(
        "SELECT source_id, side, party_name, phone, contact_id FROM transaction_parties"
    ):
        key = (r['source_id'], r['side'])
        if r['party_name']:
            party_names_by_key.setdefault(key, []).append(r['party_name'])
        if r['phone']:
            phones_by_key.setdefault(key, []).append(r['phone'])
        if r['contact_id']:
            contact_ids_by_key.setdefault(key, []).append(r['contact_id'])

    contacts_by_id = {
        r['id']: (r['first_name'], r['last_name'])
        for r in conn.execute("SELECT id, first_name, last_name FROM contacts")
    }

    # Step 4: iterate distinct party-sides with their tx + mailing data
    fp_rows = []
    atom_rows = []
    seen_keys = set()

    query = """
        SELECT DISTINCT
            tp.source_id,
            tp.side,
            t.sale_date,
            CASE tp.side WHEN 'buyer' THEN t.buyer_trade_name ELSE t.seller_trade_name END AS trade_name,
            CASE tp.side WHEN 'buyer' THEN t.buyer_care_of ELSE t.seller_care_of END AS care_of,
            CASE tp.side WHEN 'buyer' THEN t.buyer_companies_json ELSE t.seller_companies_json END AS companies_json,
            CASE tp.side WHEN 'buyer' THEN t.buyer_law_firms_json ELSE t.seller_law_firms_json END AS law_firms_json,
            tma.street_number, tma.street_name, tma.street_suffix, tma.street_direction,
            tma.suite_type, tma.suite_number, tma.city, tma.province, tma.postal, tma.country
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN transaction_mailing_addresses tma
            ON tma.source_id = tp.source_id AND tma.side = tp.side
    """
    for r in conn.execute(query):
        key = (r['source_id'], r['side'])
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Singleton atoms -> party_fingerprints row
        phone = None
        for ph in phones_by_key.get(key, []):
            p = normalize_phone(ph)
            if p:
                phone = p
                break

        contact_fp = None
        for cid in contact_ids_by_key.get(key, []):
            fn, ln = contacts_by_id.get(cid, (None, None))
            cfp = normalize_contact_name(fn, ln)
            if cfp:
                contact_fp = cfp
                break

        fp_rows.append((
            r['source_id'],
            r['side'],
            normalize_street_number(r['street_number']),
            normalize_street_name(r['street_name']),
            normalize_street_suffix(r['street_suffix']),
            normalize_street_direction(r['street_direction']),
            normalize_suite_type(r['suite_type']),
            normalize_suite_number(r['suite_number']),
            normalize_city(r['city']),
            normalize_province(r['province']),
            normalize_postal(r['postal']),
            r['postal'],  # postal_raw — preserve source string verbatim
            normalize_country(r['country']),
            phone,
            contact_fp,
            r['sale_date'],
        ))

        # Multi-valued atoms -> party_atoms rows
        for pname in party_names_by_key.get(key, []):
            _emit_brand_atoms(atom_rows, r['source_id'], r['side'], pname,
                              'party_name', 'brand_phrase', 'brand_token')

        _emit_brand_atoms(atom_rows, r['source_id'], r['side'], r['trade_name'],
                          'trade_name', 'brand_phrase', 'brand_token')
        _emit_brand_atoms(atom_rows, r['source_id'], r['side'], r['care_of'],
                          'care_of', 'brand_phrase', 'brand_token')

        for c in _parse_json_array(r['companies_json']):
            _emit_brand_atoms(atom_rows, r['source_id'], r['side'], c,
                              'companies_json', 'brand_phrase', 'brand_token')

        for lf in _parse_json_array(r['law_firms_json']):
            _emit_brand_atoms(atom_rows, r['source_id'], r['side'], lf,
                              'law_firms_json', 'law_firm_phrase', 'law_firm_token')

    # Step 5: bulk insert
    print(f'  Inserting {len(fp_rows):,} party_fingerprints rows...')
    conn.executemany(
        """INSERT INTO party_fingerprints
           (source_id, side, street_number, street_name, street_suffix, street_direction,
            suite_type, suite_number, city, province, postal, postal_raw, country,
            phone, contact_fingerprint, sale_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        fp_rows,
    )
    print(f'  Inserting {len(atom_rows):,} party_atoms rows...')
    conn.executemany(
        """INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field)
           VALUES (?, ?, ?, ?, ?)""",
        atom_rows,
    )
    conn.commit()
    print(f'  Fingerprint pass complete: {len(fp_rows):,} party-sides, '
          f'{len(atom_rows):,} atoms.')
