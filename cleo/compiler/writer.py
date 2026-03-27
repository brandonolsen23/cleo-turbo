"""
Writer — reads Clean Records and populates SQLite derived tables.

Three passes:
  1. Groups: extract party names → normalize → assign GRP_ IDs
  2. Contacts: extract contact names → fingerprint → assign CON_ IDs
  3. Properties + Transactions + Transaction Parties: link everything

CRM tables are never touched. Derived tables are truncated and rebuilt.
"""

import json
import time

from .reader import iter_clean_records, read_parcel, count_clean_records
from .reconciler import IDRegistry, make_name_fingerprint, normalize_group_name
from ..database.schema import drop_derived_tables, create_all_tables


def run_compiler(conn):
    """Run the full Compiler: read clean-data/, write to SQLite."""

    print('Cleo Compiler')
    print()

    # Count records
    total = count_clean_records()
    print(f'Clean Records to process: {total:,}')
    print()

    # Disable FK checks during bulk load (properties inserted after transactions)
    conn.execute("PRAGMA foreign_keys=OFF")

    # Drop and recreate derived tables (CRM tables preserved)
    print('Dropping derived tables...')
    drop_derived_tables(conn)
    print('Recreating tables...')
    create_all_tables(conn)

    # Initialize ID registry
    registry = IDRegistry(conn)
    registry.load()

    start = time.time()

    # ================================================================
    # Pass 1: Groups — collect all party names, assign GRP_ IDs
    # ================================================================
    print('Pass 1: Groups...')
    group_data = {}  # normalized_name -> {id, display_name, names: set, tx_count}

    for source_id, rec in iter_clean_records():
        for side in ['seller', 'buyer']:
            parties = rec.get(side, {}).get('parties', [])
            for party in parties:
                name = party.get('name', '').strip()
                if not name or name == 'Named Individual(s)':
                    continue
                normalized = normalize_group_name(name)
                if not normalized:
                    continue
                if normalized not in group_data:
                    gid = registry.get_or_create_group_id(normalized)
                    group_data[normalized] = {
                        'id': gid,
                        'display_name': name,
                        'normalized_name': normalized,
                        'names': set(),
                        'tx_count': 0,
                        'property_arns': set(),
                    }
                group_data[normalized]['names'].add((name, source_id))
                group_data[normalized]['tx_count'] += 1

                # Track properties owned (buyer side only)
                if side == 'buyer':
                    arn = rec.get('site', {}).get('arn', {}).get('api_format', '')
                    if arn and not all(c == '0' for c in arn):
                        group_data[normalized]['property_arns'].add(arn)

    # Insert groups
    for norm, g in group_data.items():
        conn.execute(
            "INSERT INTO groups (id, display_name, normalized_name, status, property_count, transaction_count) "
            "VALUES (?, ?, ?, 'pool', ?, ?)",
            (g['id'], g['display_name'], g['normalized_name'],
             len(g['property_arns']), g['tx_count'])
        )
        # Insert known name variants
        seen_names = set()
        for name, sid in g['names']:
            norm_variant = normalize_group_name(name)
            if norm_variant not in seen_names:
                seen_names.add(norm_variant)
                conn.execute(
                    "INSERT OR IGNORE INTO group_names (group_id, name, normalized, source_id) VALUES (?, ?, ?, ?)",
                    (g['id'], name, norm_variant, sid)
                )
    conn.commit()
    print(f'  Groups: {len(group_data):,}')

    # ================================================================
    # Pass 2: Contacts — collect all contact names, assign CON_ IDs
    # ================================================================
    print('Pass 2: Contacts...')
    contact_data = {}  # fingerprint -> {id, first_name, last_name, display_name, ...}

    for source_id, rec in iter_clean_records():
        sale_date = rec.get('transaction', {}).get('sale_date', '')

        for side in ['seller', 'buyer']:
            contacts = rec.get(side, {}).get('contacts', [])
            phone = rec.get(side, {}).get('phone', '')

            # Determine group for this side
            parties = rec.get(side, {}).get('parties', [])
            group_id = None
            group_display = ''
            if parties:
                first_party = parties[0].get('name', '').strip()
                if first_party and first_party != 'Named Individual(s)':
                    norm = normalize_group_name(first_party)
                    if norm in group_data:
                        group_id = group_data[norm]['id']
                        group_display = group_data[norm]['display_name']

            for contact in contacts:
                name = contact.get('name', '').strip()
                if not name:
                    continue
                fingerprint = make_name_fingerprint(name)
                if not fingerprint:
                    continue

                # Split name into first/last (simple split on last space)
                parts = name.split()
                first = parts[0] if parts else ''
                last = ' '.join(parts[1:]) if len(parts) > 1 else ''

                if fingerprint not in contact_data:
                    cid = registry.get_or_create_contact_id(fingerprint)
                    contact_data[fingerprint] = {
                        'id': cid,
                        'fingerprint': fingerprint,
                        'first_name': first,
                        'last_name': last,
                        'display_name': name,
                        'phone': phone,
                        'job_title': contact.get('title', ''),
                        'company_name': group_display,
                        'current_group_id': group_id,
                        'tx_count': 0,
                        'first_seen': sale_date,
                        'last_seen': sale_date,
                    }

                cd = contact_data[fingerprint]
                cd['tx_count'] += 1

                # Update with most recent info
                if sale_date and (not cd['last_seen'] or sale_date > cd['last_seen']):
                    cd['last_seen'] = sale_date
                    if phone:
                        cd['phone'] = phone
                    if contact.get('title'):
                        cd['job_title'] = contact['title']
                    if group_id:
                        cd['current_group_id'] = group_id
                        cd['company_name'] = group_display

                if sale_date and (not cd['first_seen'] or sale_date < cd['first_seen']):
                    cd['first_seen'] = sale_date

    # Insert contacts
    for fp, c in contact_data.items():
        conn.execute(
            "INSERT INTO contacts (id, name_fingerprint, first_name, last_name, display_name, "
            "phone, job_title, company_name, current_group_id, status, source, "
            "transaction_count, first_seen_date, last_seen_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pool', 'transaction', ?, ?, ?)",
            (c['id'], c['fingerprint'], c['first_name'], c['last_name'], c['display_name'],
             c['phone'], c['job_title'], c['company_name'], c['current_group_id'],
             c['tx_count'], c['first_seen'], c['last_seen'])
        )
    conn.commit()
    print(f'  Contacts: {len(contact_data):,}')

    # Update group contact counts
    for norm, g in group_data.items():
        count = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE current_group_id = ?", (g['id'],)
        ).fetchone()[0]
        conn.execute("UPDATE groups SET contact_count = ? WHERE id = ?", (count, g['id']))
    conn.commit()

    # ================================================================
    # Pass 3: Properties + Transactions + Transaction Parties
    # ================================================================
    print('Pass 3: Properties + Transactions...')
    property_data = {}  # arn -> {id, best_record}
    tx_count = 0
    party_count = 0

    for source_id, rec in iter_clean_records():
        tx = rec.get('transaction', {})
        site = rec.get('site', {})
        prop = rec.get('property', {})
        parcel_info = rec.get('parcel')

        arn = site.get('arn', {}).get('api_format', '')
        if arn and all(c == '0' for c in arn):
            arn = ''
        pin = site.get('pin', {}).get('api_format', '')

        # Get display address
        addrs = prop.get('addresses', [])
        display_address = addrs[0].get('display', '') if addrs else ''
        # Ensure commas have a space after them (multi-address: "1677,1679" → "1677, 1679")
        import re as _re
        display_address = _re.sub(r',(?!\s)', ', ', display_address)

        # Property (one per ARN)
        property_id = None
        if arn:
            if arn not in property_data:
                pid = registry.get_or_create_property_id(arn)
                property_data[arn] = {
                    'id': pid,
                    'arn': arn,
                    'display_address': display_address,
                    'city': tx.get('city', ''),
                    'region': tx.get('region', ''),
                    'postal': prop.get('postal', ''),
                    'acreage': site.get('acreage'),
                    'legal_description': site.get('legal_description', ''),
                    'sale_date': tx.get('sale_date', ''),
                    'sale_price': tx.get('sale_price'),
                    'tx_count': 0,
                    'owner_name': '',
                    'owner_group_id': None,
                    'source_id': source_id,
                }

            pd = property_data[arn]
            pd['tx_count'] += 1

            # Update with most recent transaction
            if tx.get('sale_date', '') and (not pd['sale_date'] or tx['sale_date'] > pd['sale_date']):
                pd['sale_date'] = tx['sale_date']
                pd['sale_price'] = tx.get('sale_price')
                pd['display_address'] = display_address or pd['display_address']
                pd['city'] = tx.get('city', '') or pd['city']
                pd['region'] = tx.get('region', '') or pd['region']
                pd['source_id'] = source_id
                # Current owner = buyer of most recent transaction
                buyer_parties = rec.get('buyer', {}).get('parties', [])
                if buyer_parties:
                    owner_name = buyer_parties[0].get('name', '')
                    pd['owner_name'] = owner_name
                    norm = normalize_group_name(owner_name)
                    if norm in group_data:
                        pd['owner_group_id'] = group_data[norm]['id']

            property_id = pd['id']

        # Transaction
        seller_parties = [p.get('name', '') for p in rec.get('seller', {}).get('parties', [])]
        buyer_parties = [p.get('name', '') for p in rec.get('buyer', {}).get('parties', [])]

        conn.execute(
            "INSERT OR IGNORE INTO transactions (source_id, property_id, arn, sale_date, sale_price, "
            "transaction_note, display_address, city, region, postal, seller_parties, buyer_parties, "
            "seller_phone, buyer_phone, description, acreage, pin, legal_description, "
            "consideration_json, broker_json, photos_json, source_folder) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_id, property_id, arn,
             tx.get('sale_date'), tx.get('sale_price'), tx.get('transaction_note', ''),
             display_address, tx.get('city', ''), tx.get('region', ''), prop.get('postal', ''),
             json.dumps(seller_parties), json.dumps(buyer_parties),
             rec.get('seller', {}).get('phone', ''), rec.get('buyer', {}).get('phone', ''),
             rec.get('description', {}).get('description', ''),
             site.get('acreage'), pin, site.get('legal_description', ''),
             json.dumps(rec.get('consideration', {})),
             json.dumps(rec.get('broker', {})),
             json.dumps(rec.get('photos', {})),
             rec.get('source_folder', ''))
        )
        tx_count += 1

        # Transaction parties
        for side in ['seller', 'buyer']:
            parties = rec.get(side, {}).get('parties', [])
            contacts = rec.get(side, {}).get('contacts', [])
            phone = rec.get(side, {}).get('phone', '')

            # Link group
            for party in parties:
                pname = party.get('name', '').strip()
                if not pname or pname == 'Named Individual(s)':
                    continue
                norm = normalize_group_name(pname)
                gid = group_data[norm]['id'] if norm in group_data else None

                # Link contacts for this side
                for contact in contacts:
                    cname = contact.get('name', '').strip()
                    if not cname:
                        continue
                    fp = make_name_fingerprint(cname)
                    cid = contact_data[fp]['id'] if fp in contact_data else None

                    conn.execute(
                        "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, "
                        "party_name, contact_title, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (source_id, cid, gid, side, pname, contact.get('title', ''), phone)
                    )
                    party_count += 1

                # If no contacts, still link the group to the transaction
                if not contacts:
                    conn.execute(
                        "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, "
                        "party_name, contact_title, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (source_id, None, group_data[norm]['id'] if norm in group_data else None,
                         side, pname, '', phone)
                    )
                    party_count += 1

        if tx_count % 5000 == 0:
            conn.commit()

    conn.commit()
    print(f'  Transactions: {tx_count:,}')
    print(f'  Transaction parties: {party_count:,}')

    # Insert properties
    prop_count = 0
    for arn, pd in property_data.items():
        # Load parcel geometry if available
        parcel = read_parcel(arn)
        parcel_geojson = json.dumps(parcel['geometry']) if parcel and parcel.get('geometry') else None
        lat = parcel['centroid'][0] if parcel and parcel.get('centroid') else None
        lng = parcel['centroid'][1] if parcel and parcel.get('centroid') else None

        conn.execute(
            "INSERT INTO properties (id, arn, display_address, city, region, postal, acreage, "
            "legal_description, current_owner_name, current_owner_group_id, most_recent_source_id, "
            "most_recent_sale_date, most_recent_sale_price, transaction_count, lat, lng, parcel_geojson) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pd['id'], arn, pd['display_address'], pd['city'], pd['region'], pd['postal'],
             pd['acreage'], pd['legal_description'], pd['owner_name'], pd['owner_group_id'],
             pd['source_id'], pd['sale_date'], pd['sale_price'], pd['tx_count'],
             lat, lng, parcel_geojson)
        )
        prop_count += 1
    conn.commit()
    print(f'  Properties: {prop_count:,}')

    # ================================================================
    # Rebuild FTS indexes
    # ================================================================
    print('Rebuilding FTS indexes...')
    conn.execute("INSERT INTO properties_fts(properties_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO contacts_fts(contacts_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO groups_fts(groups_fts) VALUES('rebuild')")
    conn.commit()

    # Re-enable FK checks
    conn.execute("PRAGMA foreign_keys=ON")

    # Save ID counters
    registry.save_counters()

    elapsed = time.time() - start
    print()
    print(f'Compiler done in {elapsed:.1f}s')
    print(f'  Properties:    {prop_count:,}')
    print(f'  Transactions:  {tx_count:,}')
    print(f'  Groups:        {len(group_data):,}')
    print(f'  Contacts:      {len(contact_data):,}')
    print(f'  Parties:       {party_count:,}')
