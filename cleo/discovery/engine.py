"""
Engine orchestrator for the Group Discovery Algorithm.

Wires together signal extraction, clustering, and validation into a
single callable function used by the CLI and future API routes.
"""

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from .types import RunConfig, RunResult
from .signals import extract_signals
from .clustering import build_exact_match_clusters
from .rules import build_rule_based_clusters
from .validation import load_ground_truth, validate_clusters


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
    """Set anchor_group_id and anchor_name to the member with the highest transaction_count."""
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
        f"SELECT id, display_name, transaction_count FROM groups WHERE id IN ({placeholders})",
        list(all_member_ids),
    ).fetchall()

    group_info = {row["id"]: row for row in rows}

    for cluster in clusters:
        best_id = None
        best_count = -1
        best_name = ""
        for gid in cluster.member_group_ids:
            info = group_info.get(gid)
            if info is None:
                continue
            tx_count = info["transaction_count"] or 0
            if tx_count > best_count:
                best_count = tx_count
                best_id = gid
                best_name = info["display_name"] or gid
        if best_id:
            cluster.anchor_group_id = best_id
            cluster.anchor_name = best_name


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


def run_discovery(db, config: RunConfig = None) -> RunResult:
    """Run the full discovery pipeline.

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

    # ── Step 1: Build clusters (rule-based pair evaluation) ─────────────────
    print("[discovery] Step 1: Building rule-based clusters (2+ signal types per pair)...")
    clusters, suggestions, evidence_list = build_rule_based_clusters(signals)
    print(f"[discovery]   Confirmed clusters: {len(clusters)}")
    print(f"[discovery]   Suggestions (below threshold): {len(suggestions)}")
    if suggestions:
        from collections import Counter
        rule_counts = Counter(rule_id for _, _, rule_id, _ in suggestions)
        for rule_id, count in rule_counts.most_common():
            print(f"[discovery]     suggestion rule {rule_id}: {count}")
    print()

    # ── Assign IDs and anchors ────────────────────────────────────────────────
    if clusters:
        clusters = _assign_cluster_ids(clusters)
        _resolve_anchors(clusters, db)

        total_members = sum(len(c.member_group_ids) for c in clusters)
        print(f"[discovery] Cluster IDs assigned ({clusters[0].cluster_id} – {clusters[-1].cluster_id})")
        print(f"[discovery] Groups in clusters: {total_members}")
        print()

    # ── Validate mode ─────────────────────────────────────────────────────────
    gt_results = None
    if config.mode in ("validate", "dry_run"):
        print("[discovery] Loading ground truth...")
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
        else:
            print("[discovery]   No ground truth entries found — skipping validation.")
        print()

    # ── Write evidence ────────────────────────────────────────────────────────
    if config.mode != "dry_run" and evidence_list:
        print("[discovery] Writing evidence to database...")
        evidence_count = _write_evidence_from_list(db, run_id, evidence_list)
        print(f"[discovery]   Evidence rows written: {evidence_count}")
        print()

    # ── Build result ──────────────────────────────────────────────────────────
    all_group_ids = {s.group_id for s in signals}
    result = RunResult(
        run_id=run_id,
        mode=config.mode,
        clusters_found=len(clusters),
        merges_executed=0,          # execute mode not yet implemented
        suggestions_created=len(suggestions),
        groups_processed=len(all_group_ids),
        iterations=1,
        ground_truth_results=gt_results,
    )

    # ── Log run ───────────────────────────────────────────────────────────────
    _log_run(db, run_id, started_at, result, config, gt_results)
    print(f"[discovery] Run logged to discovery_runs.")
    print(f"[discovery] Done. clusters_found={result.clusters_found}  groups_processed={result.groups_processed}")

    return result
