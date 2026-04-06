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

from .reader import (iter_clean_records, iter_osm_records, iter_gw_records,
                     read_parcel, count_clean_records, count_osm_records, count_gw_records)
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

        # Extract property type from source_folder (e.g., "Peel_Region/industrial/p033" → "industrial")
        source_folder = rec.get('source_folder', '')
        folder_parts = source_folder.split('/') if source_folder else []
        property_type = folder_parts[1] if len(folder_parts) >= 2 else ''

        # Determine ARN: prefer parcel-resolved ARN (validated), fall back to site ARN
        parcel_info = rec.get('parcel') or {}
        resolved_arn = parcel_info.get('resolved_arn', '')
        if resolved_arn and all(c == '0' for c in resolved_arn):
            resolved_arn = ''

        site_arn = site.get('arn', {}).get('api_format', '')
        if site_arn and all(c == '0' for c in site_arn):
            site_arn = ''

        # Use resolved ARN if available (it's been validated against AgMaps)
        # Only fall back to site ARN if it has a parcel in cache (verified geometry)
        arn = ''
        if resolved_arn:
            arn = resolved_arn
        elif site_arn and read_parcel(site_arn):
            arn = site_arn
        # If site_arn exists but has no cached parcel, DON'T create a ghost property

        pin = site.get('pin', {}).get('api_format', '')

        # Get display address
        addrs = prop.get('addresses', [])
        display_address = addrs[0].get('display', '') if addrs else ''
        import re as _re
        display_address = _re.sub(r',(?!\s)', ', ', display_address)

        # Property (one per ARN — only when we have validated geometry)
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
                    'property_type': property_type,
                }

            pd = property_data[arn]
            pd['tx_count'] += 1
            # Always fill property_type if we have one and it's not set yet
            if property_type and not pd['property_type']:
                pd['property_type'] = property_type

            # Update with most recent transaction
            if tx.get('sale_date', '') and (not pd['sale_date'] or tx['sale_date'] >= pd['sale_date']):
                pd['sale_date'] = tx['sale_date']
                pd['sale_price'] = tx.get('sale_price')
                pd['display_address'] = display_address or pd['display_address']
                pd['city'] = tx.get('city', '') or pd['city']
                pd['region'] = tx.get('region', '') or pd['region']
                pd['source_id'] = source_id
                pd['property_type'] = property_type or pd['property_type']
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

        # Consideration (inline on transaction)
        consideration = rec.get('consideration', {})

        # Party metadata (inline on transaction, per side)
        seller_data = rec.get('seller', {})
        buyer_data = rec.get('buyer', {})
        seller_care_of_raw = seller_data.get('care_of') or ''
        buyer_care_of_raw = buyer_data.get('care_of') or ''
        seller_care_of = seller_care_of_raw.get('text', '') if isinstance(seller_care_of_raw, dict) else (seller_care_of_raw or '')
        buyer_care_of = buyer_care_of_raw.get('text', '') if isinstance(buyer_care_of_raw, dict) else (buyer_care_of_raw or '')

        conn.execute(
            "INSERT OR IGNORE INTO transactions (source_id, property_id, arn, sale_date, sale_price, "
            "transaction_note, display_address, city, region, postal, seller_parties, buyer_parties, "
            "seller_phone, buyer_phone, description, acreage, pin, legal_description, "
            "pin_display, arn_display, pin_multiple, parcel_method, location, surface_rights_only, "
            "more_info_url, "
            "cash, debt, chattels, other_consideration, charges_json, "
            "seller_trade_name, seller_care_of, seller_law_firms_json, seller_companies_json, "
            "buyer_trade_name, buyer_care_of, buyer_law_firms_json, buyer_companies_json, "
            "photos_json, source_folder) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, "
            "?, ?, ?, ?, "
            "?, ?, ?, ?, "
            "?, ?)",
            (source_id, property_id, arn,
             tx.get('sale_date'), tx.get('sale_price'), tx.get('transaction_note', ''),
             display_address, tx.get('city', ''), tx.get('region', ''), prop.get('postal', ''),
             json.dumps(seller_parties), json.dumps(buyer_parties),
             rec.get('seller', {}).get('phone', ''), rec.get('buyer', {}).get('phone', ''),
             rec.get('description', {}).get('description', ''),
             site.get('acreage'), pin, site.get('legal_description', ''),
             site.get('pin', {}).get('display', ''),
             site.get('arn', {}).get('display', ''),
             1 if site.get('pin', {}).get('multiple') else 0,
             parcel_info.get('method', ''),
             site.get('location', ''),
             1 if site.get('surface_rights_only') else 0,
             rec.get('description', {}).get('more_info_url', ''),
             consideration.get('cash'),
             consideration.get('debt'),
             consideration.get('chattels'),
             consideration.get('other'),
             json.dumps(consideration.get('charges', [])),
             seller_data.get('trade_name', ''),
             seller_care_of,
             json.dumps(seller_data.get('law_firms', [])),
             json.dumps(seller_data.get('companies', [])),
             buyer_data.get('trade_name', ''),
             buyer_care_of,
             json.dumps(buyer_data.get('law_firms', [])),
             json.dumps(buyer_data.get('companies', [])),
             json.dumps(rec.get('photos', {})),
             rec.get('source_folder', ''))
        )
        tx_count += 1

        # Mailing addresses (Phase 1)
        for side in ['seller', 'buyer']:
            addr = rec.get(side, {}).get('address', {})
            if addr.get('display') or addr.get('geocode_string'):
                comps = addr.get('components', {})
                conn.execute(
                    "INSERT OR IGNORE INTO transaction_mailing_addresses "
                    "(source_id, side, display, street_number, street_name, street_suffix, "
                    "street_direction, suite_type, suite_number, city, province, postal, "
                    "country, geocode_string) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_id, side,
                     addr.get('display', ''),
                     comps.get('street_number', ''),
                     comps.get('street_name', ''),
                     comps.get('street_suffix', ''),
                     comps.get('street_direction', ''),
                     comps.get('suite_type', ''),
                     comps.get('suite_number', ''),
                     addr.get('city', ''),
                     addr.get('province', ''),
                     addr.get('postal', ''),
                     addr.get('country', ''),
                     addr.get('geocode_string', ''))
                )

        # Brokers (one-to-many: transaction → brokerages → agents)
        broker_data = rec.get('broker', {})
        brokers = broker_data.get('brokers', [])
        for broker in brokers:
            broker_name = broker.get('brokerage') or broker.get('name', '')
            broker_phone = broker.get('phone', '')
            agents = broker.get('agents', [])
            if broker_name or broker_phone or agents:
                cursor = conn.execute(
                    "INSERT INTO transaction_brokers (source_id, broker_name, phone) "
                    "VALUES (?, ?, ?)",
                    (source_id, broker_name, broker_phone)
                )
                broker_id = cursor.lastrowid
                for agent_name in agents:
                    if agent_name:
                        conn.execute(
                            "INSERT INTO transaction_broker_agents (broker_id, agent_name) "
                            "VALUES (?, ?)",
                            (broker_id, agent_name)
                        )

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
    prop_errors = 0
    for arn, pd in property_data.items():
        try:
            # Load parcel geometry if available
            parcel = read_parcel(arn)
            parcel_geojson = json.dumps(parcel['geometry']) if parcel and parcel.get('geometry') else None
            lat = parcel['centroid'][0] if parcel and parcel.get('centroid') else None
            lng = parcel['centroid'][1] if parcel and parcel.get('centroid') else None

            conn.execute(
                "INSERT INTO properties (id, arn, display_address, city, region, postal, acreage, "
                "legal_description, current_owner_name, current_owner_group_id, most_recent_source_id, "
                "most_recent_sale_date, most_recent_sale_price, most_recent_sale_source, transaction_count, "
                "primary_property_type, lat, lng, parcel_geojson) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pd['id'], arn, pd['display_address'], pd['city'], pd['region'], pd['postal'],
                 pd['acreage'], pd['legal_description'], pd['owner_name'], pd['owner_group_id'],
                 pd['source_id'], pd['sale_date'], pd['sale_price'], 'RT', pd['tx_count'],
                 pd['property_type'], lat, lng, parcel_geojson)
            )
            prop_count += 1
        except Exception as e:
            prop_errors += 1
            if prop_errors <= 5:
                print(f'  WARNING: property {pd["id"]} (ARN {arn}): {e}')

        if prop_count % 5000 == 0:
            conn.commit()

    conn.commit()
    print(f'  Properties: {prop_count:,}')
    if prop_errors:
        print(f'  Property errors: {prop_errors:,}')

    # ================================================================
    # Pass 4: POIs — link to existing properties or create new ones
    # ================================================================
    osm_count = count_osm_records()
    poi_count = 0
    poi_new_props = 0

    if osm_count > 0:
        print(f'Pass 4: POIs ({osm_count:,} OSM records)...')

        for poi_id, poi in iter_osm_records():
            coords = poi.get('coords', {})
            lat = coords.get('lat')
            lng = coords.get('lng')
            if not lat or not lng:
                continue

            arn = poi.get('arn')
            property_id = None

            if arn and not all(c == '0' for c in arn):
                if arn in property_data:
                    # Property exists from RT transactions — link POI to it
                    property_id = property_data[arn]['id']
                else:
                    # New property from POI data (no transactions for this parcel)
                    pid = registry.get_or_create_property_id(arn)
                    parcel = read_parcel(arn)
                    parcel_geojson = json.dumps(parcel['geometry']) if parcel and parcel.get('geometry') else None
                    # Use the POI's actual coordinates — they sit right on the building.
                    # Parcel centroid is just the middle of the lot shape (often a parking lot).
                    p_lat = lat
                    p_lng = lng

                    # Build display address from POI address fields
                    addr = poi.get('address', {})
                    parts = []
                    if addr.get('housenumber'):
                        parts.append(addr['housenumber'])
                    if addr.get('street'):
                        parts.append(addr['street'])
                    display_address = ' '.join(parts)

                    conn.execute(
                        "INSERT OR IGNORE INTO properties (id, arn, display_address, city, region, postal, "
                        "transaction_count, primary_property_type, lat, lng, parcel_geojson) "
                        "VALUES (?, ?, ?, ?, '', '', 0, 'retail', ?, ?, ?)",
                        (pid, arn, display_address, addr.get('city', ''),
                         p_lat, p_lng, parcel_geojson)
                    )

                    property_data[arn] = {'id': pid, 'arn': arn}
                    property_id = pid
                    poi_new_props += 1

            # Build display address for POI record
            addr = poi.get('address', {})
            poi_parts = []
            if addr.get('housenumber'):
                poi_parts.append(addr['housenumber'])
            if addr.get('street'):
                poi_parts.append(addr['street'])
            poi_address = ' '.join(poi_parts)

            building = poi.get('building') or {}
            building_geojson = json.dumps(building['polygon']) if building.get('polygon') else None

            conn.execute(
                "INSERT OR IGNORE INTO pois (id, source, brand, category, name, lat, lng, "
                "address, city, phone, website, property_id, arn, "
                "cuisine, operator, facebook, instagram, drive_through, "
                "osm_id, building_geojson, approx_sqft) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (poi_id, poi.get('source', 'osm'),
                 poi.get('tracked_brand') or poi.get('brand', ''),
                 poi.get('category', ''), poi.get('name', ''),
                 lat, lng, poi_address, addr.get('city', ''),
                 poi.get('phone', ''), poi.get('website', ''),
                 property_id, arn,
                 poi.get('cuisine', ''), poi.get('operator', ''),
                 poi.get('facebook', ''), poi.get('instagram', ''),
                 poi.get('drive_through', ''),
                 poi.get('osm_id', ''), building_geojson,
                 building.get('approx_sqft'))
            )
            poi_count += 1

            if poi_count % 5000 == 0:
                conn.commit()

        conn.commit()
        print(f'  POIs: {poi_count:,}')
        print(f'  New POI-sourced properties: {poi_new_props:,}')
    else:
        print('Pass 4: POIs (no OSM data, skipping)')

    # ================================================================
    # Pass 5: GW Assessments — enrich properties with GW data
    # ================================================================
    gw_count = count_gw_records()
    gw_assessment_count = 0
    gw_new_props = 0
    gw_enriched = 0

    if gw_count > 0:
        print(f'Pass 5: GW Assessments ({gw_count:,} records)...')

        for gw_id, gw in iter_gw_records():
            parcel_info = gw.get('parcel', {})
            resolved_arn = parcel_info.get('resolved_arn')
            gw_prop = gw.get('property', {})
            gw_owner = gw.get('owner', {})

            property_id = None

            if resolved_arn and not all(c == '0' for c in resolved_arn):
                if resolved_arn in property_data:
                    # Existing property — enrich display fields (GW is authoritative)
                    property_id = property_data[resolved_arn]['id']

                    updates = []
                    params = []

                    owner_name = gw_owner.get('name', '')
                    if owner_name:
                        updates.append("current_owner_name = ?")
                        params.append(owner_name)

                    display_addr = gw_prop.get('display_address', '')
                    if display_addr:
                        updates.append("display_address = ?")
                        params.append(display_addr)

                    city = gw_prop.get('city', '')
                    if city:
                        updates.append("city = ?")
                        params.append(city)

                    postal = gw_prop.get('postal', '')
                    if postal:
                        updates.append("postal = ?")
                        params.append(postal)

                    # Municipality from first assessment
                    assessments = gw.get('assessments', [])
                    if assessments:
                        municipality = assessments[0].get('municipality', '')
                        if municipality:
                            updates.append("gw_municipality = ?")
                            params.append(municipality)

                    if updates:
                        params.append(property_id)
                        conn.execute(
                            f"UPDATE properties SET {', '.join(updates)} WHERE id = ?",
                            params
                        )
                        gw_enriched += 1

                else:
                    # New property from GW data
                    pid = registry.get_or_create_property_id(resolved_arn)
                    parcel = read_parcel(resolved_arn)
                    parcel_geojson = json.dumps(parcel['geometry']) if parcel and parcel.get('geometry') else None
                    p_lat = parcel['centroid'][0] if parcel and parcel.get('centroid') else None
                    p_lng = parcel['centroid'][1] if parcel and parcel.get('centroid') else None

                    gw_municipality = ''
                    gw_assessments_list = gw.get('assessments', [])
                    if gw_assessments_list:
                        gw_municipality = gw_assessments_list[0].get('municipality', '')

                    conn.execute(
                        "INSERT OR IGNORE INTO properties (id, arn, display_address, city, postal, "
                        "current_owner_name, transaction_count, primary_property_type, "
                        "gw_municipality, lat, lng, parcel_geojson) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                        (pid, resolved_arn,
                         gw_prop.get('display_address', ''),
                         gw_prop.get('city', ''),
                         gw_prop.get('postal', ''),
                         gw_owner.get('name', ''),
                         gw.get('registry', {}).get('property_type', '').lower() or 'commercial',
                         gw_municipality,
                         p_lat, p_lng, parcel_geojson)
                    )

                    property_data[resolved_arn] = {'id': pid, 'arn': resolved_arn}
                    property_id = pid
                    gw_new_props += 1

            # Insert assessment records
            for idx, assessment in enumerate(gw.get('assessments', [])):
                a_id = gw_id if idx == 0 else f'{gw_id}_{idx + 1}'
                arn_api = assessment.get('arn_api', '')

                # Link to property via this assessment's ARN if primary didn't resolve
                a_property_id = property_id
                if not a_property_id and arn_api and arn_api in property_data:
                    a_property_id = property_data[arn_api]['id']

                quality = gw.get('quality', {})
                gw_registry = gw.get('registry', {})
                conn.execute(
                    "INSERT OR IGNORE INTO gw_assessments (id, gw_id, property_id, arn, pin, "
                    "assessed_value, valuation_date, zoning, property_code, property_description, "
                    "ownership_type, frontage_ft, depth_ft, site_area_sqft, acreage, "
                    "owner_name, owner_mailing, legal_description, source_file, "
                    "land_registry_status, registration_type, lro, municipality, "
                    "has_mpac_data, is_active, address_parsed, parcel_resolved) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?)",
                    (a_id, gw_id, a_property_id, arn_api, gw.get('pin', ''),
                     assessment.get('assessed_value'),
                     assessment.get('valuation_date', ''),
                     assessment.get('zoning', ''),
                     assessment.get('property_code', ''),
                     assessment.get('property_description', ''),
                     gw_registry.get('ownership_type', ''),
                     assessment.get('frontage_ft'),
                     assessment.get('depth_ft'),
                     assessment.get('site_area_sqft'),
                     assessment.get('acreage'),
                     assessment.get('owner_names_mpac', ''),
                     assessment.get('owner_mailing_address', ''),
                     assessment.get('legal_description', ''),
                     gw.get('source_file', ''),
                     gw_registry.get('land_registry_status', ''),
                     gw_registry.get('registration_type', ''),
                     gw_registry.get('lro', ''),
                     assessment.get('municipality', ''),
                     1 if quality.get('has_mpac_data') else 0,
                     1 if quality.get('is_active') else 0,
                     1 if quality.get('address_parsed') else 0,
                     1 if quality.get('parcel_resolved') else 0)
                )
                gw_assessment_count += 1

            # Insert sales history
            sales_history = gw.get('sales_history', [])
            for sale in sales_history:
                conn.execute(
                    "INSERT INTO gw_sales_history "
                    "(gw_id, property_id, arn, sale_date, amount, sale_type, party_to, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (gw_id, property_id,
                     resolved_arn or '',
                     sale.get('date', ''),
                     sale.get('amount'),
                     sale.get('type', ''),
                     sale.get('party_to', ''),
                     sale.get('notes', ''))
                )

            # Update property's most_recent_sale_price/date from GW sales history
            # if the GW sale is newer than what's already there (or nothing is there)
            if property_id and sales_history:
                dated_sales = [s for s in sales_history if s.get('date') and s.get('amount')]
                if dated_sales:
                    most_recent = max(dated_sales, key=lambda s: s['date'])
                    gw_date = most_recent['date']
                    gw_amount = most_recent['amount']
                    conn.execute(
                        "UPDATE properties SET most_recent_sale_price = ?, most_recent_sale_date = ?, "
                        "most_recent_sale_source = 'GW' "
                        "WHERE id = ? AND (most_recent_sale_date IS NULL OR most_recent_sale_date < ?)",
                        (gw_amount, gw_date, property_id, gw_date)
                    )

            if gw_assessment_count % 200 == 0:
                conn.commit()

        conn.commit()
        gw_sales_count = conn.execute("SELECT COUNT(*) FROM gw_sales_history").fetchone()[0]
        print(f'  GW assessments: {gw_assessment_count:,}')
        print(f'  GW sales history: {gw_sales_count:,}')
        print(f'  Enriched existing properties: {gw_enriched:,}')
        print(f'  New GW-sourced properties: {gw_new_props:,}')
    else:
        print('Pass 5: GW Assessments (no GW data, skipping)')

    # ================================================================
    # Rebuild FTS indexes
    # ================================================================
    print('Rebuilding FTS indexes...')
    fts_tables = ['properties_fts', 'contacts_fts', 'groups_fts', 'transactions_fts']
    for fts in fts_tables:
        try:
            conn.execute(f"INSERT INTO {fts}({fts}) VALUES('rebuild')")
            print(f'  {fts}: OK')
        except Exception as e:
            print(f'  {fts}: FAILED — {e}')
    conn.commit()

    # Re-enable FK checks
    conn.execute("PRAGMA foreign_keys=ON")

    # Save ID counters
    registry.save_counters()

    elapsed = time.time() - start
    print()
    print(f'Compiler done in {elapsed:.1f}s')
    total_new_props = poi_new_props + gw_new_props
    print(f'  Properties:    {prop_count + total_new_props:,} ({poi_new_props:,} POI, {gw_new_props:,} GW)')
    print(f'  Transactions:  {tx_count:,}')
    print(f'  Groups:        {len(group_data):,}')
    print(f'  Contacts:      {len(contact_data):,}')
    print(f'  Parties:       {party_count:,}')
    print(f'  POIs:          {poi_count:,}')
    print(f'  GW Assessments: {gw_assessment_count:,} ({gw_enriched:,} enriched)')
