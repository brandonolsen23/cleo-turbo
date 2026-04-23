"""Developer entry point — `python -m cleo.discovery_v2`."""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.runner import run_discovery
from cleo.discovery_v2.eval import run_audit_eval, render_report
from cleo.discovery_v2.config import CALIBRATION


def main():
    conn = get_connection()
    summary = run_discovery(conn)
    print(flush=True)
    print("Running eval harness against audit portfolios...", flush=True)
    metrics = run_audit_eval(conn, CALIBRATION["audit_docs_root"])
    report_path = render_report(metrics, summary, CALIBRATION["audit_docs_root"])
    print(f"Eval report: {report_path}", flush=True)
    for m in metrics:
        print(f"  {m['audit_slug']:<30} recall={m['recall']:.0%} "
              f"purity={m['purity']:.0%}  "
              f"group={m['dominant_group_id']} ({m['dominant_group_size']})",
              flush=True)
    conn.close()


if __name__ == "__main__":
    main()
