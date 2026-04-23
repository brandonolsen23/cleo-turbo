"""Union-find clustering for Group and Contact graphs.

Strong edges form connected components. Each component becomes one
Group entity (for the Group graph) or one Contact entity (for the
Contact graph). Isolated party-sides become singleton components.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

PartySide = Tuple[str, str]
Edge = Tuple[PartySide, PartySide, str]


class _UnionFind:
    def __init__(self):
        self.parent: Dict[PartySide, PartySide] = {}
        self.rank: Dict[PartySide, int] = {}

    def add(self, x: PartySide):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: PartySide) -> PartySide:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression
        while self.parent[x] != root:
            nxt = self.parent[x]
            self.parent[x] = root
            x = nxt
        return root

    def union(self, a: PartySide, b: PartySide):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def build_components(
    edges: Iterable[Edge], *, tier: str = "strong",
) -> Dict[int, List[PartySide]]:
    """Build connected components from edges of the given tier.

    Returns {component_id: [party_side, ...]}. Component IDs are integers
    assigned in discovery order (stable within a run, NOT across runs —
    entity ID assignment happens in `entities.py`).
    """
    uf = _UnionFind()
    for a, b, t in edges:
        if t != tier:
            continue
        uf.add(a)
        uf.add(b)
        uf.union(a, b)

    groups: Dict[PartySide, List[PartySide]] = defaultdict(list)
    for node in uf.parent:
        groups[uf.find(node)].append(node)

    return {i: sorted(nodes) for i, nodes in enumerate(groups.values())}


def seed_singletons(
    components: Dict[int, List[PartySide]], all_sides: Iterable[PartySide],
) -> Dict[int, List[PartySide]]:
    """Add any party-sides that weren't in any edge as singleton components."""
    covered: Set[PartySide] = {n for nodes in components.values() for n in nodes}
    next_id = max(components.keys(), default=-1) + 1
    out = dict(components)
    for side in all_sides:
        if side in covered:
            continue
        out[next_id] = [side]
        next_id += 1
    return out
