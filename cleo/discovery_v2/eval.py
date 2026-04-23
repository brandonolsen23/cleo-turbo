"""Evaluation harness — measure discovery quality against the 8 audit portfolios.

Metrics per audit:
  - recall: fraction of audit party-sides landing in the dominant discovered Group
  - purity: fraction of the dominant Group that came from the audit
  - dominant_group_id, dominant_group_size

Also renders a markdown report to docs/discovery-audit/YYYY-MM-DD-run.md.
"""

from __future__ import annotations
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple


def compute_audit_metrics(
    audit_slug: str,
    audit_parties: List[dict],
    party_entities: Dict[Tuple[str, str], str],
) -> dict:
    """Return recall/purity for one audit portfolio."""
    n_audit = len(audit_parties)
    if n_audit == 0:
        return {"audit_slug": audit_slug, "n_audit": 0, "recall": 0.0,
                "purity": 0.0, "dominant_group_id": None, "dominant_group_size": 0}

    audit_keys = {(p["source_id"], p["side"]) for p in audit_parties}
    group_of_audit = [party_entities.get(k) for k in audit_keys]
    group_of_audit = [g for g in group_of_audit if g]

    if not group_of_audit:
        return {"audit_slug": audit_slug, "n_audit": n_audit, "recall": 0.0,
                "purity": 0.0, "dominant_group_id": None, "dominant_group_size": 0}

    dominant_group_id, dominant_in_audit = Counter(group_of_audit).most_common(1)[0]
    recall = dominant_in_audit / n_audit

    # Purity: of everyone in the dominant group globally, how many are from this audit?
    dominant_total = sum(1 for g in party_entities.values() if g == dominant_group_id)
    purity = dominant_in_audit / dominant_total if dominant_total > 0 else 0.0

    return {
        "audit_slug": audit_slug,
        "n_audit": n_audit,
        "recall": recall,
        "purity": purity,
        "dominant_group_id": dominant_group_id,
        "dominant_group_size": dominant_total,
    }


def run_audit_eval(conn, audit_docs_root: str) -> List[dict]:
    """Run eval against all audits under `audit_docs_root`. Returns metrics list."""
    from cleo.labeling.audit_parser import list_audits

    audits = list_audits(Path(audit_docs_root))
    party_entities = {
        (r["source_id"], r["side"]): r["group_id"]
        for r in conn.execute(
            "SELECT source_id, side, group_id FROM atom_party_entities "
            "WHERE group_id IS NOT NULL"
        )
    }

    results = []
    for audit in audits:
        metrics = compute_audit_metrics(audit.slug, audit.parties, party_entities)
        results.append(metrics)
    return results


def render_report(metrics_list: List[dict], run_summary: dict, audit_docs_root: str) -> Path:
    """Write a markdown report to docs/discovery-audit/YYYY-MM-DD-run.md."""
    today = date.today().isoformat()
    out_dir = Path(audit_docs_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}-phase-a-eval.md"

    lines = [
        f"# Discovery Phase A Eval — {today}",
        "",
        f"- Party-sides: {run_summary['n_party_sides']:,}",
        f"- Groups: {run_summary['n_groups']:,}",
        f"- Contacts: {run_summary['n_contacts']:,}",
        "",
        "## Per-audit metrics",
        "",
        "| audit | n_audit | recall | purity | dominant_group | group_size |",
        "|---|---|---|---|---|---|",
    ]
    for m in metrics_list:
        lines.append(
            f"| {m['audit_slug']} | {m['n_audit']} | "
            f"{m['recall']:.0%} | {m['purity']:.0%} | "
            f"{m['dominant_group_id'] or '—'} | {m['dominant_group_size']} |"
        )
    out_path.write_text("\n".join(lines) + "\n")
    return out_path
