"""
Data quality scanner — CLI entry point.

Usage:
    python3 -m engines.rt.scanner.run                          # full scan
    python3 -m engines.rt.scanner.run --rt-id RT100002         # single record
    python3 -m engines.rt.scanner.run --rule company_in_address # one rule only
    python3 -m engines.rt.scanner.run --summary                # counts only, no DB write
"""

import os
import sys
import json
import time
import uuid
import argparse
import sqlite3
from datetime import datetime, timezone

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from engines.rt.scanner.rules import check_record, RULES
from engines.rt.scanner.tracer import trace_issue


CLEAN_DIR = os.path.join(PROJECT_ROOT, "clean-data", "rt")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "cleo.db")


def scan_record(source_id, record, trace=True):
    """Scan a single record and return issues with trace results."""
    issues = check_record(record)
    results = []

    for issue in issues:
        result = {
            "source_id": source_id,
            "rule": issue.rule,
            "severity": issue.severity,
            "field_path": issue.field_path,
            "actual_value": issue.actual_value[:500] if issue.actual_value else None,
            "message": issue.message,
        }

        if trace:
            trace_result = trace_issue(source_id, issue)
            result.update(trace_result)
        else:
            result.update({
                "introduced_at": None,
                "origin_field": None,
                "source_field": None,
                "explanation": None,
                "code_location": None,
            })

        results.append(result)

    return results


def run_scan(rt_id=None, rule_filter=None, summary_only=False, trace=True):
    """Run the scanner across clean records."""
    scan_run_id = f"SCAN_{uuid.uuid4().hex[:8].upper()}"
    start_time = time.time()

    # Collect files to scan
    if rt_id:
        files = [f"{rt_id}.json"]
    else:
        files = sorted(f for f in os.listdir(CLEAN_DIR) if f.endswith('.json'))

    print(f"Scanning {len(files)} records (run: {scan_run_id})...")

    all_results = []
    scanned = 0
    errors = 0

    for fname in files:
        path = os.path.join(CLEAN_DIR, fname)
        if not os.path.exists(path):
            print(f"  WARNING: {fname} not found")
            continue

        try:
            with open(path) as f:
                record = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors += 1
            continue

        source_id = fname.replace(".json", "")
        results = scan_record(source_id, record, trace=trace)

        if rule_filter:
            results = [r for r in results if r["rule"] == rule_filter]

        all_results.extend(results)
        scanned += 1

        if scanned % 10000 == 0:
            print(f"  ...scanned {scanned}/{len(files)} ({len(all_results)} issues found)")

    elapsed = time.time() - start_time

    # Summary
    print(f"\nScan complete: {scanned} records in {elapsed:.1f}s")
    print(f"  Total issues: {len(all_results)}")
    print(f"  Read errors: {errors}")

    # Breakdown by rule
    by_rule = {}
    for r in all_results:
        by_rule[r["rule"]] = by_rule.get(r["rule"], 0) + 1
    print("\n  By rule:")
    for rule, count in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"    {rule:25s} {count:>6,}")

    # Breakdown by origin stage
    by_stage = {}
    for r in all_results:
        stage = r.get("introduced_at", "unknown") or "unknown"
        by_stage[stage] = by_stage.get(stage, 0) + 1
    print("\n  By origin stage:")
    for stage, count in sorted(by_stage.items(), key=lambda x: -x[1]):
        print(f"    {stage:25s} {count:>6,}")

    # Write to database
    if not summary_only and all_results:
        print(f"\nWriting {len(all_results)} issues to database...")
        conn = sqlite3.connect(DB_PATH)

        # Clear previous open issues from this scan scope
        if rt_id:
            conn.execute("DELETE FROM data_issues WHERE source_id = ? AND status = 'open'", (rt_id,))
        else:
            conn.execute("DELETE FROM data_issues WHERE status = 'open'")

        now = datetime.now(tz=timezone.utc).isoformat()
        for r in all_results:
            conn.execute(
                """INSERT INTO data_issues
                   (source_id, rule, severity, field_path, actual_value, message,
                    introduced_at, origin_field, source_field, explanation, code_location,
                    status, scan_run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (r["source_id"], r["rule"], r["severity"], r["field_path"],
                 r["actual_value"], r["message"],
                 r.get("introduced_at"), r.get("origin_field"), r.get("source_field"),
                 r.get("explanation"), r.get("code_location"),
                 scan_run_id, now)
            )

        conn.commit()
        conn.close()
        print(f"  Done. Run ID: {scan_run_id}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleo Turbo data quality scanner")
    parser.add_argument("--rt-id", help="Scan a single RT ID")
    parser.add_argument("--rule", help="Run only this rule")
    parser.add_argument("--summary", action="store_true", help="Print summary only, don't write to DB")
    parser.add_argument("--no-trace", action="store_true", help="Skip auto-trace (faster)")
    args = parser.parse_args()

    run_scan(
        rt_id=args.rt_id,
        rule_filter=args.rule,
        summary_only=args.summary,
        trace=not args.no_trace,
    )
