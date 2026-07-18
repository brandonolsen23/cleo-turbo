#!/usr/bin/env python
"""Build anchor-collision adjudication dossiers (AI group-adjudication pilot).

Finds "anchor-collision clusters": corporate signatures (mailing address_unit,
phone, contact fingerprint) that span MANY differently-named entities with no
dominant stem -- exactly the cases the discovery engine's dominance rule
(windowed tenure dominance, cleo/discovery_v2/{anchor_scores,tenures}.py)
declines to promote. Example: Skyline's 5 Douglas St Suite 301 Guelph +
519-826-0439 + Jason Castellan span dozens of differently-named SPVs, so no
single stem ever wins the anchor. Packages each cluster as a compact evidence
dossier an AI can adjudicate (D4 flywheel: evidence first, verdicts second).

READ-ONLY on the DB: plain SELECTs, mode=ro URI. Writes JSON outputs only.

Thresholds (chosen 2026-07-07 after inspecting live distributions):
  VOLUME_MIN = 10
      Full-history party-sides on the anchor, computed from
      party_fingerprints -- NOT anchor_uniqueness.volume, because the
      snapshot volume only reflects the most-recent tenure (Skyline's
      phone: snapshot 17 vs 457 actual sides). >=10 cuts multi-tenant
      one-off noise (spec floor of 6 yields 4,587 anchors; 10 yields ~2,000).
  DOMINANCE_MAX = 0.5
      Largest single entity's share of the anchor's sides. <=0.5 means no
      majority entity -- the dominance rule cannot crown a stem. Median
      dominance among volume>=6 anchors is 0.636; 0.5 takes the bottom ~40%.
      Skyline's three signature anchors sit at 0.40-0.41.
  ENTITIES_MIN = 5
      Anchor must span >= 5 distinct entities ("many"; p50 is 6).
  UNION_MIN_SHARED_SIDES = 2
      Two anchors join one cluster only if they co-occur on >= 2
      party-sides. At 1, single-transaction bridges chain unrelated
      corporate offices into a 171-anchor giant component; at 2 the largest
      cluster is 30 anchors and Skyline resolves to its own 6-anchor cluster.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/build_adjudication_dossiers.py
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / 'data' / 'cleo.db'
OUT_MAIN = REPO / 'data' / 'adjudication_dossiers_pilot.json'
OUT_COPY = Path(
    '/Users/brandonolsen/Library/Application Support/Claude/'
    'local-agent-mode-sessions/8207b354-97bc-41d6-b836-15089c080e50/'
    'a546efd6-2a5c-40e3-abf4-77b7d1f83e31/'
    'local_583822b9-6b82-4fb3-bc61-8e4a417c891c/outputs/'
    'adjudication_dossiers_pilot.json'
)

VOLUME_MIN = 10
DOMINANCE_MAX = 0.5
ENTITIES_MIN = 5
UNION_MIN_SHARED_SIDES = 2
TOP_N = 30
DOSSIER_CHAR_BUDGET = 2600  # ~2KB text-equivalent per dossier

SKYLINE_ANCHOR = ('phone', '5198260439')  # force-include this cluster

GW_JUNK = {'N/A', 'NA', 'UNKNOWN', 'NONE'}


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def display_address_anchor(canon: str) -> str:
    """'guelph|5|douglas|street||suite|301' -> '5 Douglas Street Suite 301, Guelph'."""
    parts = (canon.split('|') + [''] * 7)[:7]
    city, num, name, suffix, direction, stype, snum = parts
    street = ' '.join(p for p in (num, name, suffix, direction) if p)
    suite = ' '.join(p for p in (stype, snum) if p)
    out = ', '.join(p for p in (' '.join(x for x in (street, suite) if x), city) if p)
    return out.title() if out else canon


def fmt_price(p) -> str:
    if p is None:
        return '?'
    if p >= 1_000_000:
        return f'${p / 1_000_000:.2f}M'
    return f'${p:,.0f}'


def years_since(iso: str | None) -> float:
    if not iso:
        return 99.0
    try:
        d = datetime.strptime(iso[:10], '%Y-%m-%d').date()
    except ValueError:
        return 99.0
    return max((date.today() - d).days, 0) / 365.25


def load_side_stem(conn) -> dict:
    """(source_id, side) -> dominant brand stem (same query as timelines.py)."""
    out = {}
    for r in conn.execute(
        """
        SELECT source_id, side, stem FROM (
            SELECT pa.source_id, pa.side, m.stem,
                   ROW_NUMBER() OVER (
                       PARTITION BY pa.source_id, pa.side
                       ORDER BY COUNT(*) DESC, m.stem ASC
                   ) AS rk
            FROM party_atoms pa
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE pa.atom_type = 'brand_phrase'
            GROUP BY pa.source_id, pa.side, m.stem
        ) WHERE rk = 1
        """
    ):
        out[(r['source_id'], r['side'])] = r['stem']
    return out


def load_side_names(conn) -> dict:
    out = defaultdict(set)
    for r in conn.execute(
        "SELECT source_id, side, party_name FROM transaction_parties "
        "WHERE party_name IS NOT NULL AND party_name != ''"
    ):
        out[(r['source_id'], r['side'])].add(r['party_name'].strip())
    return out


def load_anchor_sides(conn) -> dict:
    """(anchor_type, anchor_value) -> [((source_id, side), sale_date), ...]"""
    out = defaultdict(list)
    for col, atype in (
        ('phone', 'phone'),
        ('contact_fingerprint', 'contact'),
        ('party_address_canonical', 'address_unit'),
    ):
        for r in conn.execute(
            f"SELECT {col} AS av, source_id, side, sale_date "
            f"FROM party_fingerprints "
            f"WHERE {col} IS NOT NULL AND {col} != '' "
            f"  AND sale_date IS NOT NULL AND sale_date != ''"
        ):
            out[(atype, r['av'])].append(
                ((r['source_id'], r['side']), r['sale_date'])
            )
    return out


def load_anchor_universe(conn) -> tuple[set, set]:
    """Anchors known to anchor_uniqueness; the service-provider subset."""
    universe, svc = set(), set()
    for r in conn.execute(
        'SELECT anchor_type, anchor_value, is_service_provider FROM anchor_uniqueness'
    ):
        key = (r['anchor_type'], r['anchor_value'])
        universe.add(key)
        if r['is_service_provider']:
            svc.add(key)
    return universe, svc


def load_transactions(conn) -> dict:
    out = {}
    for r in conn.execute(
        'SELECT source_id, sale_date, display_address, city, sale_price, property_id '
        'FROM transactions'
    ):
        out[r['source_id']] = (
            r['sale_date'], r['display_address'], r['city'],
            r['sale_price'], r['property_id'],
        )
    return out


def load_groups(conn) -> tuple[dict, dict]:
    side_group = {}
    for r in conn.execute(
        "SELECT source_id, side, auto_group_id FROM auto_group_members "
        "WHERE member_type = 'party_side'"
    ):
        side_group[(r['source_id'], r['side'])] = r['auto_group_id']
    group_info = {}
    for r in conn.execute(
        'SELECT auto_group_id, display_name, tier FROM auto_groups'
    ):
        group_info[r['auto_group_id']] = (r['display_name'], r['tier'])
    return side_group, group_info


def load_gw_owners(conn) -> dict:
    out = defaultdict(set)
    for r in conn.execute(
        "SELECT property_id, owner_name FROM gw_assessments "
        "WHERE property_id IS NOT NULL AND owner_name IS NOT NULL AND owner_name != ''"
    ):
        name = r['owner_name'].strip()
        if name.upper() not in GW_JUNK:
            out[r['property_id']].add(name)
    return out


def entity_key(side_key, side_stem, side_names):
    """Entity identity for a party-side: brand stem if mapped, else the
    (lowercased) first party name. None when the side has neither."""
    stem = side_stem.get(side_key)
    if stem:
        return ('stem', stem)
    names = side_names.get(side_key)
    if names:
        return ('name', sorted(names)[0].lower())
    return None


def build_dossier(anchors, stats, anchor_sides, side_stem, side_names,
                  side_group, group_info, tx, gw_owners) -> dict:
    all_sides = {}
    for k in anchors:
        for sk, sd in anchor_sides[k]:
            all_sides[sk] = sd

    ent_sides = defaultdict(list)     # entity -> [side_key]
    ent_display = defaultdict(Counter)
    for sk in all_sides:
        e = entity_key(sk, side_stem, side_names)
        if e is None:
            continue
        ent_sides[e].append(sk)
        if e[0] == 'name':
            ent_display[e][sorted(side_names[sk])[0]] += 1

    props, groups_touched = set(), Counter()
    dates = []
    for sk in all_sides:
        t = tx.get(sk[0])
        if t and t[4]:
            props.add(t[4])
        g = side_group.get(sk)
        if g:
            groups_touched[g] += 1
        if all_sides[sk]:
            dates.append(all_sides[sk])

    entities = []
    for e, sks in sorted(ent_sides.items(), key=lambda kv: -len(kv[1])):
        e_dates = sorted(all_sides[sk] for sk in sks if all_sides[sk])
        g_count = Counter(side_group[sk] for sk in sks if sk in side_group)
        g_best = g_count.most_common(1)[0][0] if g_count else None
        g_tier = group_info.get(g_best, (None, None))[1]
        samples = []
        for sk in sorted(sks, key=lambda s: all_sides[s], reverse=True):
            t = tx.get(sk[0])
            if not t:
                continue
            samples.append(f'{t[0]} | {t[1]}, {t[2]} | {fmt_price(t[3])} | {sk[1]}')
            if len(samples) >= 5:
                break
        display = (e[1] if e[0] == 'stem'
                   else ent_display[e].most_common(1)[0][0])
        entities.append({
            'name': display,
            'kind': e[0],
            'n': len(sks),
            'range': (f'{e_dates[0]}..{e_dates[-1]}' if e_dates else None),
            'group': (f'{g_best}/{g_tier}' if g_best else None),
            'tx': samples,
        })

    # compact one-line strings; top 5 by side count
    top_groups = [
        f'{g} {group_info.get(g, ("?",))[0]} '
        f'({group_info.get(g, (None, "?"))[1]}, {c} sides)'
        for g, c in groups_touched.most_common(5)
    ]
    gw_names = set()
    for p in props:
        gw_names.update(gw_owners.get(p, ()))

    sig = []
    for k in sorted(anchors, key=lambda k: -stats[k][0]):
        vol, dom, nent = stats[k]
        sig.append({
            'type': k[0],
            'value': (display_address_anchor(k[1])
                      if k[0] == 'address_unit' else k[1]),
            'volume': vol,
            'dominance': round(dom, 3),
            'n_entities': nent,
        })

    dates.sort()
    return {
        'cluster_id': None,
        'score': None,
        'signature': sig,
        'span': {
            'n_party_sides': len(all_sides),
            'n_entities': len(ent_sides),
            'n_properties': len(props),
            'n_auto_groups': len(groups_touched),
            'first_activity': dates[0] if dates else None,
            'last_activity': dates[-1] if dates else None,
        },
        'auto_groups_top': top_groups,
        'entities': entities,
        'gw_owner_names': sorted(gw_names)[:6],
    }


def trim_to_budget(d: dict) -> None:
    """Adaptively shrink a dossier toward DOSSIER_CHAR_BUDGET chars of JSON.
    Samples (the evidence) are trimmed last-but-one; entity list length and
    the low-value lists give way first."""
    def size():
        return len(json.dumps(d, ensure_ascii=False))

    n_total = len(d['entities'])
    ladder = (
        (3, 14),   # max tx samples per entity, max entities listed
        (2, 12),
        (2, 10),
        (1, 9),
        (1, 7),
    )
    for max_tx, max_entities in ladder:
        if size() <= DOSSIER_CHAR_BUDGET:
            break
        d['entities'] = d['entities'][:max_entities]
        for e in d['entities']:
            e['tx'] = e['tx'][:max_tx]
    if size() > DOSSIER_CHAR_BUDGET:
        d['auto_groups_top'] = d['auto_groups_top'][:3]
        d['gw_owner_names'] = d['gw_owner_names'][:4]
        d['signature'] = d['signature'][:6]
    if size() > DOSSIER_CHAR_BUDGET:
        d['entities'] = d['entities'][:6]
        for e in d['entities'][3:]:
            e['tx'] = e['tx'][:0]
    if len(d['entities']) < n_total:
        d['entities_omitted'] = n_total - len(d['entities'])


def main() -> None:
    conn = connect_ro(DB_PATH)
    print(f'DB: {DB_PATH} (read-only)')
    print(f'Thresholds: volume>={VOLUME_MIN}, dominance<={DOMINANCE_MAX}, '
          f'entities>={ENTITIES_MIN}, union shared sides>={UNION_MIN_SHARED_SIDES}')

    side_stem = load_side_stem(conn)
    side_names = load_side_names(conn)
    anchor_sides = load_anchor_sides(conn)
    universe, svc = load_anchor_universe(conn)
    tx = load_transactions(conn)
    side_group, group_info = load_groups(conn)
    gw_owners = load_gw_owners(conn)

    # ── Step 1: collision anchors ─────────────────────────────────────────
    stats = {}   # anchor -> (volume, dominance, n_entities)
    for key, sides in anchor_sides.items():
        if len(sides) < VOLUME_MIN or key not in universe or key in svc:
            continue
        ents = Counter()
        for sk, _sd in sides:
            e = entity_key(sk, side_stem, side_names)
            if e:
                ents[e] += 1
        if not ents:
            continue
        dom = max(ents.values()) / sum(ents.values())
        if dom <= DOMINANCE_MAX and len(ents) >= ENTITIES_MIN:
            stats[key] = (len(sides), dom, len(ents))
    print(f'Collision anchors: {len(stats):,}')

    # ── Step 2: cluster overlapping anchors (union-find) ─────────────────
    parent = {k: k for k in stats}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_side = defaultdict(list)
    for k in stats:
        for sk, _sd in anchor_sides[k]:
            by_side[sk].append(k)
    pair_count = Counter()
    for sk, ks in by_side.items():
        if len(ks) > 1:
            for a, b in combinations(sorted(ks), 2):
                pair_count[(a, b)] += 1
    for (a, b), c in pair_count.items():
        if c >= UNION_MIN_SHARED_SIDES:
            union(a, b)

    clusters = defaultdict(list)
    for k in stats:
        clusters[find(k)].append(k)

    # ── Step 3: assemble + rank dossiers ──────────────────────────────────
    dossiers = []
    for _root, anchors in clusters.items():
        dossiers.append(build_dossier(
            anchors, stats, anchor_sides, side_stem, side_names,
            side_group, group_info, tx, gw_owners))

    # score = distinct properties x recency decay (Brandon prospects ACTIVE buyers)
    for d in dossiers:
        rec = math.exp(-years_since(d['span']['last_activity']) / 3.0)
        d['score'] = round(d['span']['n_properties'] * rec, 2)
    dossiers.sort(key=lambda d: d['score'], reverse=True)

    top = dossiers[:TOP_N]
    if SKYLINE_ANCHOR in stats:
        sky_d = next(
            (d for d in dossiers
             if any(a['type'] == 'phone' and a['value'] == SKYLINE_ANCHOR[1]
                    for a in d['signature'])),
            None,
        )
        if sky_d is not None and sky_d not in top:
            top = top[:TOP_N - 1] + [sky_d]
            print('Force-included the Skyline cluster (was outside top 30).')

    for i, d in enumerate(top, 1):
        d['cluster_id'] = f'COLL_{i:03d}'
        trim_to_budget(d)

    # ── Step 4: write outputs ─────────────────────────────────────────────
    sizes = sorted((len(v) for v in clusters.values()), reverse=True)
    size_hist = Counter(
        '1' if s == 1 else '2-3' if s <= 3 else '4-6' if s <= 6
        else '7-15' if s <= 15 else '16+' for s in sizes
    )
    summary = {
        'thresholds': {
            'volume_min': VOLUME_MIN,
            'dominance_max': DOMINANCE_MAX,
            'entities_min': ENTITIES_MIN,
            'union_min_shared_sides': UNION_MIN_SHARED_SIDES,
            'note': ('volume/dominance computed over FULL party_fingerprints '
                     'history, not the anchor_uniqueness latest-tenure snapshot'),
        },
        'n_collision_anchors': len(stats),
        'n_clusters_total': len(clusters),
        'cluster_size_histogram_anchors': dict(sorted(size_hist.items())),
        'n_party_sides_all_clusters': sum(d['span']['n_party_sides'] for d in dossiers),
        'n_properties_all_clusters': sum(d['span']['n_properties'] for d in dossiers),
        'n_selected': len(top),
    }
    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'db_path': str(DB_PATH),
        'purpose': ('Anchor-collision clusters for AI group adjudication: '
                    'shared corporate signatures spanning many differently-named '
                    'entities that the dominance rule declines to group.'),
        'summary': summary,
        'dossiers': top,
    }
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    OUT_MAIN.write_text(text)
    OUT_COPY.parent.mkdir(parents=True, exist_ok=True)
    OUT_COPY.write_text(text)

    # ── Step 5: summary stats ─────────────────────────────────────────────
    print(f'\nTotal collision clusters found: {len(clusters):,} '
          f'(selected top {len(top)})')
    print(f'Cluster size distribution (anchors per cluster): '
          f'{dict(sorted(size_hist.items()))}')
    print(f'Across ALL {len(clusters):,} clusters: '
          f"{summary['n_party_sides_all_clusters']:,} party-sides, "
          f"{summary['n_properties_all_clusters']:,} distinct properties "
          f'-- the full opportunity currently invisible to the dominance rule.')
    print(f'\nTop {len(top)} selected clusters:')
    for d in top:
        sig = d['signature'][0]['value']
        print(f"  {d['cluster_id']}  score={d['score']:>8.2f}  "
              f"{d['span']['n_entities']:>3} entities  "
              f"{d['span']['n_properties']:>4} properties  "
              f"last {d['span']['last_activity']}  sig: {sig[:60]}")
    print(f'\nWrote {OUT_MAIN}')
    print(f'Wrote {OUT_COPY}')


if __name__ == '__main__':
    sys.exit(main())
