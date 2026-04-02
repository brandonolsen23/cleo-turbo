"""
Pipeline Runner — robust wrapper for long-running pipeline stages.

Runs stages to completion with no timeout, writes live progress to
data/pipeline-status.json, and sends a macOS notification when done.
Detached from terminal — survives disconnects and sleep.

Usage:
    python engines/rt/pipeline_runner.py resolve          (just resolver)
    python engines/rt/pipeline_runner.py all               (resolve → compile → validate → rebuild)
    python engines/rt/pipeline_runner.py all --from compile (resume from compile)
"""

import json
import os
import subprocess
import sys
import time
import threading
import argparse
from datetime import datetime, timezone
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATUS_FILE = os.path.join(PROJECT_ROOT, 'data', 'pipeline-status.json')
LOG_FILE = os.path.join(PROJECT_ROOT, 'data', 'pipeline-runner.log')

sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json, safe_read_json


STAGES = {
    'resolve': {
        'description': 'Parcel resolution with cross-validation',
        'command': ['python3', '-m', 'parcel_resolver.resolve'],
        'cwd': os.path.join(PROJECT_ROOT, 'engines', 'rt'),
        'progress_dir': os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'parcel_links'),
        'total_dir': os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'addresses'),
    },
    'compile': {
        'description': 'Compile pipeline stages → clean records',
        'command': ['python3', 'compile.py'],
        'cwd': os.path.join(PROJECT_ROOT, 'engines', 'rt'),
        'progress_dir': os.path.join(PROJECT_ROOT, 'clean-data', 'rt'),
    },
    'validate': {
        'description': 'Pre-compile validation',
        'command': ['python3', 'engines/rt/validate.py'],
        'cwd': PROJECT_ROOT,
    },
    'rebuild': {
        'description': 'Database rebuild',
        'command': ['python3', 'rebuild.py'],
        'cwd': PROJECT_ROOT,
    },
}

ALL_ORDER = ['resolve', 'compile', 'validate', 'rebuild']


def _notify(title, message):
    """Send a macOS notification."""
    try:
        escaped_msg = message.replace("'", "'\"'\"'")
        escaped_title = title.replace("'", "'\"'\"'")
        os.system(f"osascript -e 'display notification \"{escaped_msg}\" with title \"{escaped_title}\"'")
    except Exception:
        pass


def _count_files(directory):
    """Count JSON files in a directory."""
    if not os.path.isdir(directory):
        return 0
    return len([f for f in os.listdir(directory) if f.endswith('.json') and not f.startswith('_')])


def _count_methods(directory):
    """Count resolution methods in parcel_links files (sample for speed)."""
    if not os.path.isdir(directory):
        return {}
    methods = Counter()
    files = [f for f in os.listdir(directory) if f.endswith('.json')]
    # Sample every 10th file for speed
    for f in files[::10]:
        try:
            d = json.load(open(os.path.join(directory, f)))
            methods[d.get('method', 'unknown')] += 1
        except Exception:
            pass
    # Scale up
    scale = len(files) / max(len(files[::10]), 1)
    return {k: int(v * scale) for k, v in methods.items()}


def write_status(stage_name, status, extra=None):
    """Write pipeline status to JSON file."""
    data = {
        'stage': stage_name,
        'stage_description': STAGES.get(stage_name, {}).get('description', ''),
        'status': status,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data.update(extra)
    safe_write_json(STATUS_FILE, data)


def run_stage(stage_name, log_fh):
    """Run a single pipeline stage to completion with progress tracking."""
    stage = STAGES[stage_name]
    cmd = stage['command']
    cwd = stage['cwd']

    print(f'\n{"="*60}', file=log_fh, flush=True)
    print(f'Stage: {stage_name} — {stage["description"]}', file=log_fh, flush=True)
    print(f'Started: {datetime.now().isoformat()}', file=log_fh, flush=True)
    print(f'{"="*60}', file=log_fh, flush=True)

    start = time.time()
    total = _count_files(stage.get('total_dir', '')) or 0

    write_status(stage_name, 'running', {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'progress': {'total': total, 'completed': 0, 'percent': 0},
    })

    # Start the subprocess
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    # Progress monitoring thread
    stop_monitor = threading.Event()

    def monitor_progress():
        progress_dir = stage.get('progress_dir')
        while not stop_monitor.is_set():
            if progress_dir:
                completed = _count_files(progress_dir)
                elapsed = time.time() - start
                pct = (completed / total * 100) if total > 0 else 0
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (total - completed) / rate if rate > 0 else 0

                progress = {
                    'total': total,
                    'completed': completed,
                    'percent': round(pct, 1),
                    'rate_per_sec': round(rate, 1),
                    'elapsed_seconds': int(elapsed),
                    'estimated_remaining_seconds': int(remaining),
                }

                # For resolve stage, sample methods
                if stage_name == 'resolve':
                    progress['methods'] = _count_methods(progress_dir)

                write_status(stage_name, 'running', {
                    'started_at': datetime.now(timezone.utc).isoformat(),
                    'progress': progress,
                })

            stop_monitor.wait(30)  # Update every 30 seconds

    monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
    monitor_thread.start()

    # Wait for completion (NO timeout)
    proc.wait()

    stop_monitor.set()
    monitor_thread.join(timeout=5)

    elapsed = time.time() - start
    success = proc.returncode == 0

    completed = _count_files(stage.get('progress_dir', '')) if stage.get('progress_dir') else 0

    write_status(stage_name, 'completed' if success else 'failed', {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds': int(elapsed),
        'exit_code': proc.returncode,
        'progress': {
            'total': total,
            'completed': completed,
            'percent': round(completed / total * 100, 1) if total > 0 else 100,
        },
    })

    print(f'\n{"="*60}', file=log_fh, flush=True)
    print(f'Stage {stage_name}: {"COMPLETED" if success else "FAILED"} in {elapsed:.0f}s', file=log_fh, flush=True)
    print(f'{"="*60}', file=log_fh, flush=True)

    return success


def run(stages_to_run, from_stage=None):
    """Run one or more pipeline stages."""
    if from_stage:
        idx = stages_to_run.index(from_stage) if from_stage in stages_to_run else 0
        stages_to_run = stages_to_run[idx:]

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with open(LOG_FILE, 'a') as log_fh:
        print(f'\n\nPipeline Runner started: {datetime.now().isoformat()}', file=log_fh, flush=True)
        print(f'Stages: {", ".join(stages_to_run)}', file=log_fh, flush=True)

        total_start = time.time()

        for stage_name in stages_to_run:
            if stage_name not in STAGES:
                print(f'Unknown stage: {stage_name}', file=log_fh, flush=True)
                continue

            success = run_stage(stage_name, log_fh)

            if not success:
                _notify('Cleo Pipeline Failed', f'Stage "{stage_name}" failed')
                print(f'\nPipeline stopped at {stage_name}', file=log_fh, flush=True)
                return False

        total_elapsed = time.time() - total_start
        minutes = int(total_elapsed / 60)

        _notify('Cleo Pipeline Complete', f'All stages done in {minutes} min')
        print(f'\nPipeline complete in {total_elapsed:.0f}s', file=log_fh, flush=True)
        write_status(stages_to_run[-1], 'all_complete', {
            'total_elapsed_seconds': int(total_elapsed),
        })

        return True


def main():
    parser = argparse.ArgumentParser(description='Pipeline Runner')
    parser.add_argument('stage', choices=list(STAGES.keys()) + ['all'],
                        help='Stage to run, or "all" for full pipeline')
    parser.add_argument('--from', dest='from_stage', type=str,
                        help='When using "all", start from this stage')
    args = parser.parse_args()

    if args.stage == 'all':
        stages = list(ALL_ORDER)
    else:
        stages = [args.stage]

    run(stages, from_stage=args.from_stage)


if __name__ == '__main__':
    main()
