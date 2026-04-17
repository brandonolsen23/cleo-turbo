"""
Engine orchestrator for the Group Discovery Algorithm.

Wires together signal extraction, clustering, iterative expansion,
cluster splitting, and validation into a single callable function
used by the CLI and future API routes.
"""

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from .types import RunConfig, RunResult
from .signals import extract_signals
from .rules import build_rule_based_clusters, expand_clusters, split_disconnected_clusters
from .contacts import build_contact_tenures, check_distinctiveness
from .validation import load_ground_truth, validate_clusters
from cleo.database.group_merge_ops import execute_merge, resolve_target
from cleo.analytics.groups import refresh_group_analytics


def _make_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return f"run_{ts}_{uid}"


def _assign_cluster_ids(clusters: list) -> list:
    """Assign sequential DISC_NNNNN IDs to clusters (in-place, sorted by size desc)."""
    clusters.sort(key=lambda c: len(c.member_group_ids), reverse=True)
    for i, cluster in enumerate(clusters, start=1):
        cluster.cluster_id = f"DISC_{i:05d}"
    return clusters


def _resolve_anchors(clusters: list, db) -> None:
    """Set anchor_group_id (highest txn count) and anchor_name (best common name).

    Anchor name priority:
      1. Most frequent trade_name / companies_json value across cluster transactions
      2. Most frequent care_of value
      3. Shared name prefix (first 2 words appearing in 50%+ of member names)
      4. Anchor group's display_name (fallback)
    """
    if not clusters:
        return

    # Gather all member IDs in one query
    all_member_ids = set()
    for cluster in clusters:
        all_member_ids.update(cluster.member_group_ids)

    if not all_member_ids:
        return

    placeholders = ",".join("?" * len(all_member_ids))
    rows = db.execute(
        f"SELECT id, display_name, normalized_name, transaction_count FROM groups WHERE id IN ({placeholders})",
        list(all_member_ids),
    ).fetchall()

    group_info = {row["id"]: row for row in rows}

    # Bulk-load trade names and care-of values for all member groups
    # Maps group_id -> list of management company names
    import json as _json
    trade_rows = db.execute(
        f"""
        SELECT tp.group_id, t.seller_trade_name, t.buyer_trade_name,
               t.seller_care_of, t.buyer_care_of,
               t.seller_companies_json, t.buyer_companies_json, tp.side
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        WHERE tp.group_id IN ({placeholders})
          AND tp.group_id IS NOT NULL
        """,
        list(all_member_ids),
    ).fetchall()

    # Build group_id -> list of (name, source) for ranking
    group_mgmt_names: dict = defaultdict(list)
    for row in trade_rows:
        gid = row["group_id"]
        side = row["side"]
        # Trade name on this group's side
        trade = row[f"{side}_trade_name"]
        if trade and trade.strip():
            group_mgmt_names[gid].append(trade.strip())
        # Care-of on this group's side
        care = row[f"{side}_care_of"]
        if care and care.strip():
            group_mgmt_names[gid].append(care.strip())
        # Companies JSON on this group's side
        companies_raw = row[f"{side}_companies_json"]
        if companies_raw and companies_raw != "[]":
            try:
                for name in _json.loads(companies_raw):
                    if name and isinstance(name, str) and name.strip():
                        group_mgmt_names[gid].append(name.strip())
            except (ValueError, TypeError):
                pass

    for cluster in clusters:
        # Pick anchor = highest transaction_count
        best_id = None
        best_count = -1
        for gid in cluster.member_group_ids:
            info = group_info.get(gid)
            if info is None:
                continue
            tx_count = info["transaction_count"] or 0
            if tx_count > best_count:
                best_count = tx_count
                best_id = gid
        if not best_id:
            continue
        cluster.anchor_group_id = best_id

        # Find best common name from management company references
        name_counts: dict = defaultdict(int)
        for gid in cluster.member_group_ids:
            for name in group_mgmt_names.get(gid, []):
                name_counts[name] += 1

        if name_counts:
            # Pick the most frequently referenced management company name
            best_common = max(name_counts, key=lambda n: name_counts[n])
            if name_counts[best_common] >= 2:
                cluster.anchor_name = best_common
                continue

        # Fallback: shared name prefix across 50%+ of members
        from cleo.compiler.reconciler import normalize_group_name
        prefix_counts: dict = defaultdict(int)
        for gid in cluster.member_group_ids:
            info = group_info.get(gid)
            if not info:
                continue
            norm = info["normalized_name"] or ""
            words = norm.split()
            if len(words) >= 2:
                prefix = words[0] + " " + words[1]
                prefix_counts[prefix] += 1

        threshold = len(cluster.member_group_ids) * 0.5
        if prefix_counts:
            best_prefix = max(prefix_counts, key=lambda p: prefix_counts[p])
            if prefix_counts[best_prefix] >= threshold and prefix_counts[best_prefix] >= 2:
                # Title-case the prefix
                cluster.anchor_name = best_prefix.title()
                continue

        # Final fallback: anchor group's display name
        anchor_info = group_info.get(best_id)
        cluster.anchor_name = anchor_info["display_name"] if anchor_info else best_id


def _write_evidence(db, run_id: str, clusters: list, signals: list) -> int:
    """Write per-cluster evidence rows to discovery_evidence. Returns count written."""
    # Build index: (signal_type, signal_value) -> list of (group_id, source_id)
    sig_index = defaultdict(list)
    for s in signals:
        sig_index[(s.signal_type, s.signal_value)].append((s.group_id, s.source_id))

    rows_written = 0
    for cluster in clusters:
        members = cluster.member_group_ids

        # For each confirmed signal category, find all (source, target) pairs
        confirmed_by_type = {
            "address": cluster.confirmed_addresses,
            "contact": cluster.confirmed_contacts,
            "phone": cluster.confirmed_phones,
            "entity": cluster.confirmed_entities,
            "name_fragment": cluster.confirmed_name_fragments,
        }

        for sig_type, confirmed_values in confirmed_by_type.items():
            for sig_value in confirmed_values:
                # All groups in this cluster that produced this signal
                matching = [
                    (gid, src_id)
                    for gid, src_id in sig_index.get((sig_type, sig_value), [])
                    if gid in members
                ]
                if len(matching) < 2:
                    continue

                # Emit evidence rows for every ordered pair
                seen_pairs = set()
                for i, (gid_a, src_a) in enumerate(matching):
                    for gid_b, _ in matching:
                        if gid_a == gid_b:
                            continue
                        pair = (gid_a, gid_b)
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        db.execute(
                            """
                            INSERT INTO discovery_evidence
                                (run_id, signal_type, signal_value,
                                 source_group_id, target_group_id,
                                 source_id, rule_id, confidence, iteration)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run_id,
                                sig_type,
                                sig_value,
                                gid_a,
                                gid_b,
                                src_a or None,
                                "exact_match",
                                0.90,
                                0,
                            ),
                        )
                        rows_written += 1

    db.commit()
    return rows_written


def _write_evidence_from_list(db, run_id: str, evidence_list: list) -> int:
    """Write pre-computed evidence rows to discovery_evidence. Returns count written."""
    rows_written = 0
    for ev in evidence_list:
        db.execute(
            """
            INSERT INTO discovery_evidence
                (run_id, signal_type, signal_value,
                 source_group_id, target_group_id,
                 source_id, rule_id, confidence, iteration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ev.signal_type,
                ev.signal_value,
                ev.source_group_id,
                ev.target_group_id,
                ev.source_id or None,
                ev.rule_id,
                ev.confidence,
                ev.iteration,
            ),
        )
        rows_written += 1
    db.commit()
    return rows_written


def _log_run(db, run_id: str, started_at: str, result: RunResult, config: RunConfig, gt_results) -> None:
    """Insert a row into discovery_runs."""
    stats = {
        "clusters_found": result.clusters_found,
        "groups_processed": result.groups_processed,
        "merges_executed": result.merges_executed,
        "suggestions_created": result.suggestions_created,
        "iterations": result.iterations,
    }
    db.execute(
        """
        INSERT INTO discovery_runs (run_id, mode, started_at, completed_at, stats_json, diff_json, config_json)
        VALUES (?, ?, ?, datetime('now'), ?, ?, ?)
        """,
        (
            run_id,
            result.mode,
            started_at,
            json.dumps(stats),
            json.dumps(gt_results) if gt_results else None,
            json.dumps({
                "mode": config.mode,
                "max_iterations": config.max_iterations,
                "min_confidence_auto": config.min_confidence_auto,
                "min_confidence_suggest": config.min_confidence_suggest,
            }),
        ),
    )
    db.commit()


def _score_clusters(clusters: list) -> None:
    """Assign confidence scores to clusters based on internal evidence strength (in-place)."""
    for cluster in clusters:
        # Count how many signal types are confirmed
        signal_types = 0
        if cluster.confirmed_addresses:
            signal_types += 1
        if cluster.confirmed_contacts:
            signal_types += 1
        if cluster.confirmed_phones:
            signal_types += 1
        if cluster.confirmed_entities:
            signal_types += 1

        # Member factor: larger clusters get a slight boost (diminishing returns above 5)
        member_factor = min(1.0, len(cluster.member_group_ids) / 5.0)

        # Base confidence from signal type diversity
        if signal_types >= 3:
            cluster.confidence = 0.95
        elif signal_types >= 2:
            cluster.confidence = 0.90
        else:
            cluster.confidence = 0.80

        # Small boost for well-connected clusters
        cluster.confidence = min(1.0, cluster.confidence + member_factor * 0.05)

        # Set status based on threshold
        if cluster.confidence >= 0.90:
            cluster.status = 'auto_confirmed'
        else:
            cluster.status = 'needs_review'


def _execute_merges(db, clusters: list, config: RunConfig, user: str = 'discovery'):
    """Execute merges for confirmed clusters (confidence >= config.min_confidence_auto).

    Returns (merge_count, skipped_count).
    """
    merge_count = 0
    skipped = 0
    affected_anchors = set()

    for cluster in clusters:
        if cluster.confidence < config.min_confidence_auto:
            continue

        anchor = cluster.anchor_group_id

        # Verify anchor exists and isn't merged
        anchor_row = db.execute(
            "SELECT id, status FROM groups WHERE id = ?", (anchor,)
        ).fetchone()
        if not anchor_row or anchor_row['status'] == 'merged':
            skipped += len(cluster.member_group_ids) - 1
            continue

        # Resolve anchor through any existing merge chains
        ultimate_anchor = resolve_target(db, anchor)
        if ultimate_anchor != anchor:
            anchor = ultimate_anchor

        for member_id in cluster.member_group_ids:
            if member_id == anchor:
                continue

            # Check if member is already merged
            member_row = db.execute(
                "SELECT id, status FROM groups WHERE id = ?", (member_id,)
            ).fetchone()
            if not member_row or member_row['status'] == 'merged':
                skipped += 1
                continue

            # Check if already merged into this target
            existing = db.execute(
                "SELECT id FROM group_merges WHERE source_group_id = ? AND target_group_id = ? AND unmerged_at IS NULL",
                (member_id, anchor)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Record the merge then execute it
            db.execute(
                "INSERT INTO group_merges (source_group_id, target_group_id, merged_by) VALUES (?, ?, ?)",
                (member_id, anchor, user)
            )
            execute_merge(db, member_id, anchor)
            merge_count += 1

        affected_anchors.add(anchor)

    db.commit()

    # Refresh analytics for all affected anchor groups
    if affected_anchors:
        refresh_group_analytics(db, group_ids=list(affected_anchors))

    return merge_count, skipped


def run_discovery(db, config: RunConfig = None) -> RunResult:
    """Run the full discovery pipeline.

    Steps:
      0. Extract signals from the database
      1. Build contact tenures (for rule 4e)
      2. Initial rule-based clustering (pair-wise 2-signal evaluation)
      3. Check contact distinctiveness
      4. Iterative expansion (loop until convergence or max_iterations)
      5. Cluster splitting (remove disconnected components)
      6. Re-check distinctiveness after expansion
      6b. Score clusters (confidence + status assignment)
      7. Assign cluster IDs and resolve anchors
      8. Validate against ground truth (validate/dry_run modes)
      8b. Execute merges (execute/incremental modes only)
      9. Write evidence to database
     10. Log the run

    Parameters
    ----------
    db : sqlite3.Connection
        Open connection to the Cleo SQLite database.
    config : RunConfig, optional
        Run parameters. Defaults to validate mode.

    Returns
    -------
    RunResult
        Summary of the run.
    """
    if config is None:
        config = RunConfig()

    run_id = _make_run_id()
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    print(f"[discovery] Run ID: {run_id}  mode={config.mode}")
    print(f"[discovery] Started at {started_at} UTC")
    print()

    # ── Step 0: Extract signals ───────────────────────────────────────────────
    print("[discovery] Step 0: Extracting signals...")
    signals = extract_signals(db)

    # Tally by type
    counts_by_type: dict = defaultdict(int)
    for s in signals:
        counts_by_type[s.signal_type] += 1

    print(f"[discovery]   Total signals: {len(signals)}")
    for sig_type in sorted(counts_by_type):
        print(f"[discovery]     {sig_type}: {counts_by_type[sig_type]}")
    print()

    # ── Step 1: Build contact tenures ─────────────────────────────────────────
    print("[discovery] Step 1: Building contact tenures...")
    tenures = build_contact_tenures(db)
    print(f"[discovery]   Contact fingerprints with tenures: {len(tenures)}")
    print()

    # ── Step 2: Initial rule-based clustering ─────────────────────────────────
    print("[discovery] Step 2: Building rule-based clusters (2+ signal types per pair)...")
    clusters, suggestions, evidence_list = build_rule_based_clusters(
        signals, contact_tenures=tenures
    )

    initial_cluster_count = len(clusters)
    initial_member_count = sum(len(c.member_group_ids) for c in clusters)

    print(f"[discovery]   Initial clusters: {initial_cluster_count}")
    print(f"[discovery]   Initial groups in clusters: {initial_member_count}")
    print(f"[discovery]   Suggestions (below threshold): {len(suggestions)}")
    if suggestions:
        from collections import Counter
        rule_counts = Counter(rule_id for _, _, rule_id, _ in suggestions)
        for rule_id, count in rule_counts.most_common():
            print(f"[discovery]     suggestion rule {rule_id}: {count}")
    print()

    # ── Step 3: Check contact distinctiveness ─────────────────────────────────
    print("[discovery] Step 3: Checking contact distinctiveness...")
    tenures = check_distinctiveness(tenures, clusters)
    distinctive_count = sum(
        1 for fp, tlist in tenures.items()
        if any(t.is_distinctive for t in tlist)
    )
    print(f"[discovery]   Distinctive contacts: {distinctive_count} / {len(tenures)}")
    print()

    # ── Step 4: Iterative expansion ───────────────────────────────────────────
    print("[discovery] Step 4: Iterative expansion...")
    total_expansion_added = 0
    final_iteration = 0

    for iteration in range(1, config.max_iterations + 1):
        new_members = expand_clusters(clusters, signals, tenures=tenures, iteration=iteration)
        final_iteration = iteration
        total_expansion_added += new_members
        print(f"[discovery]   Iteration {iteration}: +{new_members} groups added")
        if new_members == 0:
            break

    expansion_member_count = sum(len(c.member_group_ids) for c in clusters)
    print(f"[discovery]   Expansion converged after {final_iteration} iteration(s)")
    print(f"[discovery]   Groups in clusters after expansion: {expansion_member_count} (+{total_expansion_added})")
    print()

    # ── Step 5: Cluster splitting ─────────────────────────────────────────────
    print("[discovery] Step 5: Splitting disconnected clusters...")
    pre_split_count = len(clusters)
    clusters = split_disconnected_clusters(clusters, signals)
    post_split_count = len(clusters)
    split_diff = post_split_count - pre_split_count
    print(f"[discovery]   Clusters before split: {pre_split_count}")
    print(f"[discovery]   Clusters after split: {post_split_count} ({'+' if split_diff >= 0 else ''}{split_diff})")
    print()

    # ── Step 6: Re-check distinctiveness after expansion ──────────────────────
    print("[discovery] Step 6: Re-checking contact distinctiveness post-expansion...")
    tenures = check_distinctiveness(tenures, clusters)
    distinctive_count_post = sum(
        1 for fp, tlist in tenures.items()
        if any(t.is_distinctive for t in tlist)
    )
    print(f"[discovery]   Distinctive contacts: {distinctive_count_post} / {len(tenures)}")
    print()

    # ── Step 6b: Score clusters ───────────────────────────────────────────────
    if clusters:
        _score_clusters(clusters)
        auto_confirmed = sum(1 for c in clusters if c.status == 'auto_confirmed')
        needs_review = sum(1 for c in clusters if c.status == 'needs_review')
        print(f"[discovery] Step 6b: Cluster confidence scoring complete.")
        print(f"[discovery]   auto_confirmed (>= {config.min_confidence_auto}): {auto_confirmed}")
        print(f"[discovery]   needs_review: {needs_review}")
        print()

    # ── Step 7: Assign IDs and anchors ────────────────────────────────────────
    if clusters:
        clusters = _assign_cluster_ids(clusters)
        _resolve_anchors(clusters, db)

        # Persist cluster names for the API
        db.execute("DELETE FROM discovery_cluster_names WHERE run_id = ?", (run_id,))
        for cluster in clusters:
            db.execute(
                "INSERT INTO discovery_cluster_names (run_id, anchor_group_id, cluster_name) VALUES (?, ?, ?)",
                (run_id, cluster.anchor_group_id, cluster.anchor_name)
            )
        db.commit()

        total_members = sum(len(c.member_group_ids) for c in clusters)
        print(f"[discovery] Step 7: Cluster IDs assigned ({clusters[0].cluster_id} - {clusters[-1].cluster_id})")
        print(f"[discovery]   Total clusters: {len(clusters)}")
        print(f"[discovery]   Total groups in clusters: {total_members}")

        # Size distribution
        sizes = [len(c.member_group_ids) for c in clusters]
        size_dist = defaultdict(int)
        for s in sizes:
            if s <= 5:
                size_dist[f"{s}"] += 1
            elif s <= 10:
                size_dist["6-10"] += 1
            elif s <= 20:
                size_dist["11-20"] += 1
            else:
                size_dist["21+"] += 1
        print(f"[discovery]   Size distribution: {dict(sorted(size_dist.items()))}")
        print()

    # ── Step 8: Validate against ground truth ─────────────────────────────────
    gt_results = None
    if config.mode in ("validate", "dry_run"):
        print("[discovery] Step 8: Loading ground truth...")
        ground_truth = load_ground_truth(db)
        if ground_truth:
            print(f"[discovery]   Ground truth portfolios: {len(ground_truth)}")
            gt_results = validate_clusters(clusters, ground_truth)
            print()
            print("[discovery] Validation results:")
            for portfolio_name, res in gt_results.items():
                p = res["precision"]
                r = res["recall"]
                missing_count = len(res["missing"])
                unexpected_count = len(res["unexpected"])
                print(
                    f"[discovery]   {portfolio_name}: "
                    f"precision={p:.0%}  recall={r:.0%}  "
                    f"size={res['matched_cluster_size']}  "
                    f"missing={missing_count}  unexpected={unexpected_count}"
                )
                if missing_count > 0 and missing_count <= 10:
                    for m in res["missing"]:
                        print(f"[discovery]     missing: {m}")
                if unexpected_count > 0 and unexpected_count <= 10:
                    for u in res["unexpected"]:
                        print(f"[discovery]     unexpected: {u}")
        else:
            print("[discovery]   No ground truth entries found -- skipping validation.")
        print()

    # ── Step 8b: Execute merges (execute and incremental modes) ──────────────
    merges_executed = 0
    if config.mode in ('execute', 'incremental'):
        if config.mode == 'incremental':
            print("[discovery] Step 8b: Incremental mode — running full pipeline, executing only new merges...")
        else:
            print("[discovery] Step 8b: Executing merges for confirmed clusters...")
        merge_count, skipped_count = _execute_merges(db, clusters, config)
        merges_executed = merge_count
        print(f"[discovery]   Merges executed: {merge_count}, skipped: {skipped_count}")
        print()

    # ── Step 9: Write evidence ────────────────────────────────────────────────
    if config.mode != "dry_run" and evidence_list:
        print("[discovery] Step 9: Writing evidence to database...")

        # Remap all evidence target_group_ids to the cluster's anchor
        # so the API can look up clusters by anchor_group_id consistently
        group_to_anchor = {}
        for cluster in clusters:
            for gid in cluster.member_group_ids:
                group_to_anchor[gid] = cluster.anchor_group_id

        for ev in evidence_list:
            # Remap both source and target to point source→anchor
            anchor = group_to_anchor.get(ev.source_group_id) or group_to_anchor.get(ev.target_group_id)
            if anchor:
                # source = the non-anchor member, target = the anchor
                if ev.source_group_id == anchor:
                    ev.source_group_id, ev.target_group_id = ev.target_group_id, anchor
                else:
                    ev.target_group_id = anchor

        evidence_count = _write_evidence_from_list(db, run_id, evidence_list)
        print(f"[discovery]   Evidence rows written: {evidence_count}")
        print()

    # ── Step 10: Build result and log run ─────────────────────────────────────
    all_group_ids = {s.group_id for s in signals}
    result = RunResult(
        run_id=run_id,
        mode=config.mode,
        clusters_found=len(clusters),
        merges_executed=merges_executed,
        suggestions_created=len(suggestions),
        groups_processed=len(all_group_ids),
        iterations=final_iteration,
        ground_truth_results=gt_results,
    )

    _log_run(db, run_id, started_at, result, config, gt_results)
    print(f"[discovery] Run logged to discovery_runs.")
    print(f"[discovery] Done. clusters_found={result.clusters_found}  groups_processed={result.groups_processed}  iterations={result.iterations}")

    return result
