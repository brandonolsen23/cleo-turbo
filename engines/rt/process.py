"""
Pipeline Orchestrator — single entry point for processing RT records.

Modes:
    --new               Process only records missing from downstream stages (daily use).
    --from STAGE        Reprocess ALL records from a stage onward (after fixing a bug).
    --reprocess RT_IDS  Reprocess specific RT IDs from a given stage (targeted fix).

Stages: extract → dedup → classify → normalize → resolve → compile → rebuild

Usage:
    python process.py --new                          # daily: process new records only
    python process.py --new --skip resolve           # daily: skip resolve (do it later)
    python process.py --from dedup                   # re-dedup + reclassify + etc.
    python process.py --from classify                # reprocess all from classify onward
    python process.py --from classify --skip resolve # reclassify everything, keep parcel links
    python process.py --from normalize               # renormalize + compile + rebuild
    python process.py --full                         # everything from extract onward
    python process.py --resolve-unresolved           # retry only unresolved parcels
    python process.py --reprocess RT198249 --from classify   # reprocess one RT from classify
    python process.py --reprocess RT198249 --from scrape     # re-scrape + full reprocess
    python process.py --reprocess RT198249,RT198246 --from normalize  # multiple RT IDs
    python process.py --status                       # show pipeline state
    python process.py --new --dry-run                # show what would be done
"""

import glob
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
DEDUPED_DIR = os.path.join(PIPELINE_DIR, 'deduped')
CLASSIFIED_DIR = os.path.join(PIPELINE_DIR, 'classified')
ADDRESSES_DIR = os.path.join(PIPELINE_DIR, 'addresses')
PARCEL_LINKS_DIR = os.path.join(PIPELINE_DIR, 'parcel_links')
EXTRACTED_DIR = os.path.join(PIPELINE_DIR, 'extracted')

CLEAN_DATA_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'rt')

SOURCE_PAGES_DIR = os.path.join(PROJECT_ROOT, 'raw-data', 'rt', 'pages')

LOG_FILE = os.path.join(PIPELINE_DIR, '_processing_log.jsonl')
REPROCESS_MARKER = os.path.join(PIPELINE_DIR, '_reprocess.json')
LOCKFILE = os.path.join(PARCEL_LINKS_DIR, '.resolve_v2.lock')

STAGE_ORDER = ['extract', 'dedup', 'classify', 'normalize', 'resolve', 'compile', 'rebuild']


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


def run_dedup(mode='new'):
    """Run the dedup stage — picks best assembled record per RT ID."""
    if mode == 'new':
        # Check: any assembled files whose RT ID isn't in deduped/?
        assembled_files = _json_files(ASSEMBLED_DIR)
        deduped_files = _json_files(DEDUPED_DIR)
        # Get RT IDs already deduped (from filename prefix)
        deduped_rt_ids = set(f.split('__')[0] for f in deduped_files)
        assembled_rt_ids = set(f.split('__')[0] for f in assembled_files)
        pending_rt_ids = assembled_rt_ids - deduped_rt_ids
        if not pending_rt_ids:
            print(f'\n--- Dedup ---')
            print(f'  Nothing to dedup (0 pending)')
            return 0, 0
        count = len(pending_rt_ids)
        print(f'\n--- Dedup ---')
        print(f'  {count} new RT IDs to dedup')
        cmd = [sys.executable, 'dedup.py']
    elif mode == 'all':
        count = len(set(f.split('__')[0] for f in _json_files(ASSEMBLED_DIR)))
        print(f'\n--- Dedup (reprocess all) ---')
        print(f'  {count} RT IDs to dedup')
        cmd = [sys.executable, 'dedup.py', '--all']

    start = time.time()
    success, elapsed, stdout = _run_subprocess(cmd, label='dedup')

    errors = 0
    if stdout:
        for line in stdout.split('\n'):
            if 'Errors:' in line:
                try:
                    errors = int(line.split(':')[1].strip())
                except (ValueError, IndexError):
                    pass

    _log_entry('dedup', mode, count, 0, elapsed, errors)
    return count, elapsed


def _classify_input_dir():
    """Return the dir the classifier will read from: deduped/ if populated, else assembled/."""
    if os.path.isdir(DEDUPED_DIR) and any(f.endswith('.json') for f in os.listdir(DEDUPED_DIR)):
        return DEDUPED_DIR
    return ASSEMBLED_DIR


def run_classify(mode='new', file_pattern=None):
    """Run the classifier stage."""
    input_dir = _classify_input_dir()
    if mode == 'new':
        pending = _pending_files(input_dir, CLASSIFIED_DIR)
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
        count = len(_json_files(input_dir))
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

    skipped = len(_json_files(input_dir)) - count if mode == 'new' else 0
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
# Targeted Reprocess (specific RT IDs)
# ---------------------------------------------------------------------------

# Stages in pipeline order and their directories + filename patterns
_STAGE_ARTIFACT_MAP = {
    'assembled':    (ASSEMBLED_DIR,    '{rt_id}__*.json'),
    'deduped':      (DEDUPED_DIR,      '{rt_id}__*.json'),
    'classified':   (CLASSIFIED_DIR,   '{rt_id}__*.json'),
    'addresses':    (ADDRESSES_DIR,    '{rt_id}__*.json'),
    'parcel_links': (PARCEL_LINKS_DIR, '{rt_id}__*.json'),
    'clean':        (CLEAN_DATA_DIR,   '{rt_id}.json'),
}

# Which artifact stages to delete for each --from option
# e.g., --from classify deletes classified, addresses, parcel_links, clean
_REPROCESS_STAGE_ORDER = ['assembled', 'deduped', 'classified', 'addresses', 'parcel_links', 'clean']

# Mapping from --from stage names to the first artifact stage to delete
_FROM_STAGE_TO_ARTIFACT = {
    'scrape':    'assembled',   # delete everything
    'extract':   'assembled',   # delete everything (re-extract produces new assembled)
    'dedup':     'deduped',     # keep assembled, delete deduped onward
    'classify':  'classified',  # keep assembled+deduped, delete classified onward
    'normalize': 'addresses',   # keep through classified, delete addresses onward
    'resolve':   'parcel_links',# keep through addresses, delete parcel_links onward
}


def delete_artifacts(rt_ids, from_stage, dry_run=False):
    """Delete pipeline artifacts for specific RT IDs from a stage onward.

    Returns dict of {stage: count_deleted}.
    """
    first_artifact = _FROM_STAGE_TO_ARTIFACT.get(from_stage)
    if not first_artifact:
        raise ValueError(f"Unknown from_stage: {from_stage}")

    start_idx = _REPROCESS_STAGE_ORDER.index(first_artifact)
    stages_to_clear = _REPROCESS_STAGE_ORDER[start_idx:]

    deleted = {}
    for stage in stages_to_clear:
        directory, pattern_template = _STAGE_ARTIFACT_MAP[stage]
        if not os.path.isdir(directory):
            deleted[stage] = 0
            continue

        count = 0
        for rt_id in rt_ids:
            pattern = os.path.join(directory, pattern_template.format(rt_id=rt_id))
            matches = glob.glob(pattern)
            for fpath in matches:
                if dry_run:
                    print(f'    Would delete: {os.path.basename(fpath)} from {stage}/')
                else:
                    os.remove(fpath)
                count += 1
        deleted[stage] = count

    return deleted


def _read_assembled_metadata(rt_id):
    """Read source_folder, position, and sale_date from an assembled record.

    Needed for re-scrape to know where the original HTML lives and what date
    range to search. Returns dict or None if no assembled record found.
    """
    pattern = os.path.join(ASSEMBLED_DIR, f'{rt_id}__*.json')
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Use first match (should be only one after dedup, but assembled may have multiples)
    with open(matches[0]) as f:
        data = json.load(f)
    return {
        'source_folder': data.get('source_folder'),
        'position': data.get('position'),
        'sale_date': data.get('detail', {}).get('header', {}).get('date_text', ''),
        'filename': os.path.basename(matches[0]),
    }


def run_targeted_reprocess(rt_ids, from_stage, skip_stages=None, dry_run=False):
    """Reprocess specific RT IDs from a given stage.

    1. Read metadata (for scrape mode)
    2. Delete downstream artifacts
    3. Re-scrape if needed
    4. Run pipeline stages for just these RT IDs
    """
    skip_stages = skip_stages or []
    rt_id_list = ', '.join(rt_ids)
    print(f'Targeted Reprocess')
    print(f'  RT IDs:     {rt_id_list}')
    print(f'  From stage: {from_stage}')
    if skip_stages:
        print(f'  Skipping:   {", ".join(skip_stages)}')
    if dry_run:
        print(f'  DRY RUN — no changes will be made')
    print()

    overall_start = time.time()

    # --- Step 1: Read metadata before deletion (needed for re-scrape) ---
    metadata = {}
    if from_stage == 'scrape':
        for rt_id in rt_ids:
            meta = _read_assembled_metadata(rt_id)
            if meta:
                metadata[rt_id] = meta
                print(f'  {rt_id}: source={meta["source_folder"]}, pos={meta["position"]}, date={meta["sale_date"]}')
            else:
                print(f'  {rt_id}: WARNING — no assembled record found (will try scrape anyway)')

    # --- Step 2: Delete downstream artifacts ---
    print(f'\n--- Delete Artifacts (from {from_stage}) ---')
    deleted = delete_artifacts(rt_ids, from_stage, dry_run=dry_run)
    for stage, count in deleted.items():
        if count > 0:
            verb = 'Would delete' if dry_run else 'Deleted'
            print(f'  {verb} {count} file(s) from {stage}/')
    total_deleted = sum(deleted.values())
    if total_deleted == 0:
        print(f'  No artifacts found to delete.')

    if dry_run:
        print(f'\nDry run complete. Would delete {total_deleted} file(s) total.')
        return deleted

    # --- Step 3: Re-scrape if from_stage == 'scrape' ---
    if from_stage == 'scrape':
        print(f'\n--- Re-scrape ---')
        rescrape_script = os.path.join(ENGINE_DIR, 'scraper', 'rescrape.py')
        for rt_id in rt_ids:
            meta = metadata.get(rt_id)
            cmd = [sys.executable, rescrape_script, rt_id]
            if meta and meta['source_folder']:
                cmd.extend(['--source-folder', meta['source_folder']])
            if meta and meta['position'] is not None:
                cmd.extend(['--position', str(meta['position'])])

            success, elapsed, stdout = _run_subprocess(cmd, cwd=ENGINE_DIR, label=f'rescrape {rt_id}')
            if not success:
                print(f'  WARNING: Re-scrape of {rt_id} failed — continuing with pipeline')

    # --- Step 4: Re-extract if from_stage in ('scrape', 'extract') ---
    if from_stage in ('scrape', 'extract'):
        print(f'\n--- Extract (targeted) ---')
        # Re-extract the page folders that contain our RT IDs
        folders_to_extract = set()
        for rt_id in rt_ids:
            meta = metadata.get(rt_id) or _read_assembled_metadata(rt_id)
            if meta and meta.get('source_folder'):
                folders_to_extract.add(meta['source_folder'])

        for folder_key in folders_to_extract:
            success, elapsed, stdout = _run_subprocess(
                [sys.executable, 'run_pipeline.py', '--folder', folder_key],
                label=f'extract {folder_key}'
            )

    # --- Step 5: Dedup (only for targeted RT IDs) ---
    if from_stage in ('scrape', 'extract', 'dedup') and 'dedup' not in skip_stages:
        print(f'\n--- Dedup (targeted) ---')
        # Dedup in incremental mode picks up RT IDs missing from deduped/
        # Since we deleted their deduped files, they'll be re-deduped
        run_dedup(mode='new')

    # --- Step 6: Classify (targeted via --files) ---
    if from_stage in ('scrape', 'extract', 'dedup', 'classify') and 'classify' not in skip_stages:
        for rt_id in rt_ids:
            run_classify(mode='files', file_pattern=f'{rt_id}__*.json')

    # --- Step 7: Normalize (targeted via --files) ---
    if from_stage in ('scrape', 'extract', 'dedup', 'classify', 'normalize') and 'normalize' not in skip_stages:
        for rt_id in rt_ids:
            run_normalize(mode='files', file_pattern=f'{rt_id}__*.json')

    # --- Step 8: Resolve (incremental — picks up missing parcel_links) ---
    if from_stage in ('scrape', 'extract', 'dedup', 'classify', 'normalize', 'resolve') and 'resolve' not in skip_stages:
        run_resolve(mode='new')

    # --- Step 9: Compile + Rebuild (always full, they're fast) ---
    if 'compile' not in skip_stages:
        run_compile()
    if 'rebuild' not in skip_stages:
        run_rebuild()

    overall_elapsed = time.time() - overall_start
    print()
    print(f'Targeted reprocess complete in {overall_elapsed:.0f}s')
    print(f'  RT IDs: {rt_id_list}')
    print(f'  Deleted: {deleted}')

    _log_entry('reprocess', f'targeted_{from_stage}', len(rt_ids), 0, overall_elapsed, 0)
    return deleted


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status():
    """Display current pipeline state and recent processing history."""
    print('Pipeline Status')
    print('=' * 60)

    assembled = len(_json_files(ASSEMBLED_DIR))
    deduped = len(_json_files(DEDUPED_DIR))
    classified = len(_json_files(CLASSIFIED_DIR))
    addresses = len(_json_files(ADDRESSES_DIR))
    parcel_links = len(_json_files(PARCEL_LINKS_DIR))
    clean_data = len(_json_files(CLEAN_DATA_DIR)) if os.path.isdir(CLEAN_DATA_DIR) else 0

    # Pending dedup: unique RT IDs in assembled that aren't in deduped
    assembled_rt_ids = set(f.split('__')[0] for f in _json_files(ASSEMBLED_DIR))
    deduped_rt_ids = set(f.split('__')[0] for f in _json_files(DEDUPED_DIR))
    pending_dedup = len(assembled_rt_ids - deduped_rt_ids)

    # If deduped/ is empty (not yet backfilled), use assembled count for downstream pending
    classify_source = deduped if deduped > 0 else assembled
    pending_classify = classify_source - classified
    pending_normalize = classified - addresses
    pending_resolve = addresses - parcel_links

    print(f'  Assembled:     {assembled:>8,}')
    print(f'  Deduped:       {deduped:>8,}  ({pending_dedup} pending)' if pending_dedup else f'  Deduped:       {deduped:>8,}  (eliminates {assembled - deduped:,} dupes)')
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
  python process.py --from dedup                   Re-dedup + reclassify + etc.
  python process.py --from classify                Reprocess all from classify
  python process.py --from classify --skip resolve Fixed parser, keep parcel links
  python process.py --full                         Reprocess everything
  python process.py --resolve-unresolved           Retry unresolved parcels
  python process.py --status                       Show pipeline state
        """
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--new', action='store_true', help='Process only new/missing records')
    mode_group.add_argument('--from', dest='from_stage', choices=['extract', 'dedup', 'classify', 'normalize', 'resolve'],
                            help='Reprocess everything from this stage onward')
    mode_group.add_argument('--full', action='store_true', help='Reprocess everything from scratch')
    mode_group.add_argument('--resolve-unresolved', action='store_true', help='Retry only unresolved parcels')
    mode_group.add_argument('--resolve-method', type=str, help='Re-resolve records with this method')
    mode_group.add_argument('--reprocess', type=str, metavar='RT_IDS',
                            help='Reprocess specific RT IDs (comma-separated). Requires --from.')
    mode_group.add_argument('--status', action='store_true', help='Show pipeline state and history')

    parser.add_argument('--skip', action='append', default=[], choices=['dedup', 'resolve', 'compile', 'rebuild'],
                        help='Skip specific stages (can be repeated)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')
    parser.add_argument('--reprocess-from', dest='reprocess_from',
                        choices=['scrape', 'extract', 'dedup', 'classify', 'normalize', 'resolve'],
                        help='Stage to reprocess from (used with --reprocess)')

    args = parser.parse_args()

    # --- Status ---
    if args.status:
        show_status()
        return

    # --- Targeted reprocess ---
    if args.reprocess:
        if not args.reprocess_from:
            parser.error('--reprocess requires --reprocess-from to specify the starting stage')
        rt_ids = [r.strip().upper() for r in args.reprocess.split(',') if r.strip()]
        if not rt_ids:
            parser.error('No valid RT IDs provided')
        for rt_id in rt_ids:
            if not rt_id.startswith('RT') or not rt_id[2:].isdigit():
                parser.error(f'Invalid RT ID: {rt_id}')
        run_targeted_reprocess(
            rt_ids=rt_ids,
            from_stage=args.reprocess_from,
            skip_stages=args.skip,
            dry_run=args.dry_run,
        )
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
        stages_to_run = list(STAGE_ORDER)  # all stages
        stage_mode = 'new'
    elif args.full:
        stages_to_run = list(STAGE_ORDER)  # all stages
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
            # Dedup pending
            if 'dedup' in stages_to_run:
                assembled_rt_ids = set(f.split('__')[0] for f in _json_files(ASSEMBLED_DIR))
                deduped_rt_ids = set(f.split('__')[0] for f in _json_files(DEDUPED_DIR))
                pending_dedup = len(assembled_rt_ids - deduped_rt_ids)
                print(f'  dedup: {pending_dedup} new RT IDs out of {len(assembled_rt_ids)} total unique')

            classify_input = _classify_input_dir()
            for stage, in_dir, out_dir in [
                ('classify', classify_input, CLASSIFIED_DIR),
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
            if 'dedup' in stages_to_run:
                assembled_rt_ids = set(f.split('__')[0] for f in _json_files(ASSEMBLED_DIR))
                print(f'  dedup: {len(assembled_rt_ids)} unique RT IDs (full reprocess)')
            for stage, directory in [
                ('classify', _classify_input_dir()),
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

    if 'dedup' in stages_to_run:
        count, elapsed = run_dedup(mode=stage_mode)
        results['dedup'] = count
        if marker:
            _update_marker_progress('dedup', count)

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
