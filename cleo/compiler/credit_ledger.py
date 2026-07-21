"""
Credit & holdings ledgers — the single source of truth for attribution.

Contract: docs/attribution-contract.md. Built once per compile, after Pass 7
(manual owner overrides), so manual holdings can be mirrored. ADDITIVE for now:
nothing reads these tables yet (two-ledger plan, step 2).

transaction_credits — one row per (transaction, side, principal):
  1. party row w/ group_id            -> ('entity', gid, 'named')
  2. party row w/ contact_id          -> ('contact', cid, 'named')
  3. party row w/ neither             -> ('unknown', '(unnamed)', 'named')
  4. same-property rollup: contact paired with entity E (shared source_id+side)
     gets credit on any txn where E is a party, the contact is not named, and
     the txn's property_key is one the contact is directly named on
     -> ('contact', cid, 'entity_named_elsewhere', via_entity_id=E)
  5. auto_group_members party_side    -> ('auto_group', agid, 'member')

property_holdings — walk each (property_key, principal)'s credited txns in
(sale_date, source_id) order: buyer credit opens, seller credit closes.
Seller with nothing open -> pre-closed holding (acquired NULL). Open holding
(disposed NULL) == currently owned. Active 'owns' manual_owner_links resolved
to a property mirror in as open 'manual' holdings (conflicts stay flagged out).
"""

from collections import defaultdict


def _property_key(property_id, display_address, city):
    if property_id:
        return property_id
    addr = (display_address or '').strip().lower()
    if not addr:
        return None
    return f'addr:{addr}|{(city or "").strip().lower()}'


def build_credit_ledgers(conn, verbose=True):
    """Build transaction_credits + property_holdings. Returns a stats dict."""
    conn.execute("DELETE FROM transaction_credits")
    conn.execute("DELETE FROM property_holdings")

    # ── Load transactions (property key + date) ──────────────────────────
    txn = {}   # source_id -> (property_key, sale_date)
    for sid, pid, addr, city, sale_date in conn.execute(
        "SELECT source_id, property_id, display_address, city, sale_date "
        "FROM transactions"
    ):
        txn[sid] = (_property_key(pid, addr, city), sale_date or '')

    # ── Load party rows ──────────────────────────────────────────────────
    # entity_sides: (source_id, side) -> set of gids
    # contact_sides: (source_id, side) -> set of cids
    entity_sides = defaultdict(set)
    contact_sides = defaultdict(set)
    unknown_sides = set()
    for sid, side, gid, cid in conn.execute(
        "SELECT source_id, side, group_id, contact_id FROM transaction_parties"
    ):
        key = (sid, side)
        if gid:
            entity_sides[key].add(gid)
        elif cid:
            contact_sides[key].add(cid)
        else:
            unknown_sides.add(key)

    credits = []   # (source_id, side, ptype, pid, basis, via)

    # Rules 1-3: named credits
    for (sid, side), gids in entity_sides.items():
        for gid in gids:
            credits.append((sid, side, 'entity', gid, 'named', None))
    for (sid, side), cids in contact_sides.items():
        for cid in cids:
            credits.append((sid, side, 'contact', cid, 'named', None))
    for (sid, side) in unknown_sides:
        credits.append((sid, side, 'unknown', '(unnamed)', 'named', None))

    # ── Rule 4: same-property via-entity rollup ──────────────────────────
    # pairing: contact & entity share a (source_id, side)
    pairs = defaultdict(set)          # cid -> set of gids
    for key, cids in contact_sides.items():
        gids = entity_sides.get(key)
        if not gids:
            continue
        for cid in cids:
            pairs[cid] |= gids

    contact_txns = defaultdict(set)   # cid -> sids the contact is named on
    for (sid, side), cids in contact_sides.items():
        for cid in cids:
            contact_txns[cid].add(sid)

    prop_txns = defaultdict(list)     # property_key -> [sids]
    for sid, (pk, _date) in txn.items():
        if pk is not None:
            prop_txns[pk].append(sid)

    txn_entity_sides = defaultdict(set)   # sid -> {(side, gid)}
    for (sid, side), gids in entity_sides.items():
        for gid in gids:
            txn_entity_sides[sid].add((side, gid))

    via_seen = set()
    via_count = 0
    for cid, sids in contact_txns.items():
        paired = pairs.get(cid)
        if not paired:
            continue
        direct_props = {txn[s][0] for s in sids if txn.get(s) and txn[s][0]}
        for pk in direct_props:
            for sid in prop_txns.get(pk, ()):
                if sid in sids:
                    continue   # contact already named on this txn
                for side, gid in txn_entity_sides.get(sid, ()):
                    if gid not in paired:
                        continue
                    dedupe_key = (sid, side, cid)
                    if dedupe_key in via_seen:
                        continue
                    via_seen.add(dedupe_key)
                    via_count += 1
                    credits.append((sid, side, 'contact', cid,
                                    'entity_named_elsewhere', gid))

    # ── Rule 5: auto-group member credits (discovery tables may be absent) ─
    agrp_count = 0
    try:
        for agid, sid, side in conn.execute(
            "SELECT auto_group_id, source_id, side FROM auto_group_members "
            "WHERE member_type = 'party_side'"
        ):
            if sid in txn and side:
                credits.append((sid, side, 'auto_group', agid, 'member', None))
                agrp_count += 1
    except Exception:
        pass   # no discovery run yet / test fixture without the table

    # Dedupe on the PK — protects the holdings walk from double events
    # (e.g. duplicate auto_group_members rows).
    _seen = set()
    _deduped = []
    for c in credits:
        k = (c[0], c[1], c[2], c[3])
        if k not in _seen:
            _seen.add(k)
            _deduped.append(c)
    credits = _deduped

    conn.executemany(
        "INSERT OR IGNORE INTO transaction_credits "
        "(source_id, side, principal_type, principal_id, basis, via_entity_id) "
        "VALUES (?,?,?,?,?,?)",
        credits,
    )

    # ── Holdings: walk credits per (property_key, principal) by date ─────
    # unknown principals never hold; auto_group holdings derive the same way.
    events = defaultdict(list)   # (pk, ptype, pid) -> [(date, sid, side)]
    for sid, side, ptype, pid, basis, _via in credits:
        if ptype == 'unknown':
            continue
        t = txn.get(sid)
        if not t or t[0] is None:
            continue   # no property identity -> credits only, no holding
        events[(t[0], ptype, pid)].append((t[1], sid, side))

    holdings = []   # (pk, ptype, pid, acq_sid, acq_date, disp_sid, disp_date, basis)
    for (pk, ptype, pid), evs in events.items():
        # Within one transaction the SELLER credit processes first: a principal
        # on both sides (self-transfer between their entities) closes the prior
        # holding and immediately reopens — staying the owner. (Saherdid's 2017
        # RT125638/RT126004/RT126011 shape.)
        evs.sort(key=lambda e: (e[0], e[1], 0 if e[2] == 'seller' else 1))
        open_h = None   # (acq_sid, acq_date)
        for date, sid, side in evs:
            if side == 'buyer':
                if open_h is None:
                    open_h = (sid, date)
            elif side == 'seller':
                if open_h is not None:
                    holdings.append((pk, ptype, pid, open_h[0], open_h[1] or None,
                                     sid, date or None, 'derived'))
                    open_h = None
                else:
                    holdings.append((pk, ptype, pid, None, None,
                                     sid, date or None, 'derived'))
        if open_h is not None:
            holdings.append((pk, ptype, pid, open_h[0], open_h[1] or None,
                             None, None, 'derived'))

    # ── manual_owner_links -> open 'manual' holdings (one door, mirrored) ─
    open_keys = {(h[0], h[1], h[2]) for h in holdings if h[5] is None}
    manual_count = 0
    for arn, gid in conn.execute(
        "SELECT l.arn, l.group_id FROM manual_owner_links l "
        "WHERE l.relationship = 'owns' AND l.status = 'active'"
    ):
        prow = conn.execute(
            "SELECT id FROM properties WHERE arn = ?", (arn,)
        ).fetchone()
        if not prow:
            continue   # off-book: stays pending, mirrors once a row exists
        key = (prow[0], 'entity', gid)
        if key in open_keys:
            continue   # derived ledger already says they own it
        open_keys.add(key)
        holdings.append((prow[0], 'entity', gid, None, None, None, None, 'manual'))
        manual_count += 1

    conn.executemany(
        "INSERT INTO property_holdings "
        "(property_key, principal_type, principal_id, acquired_source_id, "
        " acquired_date, disposed_source_id, disposed_date, basis) "
        "VALUES (?,?,?,?,?,?,?,?)",
        holdings,
    )
    conn.commit()

    n_open = sum(1 for h in holdings if h[5] is None)
    stats = {
        'credits_total': len(credits),
        'credits_named_entity': sum(len(g) for g in entity_sides.values()),
        'credits_named_contact': sum(len(c) for c in contact_sides.values()),
        'credits_unknown': len(unknown_sides),
        'credits_via_entity': via_count,
        'credits_auto_group': agrp_count,
        'contacts_with_via_credit': len({c[3] for c in credits
                                         if c[4] == 'entity_named_elsewhere'}),
        'holdings_total': len(holdings),
        'holdings_open': n_open,
        'holdings_closed': len(holdings) - n_open,
        'holdings_preclosed': sum(1 for h in holdings
                                  if h[3] is None and h[5] is not None),
        'holdings_manual': manual_count,
    }
    if verbose:
        print(f"  Ledger: {stats['credits_total']:,} credits "
              f"({stats['credits_via_entity']:,} via-entity over "
              f"{stats['contacts_with_via_credit']:,} contacts, "
              f"{stats['credits_auto_group']:,} auto-group); "
              f"{stats['holdings_total']:,} holdings "
              f"({stats['holdings_open']:,} open, {stats['holdings_manual']:,} manual)")
    return stats
