"""
GeoWarehouse Watcher -- monitors Downloads for new HTML files and auto-processes.

Watches ~/Downloads/GeoWarehouse/gw-ingest-data/ for new geowarehouse-*.html files.
When detected, batches them and runs the full pipeline:
  ingest → parse → normalize → resolve → compile → database update

Usage:
    python engines/gw/watcher.py              # Start daemon
    python engines/gw/watcher.py --once       # Process pending files and exit
    python engines/gw/watcher.py --interval 5 # Custom batch interval (seconds)
"""

import json
import os
import shutil
import sys
import time
import argparse
import logging

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))

from gw.parse import parse_gw_html, _extract_timestamp
from gw.normalize import normalize_record
from gw.resolve_parcels import resolve_arn

from parcel_resolver.agmaps import AgMapsClient, TokenExpiredError
from parcel_resolver.token import load_token, refresh_token

logging.basicConfig(level=logging.INFO, format='%(asctime)s [GW] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('gw-watcher')

WATCH_DIR = os.path.join(os.path.expanduser('~'), 'Downloads', 'GeoWarehouse', 'gw-ingest-data')
HTML_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'html')
PARSED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parsed')
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'normalized')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parcel_links')
CLEAN_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')

for d in [HTML_DIR, PARSED_DIR, NORMALIZED_DIR, PARCEL_LINKS_DIR, CLEAN_DIR]:
    os.makedirs(d, exist_ok=True)


def find_pending_files():
    """Find new geowarehouse-*.html files not yet ingested."""
    if not os.path.isdir(WATCH_DIR):
        return []
    existing = set(os.listdir(HTML_DIR))
    return [
        f for f in os.listdir(WATCH_DIR)
        if f.startswith('geowarehouse-') and f.endswith('.html') and f not in existing
    ]


def process_batch(files):
    """Process a batch of new HTML files through the full pipeline."""
    if not files:
        return

    log.info(f'Processing batch of {len(files)} file(s)')

    # Step 1: Copy to pipeline
    for fname in files:
        shutil.copy2(os.path.join(WATCH_DIR, fname), os.path.join(HTML_DIR, fname))

    # Step 2: Parse — dedup by PIN within batch
    pin_best = {}
    parsed_records = []

    for fname in files:
        try:
            with open(os.path.join(HTML_DIR, fname), encoding='utf-8') as f:
                html = f.read()
            result = parse_gw_html(html, fname)
            if result is None:
                continue

            pin = result.get('pin', '').strip()
            ts = _extract_timestamp(fname)

            if pin:
                if pin not in pin_best or ts > pin_best[pin][0]:
                    pin_best[pin] = (ts, result)
            else:
                parsed_records.append(result)
        except Exception as e:
            log.error(f'Parse error {fname}: {e}')

    parsed_records.extend(rec for _, rec in sorted(pin_best.values(), key=lambda x: x[1].get('pin', '')))

    if not parsed_records:
        log.info('No detail pages in batch')
        return

    # Determine next GW ID
    existing_ids = [
        f for f in os.listdir(PARSED_DIR)
        if f.endswith('.json') and not f.startswith('_')
    ]
    max_id = 0
    for eid in existing_ids:
        try:
            num = int(eid.replace('GW', '').replace('.json', ''))
            max_id = max(max_id, num)
        except ValueError:
            pass

    # Step 2b: Assign IDs and write parsed
    new_records = []
    for i, record in enumerate(parsed_records, start=max_id + 1):
        gw_id = f'GW{i:05d}'
        record['gw_id'] = gw_id
        with open(os.path.join(PARSED_DIR, f'{gw_id}.json'), 'w') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        new_records.append((gw_id, record))

    # Step 3: Normalize
    normalized_records = []
    for gw_id, record in new_records:
        normalized = normalize_record(record)
        with open(os.path.join(NORMALIZED_DIR, f'{gw_id}.json'), 'w') as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        normalized_records.append((gw_id, normalized))

    # Step 4: Resolve parcels
    token = load_token()
    if not token:
        try:
            token = refresh_token()
        except Exception as e:
            log.error(f'Could not get token: {e}')
            token = None

    client = AgMapsClient(token) if token else None

    for gw_id, normalized in normalized_records:
        resolutions = []
        for assessment in normalized.get('assessments', []):
            arn_api = assessment.get('arn_api', '')
            if client:
                try:
                    parcel_file, method = resolve_arn(arn_api, client)
                except TokenExpiredError:
                    token = refresh_token()
                    client = AgMapsClient(token)
                    parcel_file, method = resolve_arn(arn_api, client)
            else:
                from parcel_resolver.cache import cache_has
                if arn_api and cache_has(arn_api):
                    parcel_file, method = f'{arn_api}.json', 'arn_cache'
                else:
                    parcel_file, method = None, 'no_token'

            resolutions.append({'arn': arn_api, 'method': method, 'parcel_file': parcel_file})

        link = {'gw_id': gw_id, 'pin': normalized.get('pin_api', ''), 'resolutions': resolutions}
        with open(os.path.join(PARCEL_LINKS_DIR, f'{gw_id}.json'), 'w') as f:
            json.dump(link, f, indent=2)

    if client:
        client.close()

    # Step 5: Compile clean records
    from gw.compile import load_json, compile_record

    for gw_id, _ in new_records:
        fname = f'{gw_id}.json'
        parsed = load_json(PARSED_DIR, fname)
        normalized = load_json(NORMALIZED_DIR, fname)
        parcel_link = load_json(PARCEL_LINKS_DIR, fname)
        if parsed and normalized:
            record = compile_record(parsed, normalized, parcel_link)
            with open(os.path.join(CLEAN_DIR, fname), 'w') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

    log.info(f'Processed {len(new_records)} record(s): {", ".join(gw_id for gw_id, _ in new_records)}')

    # Step 6: Incremental DB update
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from cleo.database.connection import get_connection
        from cleo.compiler.reader import read_parcel
        from cleo.compiler.reconciler import IDRegistry
        import json as _json

        conn = get_connection()
        registry = IDRegistry(conn)
        registry.load()

        for gw_id, _ in new_records:
            fname = f'{gw_id}.json'
            with open(os.path.join(CLEAN_DIR, fname)) as f:
                gw = _json.load(f)

            parcel_info = gw.get('parcel', {})
            resolved_arn = parcel_info.get('resolved_arn')
            gw_prop = gw.get('property', {})
            gw_owner = gw.get('owner', {})

            if resolved_arn:
                # Check if property exists
                row = conn.execute("SELECT id FROM properties WHERE arn = ?", (resolved_arn,)).fetchone()
                if row:
                    # Enrich existing
                    updates = []
                    params = []
                    if gw_owner.get('name'):
                        updates.append("current_owner_name = ?")
                        params.append(gw_owner['name'])
                    if gw_prop.get('display_address'):
                        updates.append("display_address = ?")
                        params.append(gw_prop['display_address'])
                    if gw_prop.get('city'):
                        updates.append("city = ?")
                        params.append(gw_prop['city'])
                    if gw_prop.get('postal'):
                        updates.append("postal = ?")
                        params.append(gw_prop['postal'])
                    if updates:
                        params.append(row[0])
                        conn.execute(f"UPDATE properties SET {', '.join(updates)} WHERE id = ?", params)
                    property_id = row[0]
                else:
                    # Create new property
                    pid = registry.get_or_create_property_id(resolved_arn)
                    parcel = read_parcel(resolved_arn)
                    parcel_geojson = _json.dumps(parcel['geometry']) if parcel and parcel.get('geometry') else None
                    p_lat = parcel['centroid'][0] if parcel and parcel.get('centroid') else None
                    p_lng = parcel['centroid'][1] if parcel and parcel.get('centroid') else None

                    conn.execute(
                        "INSERT OR IGNORE INTO properties (id, arn, display_address, city, postal, "
                        "current_owner_name, transaction_count, primary_property_type, asset_class, "
                        "lat, lng, parcel_geojson) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, 'commercial', 'retail', ?, ?, ?)",
                        (pid, resolved_arn, gw_prop.get('display_address', ''),
                         gw_prop.get('city', ''), gw_prop.get('postal', ''),
                         gw_owner.get('name', ''), p_lat, p_lng, parcel_geojson)
                    )
                    property_id = pid

                # Insert assessments
                for idx, assessment in enumerate(gw.get('assessments', [])):
                    a_id = gw_id if idx == 0 else f'{gw_id}_{idx + 1}'
                    conn.execute(
                        "INSERT OR REPLACE INTO gw_assessments (id, gw_id, property_id, arn, pin, "
                        "assessed_value, valuation_date, zoning, property_code, property_description, "
                        "ownership_type, frontage_ft, depth_ft, site_area_sqft, acreage, "
                        "owner_name, owner_mailing, legal_description, source_file) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (a_id, gw_id, property_id, assessment.get('arn_api', ''), gw.get('pin', ''),
                         assessment.get('assessed_value'), assessment.get('valuation_date', ''),
                         assessment.get('zoning', ''), assessment.get('property_code', ''),
                         assessment.get('property_description', ''),
                         gw.get('registry', {}).get('ownership_type', ''),
                         assessment.get('frontage_ft'), assessment.get('depth_ft'),
                         assessment.get('site_area_sqft'), assessment.get('acreage'),
                         assessment.get('owner_names_mpac', ''),
                         assessment.get('owner_mailing_address', ''),
                         assessment.get('legal_description', ''),
                         gw.get('source_file', ''))
                    )

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
                # Only if the GW sale is newer than what's already on the property
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

                # Link orphan RT transactions via PIN bridge
                # If this GW record has a PIN, check for unlinked transactions with the same PIN
                gw_pin = gw.get('pin', '')
                if property_id and gw_pin and resolved_arn:
                    orphans = conn.execute(
                        "SELECT source_id, sale_date, sale_price FROM transactions "
                        "WHERE property_id IS NULL AND pin = ?",
                        (gw_pin,)
                    ).fetchall()
                    for orphan in orphans:
                        conn.execute(
                            "UPDATE transactions SET property_id = ?, arn = ? "
                            "WHERE source_id = ?",
                            (property_id, resolved_arn, orphan[0])
                        )
                        log.info(f'  Linked orphan transaction {orphan[0]} to {property_id} via PIN {gw_pin}')

                    if orphans:
                        # Recalculate transaction_count
                        tx_count = conn.execute(
                            "SELECT COUNT(*) FROM transactions WHERE property_id = ?",
                            (property_id,)
                        ).fetchone()[0]
                        conn.execute(
                            "UPDATE properties SET transaction_count = ? WHERE id = ?",
                            (tx_count, property_id)
                        )
                        # Check if any orphan has a newer sale than what's on the property
                        for orphan in orphans:
                            o_date = orphan[1] or ''
                            o_price = orphan[2]
                            if o_date and o_price:
                                conn.execute(
                                    "UPDATE properties SET most_recent_sale_price = ?, "
                                    "most_recent_sale_date = ?, most_recent_sale_source = 'RT' "
                                    "WHERE id = ? AND (most_recent_sale_date IS NULL OR most_recent_sale_date < ?)",
                                    (o_price, o_date, property_id, o_date)
                                )

        conn.commit()
        registry.save_counters()
        conn.close()
        log.info('Database updated')
    except Exception as e:
        log.error(f'DB update failed: {e}')


def run_daemon(interval=10):
    """Run as a daemon, checking for new files periodically."""
    log.info(f'Watching {WATCH_DIR} (interval: {interval}s)')
    log.info('Press Ctrl+C to stop')

    while True:
        try:
            pending = find_pending_files()
            if pending:
                process_batch(pending)
        except KeyboardInterrupt:
            log.info('Stopped')
            break
        except Exception as e:
            log.error(f'Error: {e}')

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info('Stopped')
            break


def main():
    parser = argparse.ArgumentParser(description='GeoWarehouse file watcher')
    parser.add_argument('--once', action='store_true', help='Process pending files and exit')
    parser.add_argument('--interval', type=int, default=10, help='Batch interval in seconds')
    args = parser.parse_args()

    if args.once:
        pending = find_pending_files()
        if pending:
            log.info(f'Found {len(pending)} pending file(s)')
            process_batch(pending)
        else:
            log.info('No pending files')
    else:
        run_daemon(interval=args.interval)


if __name__ == '__main__':
    main()
