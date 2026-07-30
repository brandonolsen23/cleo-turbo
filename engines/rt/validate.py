"""
Pre-compile validation — sanity checks before destructive rebuild.

Checks clean records for consistency, compares counts against current DB,
and samples resolved records for spatial accuracy.

Usage:
    python engines/rt/validate.py
    python engines/rt/validate.py --verbose
"""

import json
import os
import random
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

CLEAN_RT = os.path.join(PROJECT_ROOT, 'clean-data', 'rt')
CLEAN_GW = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')
CLEAN_OSM = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')
PARCELS = os.path.join(PROJECT_ROOT, 'clean-data', 'parcels')
DETERMINATION_RT = os.path.join(PROJECT_ROOT, 'determination', 'rt')
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'cleo.db')
REPORT_PATH = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', '_validation_report.json')

from engines.shared.io import safe_write_json


def _count_files(directory, prefix='', suffix='.json'):
    if not os.path.isdir(directory):
        return 0
    return len([f for f in os.listdir(directory)
                if f.endswith(suffix) and not f.startswith('_') and f.startswith(prefix)])


def run(verbose=False):
    print('Cleo — Pre-Compile Validation')
    print()

    issues = []
    warnings = []
    info = []

    # ============================================================
    # 1. Record-level checks on clean-data/rt/
    # ============================================================
    rt_count = _count_files(CLEAN_RT)
    info.append(f'RT clean records: {rt_count:,}')

    if rt_count == 0:
        issues.append('CRITICAL: No RT clean records found')
    else:
        # Sample 500 records for validation
        all_files = [f for f in os.listdir(CLEAN_RT) if f.endswith('.json')]
        sample = random.sample(all_files, min(500, len(all_files)))

        source_ids = set()
        no_source_id = 0
        has_parcel = 0
        parcel_no_cache = 0
        parcel_with_cache = 0

        for fname in sample:
            rec = json.load(open(os.path.join(CLEAN_RT, fname)))

            sid = rec.get('source_id', '')
            if not sid:
                no_source_id += 1
            elif sid in source_ids:
                issues.append(f'Duplicate source_id: {sid}')
            source_ids.add(sid)

            # Clean/Determination split (D9): parcel lives in the determination
            # layer now, not the clean record. Read it from determination/rt/.
            parcel = {}
            if sid:
                _dp = os.path.join(DETERMINATION_RT, f'{sid}.json')
                if os.path.isfile(_dp):
                    parcel = json.load(open(_dp)).get('parcel') or {}
            resolved = parcel.get('resolved_arn', '')
            if resolved:
                has_parcel += 1
                cache_file = os.path.join(PARCELS, f'{resolved}.json')
                if os.path.isfile(cache_file):
                    parcel_with_cache += 1
                else:
                    parcel_no_cache += 1

        if no_source_id > 0:
            issues.append(f'{no_source_id} records missing source_id (of {len(sample)} sampled)')

        pct_resolved = has_parcel * 100 / len(sample) if sample else 0
        info.append(f'Sample resolution rate: {pct_resolved:.1f}% ({has_parcel}/{len(sample)})')

        if parcel_no_cache > 0:
            warnings.append(f'{parcel_no_cache} resolved ARNs missing from parcel cache (of {has_parcel} resolved in sample)')

        info.append(f'Resolved with cached parcel: {parcel_with_cache}')

    # ============================================================
    # 2. Count-level checks (compare against current DB)
    # ============================================================
    if os.path.isfile(DB_PATH):
        import sqlite3
        conn = sqlite3.connect(DB_PATH)

        db_props = conn.execute('SELECT COUNT(*) FROM properties').fetchone()[0]
        db_txns = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        db_contacts = conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]
        db_groups = conn.execute('SELECT COUNT(*) FROM groups').fetchone()[0]

        info.append(f'Current DB: {db_props:,} properties, {db_txns:,} transactions')

        # Check RT record count vs transaction count
        if rt_count > 0 and db_txns > 0:
            pct_diff = abs(rt_count - db_txns) * 100 / db_txns
            if pct_diff > 10:
                warnings.append(f'RT record count ({rt_count:,}) differs from DB transactions ({db_txns:,}) by {pct_diff:.1f}%')

        conn.close()
    else:
        info.append('No existing database (first build)')

    # ============================================================
    # 3. Check other data sources
    # ============================================================
    gw_count = _count_files(CLEAN_GW)
    osm_count = _count_files(CLEAN_OSM, prefix='OSM_')
    parcel_count = _count_files(PARCELS)

    info.append(f'GW clean records: {gw_count:,}')
    info.append(f'OSM POI records: {osm_count:,}')
    info.append(f'Cached parcels: {parcel_count:,}')

    if osm_count == 0:
        warnings.append('No OSM POI records — Pass 4 will be skipped')
    if gw_count == 0:
        warnings.append('No GW records — Pass 5 will be skipped')

    # ============================================================
    # Report
    # ============================================================
    print('--- INFO ---')
    for i in info:
        print(f'  {i}')

    if warnings:
        print(f'\n--- WARNINGS ({len(warnings)}) ---')
        for w in warnings:
            print(f'  {w}')

    if issues:
        print(f'\n--- ISSUES ({len(issues)}) ---')
        for i in issues:
            print(f'  {i}')

    passed = len(issues) == 0
    print(f'\nResult: {"PASS" if passed else "FAIL"}')

    report = {
        'passed': passed,
        'issues': issues,
        'warnings': warnings,
        'info': info,
        'rt_records': rt_count,
        'gw_records': gw_count,
        'osm_records': osm_count,
        'parcel_cache': parcel_count,
    }
    safe_write_json(REPORT_PATH, report)

    return passed


def main():
    parser = argparse.ArgumentParser(description='Pre-compile validation')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    passed = run(verbose=args.verbose)
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
