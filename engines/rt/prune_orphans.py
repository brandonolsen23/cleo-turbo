"""
Prune orphaned files from downstream pipeline stages.

After the dedup stage was introduced, classified/, addresses/, and parcel_links/
may contain ~31K files that correspond to duplicate assembled records that dedup
discarded. These orphans are harmless but wasteful — they inflate stage counts
and make compile read unnecessary files.

This script removes any file from classified/, addresses/, and parcel_links/
that doesn't have a matching filename in deduped/. It's a one-time cleanup
tool — after pruning, the dedup stage prevents new orphans from accumulating.

Usage:
    python3 prune_orphans.py --dry-run    # show what would be removed (ALWAYS do this first)
    python3 prune_orphans.py              # actually remove orphans
"""

import os
import sys
import time
import argparse

PIPELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline')
DEDUPED_DIR = os.path.join(PIPELINE_DIR, 'deduped')
CLASSIFIED_DIR = os.path.join(PIPELINE_DIR, 'classified')
ADDRESSES_DIR = os.path.join(PIPELINE_DIR, 'addresses')
PARCEL_LINKS_DIR = os.path.join(PIPELINE_DIR, 'parcel_links')
GEOCODED_DIR = os.path.join(PIPELINE_DIR, 'geocoded')

DIRS_TO_PRUNE = [
    ('classified', CLASSIFIED_DIR),
    ('addresses', ADDRESSES_DIR),
    ('parcel_links', PARCEL_LINKS_DIR),
    ('geocoded', GEOCODED_DIR),
]


def run(dry_run=True):
    # Verify deduped/ exists and has files
    if not os.path.isdir(DEDUPED_DIR):
        print('ERROR: deduped/ directory does not exist.')
        print('Run the dedup stage first (process.py --new) before pruning.')
        sys.exit(1)

    deduped_files = set(f for f in os.listdir(DEDUPED_DIR) if f.endswith('.json'))
    if not deduped_files:
        print('ERROR: deduped/ directory is empty.')
        print('Run the dedup stage first (process.py --new) before pruning.')
        sys.exit(1)

    print(f'Cleo Engine — Prune Orphans')
    print(f'{"DRY RUN — no files will be deleted" if dry_run else "LIVE RUN — orphans will be deleted"}')
    print(f'Canonical file set: deduped/ ({len(deduped_files):,} files)')
    print()

    total_removed = 0
    total_kept = 0

    for label, directory in DIRS_TO_PRUNE:
        if not os.path.isdir(directory):
            print(f'  {label}/: directory not found, skipping')
            continue

        dir_files = set(f for f in os.listdir(directory) if f.endswith('.json'))
        orphans = sorted(dir_files - deduped_files)
        kept = len(dir_files) - len(orphans)

        print(f'  {label}/:  {len(dir_files):,} files  →  {kept:,} kept, {len(orphans):,} orphans')

        if orphans and not dry_run:
            for fname in orphans:
                os.remove(os.path.join(directory, fname))
            total_removed += len(orphans)
        elif orphans:
            total_removed += len(orphans)

        total_kept += kept

    print()
    if dry_run:
        print(f'Would remove {total_removed:,} orphan files across all stages.')
        print(f'Would keep {total_kept:,} files that match deduped/.')
        print()
        print('Run without --dry-run to actually delete them.')
    else:
        print(f'Removed {total_removed:,} orphan files.')
        print(f'Kept {total_kept:,} files matching deduped/.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remove orphaned pipeline files not in deduped/')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed without deleting')
    args = parser.parse_args()

    run(dry_run=args.dry_run)
