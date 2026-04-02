"""
GeoWarehouse Ingester -- filters and copies GW HTML files from Downloads.

Copies only property detail pages (geowarehouse-*.html prefix) and skips
collaboration pages and other non-detail files.

Input:  ~/Downloads/GeoWarehouse/gw-ingest-data/*.html (or V3 gw_html/)
Output: engines/gw/pipeline/html/*.html

Usage:
    python engines/gw/ingest.py
    python engines/gw/ingest.py --dry-run
    python engines/gw/ingest.py --source /path/to/html
    python engines/gw/ingest.py --include-v3   (also ingest V3's filtered HTML)
"""

import os
import shutil
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HTML_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'html')

DEFAULT_SOURCE = os.path.join(
    os.path.expanduser('~'), 'Downloads', 'GeoWarehouse', 'gw-ingest-data'
)

V3_HTML_DIR = os.path.join(
    os.path.expanduser('~'),
    'Library', 'Mobile Documents', 'com~apple~CloudDocs',
    '01_Personal', '01_Brandon', '07_Development',
    '2026-02-08 - Cleo Mini V3', 'data', 'gw_html',
)


def is_detail_file(filename):
    """Check if filename matches the GW detail page pattern."""
    return filename.startswith('geowarehouse-') and filename.endswith('.html')


def run(source=None, include_v3=False, dry_run=False):
    """Ingest GW HTML files from source directory."""
    sources = []

    # Primary source
    src = source or DEFAULT_SOURCE
    if os.path.isdir(src):
        sources.append(('Downloads', src))
    else:
        print(f'WARNING: Source not found: {src}')

    # V3 source
    if include_v3 and os.path.isdir(V3_HTML_DIR):
        sources.append(('V3', V3_HTML_DIR))
    elif include_v3:
        print(f'WARNING: V3 HTML dir not found: {V3_HTML_DIR}')

    if not sources:
        print('ERROR: No source directories found.')
        sys.exit(1)

    os.makedirs(HTML_DIR, exist_ok=True)
    existing = set(os.listdir(HTML_DIR))

    print('Cleo Engine -- Ingest GeoWarehouse HTML')

    total_found = 0
    total_detail = 0
    total_skipped_type = 0
    total_copied = 0
    total_already = 0

    for label, src_dir in sources:
        all_files = [f for f in os.listdir(src_dir) if f.endswith('.html')]
        detail_files = [f for f in all_files if is_detail_file(f)]
        non_detail = len(all_files) - len(detail_files)

        new_files = [f for f in detail_files if f not in existing]
        already = len(detail_files) - len(new_files)

        print(f'\n  [{label}] {src_dir}')
        print(f'    Total HTML:    {len(all_files):,}')
        print(f'    Detail pages:  {len(detail_files):,}')
        print(f'    Non-detail:    {non_detail:,} (skipped)')
        print(f'    Already have:  {already:,}')
        print(f'    New to copy:   {len(new_files):,}')

        total_found += len(all_files)
        total_detail += len(detail_files)
        total_skipped_type += non_detail
        total_already += already

        if not dry_run:
            for fname in new_files:
                shutil.copy2(os.path.join(src_dir, fname), os.path.join(HTML_DIR, fname))
                existing.add(fname)
                total_copied += 1

    print(f'\nSummary:')
    print(f'  Total found:    {total_found:,}')
    print(f'  Detail pages:   {total_detail:,}')
    print(f'  Non-detail:     {total_skipped_type:,}')
    print(f'  Already had:    {total_already:,}')
    print(f'  Copied:         {total_copied:,}')
    print(f'  Total in pipeline: {len(os.listdir(HTML_DIR)):,}')


def main():
    parser = argparse.ArgumentParser(description='Ingest GeoWarehouse HTML files')
    parser.add_argument('--source', type=str, help='Source directory for HTML files')
    parser.add_argument('--include-v3', action='store_true',
                        help='Also ingest from V3 gw_html directory')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be ingested without copying')
    args = parser.parse_args()

    run(source=args.source, include_v3=args.include_v3, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
