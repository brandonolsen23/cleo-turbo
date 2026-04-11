"""
RT Pipeline Orchestrator — runs all stages in order with dependency checks.

Usage:
    python engines/rt/run_all.py                    (full pipeline)
    python engines/rt/run_all.py --from resolve     (resume from a specific stage)
    python engines/rt/run_all.py --stage validate   (run just one stage)
    python engines/rt/run_all.py --skip geocode     (skip a stage)
    python engines/rt/run_all.py --dry-run           (show what would run)
"""

import json
import os
import subprocess
import sys
import time
import argparse
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATUS_FILE = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', '_stage_status.json')

sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json, safe_read_json


STAGES = [
    {
        'name': 'normalize',
        'description': 'Address normalization',
        'command': ['python3', '-m', 'address_normalizer.run'],
        'cwd': os.path.join(PROJECT_ROOT, 'engines', 'rt'),
        'timeout': 3600,  # 1 hour
    },
    {
        'name': 'resolve',
        'description': 'Unified parcel resolution (v2: PIN bridge + Ontario geocoder + AgMaps)',
        'command': ['python3', '-m', 'parcel_resolver.resolve_v2'],
        'cwd': os.path.join(PROJECT_ROOT, 'engines', 'rt'),
        'timeout': None,  # no timeout — can take hours (155K records @ ~1/sec)
    },
    {
        'name': 'compile',
        'description': 'Compile pipeline stages → clean records',
        'command': ['python3', 'compile.py'],
        'cwd': os.path.join(PROJECT_ROOT, 'engines', 'rt'),
        'timeout': 1800,  # 30 min
    },
    {
        'name': 'validate',
        'description': 'Pre-compile validation',
        'command': ['python3', 'engines/rt/validate.py'],
        'cwd': PROJECT_ROOT,
        'timeout': 300,  # 5 min
    },
    {
        'name': 'rebuild',
        'description': 'Database rebuild (via rebuild.py subprocess)',
        'command': ['python3', 'rebuild.py'],
        'cwd': PROJECT_ROOT,
        'timeout': 1800,  # 30 min
    },
]


def load_status():
    return safe_read_json(STATUS_FILE) or {}


def save_status(status):
    safe_write_json(STATUS_FILE, status)


def run_stage(stage, dry_run=False):
    """Run a single pipeline stage."""
    name = stage['name']
    desc = stage['description']
    cmd = stage['command']
    cwd = stage['cwd']

    print(f'\n{"="*60}')
    print(f'Stage: {name} — {desc}')
    print(f'Command: {" ".join(cmd)}')
    print(f'{"="*60}')

    if dry_run:
        print('  (dry-run — skipping)')
        return True

    start = time.time()

    try:
        stage_timeout = stage.get('timeout')  # None = no timeout
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=stage_timeout,
        )
        elapsed = time.time() - start
        success = result.returncode == 0

        # Update status
        status = load_status()
        status[name] = {
            'last_run': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': round(elapsed, 1),
            'success': success,
            'exit_code': result.returncode,
        }
        save_status(status)

        if success:
            print(f'\n  Completed in {elapsed:.1f}s')
        else:
            print(f'\n  FAILED (exit code {result.returncode}) after {elapsed:.1f}s')

        return success

    except subprocess.TimeoutExpired:
        print(f'\n  TIMEOUT after 2 hours')
        return False
    except Exception as e:
        print(f'\n  ERROR: {e}')
        return False


def run(from_stage=None, single_stage=None, skip_stages=None, dry_run=False):
    """Run the full pipeline or a subset of stages."""
    skip = set(skip_stages.split(',')) if skip_stages else set()

    # Determine which stages to run
    stages_to_run = STAGES
    if single_stage:
        stages_to_run = [s for s in STAGES if s['name'] == single_stage]
        if not stages_to_run:
            print(f'ERROR: Unknown stage "{single_stage}"')
            print(f'Available: {", ".join(s["name"] for s in STAGES)}')
            sys.exit(1)
    elif from_stage:
        found = False
        filtered = []
        for s in STAGES:
            if s['name'] == from_stage:
                found = True
            if found:
                filtered.append(s)
        if not filtered:
            print(f'ERROR: Unknown stage "{from_stage}"')
            sys.exit(1)
        stages_to_run = filtered

    print('Cleo RT Pipeline Orchestrator')
    print(f'Stages: {", ".join(s["name"] for s in stages_to_run)}')
    if skip:
        print(f'Skipping: {", ".join(skip)}')
    if dry_run:
        print('Mode: DRY RUN')
    print()

    # Show current status
    status = load_status()
    if status:
        print('Last run status:')
        for name, info in status.items():
            last = info.get('last_run', '?')[:19]
            ok = '✓' if info.get('success') else '✗'
            print(f'  {ok} {name}: {last} ({info.get("elapsed_seconds", "?")}s)')
        print()

    total_start = time.time()
    failed = []

    for stage in stages_to_run:
        if stage['name'] in skip:
            print(f'\nSkipping: {stage["name"]}')
            continue

        success = run_stage(stage, dry_run=dry_run)

        if not success and stage['name'] == 'validate':
            print('\n  Validation failed. Use --skip validate to bypass.')
            print('  Or fix the issues and re-run.')
            failed.append(stage['name'])
            break

        if not success and not stage.get('optional'):
            print(f'\n  Stage {stage["name"]} failed. Stopping pipeline.')
            failed.append(stage['name'])
            break

    total_elapsed = time.time() - total_start
    print(f'\n{"="*60}')
    if failed:
        print(f'Pipeline STOPPED — failed at: {", ".join(failed)}')
    else:
        print(f'Pipeline complete in {total_elapsed:.1f}s')
    print(f'{"="*60}')


def main():
    parser = argparse.ArgumentParser(description='RT Pipeline Orchestrator')
    parser.add_argument('--from', dest='from_stage', type=str,
                        help='Resume from this stage')
    parser.add_argument('--stage', type=str,
                        help='Run only this stage')
    parser.add_argument('--skip', type=str,
                        help='Comma-separated stages to skip')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    run(
        from_stage=args.from_stage,
        single_stage=args.stage,
        skip_stages=args.skip,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    main()
