"""
Test the unified resolver against known records.

Three test phases:
  Phase 1 — Offline (no APIs): Tests adapter conversion, cache-only resolution,
            and backward compatibility with compile stage. Safe to run anytime.
  Phase 2 — Comparison: Loads existing parcel_links (old results) and runs the
            unified resolver in cache-only mode to compare. No API calls.
  Phase 3 — Live (requires APIs): Runs a small batch through the full chain
            with AgMaps + Ontario geocoder. Needs Playwright + token.

Usage:
    python -m parcel_resolver.test_unified                     # Phase 1 only (safe, fast)
    python -m parcel_resolver.test_unified --compare           # Phase 1 + 2
    python -m parcel_resolver.test_unified --live              # Phase 1 + 2 + 3
    python -m parcel_resolver.test_unified --live --limit 20   # Live with limited batch
"""

import json
import os
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from cleo.resolver import resolve, ResolverContext, ResolutionInput, GeocodableAddress, Method
from engines.rt.parcel_resolver.adapter import addresses_to_input, result_to_parcel_link

ADDRESSES_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'addresses')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'parcel_links')
CLEAN_RT_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'rt')


# ── Test records ────────────────────────────────────────────────────

# Known problem case: Shoppers Drug Mart at 107 Edward St, St. Thomas
# Was resolving to Rona parcel next door due to PIP bug.
# PIN 351870056 should bridge to the correct parcel.
SHOPPERS_FILE = 'RT156261__Elgin_County__office__p001__pos007.json'

# Records with known old methods (for comparison testing)
KNOWN_RECORDS = [
    'RT100001__Metro_Toronto__industrial__p023__pos016.json',   # was arn_verified
    'RT100000__Oxford_County__farm__p010__pos040.json',         # was spatial_geocode
    'RT100005__Ottawa-Carleton__office__p011__pos007.json',     # was spatial_geocode
    'RT100008__Metro_Toronto__multifamily__p044__pos023.json',  # was arn_verified
]


def _pass(msg):
    print(f'  ✓ {msg}')

def _fail(msg):
    print(f'  ✗ FAIL: {msg}')
    return False

def _warn(msg):
    print(f'  ⚠ {msg}')


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Offline tests (no API calls)
# ═══════════════════════════════════════════════════════════════════

def test_phase1():
    """Tests that run with zero API calls — cache only."""
    print()
    print('═══ Phase 1: Offline Tests (cache-only, no APIs) ═══')
    print()
    passed = 0
    failed = 0

    # ── Test 1.1: Adapter conversion ────────────────────────────
    print('Test 1.1: RT adapter — addresses → ResolutionInput')
    try:
        with open(os.path.join(ADDRESSES_DIR, SHOPPERS_FILE)) as f:
            addr = json.load(f)
        ri = addresses_to_input(addr)

        assert ri.source == 'rt', f'source should be rt, got {ri.source}'
        assert ri.source_id == 'RT156261', f'source_id should be RT156261, got {ri.source_id}'
        assert ri.pin == '351870056', f'pin should be 351870056, got {ri.pin}'
        assert ri.arn is None or ri.arn == '', f'arn should be empty, got {ri.arn}'
        assert len(ri.addresses) >= 1, f'should have at least 1 address, got {len(ri.addresses)}'
        assert '107 Edward' in ri.addresses[0].geocode_string, \
            f'geocode_string should contain "107 Edward", got {ri.addresses[0].geocode_string}'
        _pass(f'RT156261 → source={ri.source}, pin={ri.pin}, addrs={len(ri.addresses)}')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.2: Cache-only resolution ─────────────────────────
    print('Test 1.2: Cache-only resolve (no API clients)')
    try:
        result = resolve(ri)
        assert result.method in (Method.UNRESOLVED, Method.PIN_BRIDGE, Method.ARN_ONLY), \
            f'Expected cache-only method, got {result.method}'
        _pass(f'method={result.method}, confidence={result.confidence}')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.3: Result → parcel_link format ───────────────────
    print('Test 1.3: ResolutionResult → parcel_link backward compatibility')
    try:
        link = result_to_parcel_link(result, 'RT156261')
        # Check required keys for compile.py
        assert 'rt_id' in link, 'missing rt_id'
        assert 'resolved_arn' in link, 'missing resolved_arn'
        assert 'method' in link, 'missing method'
        assert 'parcel_file' in link, 'missing parcel_file'
        # Check new additive keys
        assert 'confidence' in link, 'missing confidence'
        assert 'pip_verified' in link, 'missing pip_verified'
        _pass(f'link keys: {sorted(link.keys())}')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.4: Error path ────────────────────────────────────
    print('Test 1.4: Error result handling')
    try:
        from cleo.resolver.types import ResolutionResult as RR
        err = RR.error('test error')
        err_link = result_to_parcel_link(err, 'RT999999')
        assert err_link['method'] == 'error', f'expected method=error, got {err_link["method"]}'
        assert err_link['resolved_arn'] is None, 'error should have no ARN'
        assert err_link['parcel_file'] is None, 'error should have no parcel_file'
        _pass('error link format correct')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.5: Compile stage compatibility ───────────────────
    print('Test 1.5: Simulate compile stage reading new-format parcel_link')
    try:
        # This mimics what compile.py:build_clean_record does (lines 95-114)
        parcel = None
        if link.get('resolved_arn'):
            arn = link['resolved_arn']
            if isinstance(arn, dict):
                arn = arn.get('api_format') or arn.get('original') or ''
            if arn:
                parcel = {
                    'resolved_arn': arn,
                    'method': link.get('method', 'unknown'),
                    'parcel_file': link.get('parcel_file'),
                }
        # For unresolved records, parcel should be None
        if result.method == Method.UNRESOLVED:
            assert parcel is None, 'unresolved should produce parcel=None'
            _pass('compile compat: unresolved → parcel=None (correct)')
        else:
            assert parcel is not None, 'resolved should produce parcel dict'
            _pass(f'compile compat: parcel={parcel}')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.6: All known records convert cleanly ─────────────
    print('Test 1.6: Convert all known test records through adapter')
    try:
        for fname in KNOWN_RECORDS:
            path = os.path.join(ADDRESSES_DIR, fname)
            if not os.path.isfile(path):
                _warn(f'skipped (file not found): {fname}')
                continue
            with open(path) as f:
                addr = json.load(f)
            ri = addresses_to_input(addr)
            result = resolve(ri)
            link = result_to_parcel_link(result, ri.source_id)
            # Basic sanity
            assert link['rt_id'] == ri.source_id
            assert link['method'] in (
                Method.VERIFIED, Method.SPATIAL_CONSENSUS, Method.SPATIAL_GEOCODE,
                Method.SPATIAL_OVERRIDE, Method.SPATIAL_COORDS, Method.ARN_ONLY,
                Method.PIN_BRIDGE, Method.UNRESOLVED, Method.ERROR,
            )
            _pass(f'{ri.source_id} → method={result.method}, confidence={result.confidence}')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    # ── Test 1.7: GW + OSM adapters ────────────────────────────
    print('Test 1.7: GW and OSM adapter round-trips')
    try:
        from engines.gw.adapter import normalized_to_inputs, results_to_gw_parcel_link
        from engines.osm.adapter import poi_to_input, apply_result_to_poi

        # GW
        gw_dir = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')
        gw_files = sorted(f for f in os.listdir(gw_dir) if f.endswith('.json'))[:3]
        for gf in gw_files:
            with open(os.path.join(gw_dir, gf)) as f:
                gw = json.load(f)
            # GW clean-data format has slightly different keys than normalized
            # We need the normalized format — check if this file works
            gw_id = gw.get('source_id', gf.replace('.json', ''))
            # Simulate a minimal normalized record
            assessments = gw.get('assessments', [])
            norm = {
                'gw_id': gw_id,
                'pin_api': gw.get('pin', ''),
                'assessments': [{'arn_api': a.get('arn_api', a.get('arn', ''))} for a in assessments]
            }
            inputs = normalized_to_inputs(norm)
            results = []
            for arn_api, ri in inputs:
                r = resolve(ri)
                results.append((arn_api, r))
            link = results_to_gw_parcel_link(gw_id, norm.get('pin_api', ''), results)
            assert 'gw_id' in link
            assert 'resolutions' in link

        _pass(f'GW adapter: {len(gw_files)} records converted')

        # OSM
        osm_dir = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')
        osm_files = sorted(f for f in os.listdir(osm_dir) if f.endswith('.json'))[:3]
        for of in osm_files:
            with open(os.path.join(osm_dir, of)) as f:
                poi = json.load(f)
            ri = poi_to_input(poi)
            r = resolve(ri)
            poi_out = apply_result_to_poi(poi, r)
            assert 'parcel_status' in poi_out
            assert 'arn' in poi_out

        _pass(f'OSM adapter: {len(osm_files)} records converted')
        passed += 1
    except Exception as e:
        _fail(f'{e}')
        failed += 1

    print()
    print(f'Phase 1 Results: {passed} passed, {failed} failed')
    return failed == 0


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Comparison (old vs new, cache-only)
# ═══════════════════════════════════════════════════════════════════

def test_phase2(limit=500):
    """Compare old parcel_links against unified resolver in cache-only mode.

    This test re-resolves records through the unified chain using ONLY the
    parcel cache (no API calls). Records that previously used arn_cache or
    arn_api should still resolve to the same ARN. Records that used geocoding
    will show as unresolved (expected — no geocoder available).

    The goal is to confirm that the adapter conversion + cache path produces
    identical results to the old code for cache-hit records.
    """
    print()
    print(f'═══ Phase 2: Comparison (old vs new, cache-only, {limit} records) ═══')
    print()

    # Load PIN→ARN bridge (local, no API)
    from cleo.resolver.pin_bridge import build_gw_pin_to_arn
    pin_to_arn = build_gw_pin_to_arn()
    ctx = ResolverContext(pin_to_arn=pin_to_arn)

    # Get a sample of existing parcel_links files
    all_links = sorted(
        f for f in os.listdir(PARCEL_LINKS_DIR)
        if f.endswith('.json') and not f.startswith('.')
    )

    import random
    random.seed(42)
    sample = random.sample(all_links, min(limit, len(all_links)))

    stats = {
        'same_arn': 0,          # New result matches old ARN
        'different_arn': 0,     # New result has different ARN (potential issue)
        'old_resolved_new_not': 0,  # Old had ARN, new doesn't (expected for geocode-only records)
        'old_not_new_resolved': 0,  # Old had no ARN, new does (improvement from PIN bridge)
        'both_unresolved': 0,
        'skipped': 0,
        'errors': 0,
    }
    differences = []

    for fname in sample:
        try:
            # Load old result
            with open(os.path.join(PARCEL_LINKS_DIR, fname)) as f:
                old_link = json.load(f)
            old_arn = old_link.get('resolved_arn')
            old_method = old_link.get('method', '')

            # Load addresses and re-resolve
            addr_path = os.path.join(ADDRESSES_DIR, fname)
            if not os.path.isfile(addr_path):
                stats['skipped'] += 1
                continue

            with open(addr_path) as f:
                addr = json.load(f)

            ri = addresses_to_input(addr)
            new_result = resolve(ri, ctx)
            new_arn = new_result.resolved_arn

            # Compare
            if old_arn and new_arn and old_arn == new_arn:
                stats['same_arn'] += 1
            elif old_arn and new_arn and old_arn != new_arn:
                stats['different_arn'] += 1
                differences.append({
                    'file': fname,
                    'rt_id': old_link.get('rt_id', '?'),
                    'old_arn': old_arn,
                    'old_method': old_method,
                    'new_arn': new_arn,
                    'new_method': new_result.method,
                })
            elif old_arn and not new_arn:
                stats['old_resolved_new_not'] += 1
                # Expected for records that used geocoding — we have no geocoder here
            elif not old_arn and new_arn:
                stats['old_not_new_resolved'] += 1
                # Improvement — PIN bridge or cache hit that old code missed
            else:
                stats['both_unresolved'] += 1

        except Exception as e:
            stats['errors'] += 1

    print(f'Compared {len(sample) - stats["skipped"]:,} records:')
    print(f'  Same ARN (match):         {stats["same_arn"]:,}')
    print(f'  Different ARN (⚠):        {stats["different_arn"]:,}')
    print(f'  Old resolved, new not:     {stats["old_resolved_new_not"]:,}  (expected — no geocoder)')
    print(f'  Old not, new resolved:     {stats["old_not_new_resolved"]:,}  (improvement)')
    print(f'  Both unresolved:           {stats["both_unresolved"]:,}')
    print(f'  Errors:                    {stats["errors"]:,}')
    print(f'  Skipped (missing file):    {stats["skipped"]:,}')

    if differences:
        print()
        print(f'  ⚠ {len(differences)} records resolved to DIFFERENT ARNs:')
        for d in differences[:10]:
            print(f'    {d["rt_id"]}: old={d["old_arn"]} ({d["old_method"]}) → new={d["new_arn"]} ({d["new_method"]})')
        if len(differences) > 10:
            print(f'    ... and {len(differences) - 10} more')
    else:
        print()
        _pass('No ARN conflicts detected')

    # The key metric: for records where BOTH old and new resolved,
    # they should agree. different_arn should be 0 or very low.
    success = stats['different_arn'] == 0
    if success:
        _pass('Phase 2 PASSED — all cache-resolved records agree')
    else:
        _fail(f'Phase 2: {stats["different_arn"]} records disagree')

    return success


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Live test (requires APIs)
# ═══════════════════════════════════════════════════════════════════

def test_phase3(limit=10, headless=True):
    """Run a small batch through the FULL resolution chain with live APIs.

    This spins up the AgMaps client and Ontario geocoder, resolves a handful
    of records, and compares against old results. This is the final confidence
    check before a full reprocess.
    """
    print()
    print(f'═══ Phase 3: Live Test ({limit} records, full chain) ═══')
    print()

    from engines.rt.parcel_resolver.agmaps import AgMapsClient
    from engines.rt.parcel_resolver.ontario_geocoder import OntarioGeocoderClient
    from engines.rt.parcel_resolver.pin_bridge import build_gw_pin_to_arn
    from engines.rt.parcel_resolver.token import load_token, refresh_token

    # Setup
    print('Loading PIN→ARN bridge...')
    pin_to_arn = build_gw_pin_to_arn()
    print(f'  {len(pin_to_arn):,} pairs')

    print('Loading token...')
    token = load_token()
    if not token:
        print('  Fetching fresh token...')
        token = refresh_token()
    agmaps_client = AgMapsClient(token)

    print('Starting Ontario geocoder...')
    ont_client = OntarioGeocoderClient(delay=0.5, headless=headless, verbose=False)
    ont_client.start()

    ctx = ResolverContext(
        agmaps_client=agmaps_client,
        geocoder_client=ont_client,
        pin_to_arn=pin_to_arn,
    )

    # Test records: the Shoppers problem case + a few from each old method
    test_files = [SHOPPERS_FILE] + KNOWN_RECORDS

    # Add some random records to hit different categories
    import random
    random.seed(42)
    all_addr_files = sorted(
        f for f in os.listdir(ADDRESSES_DIR)
        if f.endswith('.json') and f not in test_files
    )
    extra = random.sample(all_addr_files, min(limit - len(test_files), len(all_addr_files)))
    test_files.extend(extra)
    test_files = test_files[:limit]

    print(f'Testing {len(test_files)} records...')
    print()

    results = []
    try:
        for fname in test_files:
            addr_path = os.path.join(ADDRESSES_DIR, fname)
            if not os.path.isfile(addr_path):
                continue

            with open(addr_path) as f:
                addr = json.load(f)

            ri = addresses_to_input(addr)
            result = resolve(ri, ctx)
            link = result_to_parcel_link(result, ri.source_id)

            # Load old result for comparison
            old_link = None
            old_path = os.path.join(PARCEL_LINKS_DIR, fname)
            if os.path.isfile(old_path):
                with open(old_path) as f:
                    old_link = json.load(f)

            old_arn = old_link.get('resolved_arn') if old_link else None
            old_method = old_link.get('method', '?') if old_link else '?'

            match = '✓' if old_arn == result.resolved_arn else '⚠ CHANGED'
            if not old_arn and not result.resolved_arn:
                match = '= (both unresolved)'

            print(f'  {ri.source_id:10s}  '
                  f'old: {old_method:20s} → new: {result.method:20s}  '
                  f'conf={result.confidence:.2f}  pip={result.pip_verified}  {match}')

            if old_arn != result.resolved_arn:
                print(f'    old_arn={old_arn}')
                print(f'    new_arn={result.resolved_arn}')
                if result.geocode:
                    print(f'    geocode: {result.geocode.addr_type} score={result.geocode.score} '
                          f'match={result.geocode.match_addr}')
                for sig in result.signals:
                    print(f'    signal: {sig.source} → {sig.candidate_arn} ({sig.details[:80]})')

            results.append({
                'rt_id': ri.source_id,
                'old_arn': old_arn,
                'new_arn': result.resolved_arn,
                'old_method': old_method,
                'new_method': result.method,
                'confidence': result.confidence,
                'pip_verified': result.pip_verified,
                'changed': old_arn != result.resolved_arn,
            })

    finally:
        ont_client.close()
        agmaps_client.close()

    # Summary
    changed = [r for r in results if r['changed']]
    print()
    print(f'Phase 3 Results:')
    print(f'  Total tested:   {len(results)}')
    print(f'  Same result:    {len(results) - len(changed)}')
    print(f'  Changed:        {len(changed)}')

    if changed:
        print()
        print('  Changed records (inspect these manually):')
        for r in changed:
            print(f'    {r["rt_id"]}: {r["old_method"]} → {r["new_method"]} '
                  f'(old={r["old_arn"]}, new={r["new_arn"]})')

    # Shoppers check
    shoppers = next((r for r in results if r['rt_id'] == 'RT156261'), None)
    if shoppers:
        print()
        if shoppers['new_arn'] and shoppers['new_arn'] != shoppers.get('old_arn'):
            print(f'  🔑 RT156261 (Shoppers) resolved to {shoppers["new_arn"]} '
                  f'(was {shoppers["old_arn"]})')
            print(f'     method={shoppers["new_method"]}, confidence={shoppers["confidence"]}')
        elif shoppers['new_arn']:
            print(f'  RT156261 (Shoppers) → {shoppers["new_arn"]} '
                  f'(unchanged, method={shoppers["new_method"]})')

    return True


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Test unified resolver')
    parser.add_argument('--compare', action='store_true',
                        help='Run Phase 2 comparison (cache-only, no APIs)')
    parser.add_argument('--live', action='store_true',
                        help='Run Phase 3 live test (requires APIs + Playwright)')
    parser.add_argument('--limit', type=int, default=10,
                        help='Number of records for live test (default: 10)')
    parser.add_argument('--compare-limit', type=int, default=500,
                        help='Number of records for comparison (default: 500)')
    parser.add_argument('--no-headless', action='store_true')
    args = parser.parse_args()

    p1 = test_phase1()

    if args.compare or args.live:
        test_phase2(limit=args.compare_limit)

    if args.live:
        test_phase3(limit=args.limit, headless=not args.no_headless)

    if not args.compare and not args.live:
        print()
        print('Next steps:')
        print('  python -m parcel_resolver.test_unified --compare            # Compare 500 records (no API)')
        print('  python -m parcel_resolver.test_unified --live --limit 10    # Full chain, 10 records')
        print('  python -m parcel_resolver.test_unified --live --limit 50    # Full chain, 50 records')


if __name__ == '__main__':
    main()
