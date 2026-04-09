"""
RT Watcher — monitors for new Realtrack HTML files and auto-processes.

Watches raw-data/rt/ for new HTML files. When detected, delegates to the
pipeline orchestrator (process.py --new) which handles all stages:
  extract → classify → normalize → resolve → compile → rebuild

The orchestrator is lockfile-aware: if resolve_v2 is running, it skips
resolve and lets new records queue up until the next cycle.

Usage:
    python engines/rt/watcher.py                  # Start daemon
    python engines/rt/watcher.py --once           # Process pending and exit
    python engines/rt/watcher.py --interval 30    # Custom poll interval (seconds)
    python engines/rt/watcher.py --dry-run        # Show what would be processed
"""

import json
import os
import subprocess
import sys
import time
import argparse
import logging
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [RT] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('rt-watcher')

# Directories
RAW_DIR = os.path.join(PROJECT_ROOT, 'raw-data', 'rt')
ENGINE_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt')
PIPELINE_DIR = os.path.join(ENGINE_DIR, 'pipeline')
ASSEMBLED_DIR = os.path.join(PIPELINE_DIR, 'assembled')
CLASSIFIED_DIR = os.path.join(PIPELINE_DIR, 'classified')
SOURCE_PAGES_DIR = os.path.join(RAW_DIR, 'pages')
EXTRACTED_DIR = os.path.join(PIPELINE_DIR, 'extracted')

STATUS_FILE = os.path.join(PROJECT_ROOT, 'data', 'rt-watcher-status.json')

DEFAULT_INTERVAL = 60  # seconds between polls


def _notify(title, message):
    """Send macOS notification."""
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}"'
        ], timeout=5, capture_output=True)
    except Exception:
        pass


def _has_pending_work():
    """Quick check: are there new HTML files or unprocessed assembled records?

    This is a lightweight check so the watcher doesn't spin up the full
    orchestrator every cycle when there's nothing to do.
    """
    # Check for unextracted page folders (new HTML from scraper)
    if os.path.isdir(SOURCE_PAGES_DIR):
        for region in os.listdir(SOURCE_PAGES_DIR):
            region_path = os.path.join(SOURCE_PAGES_DIR, region)
            if not os.path.isdir(region_path) or region.startswith('.'):
                continue
            for prop_type in os.listdir(region_path):
                type_path = os.path.join(region_path, prop_type)
                if not os.path.isdir(type_path) or prop_type.startswith('.'):
                    continue
                for page in os.listdir(type_path):
                    if page.startswith('p') and os.path.isdir(os.path.join(type_path, page)):
                        key = f'{region}/{prop_type}/{page}'
                        if not os.path.isdir(os.path.join(EXTRACTED_DIR, key)):
                            return True

    # Check for assembled files not yet classified
    if os.path.isdir(ASSEMBLED_DIR) and os.path.isdir(CLASSIFIED_DIR):
        assembled = set(f for f in os.listdir(ASSEMBLED_DIR) if f.endswith('.json'))
        classified = set(f for f in os.listdir(CLASSIFIED_DIR) if f.endswith('.json'))
        if assembled - classified:
            return True

    return False


def process_new_records(dry_run=False):
    """Delegate to process.py --new to handle all pipeline stages.

    Returns the count of processed records, or -1 on error.
    """
    if not _has_pending_work():
        return 0

    log.info('Pending work detected — running pipeline orchestrator')

    cmd = [sys.executable, os.path.join(ENGINE_DIR, 'process.py'), '--new']
    if dry_run:
        cmd.append('--dry-run')

    try:
        result = subprocess.run(
            cmd, cwd=ENGINE_DIR,
            capture_output=True, text=True,
            timeout=7200,  # 2 hour max
        )

        # Log orchestrator output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                log.info(f'  {line}')

        if result.returncode != 0:
            log.error(f'Orchestrator failed (exit {result.returncode})')
            if result.stderr:
                for line in result.stderr.strip().split('\n')[:10]:
                    log.error(f'  {line}')
            return -1

        # Parse results from output
        count = 0
        if result.stdout:
            for line in result.stdout.split('\n'):
                if 'classify' in line.lower() and 'processed' in line.lower():
                    # Try to extract count
                    try:
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if p == 'processed' and i > 0:
                                count = max(count, int(parts[i-1].replace(',', '')))
                    except (ValueError, IndexError):
                        pass

        if count > 0 and not dry_run:
            _notify('Cleo RT Watcher', f'Processed {count} new RT records')

        return count

    except subprocess.TimeoutExpired:
        log.error('Orchestrator timed out (2h limit)')
        return -1
    except Exception as e:
        log.error(f'Orchestrator error: {e}')
        return -1


def run(once=False, interval=DEFAULT_INTERVAL, dry_run=False):
    """Main watcher loop."""
    log.info('Cleo RT Watcher starting')
    log.info(f'Watching: {RAW_DIR}')
    log.info(f'Interval: {interval}s')
    if dry_run:
        log.info('Mode: DRY RUN')
    print()

    if once:
        count = process_new_records(dry_run=dry_run)
        if count > 0:
            log.info(f'Processed {count} records')
        elif count == 0:
            log.info('No new records to process')
        else:
            log.error('Processing failed')
        return

    # Daemon loop
    while True:
        try:
            count = process_new_records(dry_run=dry_run)
            if count > 0:
                log.info(f'Batch complete: {count} records')
            elif count < 0:
                log.warning('Batch had errors — will retry next cycle')

            # Update status file
            status = {
                'last_check': datetime.now(timezone.utc).isoformat(),
                'last_count': count,
                'watching': RAW_DIR,
                'interval': interval,
            }
            safe_write_json(STATUS_FILE, status)

        except KeyboardInterrupt:
            log.info('Watcher stopped by user')
            break
        except Exception as e:
            log.error(f'Unexpected error: {e}')

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='RT Watcher — auto-process new Realtrack files')
    parser.add_argument('--once', action='store_true',
                        help='Process pending files and exit')
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL,
                        help=f'Poll interval in seconds (default: {DEFAULT_INTERVAL})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed')
    args = parser.parse_args()

    run(once=args.once, interval=args.interval, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
