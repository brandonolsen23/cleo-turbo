"""
GeoWarehouse Data Quality -- validates parsed and normalized records.

Writes issues to the data_issues table for tracking in the app.

Usage:
    python engines/gw/quality.py
    python engines/gw/quality.py --dry-run
"""

import json
import os
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

NORMALIZED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'normalized')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parcel_links')


RULES = [
    # (rule_id, severity, check_fn_name, description)
    ('gw_no_pin', 'error', 'check_no_pin', 'Detail page with no PIN'),
    ('gw_no_arn', 'warning', 'check_no_arn', 'Detail page with no ARN/assessment'),
    ('gw_no_address', 'error', 'check_no_address', 'No address in summary or MPAC'),
    ('gw_inactive_registry', 'info', 'check_inactive', '"Not Active" registry status'),
    ('gw_multiple_arns', 'info', 'check_multi_arn', 'Multi-parcel property'),
    ('gw_address_parse_failed', 'warning', 'check_addr_parse', 'MPAC address could not be decomposed'),
    ('gw_no_postal', 'warning', 'check_no_postal', 'No postal code extracted'),
    ('gw_parcel_unresolved', 'error', 'check_parcel_unresolved', 'Could not resolve to parcel'),
]


def check_no_pin(norm, parcel_link):
    return not norm.get('pin', '').strip()

def check_no_arn(norm, parcel_link):
    return len(norm.get('assessments', [])) == 0

def check_no_address(norm, parcel_link):
    addr = norm.get('address')
    return not addr or not addr.get('street')

def check_inactive(norm, parcel_link):
    return not norm.get('is_active', True)

def check_multi_arn(norm, parcel_link):
    return len(norm.get('assessments', [])) > 1

def check_addr_parse(norm, parcel_link):
    return 'address_parse_failed' in norm.get('issues', [])

def check_no_postal(norm, parcel_link):
    addr = norm.get('address')
    return addr and not addr.get('postal_code')

def check_parcel_unresolved(norm, parcel_link):
    if not parcel_link:
        return True
    resolutions = parcel_link.get('resolutions', [])
    if not resolutions:
        return True
    return all(r.get('method') in ('no_arn', 'arn_api_miss', '') for r in resolutions)


CHECK_FNS = {
    'check_no_pin': check_no_pin,
    'check_no_arn': check_no_arn,
    'check_no_address': check_no_address,
    'check_inactive': check_inactive,
    'check_multi_arn': check_multi_arn,
    'check_addr_parse': check_addr_parse,
    'check_no_postal': check_no_postal,
    'check_parcel_unresolved': check_parcel_unresolved,
}


def run(dry_run=False):
    """Run all quality checks on GW records."""
    if not os.path.isdir(NORMALIZED_DIR):
        print('ERROR: No normalized records found.')
        sys.exit(1)

    files = sorted(f for f in os.listdir(NORMALIZED_DIR)
                   if f.endswith('.json') and not f.startswith('_'))

    print('Cleo Engine -- GeoWarehouse Data Quality')
    print(f'Records: {len(files):,}')
    print()

    all_issues = []
    rule_counts = {}

    for fname in files:
        with open(os.path.join(NORMALIZED_DIR, fname)) as f:
            norm = json.load(f)

        parcel_link = None
        pl_path = os.path.join(PARCEL_LINKS_DIR, fname)
        if os.path.isfile(pl_path):
            with open(pl_path) as f:
                parcel_link = json.load(f)

        gw_id = norm.get('gw_id', fname.replace('.json', ''))

        for rule_id, severity, check_fn_name, description in RULES:
            check_fn = CHECK_FNS[check_fn_name]
            if check_fn(norm, parcel_link):
                all_issues.append({
                    'source_id': gw_id,
                    'rule': rule_id,
                    'severity': severity,
                    'field_path': 'gw',
                    'message': description,
                    'introduced_at': 'gw_pipeline',
                })
                rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

    print(f'Issues found: {len(all_issues):,}')
    for rule_id, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        severity = next(s for r, s, _, _ in RULES if r == rule_id)
        print(f'  [{severity}] {rule_id}: {count}')

    if dry_run or not all_issues:
        return

    # Write to database
    from cleo.database.connection import get_connection
    conn = get_connection()

    # Clear old GW issues
    conn.execute("DELETE FROM data_issues WHERE rule LIKE 'gw_%'")

    for issue in all_issues:
        conn.execute(
            "INSERT INTO data_issues (source_id, rule, severity, field_path, message, "
            "introduced_at, status) VALUES (?, ?, ?, ?, ?, ?, 'open')",
            (issue['source_id'], issue['rule'], issue['severity'],
             issue['field_path'], issue['message'], issue['introduced_at'])
        )

    conn.commit()
    conn.close()
    print(f'\nWrote {len(all_issues):,} issues to data_issues table')


def main():
    parser = argparse.ArgumentParser(description='GeoWarehouse data quality checks')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
