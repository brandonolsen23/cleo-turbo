"""
Run pipeline — processes all source data through extract → assemble.

Walks every page folder in the source data, runs all three parsers,
saves extracted records, then assembles and cross-checks.

Usage:
    python3 run_pipeline.py                    # full run
    python3 run_pipeline.py --folder Metro_Toronto/retail/p001   # one folder
    python3 run_pipeline.py --limit 100        # first 100 folders
    python3 run_pipeline.py --dry-run          # show what would be processed
"""

import json
import os
import sys
import time
import re
import argparse

from parsers.detail import parse_detail
from parsers.export import parse_export_file
from parsers.results import parse_results_file
from assembler import assemble_record, find_matching_export


def find_page_folders(source_root):
    """Find all page folders (pNNN) in the source data tree.

    Returns list of (folder_path, source_folder_key) tuples.
    folder_path: absolute path to the page folder
    source_folder_key: relative path like 'Metro_Toronto/retail/p001'
    """
    folders = []
    for region in sorted(os.listdir(source_root)):
        region_path = os.path.join(source_root, region)
        if not os.path.isdir(region_path) or region.startswith('.'):
            continue
        for prop_type in sorted(os.listdir(region_path)):
            type_path = os.path.join(region_path, prop_type)
            if not os.path.isdir(type_path) or prop_type.startswith('.'):
                continue
            for page in sorted(os.listdir(type_path)):
                page_path = os.path.join(type_path, page)
                if not os.path.isdir(page_path) or not page.startswith('p'):
                    continue
                source_key = f'{region}/{prop_type}/{page}'
                folders.append((page_path, source_key))
    return folders


def process_folder(folder_path, source_key, pipeline_dir):
    """Process one page folder: extract all three sources, assemble.

    Returns:
        dict with stats: total, assembled, join_failures, errors
    """
    stats = {'total': 0, 'assembled': 0, 'join_failures': 0, 'errors': []}

    # Find all detail files in this folder
    detail_files = sorted([
        f for f in os.listdir(folder_path)
        if f.startswith('detail_') and f.endswith('.html')
    ])

    if not detail_files:
        return stats

    # Parse export.json (all positions at once)
    export_path = os.path.join(folder_path, 'export.json')
    export_records = []
    if os.path.isfile(export_path):
        try:
            export_records = parse_export_file(export_path)
        except Exception as e:
            stats['errors'].append(f'export.json: {e}')

    # Parse results.html (all positions at once)
    results_path = os.path.join(folder_path, 'results.html')
    results_records = []
    if os.path.isfile(results_path):
        try:
            results_records = parse_results_file(results_path)
        except Exception as e:
            stats['errors'].append(f'results.html: {e}')

    # Create output directories
    extracted_dir = os.path.join(pipeline_dir, 'extracted', source_key)
    assembled_dir = os.path.join(pipeline_dir, 'assembled')
    os.makedirs(extracted_dir, exist_ok=True)
    os.makedirs(assembled_dir, exist_ok=True)

    for detail_file in detail_files:
        stats['total'] += 1

        # Get position from filename
        pos_match = re.match(r'detail_(\d+)\.html', detail_file)
        if not pos_match:
            stats['errors'].append(f'{detail_file}: cannot parse position from filename')
            continue
        position = int(pos_match.group(1))

        detail_path = os.path.join(folder_path, detail_file)

        try:
            # Parse detail
            detail_record = parse_detail(detail_path, source_key, position)

            # Get matching export and results by position
            export_record = export_records[position] if position < len(export_records) else None
            results_record = results_records[position] if position < len(results_records) else None

            # If position-based export has empty address, it's a blank/garbage row —
            # treat it as missing so the address-based fallback kicks in
            if export_record and not export_record.get('address', '').strip():
                export_record = None

            # Save extracted records
            rt_id = detail_record['meta']['rt_id']

            with open(os.path.join(extracted_dir, f'detail_{position:03d}.json'), 'w') as f:
                json.dump(detail_record, f, indent=2)

            if export_record:
                with open(os.path.join(extracted_dir, f'export_{position:03d}.json'), 'w') as f:
                    json.dump(export_record, f, indent=2)

            if results_record:
                with open(os.path.join(extracted_dir, f'results_{position:03d}.json'), 'w') as f:
                    json.dump(results_record, f, indent=2)

            # Assemble — try position-based join first
            assembled = assemble_record(detail_record, export_record, results_record)

            # If position join failed OR export is missing, try address-based matching
            if (not assembled['join_verified'] or export_record is None) and export_records:
                matched_export = find_matching_export(detail_record, export_records)
                if matched_export:
                    assembled = assemble_record(detail_record, matched_export, results_record)

            if not assembled['join_verified']:
                stats['join_failures'] += 1

            # Save assembled record — use folder + position to avoid
            # overwriting when the same RT appears under multiple property types
            if rt_id:
                safe_folder = source_key.replace('/', '__')
                filename = f'{rt_id}__{safe_folder}__pos{position:03d}.json'
                with open(os.path.join(assembled_dir, filename), 'w') as f:
                    json.dump(assembled, f, indent=2)
                stats['assembled'] += 1
            else:
                stats['errors'].append(f'{detail_file}: no RT ID found in footer')

        except Exception as e:
            stats['errors'].append(f'{detail_file}: {e}')

    return stats


def main():
    parser = argparse.ArgumentParser(description='Run the Cleo extraction pipeline')
    parser.add_argument('--folder', help='Process only this folder (e.g., Metro_Toronto/retail/p001)')
    parser.add_argument('--limit', type=int, help='Process only the first N folders')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without doing it')
    args = parser.parse_args()

    # Load config
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path) as f:
        config = json.load(f)

    source_root = os.path.join(config['source_data'], 'pages')
    pipeline_dir = config['pipeline_output']

    # Find folders to process
    if args.folder:
        folder_path = os.path.join(source_root, args.folder)
        if not os.path.isdir(folder_path):
            print(f'ERROR: Folder not found: {folder_path}')
            sys.exit(1)
        folders = [(folder_path, args.folder)]
    else:
        folders = find_page_folders(source_root)

    if args.limit:
        folders = folders[:args.limit]

    print(f'Cleo Engine Pipeline')
    print(f'Source: {source_root}')
    print(f'Output: {pipeline_dir}')
    print(f'Folders to process: {len(folders)}')
    print()

    if args.dry_run:
        for _, key in folders[:20]:
            print(f'  {key}')
        if len(folders) > 20:
            print(f'  ... and {len(folders) - 20} more')
        return

    # Process
    total_stats = {'total': 0, 'assembled': 0, 'join_failures': 0, 'errors': []}
    start_time = time.time()

    for i, (folder_path, source_key) in enumerate(folders):
        stats = process_folder(folder_path, source_key, pipeline_dir)

        total_stats['total'] += stats['total']
        total_stats['assembled'] += stats['assembled']
        total_stats['join_failures'] += stats['join_failures']
        total_stats['errors'].extend(stats['errors'])

        # Progress every 50 folders
        if (i + 1) % 50 == 0 or i == len(folders) - 1:
            elapsed = time.time() - start_time
            print(f'  [{i+1}/{len(folders)}] {total_stats["assembled"]} assembled, '
                  f'{total_stats["join_failures"]} join failures, '
                  f'{len(total_stats["errors"])} errors '
                  f'({elapsed:.0f}s)')

    # Summary
    elapsed = time.time() - start_time
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  Records processed: {total_stats["total"]}')
    print(f'  Assembled:         {total_stats["assembled"]}')
    print(f'  Join failures:     {total_stats["join_failures"]}')
    print(f'  Errors:            {len(total_stats["errors"])}')

    if total_stats['errors']:
        print()
        print(f'First 20 errors:')
        for err in total_stats['errors'][:20]:
            print(f'  {err}')

    if total_stats['join_failures'] > 0:
        print()
        print(f'WARNING: {total_stats["join_failures"]} records failed join cross-check.')
        print(f'Check assembled JSON files where join_verified = false.')


if __name__ == '__main__':
    main()
