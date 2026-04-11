"""
Run classifier — processes deduped records through the classifier.
Uses parallel processing for speed.

Reads from pipeline/deduped/ (output of dedup stage). If deduped/ doesn't
exist or is empty, falls back to pipeline/assembled/ for backward compat.

Modes:
    Default:      Only classify files that don't have a classified
                  counterpart yet (incremental — safe for daily use).
    --all:        Classify ALL files, overwriting existing output.
                  Use after fixing the classifier to reprocess everything.
    --files:      Classify only the specified files (comma-separated or glob).

Usage:
    python3 run_classifier.py                    # incremental (new records only)
    python3 run_classifier.py --all              # reprocess everything
    python3 run_classifier.py --files "RT198*.json"  # specific files
    python3 run_classifier.py --workers 4        # limit to 4 cores
    python3 run_classifier.py --limit 100        # first 100 records
    python3 run_classifier.py --single           # single-threaded (for debugging)
"""

import json
import fnmatch
import os
import sys
import time
import argparse
from multiprocessing import Pool, cpu_count

from classifier.classify import classify_record


def classify_file(args):
    """Classify a single file. Designed for multiprocessing.Pool."""
    input_path, classified_path = args
    try:
        with open(input_path) as f:
            assembled = json.load(f)
        classified = classify_record(assembled)
        with open(classified_path, 'w') as f:
            json.dump(classified, f, indent=2)
        return (True, None)
    except Exception as e:
        return (False, f'{os.path.basename(input_path)}: {e}')


def find_pending_files(input_dir, classified_dir):
    """Find input files that don't have a classified counterpart yet."""
    input_files = set(f for f in os.listdir(input_dir) if f.endswith('.json'))
    classified_files = set(f for f in os.listdir(classified_dir) if f.endswith('.json'))
    return sorted(input_files - classified_files)


def resolve_input_dir(config):
    """Determine the input directory: deduped/ if populated, else assembled/.

    After the dedup stage is integrated, deduped/ is the canonical input.
    Falls back to assembled/ for backward compatibility.
    """
    deduped_dir = os.path.join(config['pipeline_output'], 'deduped')
    assembled_dir = os.path.join(config['pipeline_output'], 'assembled')

    if os.path.isdir(deduped_dir) and any(f.endswith('.json') for f in os.listdir(deduped_dir)):
        return deduped_dir
    return assembled_dir


def main():
    parser = argparse.ArgumentParser(description='Run classifier on assembled records')
    parser.add_argument('--all', action='store_true', help='Reprocess ALL records (overwrite existing)')
    parser.add_argument('--files', type=str, help='Process only these files (comma-separated names or glob pattern)')
    parser.add_argument('--workers', type=int, default=None, help='Number of parallel workers (default: all cores)')
    parser.add_argument('--limit', type=int, help='Limit to first N records')
    parser.add_argument('--single', action='store_true', help='Single-threaded (for debugging)')
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path) as f:
        config = json.load(f)

    input_dir = resolve_input_dir(config)
    classified_dir = os.path.join(config['pipeline_output'], 'classified')
    os.makedirs(classified_dir, exist_ok=True)

    input_label = 'deduped' if 'deduped' in input_dir else 'assembled'

    # Determine which files to process
    if args.files:
        # Explicit file list or glob pattern
        all_input = sorted(f for f in os.listdir(input_dir) if f.endswith('.json'))
        parts = [p.strip() for p in args.files.split(',')]
        files = []
        for pattern in parts:
            matched = fnmatch.filter(all_input, pattern)
            files.extend(matched)
        files = sorted(set(files))
        mode = 'files'
    elif args.all:
        # Reprocess everything
        files = sorted(f for f in os.listdir(input_dir) if f.endswith('.json'))
        mode = 'all'
    else:
        # Incremental: only new files
        files = find_pending_files(input_dir, classified_dir)
        mode = 'new'

    if args.limit:
        files = files[:args.limit]

    skipped = 0
    if mode == 'new':
        total_input = len([f for f in os.listdir(input_dir) if f.endswith('.json')])
        skipped = total_input - len(files)

    tasks = [
        (os.path.join(input_dir, f), os.path.join(classified_dir, f))
        for f in files
    ]

    workers = 1 if args.single else (args.workers or cpu_count())

    if not tasks:
        print(f'Cleo Engine — Classifier')
        print(f'Nothing to classify (0 pending records)')
        return

    print(f'Cleo Engine — Classifier')
    print(f'Mode: {mode}  (reading from {input_label}/)')
    print(f'Records to process: {len(tasks)}' + (f'  (skipped {skipped} already classified)' if skipped else ''))
    print(f'Workers: {workers}')
    print()

    start = time.time()
    errors = []
    done = 0

    if workers == 1:
        for i, task in enumerate(tasks):
            success, err = classify_file(task)
            done += 1
            if not success:
                errors.append(err)
            if (i + 1) % 500 == 0:
                elapsed = time.time() - start
                print(f'  [{i+1}/{len(tasks)}] {elapsed:.0f}s')
    else:
        with Pool(workers) as pool:
            for i, (success, err) in enumerate(pool.imap_unordered(classify_file, tasks, chunksize=50)):
                done += 1
                if not success:
                    errors.append(err)
                if (i + 1) % 2000 == 0 or (i + 1) == len(tasks):
                    elapsed = time.time() - start
                    print(f'  [{i+1}/{len(tasks)}] {elapsed:.0f}s')

    elapsed = time.time() - start
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  Classified: {done}')
    print(f'  Errors: {len(errors)}')

    if errors:
        print()
        print('First 10 errors:')
        for e in errors[:10]:
            print(f'  {e}')


if __name__ == '__main__':
    main()
