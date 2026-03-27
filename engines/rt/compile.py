"""
Compile stage — merges classified + addresses + parcel_links into Clean Records.

Reads:
    pipeline/classified/*.json     (transaction data, parties, contacts, broker)
    pipeline/addresses/*.json      (normalized addresses, search keys, ARN/PIN)
    pipeline/parcel_links/*.json   (parcel resolution: ARN → parcel file, or unresolved)

Writes:
    clean-data/rt/{RT_ID}.json     (one Clean Record per unique RT ID)

Deduplication:
    The same RT ID can appear multiple times (same transaction scraped under
    different property-type folders). This stage picks the best record per RT ID
    using a scoring function, and writes one Clean Record.

Usage:
    python3 compile.py
    python3 compile.py --limit 100
    python3 compile.py --dry-run
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone


# Paths relative to this script (engines/rt/)
CLASSIFIED_DIR = os.path.join(os.path.dirname(__file__), 'pipeline', 'classified')
ADDRESSES_DIR = os.path.join(os.path.dirname(__file__), 'pipeline', 'addresses')
PARCEL_LINKS_DIR = os.path.join(os.path.dirname(__file__), 'pipeline', 'parcel_links')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'rt')

for d in [CLASSIFIED_DIR, ADDRESSES_DIR, PARCEL_LINKS_DIR, OUTPUT_DIR]:
    globals()[list(globals().keys())[-1]]  # no-op, just to keep linter happy

CLASSIFIED_DIR = os.path.abspath(CLASSIFIED_DIR)
ADDRESSES_DIR = os.path.abspath(ADDRESSES_DIR)
PARCEL_LINKS_DIR = os.path.abspath(PARCEL_LINKS_DIR)
OUTPUT_DIR = os.path.abspath(OUTPUT_DIR)


def score_record(classified, addresses, parcel_link):
    """Score a record for deduplication. Higher = better."""
    score = 0

    # Prefer join-verified records
    if classified.get('join_verified'):
        score += 10

    # Prefer records with ARN
    arn = addresses.get('arn', {}).get('api_format', '').strip()
    if arn and not all(c == '0' for c in arn):
        score += 5

    # Prefer records with a resolved parcel
    if parcel_link and parcel_link.get('resolved_arn'):
        score += 5

    # Prefer records with buyer contacts
    buyer_contacts = classified.get('buyer', {}).get('contacts', [])
    if buyer_contacts:
        score += 3

    # Prefer records with seller contacts
    seller_contacts = classified.get('seller', {}).get('contacts', [])
    if seller_contacts:
        score += 3

    # Prefer records with broker info
    brokers = classified.get('broker', {}).get('brokers', [])
    if brokers:
        score += 2

    # Prefer records with phone numbers
    if classified.get('buyer', {}).get('phone'):
        score += 1
    if classified.get('seller', {}).get('phone'):
        score += 1

    return score


def build_clean_record(classified, addresses, parcel_link):
    """Merge classified + addresses + parcel_link into a Clean Record."""
    header = classified.get('header', {})
    seller = classified.get('seller', {})
    buyer = classified.get('buyer', {})
    site = classified.get('site', {})

    # Parcel data
    parcel = None
    if parcel_link and parcel_link.get('resolved_arn'):
        parcel = {
            'resolved_arn': parcel_link['resolved_arn'],
            'method': parcel_link['method'],
            'parcel_file': parcel_link['parcel_file'],
        }

    return {
        'source_id': classified['rt_id'],
        'source': 'rt',
        'source_folder': classified.get('source_folder', ''),
        'compiled_at': datetime.now(timezone.utc).isoformat(),

        'transaction': {
            'sale_date': header.get('sale_date'),
            'sale_price': header.get('sale_price'),
            'transaction_note': header.get('transaction_note', ''),
            'city': header.get('city', ''),
            'region': header.get('region', ''),
        },

        'property': {
            'addresses': addresses.get('property', {}).get('addresses', []),
            'city': addresses.get('property', {}).get('city', ''),
            'region': addresses.get('property', {}).get('region', ''),
            'postal': addresses.get('property', {}).get('postal_from_export', ''),
        },

        'seller': {
            'parties': seller.get('parties', []),
            'phone': seller.get('phone', ''),
            'trade_name': seller.get('trade_name', ''),
            'contacts': seller.get('contacts', []),
            'care_of': seller.get('care_of'),
            'law_firms': seller.get('law_firms', []),
            'companies': seller.get('companies', []),
            'address': addresses.get('seller', {}).get('address', {}),
        },

        'buyer': {
            'parties': buyer.get('parties', []),
            'phone': buyer.get('phone', ''),
            'trade_name': buyer.get('trade_name', ''),
            'contacts': buyer.get('contacts', []),
            'care_of': buyer.get('care_of'),
            'law_firms': buyer.get('law_firms', []),
            'companies': buyer.get('companies', []),
            'address': addresses.get('buyer', {}).get('address', {}),
        },

        'site': {
            'pin': addresses.get('pin', {}),
            'arn': addresses.get('arn', {}),
            'acreage': site.get('acreage'),
            'legal_description': site.get('legal_description', ''),
            'location': site.get('location', ''),
            'surface_rights_only': site.get('surface_rights_only', False),
        },

        'parcel': parcel,

        'consideration': classified.get('consideration', {}),

        'broker': classified.get('broker', {}),

        'description': classified.get('description', {}),

        'photos': classified.get('photos', {}),
    }


def run(limit=None, dry_run=False):
    """Run the Compile stage."""

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Build file list — we need files that exist in all three pipeline dirs
    classified_files = set(f for f in os.listdir(CLASSIFIED_DIR) if f.endswith('.json'))
    addresses_files = set(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))
    parcel_links_files = set(f for f in os.listdir(PARCEL_LINKS_DIR) if f.endswith('.json')) if os.path.isdir(PARCEL_LINKS_DIR) else set()

    # Files present in both classified and addresses (parcel_links may be missing for some)
    all_files = sorted(classified_files & addresses_files)

    print(f'Cleo Engine — Compile')
    print(f'Classified files:   {len(classified_files):,}')
    print(f'Addresses files:    {len(addresses_files):,}')
    print(f'Parcel links files: {len(parcel_links_files):,}')
    print(f'Files to process:   {len(all_files):,}')
    print()

    # Group by RT ID for deduplication
    # Filename format: RT{id}__{region}__{type}__{page}__pos{NNN}.json
    rt_groups = {}
    for fname in all_files:
        rt_id = fname.split('__')[0]  # e.g. "RT100000"
        if rt_id not in rt_groups:
            rt_groups[rt_id] = []
        rt_groups[rt_id].append(fname)

    unique_ids = len(rt_groups)
    duplicated = sum(1 for files in rt_groups.values() if len(files) > 1)

    print(f'Unique RT IDs:      {unique_ids:,}')
    print(f'IDs with duplicates: {duplicated:,}')
    print(f'Total after dedup:  {unique_ids:,}')
    print()

    if dry_run:
        # Show duplicate distribution
        dup_counts = {}
        for files in rt_groups.values():
            n = len(files)
            dup_counts[n] = dup_counts.get(n, 0) + 1
        print('Duplicate distribution:')
        for n in sorted(dup_counts.keys()):
            label = f'{n} file{"s" if n > 1 else ""}'
            print(f'  {label}: {dup_counts[n]:,} RT IDs')
        return

    if limit:
        rt_ids = sorted(rt_groups.keys())[:limit]
    else:
        rt_ids = sorted(rt_groups.keys())

    # Process each unique RT ID
    stats = {'compiled': 0, 'errors': 0, 'with_parcel': 0, 'without_parcel': 0}
    start_time = time.time()

    for i, rt_id in enumerate(rt_ids):
        try:
            candidate_files = rt_groups[rt_id]

            # Load all candidates and score them
            best_fname = None
            best_score = -1
            best_data = None

            for fname in candidate_files:
                with open(os.path.join(CLASSIFIED_DIR, fname)) as f:
                    classified = json.load(f)
                with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                    addresses = json.load(f)

                parcel_link = None
                if fname in parcel_links_files:
                    with open(os.path.join(PARCEL_LINKS_DIR, fname)) as f:
                        parcel_link = json.load(f)

                s = score_record(classified, addresses, parcel_link)
                if s > best_score:
                    best_score = s
                    best_fname = fname
                    best_data = (classified, addresses, parcel_link)

            # Build the Clean Record from the best candidate
            classified, addresses, parcel_link = best_data
            clean_record = build_clean_record(classified, addresses, parcel_link)

            # Write to clean-data/rt/
            out_path = os.path.join(OUTPUT_DIR, f'{rt_id}.json')
            with open(out_path, 'w') as f:
                json.dump(clean_record, f, indent=2, ensure_ascii=False)

            stats['compiled'] += 1
            if clean_record.get('parcel'):
                stats['with_parcel'] += 1
            else:
                stats['without_parcel'] += 1

        except Exception as e:
            stats['errors'] += 1
            if stats['errors'] <= 10:
                print(f'  ERROR: {rt_id}: {e}')

        # Progress
        if (i + 1) % 5000 == 0 or (i + 1) == len(rt_ids):
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f'  [{i+1:,}/{len(rt_ids):,}] '
                f'compiled: {stats["compiled"]:,}  '
                f'with_parcel: {stats["with_parcel"]:,}  '
                f'errors: {stats["errors"]:,}  '
                f'({rate:.0f} rec/s, {elapsed:.0f}s)'
            )

    elapsed = time.time() - start_time
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  Compiled:       {stats["compiled"]:,}')
    print(f'  With parcel:    {stats["with_parcel"]:,}')
    print(f'  Without parcel: {stats["without_parcel"]:,}')
    print(f'  Errors:         {stats["errors"]:,}')
    print(f'  Output dir:     {OUTPUT_DIR}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compile Clean Records from pipeline outputs')
    parser.add_argument('--limit', type=int, help='Compile only the first N unique RT IDs')
    parser.add_argument('--dry-run', action='store_true', help='Show stats without compiling')
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run)
