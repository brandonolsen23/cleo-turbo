# RT Category Backfill

`engines/rt/scraper/backfill_categories.py` re-runs Realtrack per-category
searches over historical date windows and appends each category's export rows
to `raw-data/rt/category_evidence.jsonl` — the same append-only label-evidence
file, and the exact same line schema (export fields + `rt_category`,
`window {start, end}`, `captured_at`), that the daily scraper's verify pass
writes. Downstream joins (ARN/rollno + sale date) treat daily and backfill
evidence identically.

**Evidence-only guarantee (doctrine D1):** the script appends JSONL lines and
maintains its own state file. It downloads no detail pages, saves no raw HTML,
writes nothing to the DB (reads `data/cleo.db` with a single `SELECT` for
`--auto`), and never edits existing files.

## Resumability

- State: `raw-data/rt/category_backfill_state.json` — one entry per
  (window, category) with status done/failed, rows, timestamps. Written
  atomically after every category. Re-running skips done work; failed
  categories retry automatically on the next run.
- Lock: `raw-data/rt/category_backfill.lock` (pidfile). A second instance
  refuses to start; stale locks are cleaned automatically.

## Batching overnight runs

```bash
# See remaining work (no network, no login)
.venv/bin/python -m engines.rt.scraper.backfill_categories --auto --dry-run

# Nightly: auto-pick the next 40 pending monthly windows (~40-60 min at 0.5s)
.venv/bin/python -m engines.rt.scraper.backfill_categories --auto --limit-windows 40

# Explicit range, gentler pacing
.venv/bin/python -m engines.rt.scraper.backfill_categories --from 2019-01 --to 2019-12 --delay 0.6
```

Full historical span is ~364 monthly windows (1996-01 to 2026-04), 11
categories each, >= 33 requests per window — about 9-10 nightly runs at
`--limit-windows 40`. Don't run alongside the daily scraper; check
`pgrep -f daily_scraper` first.
