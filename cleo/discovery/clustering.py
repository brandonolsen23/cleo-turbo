"""
Step 1 of the Group Discovery Algorithm: Exact Match Clustering.

Groups entities that share identical signals using Union-Find (disjoint-set union)
with path compression. A shared signal is a (signal_type, signal_value) pair that
appears on 2+ distinct groups — strong evidence they belong to the same portfolio.
"""

from collections import defaultdict
from .types import Signal, Cluster


def build_exact_match_clusters(signals: list) -> list:
    """Step 1: Build clusters from groups that share identical signals.

    Uses Union-Find to efficiently group entities connected by shared signals.
    A shared signal = same (signal_type, signal_value) appearing on 2+ groups.

    Returns a list of Cluster objects, each containing 2+ member groups.
    """
    # Index: (signal_type, signal_value) -> set of group_ids
    signal_index = defaultdict(set)
    for s in signals:
        signal_index[(s.signal_type, s.signal_value)].add(s.group_id)

    # Union-Find
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

    # Connect groups that share any signal
    for (sig_type, sig_value), group_ids in signal_index.items():
        if len(group_ids) < 2:
            continue
        group_list = list(group_ids)
        for i in range(1, len(group_list)):
            union(group_list[0], group_list[i])

    # Build clusters from connected components
    components = defaultdict(set)
    for gid in parent:
        components[find(gid)].add(gid)

    # Create Cluster objects for components with 2+ members
    clusters = []
    for root, member_ids in components.items():
        if len(member_ids) < 2:
            continue

        cluster = Cluster(
            cluster_id='',       # assigned later
            anchor_group_id='',  # determined later
            anchor_name='',
            member_group_ids=member_ids,
        )

        # Record which signals are confirmed (shared by 2+ members in this cluster)
        for (sig_type, sig_value), group_ids in signal_index.items():
            shared = group_ids & member_ids
            if len(shared) >= 2:
                if sig_type == 'address':
                    cluster.confirmed_addresses.add(sig_value)
                elif sig_type == 'contact':
                    cluster.confirmed_contacts.add(sig_value)
                elif sig_type == 'phone':
                    cluster.confirmed_phones.add(sig_value)
                elif sig_type in ('trade_name', 'care_of', 'entity'):
                    cluster.confirmed_entities.add(sig_value)
                elif sig_type == 'name_fragment':
                    cluster.confirmed_name_fragments.add(sig_value)

        clusters.append(cluster)

    return clusters
