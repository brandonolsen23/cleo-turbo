"""Materialize per-Group and per-Contact timelines from atom_party_entities.

Drops and rebuilds every run. Called after entities are assigned.
"""

from __future__ import annotations


def materialize_timelines(conn):
    """Rebuild all timeline tables from atom_party_entities."""
    for tbl in (
        "atom_group_addresses", "atom_group_phones", "atom_group_contacts",
        "atom_contact_groups", "atom_contact_addresses",
    ):
        conn.execute(f"DELETE FROM {tbl}")

    # Group-level timelines
    conn.execute("""
        INSERT INTO atom_group_addresses
            (group_id, postal, street_number, street_name, street_suffix,
             first_seen, last_seen, n_observations)
        SELECT ape.group_id,
               pf.postal, pf.street_number, pf.street_name, pf.street_suffix,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL
          AND (pf.street_number IS NOT NULL OR pf.postal IS NOT NULL)
        GROUP BY ape.group_id, pf.postal, pf.street_number, pf.street_name, pf.street_suffix
    """)

    conn.execute("""
        INSERT INTO atom_group_phones
            (group_id, phone, first_seen, last_seen, n_observations)
        SELECT ape.group_id, pf.phone, MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL AND pf.phone IS NOT NULL AND pf.phone != ''
        GROUP BY ape.group_id, pf.phone
    """)

    conn.execute("""
        INSERT INTO atom_group_contacts
            (group_id, contact_id, first_seen, last_seen, n_observations)
        SELECT ape.group_id, ape.contact_id,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL AND ape.contact_id IS NOT NULL
        GROUP BY ape.group_id, ape.contact_id
    """)

    # Contact-level timelines
    conn.execute("""
        INSERT INTO atom_contact_groups
            (contact_id, group_id, first_seen, last_seen, n_observations)
        SELECT ape.contact_id, ape.group_id,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.contact_id IS NOT NULL AND ape.group_id IS NOT NULL
        GROUP BY ape.contact_id, ape.group_id
    """)

    conn.execute("""
        INSERT INTO atom_contact_addresses
            (contact_id, postal, street_number, street_name, street_suffix,
             first_seen, last_seen, n_observations)
        SELECT ape.contact_id,
               pf.postal, pf.street_number, pf.street_name, pf.street_suffix,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.contact_id IS NOT NULL
          AND (pf.street_number IS NOT NULL OR pf.postal IS NOT NULL)
        GROUP BY ape.contact_id, pf.postal, pf.street_number, pf.street_name, pf.street_suffix
    """)

    conn.commit()
