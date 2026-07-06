# Portfolio Capture — runbook + payload schema

One validated door for committing owner intelligence (Cowork research, GW
exports, Realtrack party data) into Cleo: `POST /api/portfolio/capture`.
Built per the locked spec (Portfolio-Capture-Cowork-Integration-Plan.docx,
Sections 5-13). Milestones M2 (endpoint) and M4 (match-key sweep).

## Endpoint

```
POST /api/portfolio/capture?dry_run=bool&apply_merges=bool
```

- `dry_run` defaults to **true**: full write order runs in one transaction,
  the diff is returned, then everything rolls back.
- Commit: `dry_run=false`. Merges apply ONLY with `apply_merges=true`
  (never automatic — spec D4). Links get `approved_by/approved_at` stamped
  on commit.
- Auth: standard JWT (`get_current_user`).
- Status codes: 200 diff · 422 payload/specificity rejection · 409
  normalized-name collision with an unrelated group (supply `group.id`).

## Payload (Section 5)

```json
{
  "group": {"display_name": "The Biddington Group", "business_lines": ["owner"],
             "hq_address": "...", "domain": "...", "website": "...",
             "partners": [], "summary": "...", "id": null},
  "aliases": [{"alias": "...", "source_url": "...", "confidence": 0.9}],
  "match_keys": [{"type": "address|phone|domain|spv_name|person",
                   "value_raw": "...", "source_url": "...", "confidence": 0.9}],
  "contacts": [{"name": "...", "role": "...", "phone": "...", "email": "...",
                 "is_current": true}],
  "properties": [{"arn": "25 18 060 613 08750", "display_address": "...",
                   "city": "...", "relationship": "owns",
                   "source": "geowarehouse", "confidence": 0.98,
                   "registry_confirmed": true}],
  "merge_candidates": ["GRP_107934"],
  "captured_by": "cowork:brandon"
}
```

Rules that bite:
- ARNs are engine-normalized (engines/rt pin_arn / engines/gw format_arn);
  never hand-scraped. Invalid ARNs are skipped with a warning.
- Only `address` and `spv_name` keys sweep (D3). A `spv_name` that
  normalizes to a single common word ("Forum") is rejected 422; an address
  without street number + city is stored identity-only (`sweepable=0`).
- `registry_confirmed` links fill dark properties unconditionally;
  `web_asserted` links fill only at confidence >= 0.90, else they land
  `status='pending'` for review. Realtrack owners are never overwritten —
  conflicts surface in `data_issues`.

## Safe rollout (Section 15)

1. `cp data/cleo.db /tmp/cleo_test.db`
2. `.venv/bin/python scripts/test_portfolio_capture_m1.py /tmp/cleo_test.db`
   (use PYTHONPATH=. if run outside repo root)
3. `cp data/cleo.db /tmp/cleo_m2_test.db && .venv/bin/python scripts/test_portfolio_capture_m2.py /tmp/cleo_m2_test.db`
4. `cp data/cleo.db /tmp/cleo_test.db && .venv/bin/python scripts/pilot_biddington.py /tmp/cleo_test.db`
5. Only after all green: run the same capture against the live API
   (dry_run first, always).

Capture is durable: manual_owner_links survive `drop_derived_tables()` and
the compiler re-applies them on every rebuild (owner_overrides final pass).
