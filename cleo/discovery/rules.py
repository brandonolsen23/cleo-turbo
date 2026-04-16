"""
Rule-based pair evaluation for the discovery algorithm.

Evaluates each pair of groups against the confidence hierarchy.
Requires 2+ independent signal types for auto-confirmation.
Replaces the Phase 1 exact-match clustering that created mega-clusters
via unconstrained transitive closure.

Rule hierarchy (first match wins):
  4a: management_company + contact     -> 1.00
  4b: contact + address                -> 0.99
  4c: management_company + address     -> 0.95
  4d: management_company + phone       -> 0.90
  4g: phone + address                  -> 0.80
  4g: phone + name_fragment            -> 0.80
  multi: 2+ categories (no specific rule) -> 0.85
  4i: address only                     -> 0.60 (suggest only)
  4j: single signal only               -> 0.00 (no action)
"""

from collections import defaultdict
from .types import Signal, Cluster, Evidence


# Maximum groups sharing a single signal value before we skip it (noise filter).
# Signals shared by more than this many groups are almost certainly office buildings,
# law firms, or other noise — including them would cause O(n^2) pair explosion.
MAX_SIGNAL_FANOUT = 50


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def _build_signal_index(signals):
    """Build (signal_type, signal_value) -> set(group_ids) index."""
    index = defaultdict(set)
    for s in signals:
        index[(s.signal_type, s.signal_value)].add(s.group_id)
    return index


def _build_entity_neighbors(signals):
    """Build group_id -> set(neighbor_group_ids) from entity co-occurrence signals.

    Entity signals have signal_value = the co-occurring group_id.
    If GRP_A co-occurs with GRP_C on a transaction, there will be:
      Signal('entity', 'GRP_C', 'GRP_A', ...) and
      Signal('entity', 'GRP_A', 'GRP_C', ...)
    We build a bidirectional neighbor map from these.
    """
    neighbors = defaultdict(set)
    for s in signals:
        if s.signal_type == 'entity':
            neighbors[s.group_id].add(s.signal_value)
            neighbors[s.signal_value].add(s.group_id)
    return neighbors


def _build_group_signals(signal_index):
    """Build per-group signal index for fast pair-category lookups.

    Returns: group_signals[group_id][signal_type] = set of signal_values

    Skips any signal value with fanout > MAX_SIGNAL_FANOUT.
    Only includes the direct signal types (contact, address, phone, trade_name,
    care_of, name_fragment) — entity signals are handled separately via the
    entity neighbor map.
    """
    group_signals = defaultdict(lambda: defaultdict(set))
    for (sig_type, sig_value), group_ids in signal_index.items():
        if sig_type == 'entity':
            continue  # handled by _build_entity_neighbors
        if len(group_ids) > MAX_SIGNAL_FANOUT:
            continue
        for gid in group_ids:
            group_signals[gid][sig_type].add(sig_value)
    return group_signals


# ---------------------------------------------------------------------------
# Pair evaluation
# ---------------------------------------------------------------------------

def _get_pair_categories(gid_a, gid_b, group_signals, entity_neighbors):
    """Determine which signal categories a pair of groups shares.

    Returns a dict: {category_name: set of evidence values}

    Categories:
      - contact:            shared name_fingerprint
      - address:            shared mailing address
      - phone:              shared phone number
      - management_company: shared trade_name, care_of, or entity bridge
      - name_fragment:      shared first-two-words of normalized name
    """
    categories = {}

    gs_a = group_signals.get(gid_a, {})
    gs_b = group_signals.get(gid_b, {})

    # Direct signal types -> categories
    for sig_type, category in [
        ('contact', 'contact'),
        ('address', 'address'),
        ('phone', 'phone'),
        ('name_fragment', 'name_fragment'),
    ]:
        shared = gs_a.get(sig_type, set()) & gs_b.get(sig_type, set())
        if shared:
            categories[category] = shared

    # Management company: shared trade_name OR care_of OR entity bridge
    mgmt_evidence = set()

    for sig_type in ('trade_name', 'care_of'):
        shared = gs_a.get(sig_type, set()) & gs_b.get(sig_type, set())
        for val in shared:
            mgmt_evidence.add(f"{sig_type}:{val}")

    # Entity neighbor bridge: A and B both co-occur with the same group C
    neighbors_a = entity_neighbors.get(gid_a, set())
    neighbors_b = entity_neighbors.get(gid_b, set())
    common_entities = neighbors_a & neighbors_b
    for entity_id in common_entities:
        mgmt_evidence.add(f"entity_bridge:{entity_id}")

    if mgmt_evidence:
        categories['management_company'] = mgmt_evidence

    return categories


def evaluate_pair(categories: dict, contact_tenures: dict = None) -> tuple:
    """Evaluate a pair against the rule hierarchy.

    Rules (in order):
    4a: management_company + contact     -> 1.00
    4b: contact + address                -> 0.99
    4c: management_company + address     -> 0.95
    4d: management_company + phone       -> 0.90
    4e: distinctive contact alone        -> 0.90 (needs tenures)
    4f: contact + name_fragment          -> 0.85
    4g: phone + (address or name_fragment) -> 0.80
    4i: address only                     -> 0.60 (suggest)
    4j: single signal only               -> 0.00 (no action)

    Parameters
    ----------
    categories : dict
        {category_name: set of evidence values} as returned by _get_pair_categories.
    contact_tenures : dict, optional
        dict[fingerprint] -> list[ContactTenure] as built by
        contacts.build_contact_tenures() + contacts.check_distinctiveness().
        Required for rule 4e to fire.

    Returns
    -------
    (rule_id, confidence) : tuple[str, float]
        The first matching rule and its confidence score.
    """
    cats = set(categories.keys())

    if not cats:
        return ('none', 0.0)

    # Rules evaluated in priority order (first match wins)
    if 'management_company' in cats and 'contact' in cats:
        return ('4a', 1.00)
    if 'contact' in cats and 'address' in cats:
        return ('4b', 0.99)
    if 'management_company' in cats and 'address' in cats:
        return ('4c', 0.95)
    if 'management_company' in cats and 'phone' in cats:
        return ('4d', 0.90)

    # Rule 4e: a distinctive contact alone is enough to auto-confirm
    if 'contact' in cats and contact_tenures:
        from .contacts import is_distinctive_contact
        shared_contacts = categories.get('contact', set())
        if any(is_distinctive_contact(fp, contact_tenures) for fp in shared_contacts):
            return ('4e', 0.90)

    # Rule 4f: contact + name_fragment (replaces the generic 'multi' fallback for this case)
    if 'contact' in cats and 'name_fragment' in cats:
        return ('4f', 0.85)

    if 'phone' in cats and ('address' in cats or 'name_fragment' in cats):
        return ('4g', 0.80)

    # Fallback: address-only -> suggest
    if 'address' in cats and len(cats) == 1:
        return ('4i', 0.60)

    # Fallback: single signal -> no action
    if len(cats) == 1:
        return ('4j', 0.00)

    # Two+ categories but not matching any specific rule
    if len(cats) >= 2:
        return ('multi', 0.85)

    return ('none', 0.0)


# ---------------------------------------------------------------------------
# Cluster builder
# ---------------------------------------------------------------------------

def build_rule_based_clusters(signals, min_confidence=0.80, contact_tenures=None):
    """Build clusters using pair-wise rule evaluation.

    Only connects pairs with 2+ independent signal types (confidence >= min_confidence).
    This prevents the mega-cluster problem where transitive closure through single
    shared signals would chain tens of thousands of groups together.

    Parameters
    ----------
    signals : list[Signal]
        Flat list of signals as extracted by extract_signals().
    min_confidence : float
        Minimum confidence for a pair to become a confirmed edge. Default 0.80.
    contact_tenures : dict, optional
        dict[fingerprint] -> list[ContactTenure] for rule 4e (distinctive contact alone).
        If provided, enables rule 4e to fire for pairs sharing a distinctive contact.

    Returns
    -------
    (clusters, suggestions, evidence_list) : tuple
        clusters: list of Cluster objects with 2+ members
        suggestions: list of (gid_a, gid_b, rule_id, confidence) for pairs below threshold
        evidence_list: list of Evidence objects for confirmed pairs
    """
    if not signals:
        return [], [], []

    # Build indexes
    signal_index = _build_signal_index(signals)
    entity_neighbors = _build_entity_neighbors(signals)
    group_signals = _build_group_signals(signal_index)

    # ── Find all candidate pairs ──────────────────────────────────────────────
    # Iterate signal index to find pairs sharing at least one signal value.
    pair_candidates = set()

    for (sig_type, sig_value), group_ids in signal_index.items():
        if sig_type == 'entity':
            continue  # entity pairs handled below
        if len(group_ids) > MAX_SIGNAL_FANOUT:
            continue
        if len(group_ids) < 2:
            continue
        gids = sorted(group_ids)
        for i in range(len(gids)):
            for j in range(i + 1, len(gids)):
                pair_candidates.add((gids[i], gids[j]))

    # Add pairs connected through entity neighbor bridges.
    # If A->C and B->C (both co-occur with C), then (A,B) is a candidate.
    for gid_a, neighbors_a in entity_neighbors.items():
        for neighbor in neighbors_a:
            for gid_b in entity_neighbors.get(neighbor, set()):
                if gid_a >= gid_b:
                    continue
                pair_candidates.add((gid_a, gid_b))

    # ── Evaluate each pair ────────────────────────────────────────────────────
    confirmed_pairs = []  # (gid_a, gid_b, rule_id, confidence, categories)
    suggestions = []
    evidence_list = []

    for gid_a, gid_b in pair_candidates:
        categories = _get_pair_categories(gid_a, gid_b, group_signals, entity_neighbors)
        if not categories:
            continue

        rule_id, confidence = evaluate_pair(categories, contact_tenures=contact_tenures)

        if confidence >= min_confidence:
            confirmed_pairs.append((gid_a, gid_b, rule_id, confidence, categories))
            # Create evidence records for each category/value
            for cat_name, values in categories.items():
                for val in values:
                    evidence_list.append(Evidence(
                        signal_type=cat_name,
                        signal_value=val,
                        source_group_id=gid_a,
                        target_group_id=gid_b,
                        source_id='',
                        rule_id=rule_id,
                        confidence=confidence,
                        iteration=0,
                    ))
        elif confidence > 0:
            suggestions.append((gid_a, gid_b, rule_id, confidence))

    # ── Build clusters from confirmed pairs using Union-Find ──────────────────
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for gid_a, gid_b, rule_id, confidence, categories in confirmed_pairs:
        union(gid_a, gid_b)

    # Extract connected components
    components = defaultdict(set)
    for gid in parent:
        components[find(gid)].add(gid)

    # Create Cluster objects for components with 2+ members
    clusters = []
    for root, member_ids in components.items():
        if len(member_ids) < 2:
            continue

        cluster = Cluster(
            cluster_id='',
            anchor_group_id='',
            anchor_name='',
            member_group_ids=member_ids,
        )

        # Populate confirmed_* fields from the confirmed pairs in this cluster
        for gid_a, gid_b, rule_id, confidence, categories in confirmed_pairs:
            if gid_a in member_ids or gid_b in member_ids:
                for cat_name, values in categories.items():
                    if cat_name == 'address':
                        cluster.confirmed_addresses.update(values)
                    elif cat_name == 'contact':
                        cluster.confirmed_contacts.update(values)
                    elif cat_name == 'phone':
                        cluster.confirmed_phones.update(values)
                    elif cat_name == 'management_company':
                        cluster.confirmed_entities.update(values)
                    elif cat_name == 'name_fragment':
                        cluster.confirmed_name_fragments.update(values)

        clusters.append(cluster)

    return clusters, suggestions, evidence_list
