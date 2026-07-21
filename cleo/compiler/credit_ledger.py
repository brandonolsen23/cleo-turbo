"""
Credit & holdings ledgers — the single source of truth for attribution. v2.

Contract: docs/attribution-contract.md. Built once per compile as Pass 8, after
Pass 7 (manual owner overrides) so manual holdings can mirror in. ADDITIVE:
nothing reads these tables yet (two-ledger plan, step 2).

v2 rules in one breath:
  - Credits are strictly what's printed (named / member / unknown). No rollups.
  - Ownership follows the PROPERTY's timeline: every sale closes all open
    holdings on the property except its named buyers'. disposed_basis =
    'named' when the principal was the printed seller, 'property_traded' when
    the property simply moved without them. property_traded is the outreach
    signal — never an attribution.
  - Self-transfer (principal named on both sides) keeps the holding open with
    the original acquisition date.
  - Property identity: property_id, else addr-key ONLY if the address starts
    with a digit (kills the "Conc 1" legal-description collisions).
"""

from collections import defaultdict


def _property_key(property_id, display_address, city):
    if property_id:
        return property_id
    addr = (display_address or '').strip().lower()
    if not addr or not addr[0].isdigit():
        return None   # vague/legal-description address: credits only, no holdings
    return f'addr:{addr}|{(city or "").strip().lower()}'


def build_credit_ledgers(conn, verbose=True):
    """Build transaction_credits + property_holdings. Returns a stats dict."""
    conn.execute("DELETE FROM transaction_credits")
    conn.execute("DELETE FROM property_holdings")

    # ── Transactions: property key + date ────────────────────────────────
    txn = {}   # source_id -> (property_key, sale_date)
    for sid, pid, addr, city, sale_date in conn.execute(
        "SELECT source_id, property_id, display_address, city, sale_date "
        "FROM transactions"
    ):
        txn[sid] = (_property_key(pid, addr, city), sale_date or '')

    # ── Credits: strictly what's printed ─────────────────────────────────
    entity_sides = defaultdict(set)    # (sid, side) -> gids
    contact_sides = defaultdict(set)   # (sid, side) -> cids
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
    for (sid, side), gids in entity_sides.items():
        for gid in gids:
            credits.append((sid, side, 'entity', gid, 'named', None))
    for (sid, side), cids in contact_sides.items():
        for cid in cids:
            credits.append((sid, side, 'contact', cid, 'named', None))
    for (sid, side) in unknown_sides:
        credits.append((sid, side, 'unknown', '(unnamed)', 'named', None))

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

    # Dedupe on the PK — protects the walk from duplicate rows.
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

    # ── Holdings: property-timeline walk ─────────────────────────────────
    # Per transaction, who is a printed buyer / seller (holding principals).
    buyers_of = defaultdict(set)    # sid -> {(ptype, pid)}
    sellers_of = defaultdict(set)
    for sid, side, ptype, pid, basis, _via in credits:
        if ptype == 'unknown':
            continue
        if side == 'buyer':
            buyers_of[sid].add((ptype, pid))
        elif side == 'seller':
            sellers_of[sid].add((ptype, pid))

    # Property timeline includes EVERY transaction with a property identity —
    # even ones whose only parties are unknown principals (the property still
    # moved, so open holdings must close).
    prop_txns = defaultdict(list)   # property_key -> [(date, sid)]
    for sid, (pk, date) in txn.items():
        if pk is not None:
            prop_txns[pk].append((date, sid))

    holdings = []
    # (pk, ptype, pid, acq_sid, acq_date, disp_sid, disp_date, acq_basis, disp_basis)
    n_traded_closes = 0
    n_named_closes = 0
    n_preclosed = 0
    for pk, evs in prop_txns.items():
        evs.sort()
        open_h = {}   # (ptype, pid) -> (acq_sid, acq_date, acq_basis)
        for date, sid in evs:
            B = buyers_of.get(sid, set())
            S = sellers_of.get(sid, set())
            # 1. Close every open holding whose principal is not a buyer here.
            for principal in list(open_h):
                if principal in B:
                    continue   # self-transfer or re-buy: holding survives
                acq_sid, acq_date, acq_basis = open_h.pop(principal)
                if principal in S:
                    disp_basis = 'named'
                    n_named_closes += 1
                else:
                    disp_basis = 'property_traded'
                    n_traded_closes += 1
                holdings.append((pk, principal[0], principal[1],
                                 acq_sid, acq_date or None, sid, date or None,
                                 acq_basis, disp_basis))
            # 2. Printed sellers with nothing open: owned before our data.
            for principal in S:
                if principal in B or principal in open_h:
                    continue
                holdings.append((pk, principal[0], principal[1],
                                 None, None, sid, date or None,
                                 'named', 'named'))
                n_preclosed += 1
            # 3. Printed buyers open a holding.
            for (ptype, pid), basis in ((p, 'member' if p[0] == 'auto_group'
                                         else 'named') for p in B):
                if (ptype, pid) not in open_h:
                    open_h[(ptype, pid)] = (sid, date, basis)
        for (ptype, pid), (acq_sid, acq_date, acq_basis) in open_h.items():
            holdings.append((pk, ptype, pid, acq_sid, acq_date or None,
                             None, None, acq_basis, None))

    # ── manual_owner_links -> open 'manual' holdings (mirror, one door) ──
    open_keys = {(h[0], h[1], h[2]) for h in holdings if h[5] is None}
    manual_count = 0
    for arn, gid in conn.execute(
        "SELECT arn, group_id FROM manual_owner_links "
        "WHERE relationship = 'owns' AND status = 'active'"
    ):
        prow = conn.execute(
            "SELECT id FROM properties WHERE arn = ?", (arn,)
        ).fetchone()
        if not prow:
            continue   # off-book: mirrors once a property row exists
        key = (prow[0], 'entity', gid)
        if key in open_keys:
            continue   # derived ledger already says they own it
        open_keys.add(key)
        holdings.append((prow[0], 'entity', gid, None, None, None, None,
                         'manual', None))
        manual_count += 1

    conn.executemany(
        "INSERT INTO property_holdings "
        "(property_key, principal_type, principal_id, acquired_source_id, "
        " acquired_date, disposed_source_id, disposed_date, "
        " acquired_basis, disposed_basis) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        holdings,
    )
    conn.commit()

    n_open = sum(1 for h in holdings if h[5] is None)
    stats = {
        'credits_total': len(credits),
        'credits_named_entity': sum(len(g) for g in entity_sides.values()),
        'credits_named_contact': sum(len(c) for c in contact_sides.values()),
        'credits_unknown': len(unknown_sides),
        'credits_auto_group': agrp_count,
        'holdings_total': len(holdings),
        'holdings_open': n_open,
        'holdings_closed': len(holdings) - n_open,
        'closes_named': n_named_closes,
        'closes_property_traded': n_traded_closes,
        'holdings_preclosed': n_preclosed,
        'holdings_manual': manual_count,
        'contacts_with_traded_close': len({h[2] for h in holdings
                                           if h[1] == 'contact'
                                           and h[8] == 'property_traded'}),
    }
    if verbose:
        print(f"  Ledger: {stats['credits_total']:,} credits (all printed); "
              f"{stats['holdings_total']:,} holdings "
              f"({stats['holdings_open']:,} open, "
              f"{stats['closes_property_traded']:,} property-traded closes over "
              f"{stats['contacts_with_traded_close']:,} contacts, "
              f"{stats['holdings_manual']:,} manual)")
    return stats
