"""
Contact tenure establishment and distinctiveness checking.

For each contact, builds a tenure window (first/last transaction date) per group.
Checks distinctiveness: a contact whose appearances all fall within a single cluster
is 'distinctive' — safe to use as a standalone signal within their tenure.
"""

from collections import defaultdict
from .types import ContactTenure


def build_contact_tenures(db) -> dict:
    """Build contact tenure windows from transaction data.

    Queries transaction_parties joined with transactions to get
    first/last sale_date per (contact_id, group_id) pair.

    Returns: dict[contact_fingerprint] -> list[ContactTenure]
    """
    rows = db.execute("""
        SELECT c.name_fingerprint, c.id as contact_id, c.display_name,
               tp.group_id,
               MIN(t.sale_date) as first_date,
               MAX(t.sale_date) as last_date,
               COUNT(DISTINCT t.source_id) as tx_count
        FROM transaction_parties tp
        JOIN contacts c ON c.id = tp.contact_id
        JOIN transactions t ON t.source_id = tp.source_id
        WHERE tp.contact_id IS NOT NULL
          AND tp.group_id IS NOT NULL
          AND t.sale_date IS NOT NULL
          AND t.sale_date != ''
        GROUP BY c.name_fingerprint, tp.group_id
    """).fetchall()

    tenures = defaultdict(list)
    for row in rows:
        tenures[row['name_fingerprint']].append(ContactTenure(
            contact_id=row['contact_id'],
            contact_name=row['display_name'] or '',
            group_id=row['group_id'],
            first_seen=row['first_date'],
            last_seen=row['last_date'],
            transaction_count=row['tx_count'],
            is_distinctive=False,  # set later by check_distinctiveness
        ))

    return dict(tenures)


def check_distinctiveness(tenures: dict, clusters: list) -> dict:
    """Check if each contact is distinctive (all appearances in one cluster).

    A distinctive contact can be used as a standalone signal (rule 4e).
    A non-distinctive contact (appears across multiple unrelated clusters)
    is a common name or job-changer — needs a second signal.

    Args:
        tenures: dict[fingerprint] -> list[ContactTenure]
        clusters: list[Cluster] — current confirmed clusters

    Returns: updated tenures dict with is_distinctive flags set

    Also detects career changes: if a contact's appearances at different groups
    cleanly partition by date (no overlap), they get separate tenure windows
    marked as distinctive within each.
    """
    # Build group -> cluster mapping
    group_to_cluster = {}
    for cluster in clusters:
        for gid in cluster.member_group_ids:
            group_to_cluster[gid] = cluster.cluster_id

    for fingerprint, tenure_list in tenures.items():
        # Find which clusters this contact's groups belong to
        cluster_ids = set()
        unclustered_groups = set()
        for t in tenure_list:
            cid = group_to_cluster.get(t.group_id)
            if cid:
                cluster_ids.add(cid)
            else:
                unclustered_groups.add(t.group_id)

        if len(cluster_ids) <= 1 and len(unclustered_groups) <= 1:
            # All appearances in one cluster (or unclustered) — distinctive
            for t in tenure_list:
                t.is_distinctive = True
        else:
            # Check for career change (clean date partitioning)
            # Sort tenure windows by first_seen date
            sorted_tenures = sorted(tenure_list, key=lambda t: t.first_seen or '')

            # Check for overlap between consecutive tenure windows
            has_overlap = False
            for i in range(len(sorted_tenures) - 1):
                if sorted_tenures[i].last_seen and sorted_tenures[i + 1].first_seen:
                    if sorted_tenures[i].last_seen >= sorted_tenures[i + 1].first_seen:
                        has_overlap = True
                        break

            if not has_overlap and len(sorted_tenures) > 1:
                # Clean date partition — career change detected
                # Each tenure window is distinctive within its own date range
                for t in sorted_tenures:
                    t.is_distinctive = True
            else:
                # Overlapping appearances across clusters — not distinctive
                for t in tenure_list:
                    t.is_distinctive = False

    return tenures


def is_contact_in_tenure(fingerprint: str, group_id: str, tenures: dict) -> bool:
    """Check if a contact has a tenure window for a specific group."""
    for t in tenures.get(fingerprint, []):
        if t.group_id == group_id:
            return True
    return False


def is_distinctive_contact(fingerprint: str, tenures: dict) -> bool:
    """Check if a contact is marked as distinctive."""
    for t in tenures.get(fingerprint, []):
        if t.is_distinctive:
            return True
    return False
