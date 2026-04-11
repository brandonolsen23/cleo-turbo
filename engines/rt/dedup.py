"""
Dedup stage — picks the best assembled record per RT ID.

The same RT transaction can appear multiple times in assembled/ because
Realtrack lists it under multiple property type categories (e.g., comm-ind-land
AND industrial). This stage groups files by RT ID and copies the best
candidate to pipeline/deduped/, eliminating ~20% of duplicate processing
downstream.

Reads:  pipeline/assembled/*.json
Writes: pipeline/deduped/*.json  (one file per RT ID, original filename kept)

Usage:
    python3 dedup.py                  # incremental (skip existing)
    python3 dedup.py --all            # reprocess all (rewrite deduped/)
    python3 dedup.py --dry-run        # show stats without writing
    python3 dedup.py --limit 100      # first 100 RT IDs only
"""

import json
import os
import shutil
import sys
import time
import argparse
from collections import defaultdict


# Paths relative to this script (engines/rt/)
PIPELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline')
ASSEMBLED_DIR = os.path.join(PIPELINE_DIR, 'assembled')
DEDUPED_DIR = os.path.join(PIPELINE_DIR, 'deduped')


def score_assembled(data):
    """Score an assembled record for early dedup. Higher = better.

    This is a simplified scoring function that works on raw assembled JSON
    (before classify/normalize). It doesn't need to be perfect — it just
    needs to consistently pick the richer record when duplicates exist.
    """
    score = 0

    # Prefer join-verified records (detail page matched to results row)
    if data.get('join_verified'):
        score += 10

    # Prefer records with detail data (richer than results-only)
    if data.get('detail'):
        score += 5

    # Prefer records with export data
    if data.get('export'):
        score += 3

    # Prefer records where results + detail cities match (data consistency)
    results_city = (data.get('results', {}).get('city_region') or '').split(':')[0].strip()
    detail_city = (data.get('detail', {}).get('header', {}).get('city_region') or '').split(':')[0].strip()
    if results_city and detail_city and results_city.lower() == detail_city.lower():
        score += 2

    # Prefer records with more non-empty export fields
    export = data.get('export', {})
    for field in ['municipality', 'postal_code', 'sale_price', 'acreage']:
        if export.get(field):
            score += 1

    return score


def extract_rt_id(filename):
    """Extract RT ID from assembled filename.

    Filename format: RT{id}__{region}__{type}__{page}__pos{NNN}.json
    Returns: e.g. "RT100004"
    """
    return filename.split('__')[0]


def detect_collision(rt_id, winner_data, loser_data_list):
    """Check if 'duplicate' records are actually different transactions.

    Returns a list of collision warnings (empty if clean duplicates).
    """
    warnings = []
    winner_city = (winner_data.get('export', {}).get('municipality') or '').strip().lower()
    winner_price = winner_data.get('export', {}).get('sale_price')

    for loser in loser_data_list:
        loser_city = (loser.get('export', {}).get('municipality') or '').strip().lower()
        loser_price = loser.get('export', {}).get('sale_price')

        if winner_city and loser_city and winner_city != loser_city:
            warnings.append(
                f'{rt_id}: same RT ID, different cities: '
                f'{winner_city} vs {loser_city}'
            )
        elif winner_price and loser_price and winner_price != loser_price:
            warnings.append(
                f'{rt_id}: same RT ID, different sale prices: '
                f'{winner_price} vs {loser_price}'
            )

    return warnings


def run(process_all=False, dry_run=False, limit=None):
    """Run the dedup stage."""

    os.makedirs(DEDUPED_DIR, exist_ok=True)

    # Build file list from assembled/
    if not os.path.isdir(ASSEMBLED_DIR):
        print('Cleo Engine — Dedup')
        print('No assembled directory found.')
        return

    assembled_files = sorted(f for f in os.listdir(ASSEMBLED_DIR) if f.endswith('.json'))

    # Group by RT ID
    rt_groups = defaultdict(list)
    for fname in assembled_files:
        rt_id = extract_rt_id(fname)
        rt_groups[rt_id].append(fname)

    total_assembled = len(assembled_files)
    unique_ids = len(rt_groups)
    duplicated_ids = sum(1 for files in rt_groups.values() if len(files) > 1)
    wasted_copies = total_assembled - unique_ids

    # Determine which RT IDs need processing
    if process_all:
        rt_ids_to_process = sorted(rt_groups.keys())
        mode = 'all'
    else:
        # Incremental: only process RT IDs not already in deduped/
        existing_deduped = set()
        if os.path.isdir(DEDUPED_DIR):
            for f in os.listdir(DEDUPED_DIR):
                if f.endswith('.json'):
                    existing_deduped.add(extract_rt_id(f))

        rt_ids_to_process = sorted(rt_id for rt_id in rt_groups if rt_id not in existing_deduped)
        mode = 'new'

    if limit:
        rt_ids_to_process = rt_ids_to_process[:limit]

    skipped = unique_ids - len(rt_ids_to_process)

    print(f'Cleo Engine — Dedup')
    print(f'Mode: {mode}')
    print(f'Assembled files:    {total_assembled:,}')
    print(f'Unique RT IDs:      {unique_ids:,}')
    print(f'IDs with duplicates: {duplicated_ids:,}')
    print(f'Wasted copies:      {wasted_copies:,} ({wasted_copies * 100 / total_assembled:.1f}%)')
    print(f'To process:         {len(rt_ids_to_process):,}' +
          (f'  (skipped {skipped:,} already deduped)' if skipped else ''))
    print()

    if dry_run:
        # Show duplicate distribution
        dup_counts = defaultdict(int)
        for files in rt_groups.values():
            dup_counts[len(files)] += 1
        print('Duplicate distribution:')
        for n in sorted(dup_counts.keys()):
            label = f'{n} file{"s" if n > 1 else ""}'
            print(f'  {label}: {dup_counts[n]:,} RT IDs')
        return

    if not rt_ids_to_process:
        print('Nothing to dedup (0 pending)')
        return

    # Process each RT ID
    stats = {
        'copied': 0,
        'deduped': 0,
        'collisions': 0,
        'errors': 0,
    }
    collision_warnings = []
    start_time = time.time()

    for i, rt_id in enumerate(rt_ids_to_process):
        try:
            candidates = rt_groups[rt_id]

            if len(candidates) == 1:
                # No duplicates — just copy
                winner_fname = candidates[0]
            else:
                # Score each candidate and pick the best
                best_fname = None
                best_score = -1
                best_data = None
                all_data = []

                for fname in candidates:
                    fpath = os.path.join(ASSEMBLED_DIR, fname)
                    with open(fpath) as f:
                        data = json.load(f)
                    all_data.append((fname, data))
                    s = score_assembled(data)
                    if s > best_score:
                        best_score = s
                        best_fname = fname
                        best_data = data

                winner_fname = best_fname

                # Check for collisions (different transactions with same RT ID)
                loser_data = [d for fn, d in all_data if fn != winner_fname]
                warnings = detect_collision(rt_id, best_data, loser_data)
                if warnings:
                    collision_warnings.extend(warnings)
                    stats['collisions'] += 1

                stats['deduped'] += len(candidates) - 1

            # Copy winner to deduped/ (keeping original filename)
            src = os.path.join(ASSEMBLED_DIR, winner_fname)
            dst = os.path.join(DEDUPED_DIR, winner_fname)
            shutil.copy2(src, dst)
            stats['copied'] += 1

        except Exception as e:
            stats['errors'] += 1
            if stats['errors'] <= 10:
                print(f'  ERROR: {rt_id}: {e}')

        # Progress
        if (i + 1) % 10000 == 0 or (i + 1) == len(rt_ids_to_process):
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f'  [{i+1:,}/{len(rt_ids_to_process):,}] '
                f'copied: {stats["copied"]:,}  '
                f'dupes eliminated: {stats["deduped"]:,}  '
                f'collisions: {stats["collisions"]:,}  '
                f'({rate:.0f}/s, {elapsed:.0f}s)'
            )

    elapsed = time.time() - start_time
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  Copied to deduped/:  {stats["copied"]:,}')
    print(f'  Dupes eliminated:    {stats["deduped"]:,}')
    print(f'  Collisions detected: {stats["collisions"]:,}')
    print(f'  Errors:              {stats["errors"]:,}')

    if collision_warnings:
        print()
        print(f'Collision warnings (same RT ID, different data):')
        for w in collision_warnings[:20]:
            print(f'  {w}')
        if len(collision_warnings) > 20:
            print(f'  ... and {len(collision_warnings) - 20} more')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dedup assembled records by RT ID')
    parser.add_argument('--all', action='store_true', help='Reprocess all (rewrite deduped/)')
    parser.add_argument('--dry-run', action='store_true', help='Show stats without writing')
    parser.add_argument('--limit', type=int, help='Process only first N RT IDs')
    args = parser.parse_args()

    run(process_all=args.all, dry_run=args.dry_run, limit=args.limit)
