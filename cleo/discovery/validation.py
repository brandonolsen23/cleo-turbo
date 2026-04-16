import json


def load_ground_truth(db) -> list:
    rows = db.execute(
        "SELECT portfolio_name, anchor_group_id, member_group_ids_json FROM discovery_ground_truth"
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            'portfolio_name': row['portfolio_name'],
            'anchor_group_id': row['anchor_group_id'],
            'member_group_ids': set(json.loads(row['member_group_ids_json'])),
        })
    return result


def validate_clusters(clusters: list, ground_truth: list) -> dict:
    results = {}
    for gt in ground_truth:
        gt_members = gt['member_group_ids']
        portfolio_name = gt['portfolio_name']
        best_cluster = None
        best_overlap = 0
        for cluster in clusters:
            overlap = len(cluster.member_group_ids & gt_members)
            if overlap > best_overlap:
                best_overlap = overlap
                best_cluster = cluster
        if best_cluster is None or best_overlap == 0:
            results[portfolio_name] = {
                'precision': 0.0, 'recall': 0.0,
                'missing': sorted(gt_members), 'unexpected': [],
                'matched_cluster_size': 0,
            }
            continue
        found = best_cluster.member_group_ids & gt_members
        missing = gt_members - best_cluster.member_group_ids
        unexpected = best_cluster.member_group_ids - gt_members
        precision = len(found) / len(best_cluster.member_group_ids) if best_cluster.member_group_ids else 0.0
        recall = len(found) / len(gt_members) if gt_members else 0.0
        results[portfolio_name] = {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'missing': sorted(missing),
            'unexpected': sorted(unexpected),
            'matched_cluster_size': len(best_cluster.member_group_ids),
        }
    return results


def save_ground_truth(db, portfolio_name, anchor_group_id, member_group_ids, notes=''):
    existing = db.execute(
        "SELECT id FROM discovery_ground_truth WHERE portfolio_name = ?",
        (portfolio_name,)
    ).fetchone()
    member_json = json.dumps(sorted(member_group_ids))
    if existing:
        db.execute(
            "UPDATE discovery_ground_truth SET anchor_group_id = ?, member_group_ids_json = ?, notes = ?, updated_at = datetime('now') WHERE portfolio_name = ?",
            (anchor_group_id, member_json, notes, portfolio_name)
        )
    else:
        db.execute(
            "INSERT INTO discovery_ground_truth (portfolio_name, anchor_group_id, member_group_ids_json, notes) VALUES (?, ?, ?, ?)",
            (portfolio_name, anchor_group_id, member_json, notes)
        )
    db.commit()
