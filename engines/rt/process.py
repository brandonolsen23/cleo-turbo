"""
Pipeline Orchestrator — single entry point for processing RT records.

Two modes:
    --new           Process only records missing from downstream stages (daily use).
    --from STAGE    Reprocess ALL records from a stage onward (after fixing a bug).

Stages: extract → classify → normalize → resolve → compile → rebuild

Usage:
    python process.py --new                          # daily: process new records only
    python process.py --new --skip resolve           # daily: skip resolve (do it later)
    python process.py --from classify                # reprocess all from classify onward
    python process.py --from classify --skip resolve # reclassify everything, keep parcel links
    python process.py --from normalize               # renormalize + compile + rebuild
    python process.py --full                         # everything from extract onward
    python process.py --resolve-unresolved           # retry only unresolved parcels
    python process.py --status                       # show pipeline state
    python process.py --new --dry-run                # show what would be done
"""

import json
import os
import sys
import time
import subprocess
import argparse
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(ENGINE_DIR, '..', '..'))
PIPELINE_DIR = os.path.join(ENGINE_DIR, 'pipeline')

ASSEMBLED_DIR = os.path.join(PIPELINE_DIR, 'assembled')
CLASSIFIED_DIR = os.path.join(PIPELINE_DIR, 'classified')
ADDRESSES_DIR = os.path.join(PIPELINE_DIR, 'addresses')
PARCEL_LINKS_DIR = os.path.join(PIPELINE_DIR, 'parcel_links')
EXTRACTED_DIR = os.path.join(PIPELINE_DIR, 'extracted')

CLEAN_DATA_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'rt')

SOURCE_PAGES_DIR = os.path.join(PROJECT_ROOT, 'raw-data', 'rt', 'pages')

LOG_FILE = os.path.join(PIPELINE_DIR, '_processing_log.jsonl')
REPROCESS_MARKER = os.path.join(PIPELINE_DIR, '_reprocess.json')
LOCKFILE = os.path.join(PARCEL_LINKS_DIR, '.resolve_v2.lock')

STAGE_ORDER = ['extract', 'classify', 'normalize', 'resolve', 'compile', 'rebuild']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_files(directory):
    """Return set of .json filenames in a directory."""
    if not os.path.isdir(directory):
        return set()
    return set(f for f in os.listdir(directory) if f.endswith('.json'))


def _pending_files(input_dir, output_dir):
    """Find files in input_dir that don't have a counterpart in output_dir."""
    input_files = _json_files(input_dir)
    output_files = _json_files(output_dir)
    return sorted(input_files - output_files)


def _is_resolve_locked():
    """Check if resolve_v2 is currently running (lockfile with live PID)."""
    if not os.path.isfile(LOCKFILE):
        return False
    try:
        with open(LOCKFILE) as f:
            info = json.load(f)
        pid = info.get('pid')
        if pid:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                pass
    except (json.JSONDecodeError, OSError):
        pass
    return False


def _log_entry(stage, mode, files_processed, files_skipped, elapsed, errors):
    """Append a line to the processing log."""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'stage': stage,
        'mode': mode,
        'files_processed': files_processed,
        'files_skipped': files_skipped,
        'elapsed_seconds': round(elapsed, 1),
        'errors': errors,
    }
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    return entry


def _run_subprocess(cmd, cwd=None, label=''):
    """Run a subprocess and return (success, elapsed, stdout)."""
    start = time.time()
    print(f'  Running: {" ".join(cmd)}')
    result = subprocess.run(
        cmd, cwd=cwd or ENGINE_DIR,
        capture_output=True, text=True, timeout=7200,
    )
    elapsed = time.time() - start
    if result.stdout:
        # Indent subprocess output
        for line in result.stdout.strip().split('\n'):
            print(f'    {line}')
    if result.returncode != 0:
        print(f'  ERROR ({label}): exit code {result.returncode}')
        if result.stderr:
            for line in result.stderr.strip().split('\n')[:10]:
                print(f'    {line}')
    return result.returncode == 0, elapsed, result.stdout


# ---------------------------------------------------------------------------
# Pipeline Stages
# ---------------------------------------------------------------------------

def run_extract_new():
    """Find unextracted page folders and run run_pipeline.py on each."""
    if not os.path.isdir(SOURCE_PAGES_DIR):
        print('  No source pages directory found, skipping extract.')
        return 0, 0

    # Walk 3 levels: region/type/page — same logic as run_pipeline.py
    all_folders = []
    for region in sorted(os.listdir(SOURCE_PAGES_DIR)):
        region_path = os.path.join(SOURCE_PAGES_DIR, region)
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
                all_folders.append(source_key)

    # Check which folders have been extracted
    new_folders = []
    for key in all_folders:
        extracted_path = os.path.join(EXTRACTED_DIR, key)
        if not os.path.isdir(extracted_path):
            new_folders.append(key)

    if not new_folders:
        return 0, 0

    print(f'\n--- Extract ---')
    print(f'  {len(new_folders)} unextracted page folders found')

    total_assembled = 0
    total_elapsed = 0
    for folder_key in new_folders:
        success, elapsed, stdout = _run_subprocess(
            [sys.executable, 'run_pipeline.py', '--folder', folder_key],
            label=f'extract {folder_key}'
        )
        total_elapsed += elapsed
        # Count assembled records from stdout
        if stdout and 'assembled' in stdout.lower():
            for line in stdout.split('\n'):
                if 'Assembled:' in line:
                    try:
                        total_assembled += int(line.split(':')[1].strip())
                    except (ValueError, IndexError):
                        pass

    _log_entry('extract', 'new', total_assembled, 0, total_elapsed, 0)
    return len(new_folders), total_assembled


def run_classify(mode='new', file_pattern=None):
    """Run the classifier stage."""
    if mode == 'new':
        pending = _pending_files(ASSEMBLED_DIR, CLASSIFIED_DIR)
        if not pending:
            print(f'\n--- Classify ---')
            print(f'  Nothing to classify (0 pending)')
            return 0, 0
        count = len(pending)
        print(f'\n--- Classify ---')
        print(f'  {count} records to classify')
        # Use incremental mode (default) — it will find the same pending files
        cmd = [sys.executable, 'run_classifier.py']
    elif mode == 'all':
        count = len(_json_files(ASSEMBLED_DIR))
        print(f'\n--- Classify (reprocess all) ---')
        print(f'  {count} records to classify')
        cmd = [sys.executable, 'run_classifier.py', '--all']
    elif mode == 'files' and file_pattern:
        print(f'\n--- Classify (targeted) ---')
        cmd = [sys.executable, 'run_classifier.py', '--files', file_pattern]
        count = -1  # Unknown until it runs

    start = time.time()
    success, elapsed, stdout = _run_subprocess(cmd, label='classify')

    # Parse count from output if we don't know it
    if count == -1:
        count = 0
        if stdout:
            for line in stdout.split('\n'):
                if 'Records to process:' in line:
                    try:
                        count = int(line.split(':')[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass

    skipped = len(_json_files(ASSEMBLED_DIR)) - count if mode == 'new' else 0
    errors = 0
    if stdout:
        for line in stdout.split('\n'):
            if 'Errors:' in line:
                try:
                    errors = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass

    _log_entry('classify', mode, count, skipped, elapsed, errors)
    return count, elapsed


def run_normalize(mode='new', file_pattern=None):
    """Run the address normalizer stage."""
    if mode == 'new':
        pending = _pending_files(CLASSIFIED_DIR, ADDRESSES_DIR)
        if not pending:
            print(f'\n--- Normalize ---')
            print(f'  Nothing to normalize (0 pending)')
            return 0, 0
        count = len(pending)
        print(f'\n--- Normalize ---')
        print(f'  {count} records to normalize')
        cmd = [sys.executable, '-m', 'address_normalizer.run']
    elif mode == 'all':
        count = len(_json_files(CLASSIFIED_DIR))
        print(f'\n--- Normalize (reprocess all) ---')
        print(f'  {count} records to normalize')
        cmd = [sys.executable, '-m', 'address_normalizer.run', '--all']
    elif mode == 'files' and file_pattern:
        print(f'\n--- Normalize (targeted) ---')
        cmd = [sys.executable, '-m', 'address_normalizer.run', '--files', file_pattern]
        count = -1

    start = time.time()
    success, elapsed, stdout = _run_subprocess(cmd, label='normalize')

    if count == -1:
        count = 0

    skipped = len(_json_files(CLASSIFIED_DIR)) - count if mode == 'new' else 0
    errors = 0
    if stdout:
        for line in stdout.split('\n'):
            if 'Errors' in line and '(' in line:
                try:
                    errors = int(line.split('(')[1].split(')')[0])
                except (ValueError, IndexError):
                    pass

    _log_entry('normalize', mode, count, skipped, elapsed, errors)
    return count, elapsed


def run_resolve(mode='new', reprocess_unresolved=False, reprocess_method=None):
    """Run the resolve stage."""
    if _is_resolve_locked():
        print(f'\n--- Resolve ---')
        print(f'  SKIPPED — resolve_v2 is already running (lockfile active)')
        _log_entry('resolve', 'skipped_locked', 0, 0, 0, 0)
        return 0, 0

    if mode == 'new':
        pending = _pending_files(ADDRESSES_DIR, PARCEL_LINKS_DIR)
        if not pending:
            print(f'\n--- Resolve ---')
            print(f'  Nothing to resolve (0 pending)')
            return 0, 0
        count = len(pending)
        print(f'\n--- Resolve ---')
        print(f'  {count} records to resolve')
        # resolve_v2 is already incremental — it skips existing parcel_links
        cmd = [sys.executable, '-m', 'parcel_resolver.resolve_v2']
    elif mode == 'all':
        count = len(_json_files(ADDRESSES_DIR))
        print(f'\n--- Resolve (reprocess all) ---')
        print(f'  {count} records to resolve')
        cmd = [sys.executable, '-m', 'parcel_resolver.resolve_v2', '--reprocess']
    else:
        cmd = [sys.executable, '-m', 'parcel_resolver.resolve_v2']
        count = -1

    if reprocess_unresolved:
        cmd = [sys.executable, '-m', 'parcel_resolver.resolve_v2', '--reprocess-unresolved']
        print(f'\n--- Resolve (retry unresolved) ---')
        count = -1
    if reprocess_method:
        cmd = [sys.executable, '-m', 'parcel_resolver.resolve_v2', '--reprocess-method', reprocess_method]
        print(f'\n--- Resolve (reprocess method: {reprocess_method}) ---')
        count = -1

    start = time.time()
    success, elapsed, stdout = _run_subprocess(cmd, label='resolve')

    if count == -1:
        count = 0

    _log_entry('resolve', mode, count, 0, elapsed, 0 if success else 1)
    return count, elapsed


def run_compile():
    """Run the compile stage (always full)."""
    print(f'\n--- Compile ---')
    cmd = [sys.executable, 'compile.py']
    success, elapsed, stdout = _run_subprocess(cmd, label='compile')

    count = len(_json_files(CLEAN_DATA_DIR)) if os.path.isdir(CLEAN_DATA_DIR) else 0
    _log_entry('compile', 'full', count, 0, elapsed, 0 if success else 1)
    return count, elapsed


def run_rebuild():
    """Run the database rebuild (always full)."""
    print(f'\n--- Rebuild ---')
    rebuild_script = os.path.join(PROJECT_ROOT, 'rebuild.py')
    if not os.path.isfile(rebuild_script):
        # Try the compiler directly
        cmd = [sys.executable, '-m', 'cleo.compiler']
        success, elapsed, stdout = _run_subprocess(cmd, cwd=PROJECT_ROOT, label='rebuild')
    else:
        cmd = [sys.executable, rebuild_script]
        success, elapsed, stdout = _run_subprocess(cmd, cwd=PROJECT_ROOT, label='rebuild')

    _log_entry('rebuild', 'full', 0, 0, elapsed, 0 if success else 1)
    return 0, elapsed


# ---------------------------------------------------------------------------
# Reprocess Marker
# ---------------------------------------------------------------------------

def _read_reprocess_marker():
    """Read the reprocess marker if it exists and is valid."""
    if not os.path.isfile(REPROCESS_MARKER):
        return None
    try:
        with open(REPROCESS_MARKER) as f:
            content = f.read().strip()
        if not content or content == '{}':
            return None
        data = json.loads(content)
        if not data.get('from_stage'):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_reprocess_marker(from_stage, skip_stages=None, reason=''):
    """Write a reprocess marker."""
    marker = {
        'created': datetime.now(timezone.utc).isoformat(),
        'from_stage': from_stage,
        'skip_stages': skip_stages or [],
        'reason': reason,
        'progress': {},
    }
    with open(REPROCESS_MARKER, 'w') as f:
        json.dump(marker, f, indent=2)
    return marker


def _update_marker_progress(stage, completed):
    """Update progress in the reprocess marker."""
    marker = _read_reprocess_marker()
    if marker:
        marker['progress'][stage] = {
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'files_processed': completed,
        }
        with open(REPROCESS_MARKER, 'w') as f:
            json.dump(marker, f, indent=2)


def _delete_reprocess_marker():
    """Delete the reprocess marker (reprocess complete)."""
    if os.path.isfile(REPROCESS_MARKER):
        os.remove(REPROCESS_MARKER)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status():
    """Display current pipeline state and recent processing history."""
    print('Pipeline Status')
    print('=' * 60)

    assembled = len(_json_files(ASSEMBLED_DIR))
    classified = len(_json_files(CLASSIFIED_DIR))
    addresses = len(_json_files(ADDRESSES_DIR))
    parcel_links = len(_json_files(PARCEL_LINKS_DIR))
    clean_data = len(_json_files(CLEAN_DATA_DIR)) if os.path.isdir(CLEAN_DATA_DIR) else 0

    pending_classify = assembled - classified
    pending_normalize = classified - addresses
    pending_resolve = addresses - parcel_links

    print(f'  Assembled:     {assembled:>8,}')
    print(f'  Classified:    {classified:>8,}  ({pending_classify} pending)' if pending_classify else f'  Classified:    {classified:>8,}')
    print(f'  Normalized:    {addresses:>8,}  ({pending_normalize} pending)' if pending_normalize else f'  Normalized:    {addresses:>8,}')
    print(f'  Resolved:      {parcel_links:>8,}  ({pending_resolve} pending)' if pending_resolve else f'  Resolved:      {parcel_links:>8,}')
    print(f'  Clean-data:    {clean_data:>8,}')
    print()

    # Resolve lock
    if _is_resolve_locked():
        try:
            with open(LOCKFILE) as f:
                lock_info = json.load(f)
            print(f'  Resolve lock:  ACTIVE (PID {lock_info.get("pid")})')
        except Exception:
            print(f'  Resolve lock:  ACTIVE')
    else:
        print(f'  Resolve lock:  inactive')

    # Reprocess marker
    marker = _read_reprocess_marker()
    if marker:
        print(f'  Reprocess:     ACTIVE (from {marker["from_stage"]}, started {marker["created"][:16]})')
        for stage, prog in marker.get('progress', {}).items():
            print(f'                 {stage}: {prog["files_processed"]} files completed')
    else:
        print(f'  Reprocess:     none active')

    # Recent processing history
    print()
    print('Processing History (last 10 runs)')
    print('-' * 60)
    if os.path.isfile(LOG_FILE):
        lines = []
        with open(LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        # Group by timestamp (same run = same second roughly)
        if lines:
            recent = lines[-30:]  # Last 30 log entries
            for entry in recent:
                ts = entry['timestamp'][:16].replace('T', ' ')
                stage = entry['stage']
                mode = entry['mode']
                processed = entry['files_processed']
                elapsed = entry['elapsed_seconds']
                errors = entry.get('errors', 0)
                err_str = f'  [{errors} errors]' if errors else ''
                print(f'  {ts}  {stage:<12} {mode:<10} {processed:>7,} processed  ({elapsed:.0f}s){err_str}')
        else:
            print('  No processing history yet.')
    else:
        print('  No processing history yet.')

    # Summary stats
    if os.path.isfile(LOG_FILE):
        total_runs = 0
        total_processed = 0
        total_errors = 0
        with open(LOG_FILE) as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        total_runs += 1
                        total_processed += entry.get('files_processed', 0)
                        total_errors += entry.get('errors', 0)
                    except json.JSONDecodeError:
                        pass
        print()
        print(f'Totals: {total_runs} stage runs  |  {total_processed:,} records processed  |  {total_errors} errors')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='RT Pipeline Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process.py --new                          Daily: process new records
  python process.py --new --skip resolve           Daily: skip resolve
  python process.py --from classify                Reprocess all from classify
  python process.py --from classify --skip resolve Fixed parser, keep parcel links
  python process.py --full                         Reprocess everything
  python process.py --resolve-unresolved           Retry unresolved parcels
  python process.py --status                       Show pipeline state
        """
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--new', action='store_true', help='Process only new/missing records')
    mode_group.add_argument('--from', dest='from_stage', choices=['extract', 'classify', 'normalize', 'resolve'],
                            help='Reprocess everything from this stage onward')
    mode_group.add_argument('--full', action='store_true', help='Reprocess everything from scratch')
    mode_group.add_argument('--resolve-unresolved', action='store_true', help='Retry only unresolved parcels')
    mode_group.add_argument('--resolve-method', type=str, help='Re-resolve records with this method')
    mode_group.add_argument('--status', action='store_true', help='Show pipeline state and history')

    parser.add_argument('--skip', action='append', default=[], choices=['resolve', 'compile', 'rebuild'],
                        help='Skip specific stages (can be repeated)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')

    args = parser.parse_args()

    # --- Status ---
    if args.status:
        show_status()
        return

    # --- Check for interrupted reprocess ---
    marker = _read_reprocess_marker()
    if marker and not args.new:
        print(f'Resuming interrupted reprocess from {marker["from_stage"]}')
        print(f'  Started: {marker["created"]}')
        print(f'  Completed stages: {", ".join(marker.get("progress", {}).keys()) or "none"}')
        print()

    overall_start = time.time()
    mode_label = 'new' if args.new else ('full' if args.full else f'from_{args.from_stage}' if args.from_stage else 'resolve_retry')

    print(f'RT Pipeline Orchestrator')
    print(f'Mode: {mode_label}')
    if args.skip:
        print(f'Skipping: {", ".join(args.skip)}')
    if args.dry_run:
        print(f'DRY RUN — no changes will be made')
    print()

    # --- Resolve-specific modes ---
    if args.resolve_unresolved or args.resolve_method:
        if args.dry_run:
            print('Would run resolve with retry flags.')
            return
        run_resolve(mode='retry', reprocess_unresolved=args.resolve_unresolved,
                    reprocess_method=args.resolve_method)
        if 'compile' not in args.skip:
            run_compile()
        if 'rebuild' not in args.skip:
            run_rebuild()
        elapsed = time.time() - overall_start
        print(f'\nDone in {elapsed:.0f}s')
        return

    # --- Determine which stages to run ---
    if args.new:
        stages_to_run = ['extract', 'classify', 'normalize', 'resolve', 'compile', 'rebuild']
        stage_mode = 'new'
    elif args.full:
        stages_to_run = ['extract', 'classify', 'normalize', 'resolve', 'compile', 'rebuild']
        stage_mode = 'all'
    elif args.from_stage:
        stage_idx = STAGE_ORDER.index(args.from_stage)
        stages_to_run = STAGE_ORDER[stage_idx:]
        stage_mode = 'all'

    # Apply skip flags
    for skip in args.skip:
        if skip in stages_to_run:
            stages_to_run.remove(skip)

    # --- Dry run (before creating any markers) ---
    if args.dry_run:
        print(f'Stages to run: {" → ".join(stages_to_run)}')
        if stage_mode == 'new':
            for stage, in_dir, out_dir in [
                ('classify', ASSEMBLED_DIR, CLASSIFIED_DIR),
                ('normalize', CLASSIFIED_DIR, ADDRESSES_DIR),
                ('resolve', ADDRESSES_DIR, PARCEL_LINKS_DIR),
            ]:
                if stage in stages_to_run:
                    pending = _pending_files(in_dir, out_dir)
                    total = len(_json_files(in_dir))
                    print(f'  {stage}: {len(pending)} pending out of {total} total')

            # Check for new extract folders
            if 'extract' in stages_to_run:
                all_folders = []
                if os.path.isdir(SOURCE_PAGES_DIR):
                    for region in os.listdir(SOURCE_PAGES_DIR):
                        rp = os.path.join(SOURCE_PAGES_DIR, region)
                        if not os.path.isdir(rp) or region.startswith('.'): continue
                        for pt in os.listdir(rp):
                            tp = os.path.join(rp, pt)
                            if not os.path.isdir(tp) or pt.startswith('.'): continue
                            for pg in os.listdir(tp):
                                pp = os.path.join(tp, pg)
                                if os.path.isdir(pp) and pg.startswith('p'):
                                    key = f'{region}/{pt}/{pg}'
                                    if not os.path.isdir(os.path.join(EXTRACTED_DIR, key)):
                                        all_folders.append(key)
                print(f'  extract: {len(all_folders)} unextracted page folders')
        else:
            for stage, directory in [
                ('classify', ASSEMBLED_DIR),
                ('normalize', CLASSIFIED_DIR),
                ('resolve', ADDRESSES_DIR),
            ]:
                if stage in stages_to_run:
                    print(f'  {stage}: {len(_json_files(directory))} records (full reprocess)')
        return

    # --- Create reprocess marker (only for actual runs, not dry runs) ---
    if stage_mode == 'all' and not marker:
        from_label = 'extract' if args.full else args.from_stage
        _write_reprocess_marker(from_label, skip_stages=args.skip,
                                reason=f'--{"full" if args.full else "from " + args.from_stage}')
        marker = _read_reprocess_marker()

    # --- Execute stages ---
    results = {}

    if 'extract' in stages_to_run:
        if stage_mode == 'new':
            folders, assembled = run_extract_new()
            results['extract'] = assembled
        else:
            # Full reprocess of extract isn't common — run the full pipeline
            print(f'\n--- Extract (full) ---')
            success, elapsed, stdout = _run_subprocess(
                [sys.executable, 'run_pipeline.py'], label='extract full'
            )
            _log_entry('extract', 'all', 0, 0, elapsed, 0 if success else 1)

    if 'classify' in stages_to_run:
        count, elapsed = run_classify(mode=stage_mode)
        results['classify'] = count
        if marker:
            _update_marker_progress('classify', count)

    if 'normalize' in stages_to_run:
        count, elapsed = run_normalize(mode=stage_mode)
        results['normalize'] = count
        if marker:
            _update_marker_progress('normalize', count)

    if 'resolve' in stages_to_run:
        count, elapsed = run_resolve(mode=stage_mode)
        results['resolve'] = count
        if marker:
            _update_marker_progress('resolve', count)

    if 'compile' in stages_to_run:
        count, elapsed = run_compile()
        results['compile'] = count

    if 'rebuild' in stages_to_run:
        count, elapsed = run_rebuild()
        results['rebuild'] = 0

    # Clean up reprocess marker if we completed a full reprocess
    if marker and stage_mode == 'all':
        _delete_reprocess_marker()
        print(f'\nReprocess complete — marker cleared.')

    overall_elapsed = time.time() - overall_start
    print()
    print(f'Pipeline complete in {overall_elapsed:.0f}s')
    print(f'  Results: {results}')


if __name__ == '__main__':
    main()
