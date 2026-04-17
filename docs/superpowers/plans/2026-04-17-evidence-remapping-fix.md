# Evidence Remapping Fix — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the evidence writing so the Discovery frontend correctly shows cluster names and members without creating false mega-clusters.

**Root Cause:** The evidence remapping commit (`ad09b75`) introduced a bug where evidence target_group_ids get remapped across cluster boundaries, causing separate clusters to merge in the evidence table. Before the fix: largest cluster = 64 members. After: 2,916.

**Architecture:** The evidence table needs all rows for a given cluster to share the same `target_group_id` (the cluster's anchor). But the remapping must ONLY remap within a cluster — never across clusters.

---

## The Problem in Detail

The rules engine (`build_rule_based_clusters`) produces `Evidence` objects with pairwise source/target group IDs. These are the original pair from the rule evaluation, not the cluster's anchor. For example:

- Evidence(source=GRP_A, target=GRP_B) — rule 4b confirmed this pair
- Evidence(source=GRP_C, target=GRP_D) — rule 4a confirmed this pair
- After Union-Find: Cluster 1 = {A, B, C}, anchor = B; Cluster 2 = {D, E}, anchor = D

The API needs all evidence for Cluster 1 to have `target_group_id = B` (the anchor). The broken remapping used `group_to_anchor.get(ev.source_group_id) OR group_to_anchor.get(ev.target_group_id)` — the `OR` fallback could pick an anchor from the wrong cluster when a group appeared in evidence for a pair that crossed cluster boundaries (suggestions that were below threshold but still in the evidence list).

## Fix

### Task 1: Revert the broken remapping, use cluster-aware approach

**File:** `cleo/discovery/engine.py`

Replace the current remapping logic (the block added in commit `ad09b75`) with:

```python
# Build group -> anchor mapping ONLY within each cluster
group_to_anchor = {}
for cluster in clusters:
    for gid in cluster.member_group_ids:
        group_to_anchor[gid] = cluster.anchor_group_id

# Filter and remap evidence: only keep evidence where BOTH groups are in the same cluster
remapped_evidence = []
for ev in evidence_list:
    src_anchor = group_to_anchor.get(ev.source_group_id)
    tgt_anchor = group_to_anchor.get(ev.target_group_id)
    
    # Both groups must be in the same cluster
    if src_anchor and tgt_anchor and src_anchor == tgt_anchor:
        anchor = src_anchor
        # Make source = the non-anchor member, target = the anchor
        if ev.source_group_id == anchor:
            ev.source_group_id = ev.target_group_id
        ev.target_group_id = anchor
        remapped_evidence.append(ev)
    elif src_anchor and not tgt_anchor:
        # Target not in any cluster (orphan pair) — keep as-is with anchor
        ev.target_group_id = src_anchor
        remapped_evidence.append(ev)
    elif tgt_anchor and not src_anchor:
        # Source not in any cluster — keep with source pointing at anchor
        ev.target_group_id = tgt_anchor
        remapped_evidence.append(ev)
    # Else: groups in different clusters — drop this evidence row

evidence_count = _write_evidence_from_list(db, run_id, remapped_evidence)
```

**Key change:** The `src_anchor == tgt_anchor` check ensures we never bridge clusters. Evidence where source and target ended up in different clusters gets dropped (it was below-threshold or got separated by cluster splitting).

### Task 2: Also capture expansion evidence

Currently, the expansion phase (`expand_clusters`) adds groups to clusters but doesn't generate Evidence objects. This means groups added via expansion have NO evidence in the table — they show up as members but with no "Linked By" signals in the UI.

**File:** `cleo/discovery/rules.py` — `expand_clusters()` function

When a group is added to a cluster during expansion, generate Evidence objects and append to the evidence_list:

```python
# In expand_clusters, when a group is confirmed:
for cat_name, values in best_categories.items():
    for val in values:
        evidence_list.append(Evidence(
            signal_type=cat_name,
            signal_value=val,
            source_group_id=gid,
            target_group_id=best_cluster.anchor_group_id,
            source_id='',
            rule_id=best_rule,
            confidence=best_conf,
            iteration=iteration,
        ))
```

This requires `expand_clusters` to accept and return the evidence_list, or to return new evidence separately.

### Task 3: Run validate and verify

1. Run `python -m cleo.discovery run --validate`
2. Verify: largest cluster should be ~64 (not 2,916)
3. Verify: RioCan cluster exists with correct name
4. Verify: cluster detail pages show "Linked By" signals for all members
5. Verify: 114 tests still pass

### Task 4: Commit

```bash
git add cleo/discovery/engine.py cleo/discovery/rules.py
git commit -m "fix(discovery): cluster-aware evidence remapping, expansion evidence"
```

## Verification Checklist

- [ ] Largest cluster is reasonable (<200 members) — not a mega-cluster
- [ ] RioCan appears as its own cluster with "RioCan" or "RioCan REIT" name
- [ ] Cluster detail shows "Linked By" evidence for every member
- [ ] Portfolio Value sort works correctly on Discovery page
- [ ] All 114 tests pass
- [ ] DH ground truth: precision=100%, recall=13% (unchanged)

## Future Improvements (not in this fix)

1. **Portfolio value** — currently only uses anchor's `group_analytics.total_assessed_value`. Should SUM across all cluster member group_analytics.
2. **Cluster size cap** — consider a max cluster size (e.g., 200) with a flag for clusters that exceed it. Mega-clusters might indicate a signal that should be excluded.
3. **Unmerge workflow** — Brandon has 170 manual merges that hide signals from the algorithm. A "reset and re-discover" workflow would unmerge everything, recompile, and let the algorithm re-cluster from scratch.
