"""
Unified Resolve Stage (v2) — batch orchestrator for RT parcel resolution.

Delegates all per-record resolution to the unified resolver (cleo.resolver).
This file handles only batch orchestration: file list management, lockfile,
token management, checkpointing, progress reporting, and CLI arguments.

Resolution chain (via cleo.resolver.chain):
  1. PIN→ARN bridge (local GW lookup, zero API calls)
  2. ARN lookup (cache → AgMaps API)
  3. Address geocoding (Ontario geocoder, all variants, 44 attributes)
  4. Coordinate PIP (spatial query)
  5. Cross-validation (decision hierarchy)
  6. PIP verification (local grid-based, zero API calls)

Methods written to parcel_links (standardized across all sources):
  - verified:           ARN + geocode + PIP agree
  - spatial_consensus:  Multiple address variants agree on same parcel
  - spatial_geocode:    Single geocode + PIP
  - spatial_override:   Geocode overrode source ARN
  - spatial_coords:     Direct coordinate PIP (OSM-style, rare for RT)
  - arn_only:           ARN resolved, no geocode validation
  - pin_bridge:         PIN→ARN via GW lookup
  - unresolved:         All methods failed (reason field explains why)
  - error:              Exception during resolution

Resumable: skips records that already have a parcel_links file.
Use --reprocess to force re-resolution of all records.
Use --reprocess-unresolved to only re-resolve previously unresolved records.
Use --reprocess-method <name> to re-resolve records with a specific method.

Usage:
    python -m parcel_resolver.resolve_v2
    python -m parcel_resolver.resolve_v2 --limit 100
    python -m parcel_resolver.resolve_v2 --reprocess
    python -m parcel_resolver.resolve_v2 --reprocess-unresolved
    python -m parcel_resolver.resolve_v2 --reprocess-method arn_only
    python -m parcel_resolver.resolve_v2 --dry-run
"""

import json
import os
import sys
import time
import argparse

from .agmaps import AgMapsClient, TokenExpiredError
from .ontario_geocoder import OntarioGeocoderClient, ThrottleError, SessionError
from .pin_bridge import build_gw_pin_to_arn
from .token import load_token, refresh_token
from .adapter import addresses_to_input, result_to_parcel_link

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json
from cleo.resolver import resolve, ResolverContext, Method


ADDRESSES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'addresses')
)
PARCEL_LINKS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'parcel_links')
)

# Checkpoint: save progress every N records so we can report on interrupt
CHECKPOINT_INTERVAL = 500

LOCKFILE = os.path.join(PARCEL_LINKS_DIR, '.resolve_v2.lock')


def _acquire_lock():
    """Prevent concurrent resolve_v2 runs. Returns True if lock acquired."""
    if os.path.isfile(LOCKFILE):
        try:
            with open(LOCKFILE) as f:
                info = json.load(f)
            pid = info.get('pid')
            # Check if the process is actually still running
            if pid:
                try:
                    os.kill(pid, 0)  # signal 0 = just check existence
                    return False  # Process is alive — lock is real
                except OSError:
                    pass  # Process is dead — stale lock
        except (json.JSONDecodeError, OSError):
            pass  # Corrupt lock file — treat as stale

    os.makedirs(os.path.dirname(LOCKFILE), exist_ok=True)
    with open(LOCKFILE, 'w') as f:
        json.dump({'pid': os.getpid(), 'started': time.strftime('%Y-%m-%d %H:%M:%S')}, f)
    return True


def _release_lock():
    """Release the lockfile."""
    try:
        os.remove(LOCKFILE)
    except OSError:
        pass


def run(limit=None, dry_run=False, reprocess=False, reprocess_unresolved=False,
        reprocess_method=None, headless=True, verbose=True):
    """Run the unified resolve stage."""

    os.makedirs(PARCEL_LINKS_DIR, exist_ok=True)

    if not dry_run and not _acquire_lock():
        print('ERROR: Another resolve_v2 instance is already running.')
        print(f'  Lock file: {LOCKFILE}')
        print(f'  If the previous run crashed, delete the lock file and retry.')
        return

    # Build file list
    all_files = sorted(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))

    # Determine which files to process
    existing_links = {}
    if os.path.isdir(PARCEL_LINKS_DIR):
        for f in os.listdir(PARCEL_LINKS_DIR):
            if f.endswith('.json'):
                existing_links[f] = True

    if reprocess:
        # Reprocess everything — but skip files already processed by unified resolver
        # (identified by having a 'pip_verified' field, which ONLY the unified resolver writes.
        #  Note: 'confidence' is NOT safe — the old resolver also wrote that field.)
        pending = []
        for f in all_files:
            if f in existing_links:
                link_path = os.path.join(PARCEL_LINKS_DIR, f)
                try:
                    with open(link_path) as fh:
                        link = json.load(fh)
                    if 'pip_verified' in link:
                        continue  # Already done by unified resolver
                except (json.JSONDecodeError, OSError):
                    pass
            pending.append(f)
    elif reprocess_unresolved:
        # Only re-resolve previously unresolved records
        pending = []
        for f in all_files:
            if f in existing_links:
                link_path = os.path.join(PARCEL_LINKS_DIR, f)
                try:
                    with open(link_path) as fh:
                        link = json.load(fh)
                    if link.get('method') in ('unresolved', 'error',
                                                Method.UNRESOLVED, Method.ERROR):
                        pending.append(f)
                except (json.JSONDecodeError, OSError):
                    pending.append(f)
            else:
                pending.append(f)
    elif reprocess_method:
        # Re-resolve records with a specific method
        pending = []
        for f in all_files:
            if f in existing_links:
                link_path = os.path.join(PARCEL_LINKS_DIR, f)
                try:
                    with open(link_path) as fh:
                        link = json.load(fh)
                    if link.get('method') == reprocess_method:
                        pending.append(f)
                except (json.JSONDecodeError, OSError):
                    pending.append(f)
            else:
                pending.append(f)
    else:
        # Default: only process files without existing parcel_links
        pending = [f for f in all_files if f not in existing_links]

    # Sort pending: ARN-having records first (resolve from cache, no geocoder needed),
    # then PIN-only, then no-identifiers (need geocoding). This avoids hitting the
    # geocoder early when it might still be rate-limited from a previous run.
    def _sort_key(fname):
        try:
            with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                rec = json.load(f)
            arn = rec.get('arn', {}).get('api_format', '').strip()
            pin = rec.get('pin', {}).get('api_format', '').strip()
            if arn and not all(c == '0' for c in arn):
                return (0, fname)  # ARN first
            elif pin:
                return (1, fname)  # PIN second
            else:
                return (2, fname)  # No identifiers last (needs geocoder)
        except Exception:
            return (2, fname)

    if reprocess:
        print('Sorting pending records (ARN-first, geocoder-needing last)...')
        pending.sort(key=_sort_key)

    if limit:
        pending = pending[:limit]

    print(f'Cleo Engine — Unified Resolve (v2)')
    print(f'Addresses files:   {len(all_files):,}')
    print(f'Already resolved:  {len(existing_links):,}')
    print(f'Pending:           {len(pending):,}')
    if reprocess:
        print(f'Mode:              REPROCESS ALL')
    elif reprocess_unresolved:
        print(f'Mode:              REPROCESS UNRESOLVED')
    elif reprocess_method:
        print(f'Mode:              REPROCESS METHOD={reprocess_method}')
    print()

    if dry_run:
        # Sample first 1000 to show categories
        categories = {'has_arn': 0, 'has_pin_no_arn': 0, 'no_identifiers': 0}
        sample_size = min(len(pending), 1000)
        for fname in pending[:sample_size]:
            with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                rec = json.load(f)
            arn = rec.get('arn', {}).get('api_format', '').strip()
            pin = rec.get('pin', {}).get('api_format', '').strip()
            if arn and not all(c == '0' for c in arn):
                categories['has_arn'] += 1
            elif pin:
                categories['has_pin_no_arn'] += 1
            else:
                categories['no_identifiers'] += 1
        print(f'Sample of {sample_size:,} pending records:')
        for cat, count in categories.items():
            pct = count * 100 / sample_size if sample_size > 0 else 0
            print(f'  {cat}: {count:,} ({pct:.1f}%)')
        return

    if not pending:
        print('Nothing to process.')
        return

    # --- Setup ---

    # 1. PIN→ARN bridge (local, fast)
    print('Loading PIN→ARN bridge from GW data...')
    pin_to_arn = build_gw_pin_to_arn()
    print(f'  {len(pin_to_arn):,} PIN→ARN pairs loaded')
    print()

    # 2. AgMaps token for parcel queries
    print('Loading AgMaps token...')
    token = load_token()
    if token:
        print('  Using saved token')
    else:
        print('  Fetching fresh token via browser...')
        token = refresh_token()
        print('  Token fetched and saved')
    agmaps_client = AgMapsClient(token)
    print()

    # 3. Ontario geocoder (Playwright session)
    print('Starting Ontario geocoder session...')
    ont_client = OntarioGeocoderClient(delay=0.5, headless=headless, verbose=verbose)
    ont_client.start()
    print()

    # 4. Create unified resolver context
    ctx = ResolverContext(
        agmaps_client=agmaps_client,
        geocoder_client=ont_client,
        pin_to_arn=pin_to_arn,
        verbose=verbose,
    )

    # --- Process ---
    stats = {
        Method.VERIFIED: 0,
        Method.SPATIAL_CONSENSUS: 0,
        Method.SPATIAL_GEOCODE: 0,
        Method.SPATIAL_OVERRIDE: 0,
        Method.SPATIAL_COORDS: 0,
        Method.ARN_ONLY: 0,
        Method.PIN_BRIDGE: 0,
        Method.UNRESOLVED: 0,
        Method.ERROR: 0,
    }
    start_time = time.time()

    try:
        for i, fname in enumerate(pending):
            try:
                # Read addresses file
                with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                    rec = json.load(f)

                rt_id = rec.get('rt_id', fname.split('__')[0])

                # Convert to unified ResolutionInput via adapter
                ri = addresses_to_input(rec)

                # Resolve via unified resolver
                try:
                    result = resolve(ri, ctx)
                except TokenExpiredError:
                    print(f'\n  Token expired at record {i+1}. Refreshing via browser...')
                    agmaps_client.close()
                    # Use the geocoder's existing browser to capture a fresh token
                    # (can't spawn a second Playwright instance — crashes with asyncio error)
                    try:
                        token = ont_client.capture_agmaps_token()
                    except Exception as e:
                        print(f'  Browser token capture failed: {e}')
                        print(f'  Falling back to fresh Playwright session...')
                        # Last resort: close geocoder, fetch token, restart geocoder
                        ont_client.close()
                        token = refresh_token()
                        ont_client = OntarioGeocoderClient(
                            delay=0.5, headless=headless, verbose=verbose
                        )
                        ont_client.start()
                    agmaps_client = AgMapsClient(token)
                    # Rebuild context with refreshed clients
                    ctx = ResolverContext(
                        agmaps_client=agmaps_client,
                        geocoder_client=ont_client,
                        pin_to_arn=pin_to_arn,
                        verbose=verbose,
                    )
                    print('  Token refreshed. Retrying...')
                    result = resolve(ri, ctx)

                # Convert result back to parcel_links format via adapter
                link = result_to_parcel_link(result, rt_id)

                # Write parcel_links file (atomic)
                safe_write_json(os.path.join(PARCEL_LINKS_DIR, fname), link)

                # Track stats
                method = result.method
                if method in stats:
                    stats[method] += 1

            except ThrottleError as e:
                # HARD STOP — pipeline must not continue
                print(f'\n\n  *** THROTTLE DETECTED — HARD STOP ***')
                print(f'  {e}')
                print(f'  Records processed: {i:,}')
                print(f'  DO NOT restart immediately. Wait at least 5 minutes.')
                stats[Method.ERROR] += 1
                break

            except Exception as e:
                stats[Method.ERROR] += 1
                # Write an error link so we don't retry this file on resume
                from cleo.resolver.types import ResolutionResult as _RR
                error_result = _RR.error(str(e))
                error_link = result_to_parcel_link(error_result, fname.split('__')[0])
                safe_write_json(os.path.join(PARCEL_LINKS_DIR, fname), error_link)

            # Progress reporting
            if (i + 1) % CHECKPOINT_INTERVAL == 0 or (i + 1) == len(pending):
                elapsed = time.time() - start_time
                resolved = sum(
                    v for k, v in stats.items()
                    if k not in (Method.UNRESOLVED, Method.ERROR)
                )
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(pending) - i - 1) / rate if rate > 0 else 0

                # Geocoder stats
                geo_stats = ''
                if ont_client:
                    gs = ont_client.stats
                    geo_stats = (
                        f'  geo:{gs["calls"]}'
                        f'(pt:{gs["point_address"]}'
                        f'/st:{gs["street_address"]}'
                        f'/miss:{gs["no_result"]})'
                    )

                print(
                    f'  [{i+1:,}/{len(pending):,}] '
                    f'resolved:{resolved:,} '
                    f'unresolved:{stats[Method.UNRESOLVED]:,} '
                    f'err:{stats[Method.ERROR]:,}'
                    f'{geo_stats} '
                    f'({rate:.1f}/s ETA:{eta/60:.0f}m)'
                )

    except KeyboardInterrupt:
        print(f'\n\n  Interrupted at record {i+1}. Progress saved — safe to resume.')

    finally:
        # Clean up
        ont_client.close()
        agmaps_client.close()
        _release_lock()

    # --- Summary ---
    elapsed = time.time() - start_time
    print()
    print(f'Unified Resolve — Summary ({elapsed:.1f}s)')
    print(f'  verified:            {stats[Method.VERIFIED]:,}')
    print(f'  spatial_consensus:   {stats[Method.SPATIAL_CONSENSUS]:,}')
    print(f'  spatial_geocode:     {stats[Method.SPATIAL_GEOCODE]:,}')
    print(f'  spatial_override:    {stats[Method.SPATIAL_OVERRIDE]:,}')
    print(f'  spatial_coords:      {stats[Method.SPATIAL_COORDS]:,}')
    print(f'  arn_only:            {stats[Method.ARN_ONLY]:,}')
    print(f'  pin_bridge:          {stats[Method.PIN_BRIDGE]:,}')
    print(f'  unresolved:          {stats[Method.UNRESOLVED]:,}')
    print(f'  errors:              {stats[Method.ERROR]:,}')

    total_resolved = sum(
        v for k, v in stats.items()
        if k not in (Method.UNRESOLVED, Method.ERROR)
    )
    total = total_resolved + stats[Method.UNRESOLVED] + stats[Method.ERROR]
    if total > 0:
        print(f'  resolution rate:     {total_resolved*100/total:.1f}%')

    # Print geocoder stats
    if ont_client:
        ont_client.print_stats()


def main():
    parser = argparse.ArgumentParser(
        description='Unified parcel resolution for RT records (v2)'
    )
    parser.add_argument('--limit', type=int,
                        help='Process only the first N pending records')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed')
    parser.add_argument('--reprocess', action='store_true',
                        help='Re-resolve ALL records (ignores existing parcel_links)')
    parser.add_argument('--reprocess-unresolved', action='store_true',
                        help='Re-resolve only previously unresolved/error records')
    parser.add_argument('--reprocess-method', type=str,
                        help='Re-resolve records with a specific method (e.g., spatial_geocode)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Show browser window (for debugging)')
    args = parser.parse_args()

    run(
        limit=args.limit,
        dry_run=args.dry_run,
        reprocess=args.reprocess,
        reprocess_unresolved=args.reprocess_unresolved,
        reprocess_method=args.reprocess_method,
        headless=not args.no_headless,
    )


if __name__ == '__main__':
    main()
