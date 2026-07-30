"""
Determine stage — the external / interpretation layer.

Produces one Determination Record per RT ID from the resolver + geocoder outputs,
keyed to source_id and provenance-tagged. Part of the Clean/Determination split
(docs/clean-determination-split-build-plan.md, doctrine D9).

STEP 1a — purely ADDITIVE. Does NOT modify the clean record, compile.py, the DB,
or writer.py. It lifts exactly what compile.py currently blends into clean-data
(the `parcel` and `geocoded_coords` blocks) into determination/rt/{RT_ID}.json, and
ADDITIONALLY preserves the full resolver `signals` (every candidate ARN per address)
that compile.py drops on the floor.

Best-candidate selection and geocode-source logic mirror engines/rt/compile.py exactly,
so the flattened parcel/geocoded values are byte-for-byte what compile writes today.

Reads:
    pipeline/classified/*.json, pipeline/addresses/*.json  (only to mirror compile's
                                                            best-candidate scoring)
    pipeline/parcel_links/*.json   (resolver output, incl. signals)
    pipeline/geocoded/*.json        (legacy Mapbox fallback)

Writes:
    determination/rt/{RT_ID}.json  (or --out-dir for /tmp testing)

Usage:
    python3 engines/rt/determine.py --limit 800 --out-dir /tmp/det_test
    python3 engines/rt/determine.py --only RT176319 --out-dir /tmp/det_test
    python3 engines/rt/determine.py           # full run -> determination/rt/
"""
import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json
from engines.rt.compile import score_record  # identical best-candidate selection

CLASSIFIED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'pipeline', 'classified'))
ADDRESSES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'pipeline', 'addresses'))
PARCEL_LINKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'pipeline', 'parcel_links'))
GEOCODED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'pipeline', 'geocoded'))
DEFAULT_OUTPUT_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, 'determination', 'rt'))


def build_parcel(parcel_link):
    """The parcel block compile.py builds (compile.py:111-131), plus preserved signals."""
    if not parcel_link:
        return None
    arn = parcel_link.get('resolved_arn')
    if isinstance(arn, dict):
        arn = arn.get('api_format') or arn.get('original') or ''
    return {
        'resolved_arn': arn or '',
        'method': parcel_link.get('method', 'unknown'),
        'reason': parcel_link.get('reason'),
        'parcel_file': parcel_link.get('parcel_file'),
        'confidence': parcel_link.get('confidence'),
        'pip_verified': parcel_link.get('pip_verified'),
        'containment': parcel_link.get('containment'),
        'loc_name': parcel_link.get('loc_name'),
        'addr_type': parcel_link.get('geocode_addr_type'),
        'geocode_score': parcel_link.get('geocode_score'),
        'field_match': parcel_link.get('field_match'),
        'tier': parcel_link.get('parcel_tier'),
        # PRESERVED — compile.py drops this. Every candidate ARN the resolver found,
        # per address/variant. The multi-parcel evidence for later reconciliation.
        'signals': parcel_link.get('signals', []),
    }


def build_geocoded_coords(parcel_link, best_fname):
    """Mirror compile.py:294-311 — v2 embedded geocode first, else legacy geocoded/ file."""
    if parcel_link and parcel_link.get('geocode'):
        geo = parcel_link['geocode']
        return {
            'lat': geo.get('lat'),
            'lng': geo.get('lng'),
            'relevance': (geo.get('score', 0) / 100.0),
            'place_name': geo.get('match_addr', ''),
        }
    geocoded_path = os.path.join(GEOCODED_DIR, best_fname)
    if os.path.isfile(geocoded_path):
        with open(geocoded_path) as f:
            return (json.load(f) or {}).get('result')
    return None


def build_determination_record(rt_id, parcel_link, best_fname):
    return {
        'source_id': rt_id,
        'source': 'rt',
        'determined_at': datetime.now(timezone.utc).isoformat(),
        'provenance': {
            'parcel': 'rt/parcel_resolver',
            'geocoded_coords': 'rt/geocode',
        },
        'parcel': build_parcel(parcel_link),
        'geocoded_coords': build_geocoded_coords(parcel_link, best_fname),
    }


def run(limit=None, out_dir=None, only=None, dry_run=False):
    out_dir = os.path.abspath(out_dir) if out_dir else DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    classified_files = set(f for f in os.listdir(CLASSIFIED_DIR) if f.endswith('.json'))
    addresses_files = set(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))
    parcel_links_files = set(f for f in os.listdir(PARCEL_LINKS_DIR) if f.endswith('.json')) if os.path.isdir(PARCEL_LINKS_DIR) else set()
    all_files = sorted(classified_files & addresses_files)

    rt_groups = {}
    for fname in all_files:
        rt_groups.setdefault(fname.split('__')[0], []).append(fname)

    rt_ids = sorted(rt_groups.keys())
    if only:
        only_set = set(only.split(','))
        rt_ids = [r for r in rt_ids if r in only_set]
    if limit:
        rt_ids = rt_ids[:limit]

    print(f'Cleo Engine - Determine   (out: {out_dir})')
    print(f'RT IDs to process: {len(rt_ids):,}')
    if dry_run:
        return

    stats = {'written': 0, 'with_parcel': 0, 'multi_candidate_arn': 0, 'errors': 0}
    start = time.time()
    for rt_id in rt_ids:
        try:
            best_fname, best_score, best_link = None, -1, None
            for fname in rt_groups[rt_id]:
                with open(os.path.join(CLASSIFIED_DIR, fname)) as f:
                    classified = json.load(f)
                with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                    addresses = json.load(f)
                parcel_link = None
                if fname in parcel_links_files:
                    with open(os.path.join(PARCEL_LINKS_DIR, fname)) as f:
                        parcel_link = json.load(f)
                s = score_record(classified, addresses, parcel_link)
                if s > best_score:
                    best_score, best_fname, best_link = s, fname, parcel_link

            rec = build_determination_record(rt_id, best_link, best_fname)
            safe_write_json(os.path.join(out_dir, f'{rt_id}.json'), rec)

            stats['written'] += 1
            if rec['parcel'] and rec['parcel'].get('resolved_arn'):
                stats['with_parcel'] += 1
            if rec['parcel']:
                cand = {s.get('candidate_arn') for s in rec['parcel'].get('signals', []) if s.get('candidate_arn')}
                if len(cand) > 1:
                    stats['multi_candidate_arn'] += 1
        except Exception as e:
            stats['errors'] += 1
            if stats['errors'] <= 10:
                print(f'  ERROR {rt_id}: {e}')

    print(f'Done in {time.time()-start:.1f}s  written={stats["written"]:,}  '
          f'with_parcel={stats["with_parcel"]:,}  multi_candidate_arn={stats["multi_candidate_arn"]:,}  '
          f'errors={stats["errors"]:,}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Build Determination Records (parcel + geocode) per RT ID')
    ap.add_argument('--limit', type=int, help='process only the first N unique RT IDs')
    ap.add_argument('--out-dir', help='output dir (default determination/rt/; use /tmp for testing)')
    ap.add_argument('--only', help='comma-separated RT IDs')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    run(limit=a.limit, out_dir=a.out_dir, only=a.only, dry_run=a.dry_run)
