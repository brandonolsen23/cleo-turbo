"""
Writer — reads Clean Records and populates SQLite derived tables.

Three passes:
  1. Groups: extract party names → normalize → assign GRP_ IDs
  2. Contacts: extract contact names → fingerprint → assign CON_ IDs
  3. Properties + Transactions + Transaction Parties: link everything

CRM tables are never touched. Derived tables are truncated and rebuilt.
"""

import json
import os
import time

from .reader import (iter_clean_records, iter_osm_records, iter_gw_records,
                     read_parcel, count_clean_records, count_osm_records, count_gw_records)
from .reconciler import IDRegistry, make_name_fingerprint, normalize_group_name, strip_leading_honorifics
from ..database.schema import drop_derived_tables, create_all_tables
from ..database.asset_classes import seed_asset_classes, map_property_type_to_asset_class
from ..database.tenant_categories import seed_tenant_categories
from ..analytics.groups import refresh_group_analytics
from ..address.decompose import decompose_simple as _decompose_simple
from ..address.formatter import format_display as _format_display


_REVERSE_GEOCODE_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'clean-data', 'reverse_geocode'
)


def _read_reverse_geocode_cache(lat, lng):
    """Look up the reverse-geocode cache by lat,lng. Returns the cached
    JSON dict (with .result possibly None) or None if no cache file."""
    if lat is None or lng is None:
        return None
    key = f'{round(float(lat), 6):.6f},{round(float(lng), 6):.6f}'
    path = os.path.join(_REVERSE_GEOCODE_DIR, f'{key}.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _format_reverse_geocode(rev):
    """Build a single street-address string from a cached reverseGeocode
    payload. Mirrors scripts/backfill_poi_reverse_geocode.format_address."""
    if not rev:
        return ''
    match = (rev.get('match_addr') or '').strip()
    if match:
        return match
    street = (rev.get('street') or '').strip()
    tail = ', '.join(p for p in (rev.get('city'), rev.get('state'), rev.get('postal')) if p)
    return f'{street}, {tail}'.strip(', ').strip() if tail else street


def _snapshot_pre_compile(conn):
    """Capture current state for post-compile reconciliation report."""
    snapshot = {'groups': {}, 'contacts': {}, 'merge_targets': {}}
    try:
        for r in conn.execute("SELECT id, display_name, status, property_count FROM groups"):
            snapshot['groups'][r[0]] = {
                'display_name': r[1], 'status': r[2], 'property_count': r[3]
            }
        for r in conn.execute("SELECT id, display_name FROM contacts"):
            snapshot['contacts'][r[0]] = {'display_name': r[1]}
        for r in conn.execute(
            "SELECT source_group_id, target_group_id FROM group_merges WHERE unmerged_at IS NULL"
        ):
            snapshot['merge_targets'][r[0]] = r[1]
    except Exception:
        pass  # Tables might not exist on first run
    return snapshot


def _generate_reconciliation_report(conn, pre):
    """Compare post-compile state against pre-compile snapshot."""
    report = {
        'disappeared_groups': [],
        'new_groups': [],
        'orphaned_merges': [],
        'property_count_swings': [],
        'orphaned_crm_refs': [],
    }

    post_groups = {}
    for r in conn.execute("SELECT id, display_name, status, property_count FROM groups"):
        post_groups[r[0]] = {
            'display_name': r[1], 'status': r[2], 'property_count': r[3]
        }

    # Disappeared groups (were active, no longer exist)
    for gid, info in pre['groups'].items():
        if gid not in post_groups and info['status'] != 'merged':
            report['disappeared_groups'].append({
                'id': gid, 'name': info['display_name'],
                'was_property_count': info['property_count']
            })

    # New groups
    for gid, info in post_groups.items():
        if gid not in pre['groups']:
            report['new_groups'].append({
                'id': gid, 'name': info['display_name'],
                'property_count': info['property_count']
            })

    # Property count swings (>50% change on groups with 3+ properties)
    for gid in set(pre['groups']) & set(post_groups):
        old_count = pre['groups'][gid]['property_count'] or 0
        new_count = post_groups[gid]['property_count'] or 0
        if old_count >= 3 and abs(new_count - old_count) / max(old_count, 1) > 0.5:
            report['property_count_swings'].append({
                'id': gid, 'name': post_groups[gid]['display_name'],
                'old_count': old_count, 'new_count': new_count
            })

    # Orphaned merges (target doesn't exist)
    for src, tgt in pre['merge_targets'].items():
        if tgt not in post_groups:
            report['orphaned_merges'].append({
                'source_id': src, 'target_id': tgt,
                'source_name': post_groups.get(src, {}).get('display_name', '(gone)')
            })

    # Check CRM integrity
    checks = [
        ("deals", "group_id", "groups"),
        ("deals", "property_id", "properties"),
        ("group_contacts", "group_id", "groups"),
        ("group_contacts", "contact_id", "contacts"),
        ("group_notes", "group_id", "groups"),
        ("contact_notes", "contact_id", "contacts"),
    ]
    for table, col, ref_table in checks:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} t LEFT JOIN {ref_table} r ON t.{col} = r.id "
                f"WHERE t.{col} IS NOT NULL AND r.id IS NULL"
            ).fetchone()[0]
            if count > 0:
                report['orphaned_crm_refs'].append({
                    'table': table, 'column': col,
                    'ref_table': ref_table, 'count': count
                })
        except Exception:
            pass

    return report


def _print_reconciliation_report(report):
    """Print the reconciliation report to stdout."""
    print()
    print('=' * 60)
    print('Reconciliation Report')
    print('=' * 60)

    if report['disappeared_groups']:
        print(f"  DISAPPEARED GROUPS: {len(report['disappeared_groups'])}")
        for g in report['disappeared_groups'][:10]:
            print(f"    {g['id']} \"{g['name']}\" (had {g['was_property_count']} properties)")
    else:
        print('  Disappeared groups: 0')

    if report['new_groups']:
        new_with_props = [g for g in report['new_groups'] if (g['property_count'] or 0) > 0]
        print(f"  New groups: {len(report['new_groups'])} ({len(new_with_props)} with properties)")
    else:
        print('  New groups: 0')

    if report['orphaned_merges']:
        print(f"  WARNING — ORPHANED MERGES: {len(report['orphaned_merges'])}")
        for m in report['orphaned_merges']:
            print(f"    {m['source_id']} → {m['target_id']} (target missing)")
    else:
        print('  Orphaned merges: 0')

    if report['property_count_swings']:
        print(f"  Property count swings (>50%): {len(report['property_count_swings'])}")
        for s in report['property_count_swings'][:10]:
            print(f"    {s['id']} \"{s['name']}\": {s['old_count']} → {s['new_count']}")

    if report['orphaned_crm_refs']:
        print(f"  WARNING — ORPHANED CRM REFERENCES:")
        for o in report['orphaned_crm_refs']:
            print(f"    {o['table']}.{o['column']} → {o['ref_table']}: {o['count']} orphaned rows")
    else:
        print('  CRM integrity: OK')

    print('=' * 60)


def run_compiler(conn):
    """Run the full Compiler: read clean-data/, write to SQLite."""

    print('Cleo Compiler')
    print()

    # Count records
    total = count_clean_records()
    print(f'Clean Records to process: {total:,}')
    print()

    # Ensure system tables exist (id_mappings, etc.) before loading registry
    create_all_tables(conn)

    # Initialize ID registry BEFORE dropping tables — reads from id_mappings (system table)
    print('Loading ID registry...')
    registry = IDRegistry(conn)
    registry.load()

    # Snapshot current state for reconciliation report
    pre_compile = _snapshot_pre_compile(conn)

    # Disable FK checks during bulk load (properties inserted after transactions)
    conn.execute("PRAGMA foreign_keys=OFF")

    # Drop and recreate derived tables (CRM tables preserved)
    print('Dropping derived tables...')
    drop_derived_tables(conn)
    print('Recreating tables...')
    create_all_tables(conn)

    # Seed asset class taxonomy
    seed_asset_classes(conn)
    seed_tenant_categories(conn)

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
    # Pass 1b: Inject user-created groups from group_overrides
    # ================================================================
    overrides = conn.execute(
        "SELECT group_id, display_name, normalized_name FROM group_overrides"
    ).fetchall()
    if overrides:
        print(f'  Injecting {len(overrides)} user-created group(s)...')
        for ov in overrides:
            gid, display, normalized = ov[0], ov[1], ov[2]
            if normalized not in group_data:
                group_data[normalized] = {
                    'id': gid,
                    'display_name': display,
                    'normalized_name': normalized,
                    'names': set(),
                    'tx_count': 0,
                    'property_arns': set(),
                }
                conn.execute(
                    "INSERT OR IGNORE INTO groups (id, display_name, normalized_name, status, "
                    "property_count, transaction_count) VALUES (?, ?, ?, 'pool', 0, 0)",
                    (gid, display, normalized)
                )
            else:
                if group_data[normalized]['id'] != gid:
                    print(f'    WARNING: override {gid} vs data {group_data[normalized]["id"]} for {normalized}')
        conn.commit()

    # ================================================================
    # Pass 1c: Apply group and contact field overrides from CRM
    # ================================================================
    # Group field overrides (status, hq_address, website, hubspot_id)
    gfo_rows = conn.execute(
        "SELECT group_id, status, hq_address, website, hubspot_id FROM group_field_overrides"
    ).fetchall()
    if gfo_rows:
        gfo_applied = 0
        for r in gfo_rows:
            gid = r[0]
            updates = []
            params = []
            if r[1] is not None:
                updates.append("status = ?")
                params.append(r[1])
            if r[2] is not None:
                updates.append("hq_address = ?")
                params.append(r[2])
            if r[3] is not None:
                updates.append("website = ?")
                params.append(r[3])
            if r[4] is not None:
                updates.append("hubspot_id = ?")
                params.append(r[4])
            if updates:
                params.append(gid)
                conn.execute(
                    f"UPDATE groups SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                gfo_applied += 1
        conn.commit()
        if gfo_applied:
            print(f'  Applied {gfo_applied} group field override(s)')

    # ================================================================
    # Apply active group merges (from CRM layer)
    # ================================================================
    active_merges = conn.execute(
        "SELECT source_group_id, target_group_id FROM group_merges WHERE unmerged_at IS NULL"
    ).fetchall()
    if active_merges:
        print(f'  Applying {len(active_merges)} active group merge(s)...')
        # Build a redirect map (follow chains to ultimate target)
        redirect = {}
        for m in active_merges:
            redirect[m[0]] = m[1]
        # Resolve chains: if A→B and B→C, make A→C
        for src in list(redirect.keys()):
            target = redirect[src]
            visited = {src}
            while target in redirect and target not in visited:
                visited.add(target)
                target = redirect[target]
            redirect[src] = target

        orphaned_merges = []
        for src, tgt in redirect.items():
            # Verify target exists in groups table
            target_exists = conn.execute("SELECT id FROM groups WHERE id = ?", (tgt,)).fetchone()
            if not target_exists:
                orphaned_merges.append((src, tgt))
                continue

            # Copy known names from source to target
            conn.execute(
                "INSERT OR IGNORE INTO group_names (group_id, name, normalized, source_id) "
                "SELECT ?, name, normalized, source_id FROM group_names WHERE group_id = ?",
                (tgt, src)
            )
            # Mark source as merged
            conn.execute("UPDATE groups SET status = 'merged' WHERE id = ?", (src,))

        # Also update the group_data dict so Pass 2/3 use the right group IDs
        for norm, g in group_data.items():
            if g['id'] in redirect and g['id'] not in dict(orphaned_merges):
                g['id'] = redirect[g['id']]

        if orphaned_merges:
            print(f'  WARNING: {len(orphaned_merges)} orphaned merge(s) — target group does not exist:')
            for src, tgt in orphaned_merges:
                print(f'    {src} → {tgt} (target missing)')

        conn.commit()
        print(f'  Applied merges: {len(redirect) - len(orphaned_merges)} source groups redirected')

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

                # Split name into first/last after stripping leading honorifics
                # so "Dr Harry Aronowicz" parses to first=Harry, last=Aronowicz
                # rather than first=Dr, last="Harry Aronowicz".
                parts = strip_leading_honorifics(name.upper().split())
                # Recover original casing from the source name where possible.
                src_tokens = name.split()
                if len(src_tokens) > len(parts):
                    src_tokens = src_tokens[len(src_tokens) - len(parts):]
                first = src_tokens[0] if src_tokens else ''
                last = ' '.join(src_tokens[1:]) if len(src_tokens) > 1 else ''

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

    # Apply contact field overrides (email, mobile, phone, job_title, etc.)
    cfo_rows = conn.execute(
        "SELECT contact_id, email, mobile, phone, job_title, contact_type, status "
        "FROM contact_field_overrides"
    ).fetchall()
    if cfo_rows:
        cfo_applied = 0
        for r in cfo_rows:
            cid = r[0]
            updates = []
            params = []
            fields = [('email', r[1]), ('mobile', r[2]), ('phone', r[3]),
                      ('job_title', r[4]), ('contact_type', r[5]), ('status', r[6])]
            for col, val in fields:
                if val is not None:
                    updates.append(f"{col} = ?")
                    params.append(val)
            if updates:
                params.append(cid)
                conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                cfo_applied += 1
        conn.commit()
        if cfo_applied:
            print(f'  Applied {cfo_applied} contact field override(s)')

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
        geocoded_coords = rec.get('geocoded_coords')  # Mapbox fallback coords

        # Extract property type from source_folder (e.g., "Peel_Region/industrial/p033" → "industrial")
        # Skip non-informative sources:
        #   - _daily scraper folders use timestamps (e.g., "_daily/2026-04-09_113935/p001")
        #   - "all" folders from bulk scraper with sf3="" don't encode a real type
        source_folder = rec.get('source_folder', '')
        folder_parts = source_folder.split('/') if source_folder else []
        if len(folder_parts) >= 2 and not folder_parts[0].startswith('_') and folder_parts[1] != 'all':
            property_type = folder_parts[1]
        else:
            property_type = ''

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
                    'geocoded_coords': geocoded_coords,
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
            "photos_json, source_folder, source_position) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, "
            "?, ?, ?, ?, "
            "?, ?, ?, ?, "
            "?, ?, ?)",
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
             rec.get('source_folder', ''),
             rec.get('source_position'))
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

            # Insert one row per party (group)
            for party in parties:
                pname = party.get('name', '').strip()
                if not pname:
                    continue
                # "Named Individual(s)" is Realtrack's placeholder for a
                # suppressed-name private party — the side IS real, the name
                # is just not disclosed. Record the row so the side exists
                # relationally, but don't attach to any group (gid = None).
                # Dropping these silently broke every downstream analysis
                # that needed full transaction-side coverage.
                if pname == 'Named Individual(s)':
                    gid = None
                else:
                    norm = normalize_group_name(pname)
                    gid = group_data[norm]['id'] if norm in group_data else None

                conn.execute(
                    "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, "
                    "party_name, contact_title, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, None, gid, side, pname, '', phone)
                )
                party_count += 1

            # Insert one row per contact (separate from parties)
            for contact in contacts:
                cname = contact.get('name', '').strip()
                if not cname:
                    continue
                fp = make_name_fingerprint(cname)
                cid = contact_data[fp]['id'] if fp in contact_data else None

                conn.execute(
                    "INSERT INTO transaction_parties (source_id, contact_id, group_id, side, "
                    "party_name, contact_title, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, cid, None, side, '', contact.get('title', ''), phone)
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

            # Fallback: use Mapbox geocoded coordinates when no parcel centroid
            if lat is None and lng is None and pd.get('geocoded_coords'):
                geo = pd['geocoded_coords']
                lat = geo.get('lat')
                lng = geo.get('lng')

            asset_class = map_property_type_to_asset_class(pd['property_type'])
            conn.execute(
                "INSERT INTO properties (id, arn, display_address, city, region, postal, acreage, "
                "legal_description, current_owner_name, current_owner_group_id, most_recent_source_id, "
                "most_recent_sale_date, most_recent_sale_price, most_recent_sale_source, transaction_count, "
                "primary_property_type, asset_class, lat, lng, parcel_geojson) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pd['id'], arn, pd['display_address'], pd['city'], pd['region'], pd['postal'],
                 pd['acreage'], pd['legal_description'], pd['owner_name'], pd['owner_group_id'],
                 pd['source_id'], pd['sale_date'], pd['sale_price'], 'RT', pd['tx_count'],
                 pd['property_type'], asset_class, lat, lng, parcel_geojson)
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

                    # Build display address from POI address fields via shared formatter
                    addr = poi.get('address', {})
                    raw_street = ''
                    parts = []
                    if addr.get('housenumber'):
                        parts.append(addr['housenumber'])
                    if addr.get('street'):
                        parts.append(addr['street'])
                    raw_street = ' '.join(parts)
                    if raw_street:
                        osm_components = _decompose_simple(raw_street)
                        display_address = _format_display(osm_components)
                    else:
                        display_address = ''

                    conn.execute(
                        "INSERT OR IGNORE INTO properties (id, arn, display_address, city, region, postal, "
                        "transaction_count, primary_property_type, asset_class, lat, lng, parcel_geojson) "
                        "VALUES (?, ?, ?, ?, '', '', 0, 'retail', 'retail', ?, ?, ?)",
                        (pid, arn, display_address, addr.get('city', ''),
                         p_lat, p_lng, parcel_geojson)
                    )

                    property_data[arn] = {'id': pid, 'arn': arn}
                    property_id = pid
                    poi_new_props += 1

            # Build display address for POI record via shared formatter
            addr = poi.get('address', {})
            poi_parts = []
            if addr.get('housenumber'):
                poi_parts.append(addr['housenumber'])
            if addr.get('street'):
                poi_parts.append(addr['street'])
            raw_poi_street = ' '.join(poi_parts)
            if raw_poi_street:
                poi_components = _decompose_simple(raw_poi_street)
                poi_address = _format_display(poi_components)
            else:
                poi_address = ''

            building = poi.get('building') or {}
            building_geojson = json.dumps(building['polygon']) if building.get('polygon') else None

            # When OSM gave no addr:* tags, fall back to the reverse-geocode
            # cache populated by scripts/backfill_poi_reverse_geocode.py so
            # we don't lose work across compiler re-runs.
            address_source = 'osm' if poi_address else None
            poi_city = addr.get('city', '')
            if not poi_address and lat is not None and lng is not None:
                cached = _read_reverse_geocode_cache(lat, lng)
                if cached is not None:
                    rev = cached.get('result')
                    if rev:
                        poi_address = _format_reverse_geocode(rev)
                        if not poi_city:
                            poi_city = rev.get('city', '') or ''
                        address_source = 'reverse_geocoded'
                    else:
                        address_source = 'reverse_geocode_failed'

            conn.execute(
                "INSERT OR IGNORE INTO pois (id, source, brand, category, name, lat, lng, "
                "address, city, phone, website, property_id, arn, "
                "cuisine, operator, facebook, instagram, drive_through, "
                "osm_id, building_geojson, approx_sqft, address_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (poi_id, poi.get('source', 'osm'),
                 poi.get('tracked_brand') or poi.get('brand', ''),
                 poi.get('category', ''), poi.get('name', ''),
                 lat, lng, poi_address, poi_city,
                 poi.get('phone', ''), poi.get('website', ''),
                 property_id, arn,
                 poi.get('cuisine', ''), poi.get('operator', ''),
                 poi.get('facebook', ''), poi.get('instagram', ''),
                 poi.get('drive_through', ''),
                 poi.get('osm_id', ''), building_geojson,
                 building.get('approx_sqft'),
                 address_source)
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

                    # Gap-fill only: don't overwrite RT display_address with GW
                    display_addr = gw_prop.get('display_address', '')
                    if display_addr:
                        updates.append("display_address = COALESCE(NULLIF(display_address, ''), ?)")
                        params.append(display_addr)

                    # Gap-fill city and postal too — don't overwrite RT values
                    city = gw_prop.get('city', '')
                    if city:
                        updates.append("city = COALESCE(NULLIF(city, ''), ?)")
                        params.append(city)

                    postal = gw_prop.get('postal', '')
                    if postal:
                        updates.append("postal = COALESCE(NULLIF(postal, ''), ?)")
                        params.append(postal)

                    # Municipality from first assessment
                    assessments = gw.get('assessments', [])
                    if assessments:
                        municipality = assessments[0].get('municipality', '')
                        if municipality:
                            updates.append("gw_municipality = ?")
                            params.append(municipality)

                    # Backfill lat/lng from parcel if missing
                    parcel = read_parcel(resolved_arn)
                    if parcel and parcel.get('centroid'):
                        p_lat = parcel['centroid'][0]
                        p_lng = parcel['centroid'][1]
                        if p_lat and p_lng:
                            updates.append("lat = COALESCE(lat, ?)")
                            params.append(p_lat)
                            updates.append("lng = COALESCE(lng, ?)")
                            params.append(p_lng)
                            parcel_geojson = json.dumps(parcel['geometry']) if parcel.get('geometry') else None
                            if parcel_geojson:
                                updates.append("parcel_geojson = COALESCE(parcel_geojson, ?)")
                                params.append(parcel_geojson)

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

                    gw_property_type = gw.get('registry', {}).get('property_type', '').lower() or 'commercial'
                    gw_asset_class = map_property_type_to_asset_class(gw_property_type)
                    conn.execute(
                        "INSERT OR IGNORE INTO properties (id, arn, display_address, city, postal, "
                        "current_owner_name, transaction_count, primary_property_type, asset_class, "
                        "gw_municipality, lat, lng, parcel_geojson) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
                        (pid, resolved_arn,
                         gw_prop.get('display_address', ''),
                         gw_prop.get('city', ''),
                         gw_prop.get('postal', ''),
                         gw_owner.get('name', ''),
                         gw_property_type,
                         gw_asset_class,
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
    # Pass 6: Link orphan transactions via PIN bridge
    # ================================================================
    #
    # Some RT transactions have incorrect ARNs (typos in source data) but
    # valid PINs. Now that gw_assessments is populated, we can look up the
    # correct ARN via PIN and link these orphaned transactions to properties.
    print('Pass 6: Linking orphan transactions via PIN...')

    orphans = conn.execute(
        "SELECT t.source_id, t.pin, t.sale_date, t.sale_price, t.display_address, "
        "t.city, t.region, t.postal "
        "FROM transactions t "
        "WHERE t.property_id IS NULL "
        "AND t.pin IS NOT NULL AND t.pin != ''"
    ).fetchall()

    pin_linked = 0
    pin_cache = {}  # pin -> (property_id, arn) to avoid repeated queries

    for orphan in orphans:
        o_source_id, o_pin, o_date, o_price, o_addr, o_city, o_region, o_postal = orphan

        if o_pin in pin_cache:
            result = pin_cache[o_pin]
        else:
            # Look up this PIN in gw_assessments to find the correct ARN
            gw_row = conn.execute(
                "SELECT arn, property_id FROM gw_assessments "
                "WHERE pin = ? AND arn != '' AND property_id IS NOT NULL "
                "LIMIT 1",
                (o_pin,)
            ).fetchone()
            if gw_row:
                result = (gw_row[1], gw_row[0])  # (property_id, arn)
            else:
                result = None
            pin_cache[o_pin] = result

        if not result:
            continue

        prop_id, correct_arn = result

        # Link the transaction
        conn.execute(
            "UPDATE transactions SET property_id = ?, arn = ? WHERE source_id = ?",
            (prop_id, correct_arn, o_source_id)
        )
        pin_linked += 1

    # Recalculate transaction_count and most_recent_sale for affected properties
    if pin_linked > 0:
        affected_props = set(v[0] for v in pin_cache.values() if v)
        for prop_id in affected_props:
            # Recount transactions
            tx_count = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE property_id = ?",
                (prop_id,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE properties SET transaction_count = ? WHERE id = ?",
                (tx_count, prop_id)
            )

            # Find most recent RT sale for this property
            latest = conn.execute(
                "SELECT sale_date, sale_price FROM transactions "
                "WHERE property_id = ? AND sale_date IS NOT NULL AND sale_date != '' "
                "AND sale_price IS NOT NULL "
                "ORDER BY sale_date DESC LIMIT 1",
                (prop_id,)
            ).fetchone()
            if latest:
                rt_date, rt_price = latest
                # Update only if RT sale is newer than what's there (including GW sales)
                conn.execute(
                    "UPDATE properties SET most_recent_sale_price = ?, "
                    "most_recent_sale_date = ?, most_recent_sale_source = 'RT' "
                    "WHERE id = ? AND (most_recent_sale_date IS NULL OR most_recent_sale_date < ?)",
                    (rt_price, rt_date, prop_id, rt_date)
                )

        conn.commit()

    print(f'  Orphan transactions with PIN: {len(orphans):,}')
    print(f'  Linked via PIN bridge: {pin_linked:,}')

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

    # ================================================================
    # Brand Registry — aggregate POI brands for the brand management UI
    # ================================================================
    print('Building brand registry...')
    brand_rows = conn.execute("""
        SELECT brand, category, COUNT(*) as cnt
        FROM pois
        WHERE brand != ''
        GROUP BY brand
    """).fetchall()

    # Load curated brands set from CSV for is_curated flag
    import csv as _csv
    import os as _os_brands
    brands_csv_path = _os_brands.path.join(
        _os_brands.path.dirname(__file__), '..', '..', 'engines', 'osm', 'brands.csv'
    )
    curated_brands = set()
    if _os_brands.path.isfile(brands_csv_path):
        with open(brands_csv_path, newline='', encoding='utf-8') as _f:
            for _row in _csv.DictReader(_f):
                _name = _row.get('Brand Name', '').strip()
                if _name:
                    curated_brands.add(_name)

    brand_reg_count = 0
    for brand, category, count in brand_rows:
        is_curated = 1 if brand in curated_brands else 0
        conn.execute(
            "INSERT OR REPLACE INTO brand_registry (brand, category, poi_count, is_curated) "
            "VALUES (?, ?, ?, ?)",
            (brand, category or '', count, is_curated)
        )
        brand_reg_count += 1

    conn.commit()
    print(f'  Brand registry: {brand_reg_count:,} brands ({sum(1 for b in brand_rows if b[0] in curated_brands):,} curated)')

    # Re-enable FK checks
    conn.execute("PRAGMA foreign_keys=ON")

    # Save ID counters
    registry.save_counters()

    # ================================================================
    # Refresh Group Analytics (materialized metrics)
    # ================================================================
    print('Refreshing group analytics...')
    analytics_count = refresh_group_analytics(conn)

    # ================================================================
    # Atom-level fingerprinting — foundation for portfolio discovery
    # ================================================================
    from cleo.atoms.fingerprint import run_fingerprint_pass
    run_fingerprint_pass(conn)

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
    print(f'  Group Analytics: {analytics_count:,}')

    # ================================================================
    # Reconciliation Report
    # ================================================================
    report = _generate_reconciliation_report(conn, pre_compile)
    _print_reconciliation_report(report)

    # Save report to JSON for tooling
    import os as _os
    report_path = _os.path.join(_os.path.dirname(__file__), '..', '..', 'data', 'reconciliation_report.json')
    try:
        _os.makedirs(_os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f'\n  Report saved to {report_path}')
    except Exception as e:
        print(f'\n  Could not save report: {e}')
