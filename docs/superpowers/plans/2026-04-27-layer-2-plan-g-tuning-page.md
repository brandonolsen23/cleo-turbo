# Layer 2 Plan G — Tuning Page + List-Page Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` (Plan G section).

**Goal:** Add a `/explorer/auto-groups/tuning` page exposing the levers the user needs to tune the algorithm — confidence histogram, close-to-promotion queue, missed-stem diagnostics — plus enrich the existing list page with anchor-diversity, distinct-contacts, and a close-to-promotion filter.

**Architecture:** Three new backend endpoints feed a new tuning page assembled from three independent display components. The list endpoint gets two computed columns and one new filter. No schema changes — all data is derivable from existing Plan A tables.

**Tech Stack:** Python 3.12, FastAPI, SQLite, React 19, Radix UI Themes, Recharts (for the histogram), TypeScript, react-router-dom.

---

## Glossary (locked from the spec — used strictly)

| Term | Meaning |
|---|---|
| **Group / auto_group** | An `auto_groups` row. Identified by `auto_group_id`. |
| **Anchor** | Phone, address (root or base), or contact_fingerprint assigned to a group. |
| **Anchor category** | `phone` / `address` (collapses `address_root`+`address_base`) / `contact`. Three total. |
| **Anchor diversity** | Count of distinct anchor categories present in a group's `auto_group_anchors`. Range 1–3. |
| **Tier** | `confirmed` / `probable` / `candidate`. |
| **Confidence bucket** | A 0.05-wide interval `[0.00, 0.05)`, `[0.05, 0.10)`, …, `[0.95, 1.00]`. 20 buckets total. |
| **Close to promotion** | Probable group with confidence in `[0.70, 0.75)` — within 0.05 of the Confirmed threshold. The cutoff is queryable via `from`/`to` params. |
| **Stem** | Canonical operator label (`kingsett`, `starlight`). A `brand_stem.stem` row when verified. |
| **Missed stem** | A 1-gram in `brand_token_summary` that was distinctive or position-anchor and had ≥ N party-sides but did NOT get into `brand_stem` (i.e., its candidate failed promotion). The diagnostic question: which stem won at the anchor where this candidate was strongest? |
| **Dominance contest** | At a given anchor (typically a phone), multiple stems can claim it. Only the one with the highest dominance share gets promoted. The "loser" stem is a missed-stem candidate. |

No alternate names. No new terms — if a new concept is needed, surface it as a question rather than inventing a name.

---

## File Structure

**Backend:**
- Modify: `cleo/web/routes/explorer.py` — add 3 tuning endpoints + extend `list_auto_groups`.
- Modify: `tests/test_routes_explorer.py` — fixture extensions + tests for new endpoints/columns.

**Frontend (new files):**
- `frontend/src/pages/ExplorerAutoGroupsTuning.tsx` — the tuning page (composes 3 sections).
- `frontend/src/components/explorer/AutoGroupsHistogram.tsx` — confidence histogram (uses Recharts; clickable buckets).
- `frontend/src/components/explorer/AutoGroupsCloseToPromotion.tsx` — table of probable groups within 0.05 of confirmed.
- `frontend/src/components/explorer/AutoGroupsMissedStems.tsx` — table of distinctive 1-grams that didn't promote.

**Frontend (modified):**
- `frontend/src/types/index.ts` — types for the 3 new endpoint responses + 2 list-summary additions.
- `frontend/src/pages/ExplorerAutoGroups.tsx` — add Tuning link, anchor-diversity + distinct-contacts columns, close-to-promotion filter.
- `frontend/src/App.tsx` — register `/explorer/auto-groups/tuning` route.

---

## Pre-flight context

**Recharts is already installed** (used elsewhere in the app for charts — verify with `grep -r "from \"recharts\"" frontend/src` if you want to confirm). Use `<BarChart>`, `<Bar>`, `<XAxis>`, `<YAxis>`, `<Tooltip>`, `<ReferenceLine>` from recharts.

**Tier thresholds**: `TIER_CONFIRMED_MIN_CONFIDENCE = 0.75`, `TIER_PROBABLE_MIN_CONFIDENCE = 0.4` (already imported in `cleo/web/routes/explorer.py` from `cleo.discovery_v2.constants`).

**Plan D's `/parties` endpoint** is the reference implementation pattern for this work — same param-validation discipline (400 on invalid), same use of bind params, same dict response shape with `results/total/page/per_page/pages`.

**Existing fixture in `tests/test_routes_explorer.py`** has `brand_token_summary`, `auto_groups`, `brand_stem`, etc. all seeded. Extend it where needed but don't replace.

---

## Tasks

### Task 1: Backend — `/tuning/histogram` endpoint

Returns confidence-bucket counts for the histogram.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes_explorer.py` (in the auto-groups section):

```python
def test_histogram_returns_buckets(client):
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    assert resp.status_code == 200
    body = resp.json()
    assert 'buckets' in body
    # 20 buckets covering [0.00, 1.00] in 0.05 increments.
    assert len(body['buckets']) == 20
    first = body['buckets'][0]
    assert first['lower'] == pytest.approx(0.0)
    assert first['upper'] == pytest.approx(0.05)
    assert 'count' in first


def test_histogram_includes_threshold_lines(client):
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    body = resp.json()
    assert body['tier_confirmed_threshold'] == pytest.approx(0.75)
    assert body['tier_probable_threshold'] == pytest.approx(0.4)


def test_histogram_counts_match_real_groups(client):
    # The fixture has at least 2 auto_groups (AGRP_00001 confirmed @ 0.85, AGRP_00002 probable @ 0.55).
    resp = client.get('/api/explorer/auto-groups/tuning/histogram')
    body = resp.json()
    total_in_buckets = sum(b['count'] for b in body['buckets'])
    # Should at least match the 2 seeded groups.
    assert total_in_buckets >= 2
    # AGRP_00001 (0.85) lands in [0.85, 0.90)
    bucket_85 = next(b for b in body['buckets'] if b['lower'] == pytest.approx(0.85))
    assert bucket_85['count'] >= 1
    # AGRP_00002 (0.55) lands in [0.55, 0.60)
    bucket_55 = next(b for b in body['buckets'] if b['lower'] == pytest.approx(0.55))
    assert bucket_55['count'] >= 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k histogram
# Expected: 3 failures
```

- [ ] **Step 3: Add the endpoint**

Insert into `cleo/web/routes/explorer.py` immediately after the existing auto-groups endpoints (after `auto_group_parties`):

```python
# ─────────────────────────────────────────────────────────────
# Tuning page endpoints (Plan G)
# ─────────────────────────────────────────────────────────────

@router.get('/auto-groups/tuning/histogram')
def auto_groups_tuning_histogram(
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Confidence histogram in 0.05-wide buckets. Returns 20 buckets covering [0.00, 1.00]."""
    # Compute bucket counts via integer math: bucket index = floor(confidence * 20),
    # clamped to [0, 19] so 1.0 confidence lands in the last bucket.
    rows = db.execute(
        """SELECT
              MIN(CAST(confidence * 20 AS INT), 19) AS bucket_idx,
              COUNT(*) AS n
           FROM auto_groups
           GROUP BY bucket_idx
           ORDER BY bucket_idx"""
    ).fetchall()
    counts_by_idx = {r['bucket_idx']: r['n'] for r in rows}

    buckets = []
    for i in range(20):
        lower = i * 0.05
        upper = (i + 1) * 0.05
        buckets.append({
            'lower': round(lower, 2),
            'upper': round(upper, 2),
            'count': counts_by_idx.get(i, 0),
        })

    return {
        'buckets': buckets,
        'tier_confirmed_threshold': TIER_CONFIRMED_MIN_CONFIDENCE,
        'tier_probable_threshold': TIER_PROBABLE_MIN_CONFIDENCE,
    }
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k histogram
# Expected: 3 passed
```

- [ ] **Step 5: Update the explorer.py docstring**

Find the docstring block listing endpoints. Add:

```
GET /api/explorer/auto-groups/tuning/histogram  — confidence-bucket counts for tuning UI
```

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /tuning/histogram endpoint"
```

---

### Task 2: Backend — `/tuning/close-to-promotion` endpoint

Returns Probable groups whose confidence is within a queryable window of the Confirmed threshold (default `[0.70, 0.75)`).

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture**

Find `_seeded_db` in `tests/test_routes_explorer.py`. The existing seed has AGRP_00001 (confidence 0.85) and AGRP_00002 (confidence 0.55). Neither is in the `[0.70, 0.75)` close-to-promotion window. Add one more group seeded at confidence 0.72:

In `_seeded_db`, after the existing `INSERT INTO auto_groups` rows, append:

```python
conn.execute("""
    INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                             n_anchors, n_members, discovered_at)
    VALUES ('AGRP_00003', 'almostkingsett', 'almostkingsett group', 'probable', 0.72, 2, 4, '2026-04-27')
""")
```

- [ ] **Step 2: Write failing tests**

Append:

```python
def test_close_to_promotion_default_window(client):
    """Default window is [0.70, 0.75) — picks up AGRP_00003 (0.72) but not AGRP_00001 (0.85) or AGRP_00002 (0.55)."""
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
    assert resp.status_code == 200
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    assert 'AGRP_00003' in sids
    assert 'AGRP_00001' not in sids
    assert 'AGRP_00002' not in sids


def test_close_to_promotion_custom_window(client):
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion',
                      params={'from': 0.50, 'to': 0.60})
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    # AGRP_00002 (0.55) lands in [0.50, 0.60), AGRP_00003 (0.72) does not.
    assert 'AGRP_00002' in sids
    assert 'AGRP_00003' not in sids


def test_close_to_promotion_window_thresholds(client):
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
    body = resp.json()
    assert body['from_confidence'] == pytest.approx(0.70)
    assert body['to_confidence'] == pytest.approx(0.75)


def test_close_to_promotion_400_on_invalid_window(client):
    # from > to should 400.
    resp = client.get('/api/explorer/auto-groups/tuning/close-to-promotion',
                      params={'from': 0.8, 'to': 0.5})
    assert resp.status_code == 400
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k close_to_promotion
# Expected: 4 failures
```

- [ ] **Step 4: Add the endpoint**

Insert after the histogram endpoint:

```python
@router.get('/auto-groups/tuning/close-to-promotion')
def auto_groups_close_to_promotion(
    from_: float = Query(0.70, alias='from', ge=0.0, le=1.0),
    to: float = Query(0.75, ge=0.0, le=1.0),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Groups whose confidence sits in [from, to). Default window is [0.70, 0.75) —
    Probable groups within 0.05 of the Confirmed threshold."""
    if from_ >= to:
        raise HTTPException(status_code=400, detail=f'Invalid window: from={from_} must be < to={to}')

    total = db.execute(
        """SELECT COUNT(*) FROM auto_groups
           WHERE confidence >= ? AND confidence < ?""",
        (from_, to),
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        """SELECT auto_group_id, canonical_stem, display_name, tier, confidence,
                  n_anchors, n_members
           FROM auto_groups
           WHERE confidence >= ? AND confidence < ?
           ORDER BY confidence DESC, canonical_stem ASC
           LIMIT ? OFFSET ?""",
        (from_, to, per_page, offset),
    ).fetchall()

    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'from_confidence': from_,
        'to_confidence': to,
    }
```

- [ ] **Step 5: Run, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k close_to_promotion
# Expected: 4 passed
```

- [ ] **Step 6: Update the docstring**

Add:

```
GET /api/explorer/auto-groups/tuning/close-to-promotion  — groups within a confidence window
```

- [ ] **Step 7: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /tuning/close-to-promotion endpoint with queryable window"
```

---

### Task 3: Backend — `/tuning/missed-stems` endpoint

Returns 1-grams that should have promoted but didn't, with the dominance-contest data showing what won at their strongest anchor.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture**

The existing fixture has `brand_stem` rows for `kingsett` and `starlight` (added in Plan D Task 1's fixture extension). To exercise the missed-stems logic, we need:
- A 1-gram that's distinctive or position-anchor in `brand_token_summary`
- With `n_party_sides >= min_n_party_sides` (default 100)
- That has NO row in `brand_stem`

Find where the fixture inserts brand_token_summary rows. Find the kingsett insert and add a missed-stem token below it:

```python
# A position-anchor 1-gram that did NOT promote — 'lostbrand', 120 sides.
# We seed brand_token_index entries to give it phone-anchor concentration.
conn.execute("""
    INSERT OR IGNORE INTO brand_token_summary
        (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
         wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword,
         filter_reason, position_consistency, total_child_coverage,
         is_position_anchor, discovered_at)
    VALUES ('lostbrand', 6.5, 120, 8, 0, 0, 0.0, 0, 0, 0, NULL, 0.95, 0.99, 1, '2026-04-26')
""")
# Confirm brand_token_index table exists (added in earlier migrations); seed entries
# that show 'lostbrand' is most concentrated at phone 4166876700 (kingsett's phone).
conn.executescript("""
    CREATE TABLE IF NOT EXISTS brand_token_index (
        token TEXT, source_id TEXT, side TEXT,
        PRIMARY KEY (token, source_id, side)
    );
""")
# Seed 4 sides with lostbrand all at phone 4166876700 (via the existing party_fingerprints
# rows RT1, RT-COV-1, RT-COV-2 + a new one).
conn.execute("""
    INSERT OR IGNORE INTO party_fingerprints (source_id, side, phone)
    VALUES ('RT-LOSTBRAND-1', 'buyer', '4166876700')
""")
for sid, side in [('RT1', 'buyer'), ('RT-COV-1', 'seller'),
                   ('RT-COV-2', 'seller'), ('RT-LOSTBRAND-1', 'buyer')]:
    conn.execute(
        "INSERT OR IGNORE INTO brand_token_index (token, source_id, side) VALUES ('lostbrand', ?, ?)",
        (sid, side),
    )
```

- [ ] **Step 2: Write failing tests**

```python
def test_missed_stems_returns_lostbrand(client):
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    assert resp.status_code == 200
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    assert 'lostbrand' in tokens


def test_missed_stems_excludes_promoted(client):
    """Tokens that ARE in brand_stem should NOT appear."""
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    # 'kingsett' and 'starlight' are seeded in brand_stem; they should NOT be missed.
    assert 'kingsett' not in tokens
    assert 'starlight' not in tokens


def test_missed_stems_includes_dominance_contest(client):
    """Each missed stem should report the strongest-phone anchor where it was concentrated,
    plus the stem that won at that anchor."""
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 100})
    body = resp.json()
    lost = next(r for r in body['results'] if r['token'] == 'lostbrand')
    # 'lostbrand' is concentrated at phone 4166876700 (kingsett's phone)
    assert lost['strongest_phone'] == '4166876700'
    assert lost['token_sides_at_anchor'] >= 1
    # The fixture's anchor_uniqueness has anchor (phone, 4166876700) seeded only via
    # other data; if no anchor_uniqueness row exists, winner_stem is null.
    # The contract: winner_stem is the dominant_stem at that anchor (may be null).
    assert 'winner_stem' in lost
    assert 'winner_dominance' in lost


def test_missed_stems_respects_min_party_sides(client):
    # Bump threshold above 'lostbrand''s 120 → it disappears.
    resp = client.get('/api/explorer/auto-groups/tuning/missed-stems',
                      params={'min_n_party_sides': 500})
    body = resp.json()
    tokens = [r['token'] for r in body['results']]
    assert 'lostbrand' not in tokens
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k missed_stems
# Expected: 4 failures
```

- [ ] **Step 4: Add the endpoint**

Insert after the close-to-promotion endpoint:

```python
@router.get('/auto-groups/tuning/missed-stems')
def auto_groups_tuning_missed_stems(
    min_n_party_sides: int = Query(100, ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """1-grams that are distinctive or position-anchor with high party-side counts
    but didn't get a verified stem. For each, surfaces the strongest-phone anchor
    and the stem that won the dominance contest at that anchor.

    Phone-only diagnostic for now — most missed stems (DD/KS/Dundee/PIRET) cluster
    at operator switchboards. Address-anchor analysis can be added later.
    """
    # Total count for pagination (cheap — counts the missed-token candidate set).
    total = db.execute(
        """SELECT COUNT(*) FROM brand_token_summary bts
           LEFT JOIN brand_stem bs ON bs.stem = bts.token
           WHERE (bts.is_distinctive = 1 OR COALESCE(bts.is_position_anchor, 0) = 1)
             AND bts.n_party_sides >= ?
             AND bs.stem IS NULL""",
        (min_n_party_sides,),
    ).fetchone()[0]

    offset = (page - 1) * per_page

    # Bulk query: for each missed token, find its strongest-phone anchor + the
    # stem that won there.
    rows = db.execute(
        """WITH missed AS (
              SELECT bts.token, bts.n_party_sides
              FROM brand_token_summary bts
              LEFT JOIN brand_stem bs ON bs.stem = bts.token
              WHERE (bts.is_distinctive = 1 OR COALESCE(bts.is_position_anchor, 0) = 1)
                AND bts.n_party_sides >= ?
                AND bs.stem IS NULL
              ORDER BY bts.n_party_sides DESC
              LIMIT ? OFFSET ?
           ),
           by_phone AS (
              SELECT m.token, pf.phone AS anchor_value, COUNT(*) AS sides_with_token,
                     ROW_NUMBER() OVER (PARTITION BY m.token ORDER BY COUNT(*) DESC) AS rk
              FROM missed m
              JOIN brand_token_index bti ON bti.token = m.token
              JOIN party_fingerprints pf
                ON pf.source_id = bti.source_id AND pf.side = bti.side
              WHERE pf.phone IS NOT NULL AND pf.phone != ''
              GROUP BY m.token, pf.phone
           )
           SELECT m.token, m.n_party_sides,
                  bp.anchor_value AS strongest_phone,
                  bp.sides_with_token AS token_sides_at_anchor,
                  au.dominant_stem AS winner_stem,
                  au.dominance_share AS winner_dominance,
                  au.volume AS anchor_volume
           FROM missed m
           LEFT JOIN by_phone bp ON bp.token = m.token AND bp.rk = 1
           LEFT JOIN anchor_uniqueness au
             ON au.anchor_type = 'phone' AND au.anchor_value = bp.anchor_value
           ORDER BY m.n_party_sides DESC""",
        (min_n_party_sides, per_page, offset),
    ).fetchall()

    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'min_n_party_sides': min_n_party_sides,
    }
```

- [ ] **Step 5: Run, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k missed_stems
# Expected: 4 passed
```

- [ ] **Step 6: Smoke test against real DB**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps
app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

r = client.get('/api/explorer/auto-groups/tuning/histogram')
print('histogram total buckets:', len(r.json()['buckets']))
total_groups = sum(b['count'] for b in r.json()['buckets'])
print('  total groups in histogram:', total_groups)

r2 = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
print('close-to-promotion (default 0.70-0.75):', r2.json()['total'], 'groups')

r3 = client.get('/api/explorer/auto-groups/tuning/missed-stems')
print('missed-stems (default min=100):', r3.json()['total'], 'tokens')
print('  first 3:', [r['token'] for r in r3.json()['results'][:3]])
" 2>&1 | tail -8
```

Expected: histogram has 20 buckets summing to 1682, close-to-promotion returns some count, missed-stems returns ~18 tokens with the first being one of `ulc / advisors / nominee / kanco`.

- [ ] **Step 7: Update the docstring**

```
GET /api/explorer/auto-groups/tuning/missed-stems  — distinctive/PA 1-grams that didn't promote, with dominance-contest data
```

- [ ] **Step 8: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /tuning/missed-stems endpoint with dominance-contest data"
```

---

### Task 4: Backend — extend list endpoint with anchor_diversity, n_distinct_contacts, close_to_promotion filter

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_list_auto_groups_returns_anchor_diversity_and_distinct_contacts(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'tier': 'confirmed'})
    body = resp.json()
    first = body['results'][0]
    assert 'anchor_diversity' in first
    # AGRP_00001 has 3 anchor types in fixture (phone, address_root, contact) → 3 categories.
    assert first['anchor_diversity'] >= 1
    assert 'n_distinct_contacts' in first
    assert isinstance(first['n_distinct_contacts'], int)


def test_list_auto_groups_close_to_promotion_filter(client):
    """When close_to_promotion=true, restrict results to confidence in [0.70, 0.75)."""
    resp = client.get('/api/explorer/auto-groups',
                      params={'close_to_promotion': 'true', 'tier': 'probable'})
    body = resp.json()
    sids = {g['auto_group_id'] for g in body['results']}
    # AGRP_00003 has confidence 0.72 → in window.
    assert 'AGRP_00003' in sids


def test_list_auto_groups_close_to_promotion_excludes_outside_window(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'close_to_promotion': 'true', 'tier': 'confirmed'})
    body = resp.json()
    # AGRP_00001 is confidence 0.85 → confirmed but NOT in [0.70, 0.75) window.
    sids = {g['auto_group_id'] for g in body['results']}
    assert 'AGRP_00001' not in sids
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "list_auto_groups_returns_anchor or close_to_promotion_filter or close_to_promotion_excludes"
# Expected: 3 failures (new fields/filter not present)
```

- [ ] **Step 3: Modify `list_auto_groups`**

Find `def list_auto_groups(` at around line 1481. Modify the signature to add a new param, and modify the SQL to compute the two new columns:

Replace the existing body of `list_auto_groups` with:

```python
@router.get('/auto-groups')
def list_auto_groups(
    tier: str = Query('confirmed'),
    q: Optional[str] = Query(None),
    close_to_promotion: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    if tier not in ('confirmed', 'probable', 'candidate'):
        raise HTTPException(status_code=400, detail=f'Invalid tier: {tier!r}')
    where = ['tier = ?']
    params: list = [tier]
    if q:
        where.append('(LOWER(display_name) LIKE ? OR LOWER(canonical_stem) LIKE ?)')
        like = f'%{q.lower()}%'
        params.extend([like, like])
    if close_to_promotion:
        where.append('confidence >= ? AND confidence < ?')
        params.extend([
            TIER_CONFIRMED_MIN_CONFIDENCE - 0.05,
            TIER_CONFIRMED_MIN_CONFIDENCE,
        ])
    where_sql = ' WHERE ' + ' AND '.join(where)

    total = db.execute(
        f'SELECT COUNT(*) FROM auto_groups{where_sql}', params
    ).fetchone()[0]
    offset = (page - 1) * per_page

    # Anchor diversity: count of distinct categories among the group's anchors.
    # Computed via correlated subquery using the address_root+address_base collapse.
    # Distinct contacts: count of distinct contact_fingerprint among party_side members.
    rows = db.execute(
        f"""SELECT ag.auto_group_id, ag.canonical_stem, ag.display_name, ag.tier,
                   ag.confidence, ag.n_anchors, ag.n_members,
                   (SELECT COUNT(DISTINCT
                                 CASE WHEN aga.anchor_type IN ('address_root', 'address_base')
                                      THEN 'address'
                                      ELSE aga.anchor_type
                                 END)
                    FROM auto_group_anchors aga
                    WHERE aga.auto_group_id = ag.auto_group_id) AS anchor_diversity,
                   (SELECT COUNT(DISTINCT pf.contact_fingerprint)
                    FROM auto_group_members agm
                    JOIN party_fingerprints pf
                      ON pf.source_id = agm.source_id AND pf.side = agm.side
                    WHERE agm.auto_group_id = ag.auto_group_id
                      AND agm.member_type = 'party_side'
                      AND pf.contact_fingerprint IS NOT NULL
                      AND pf.contact_fingerprint != '') AS n_distinct_contacts
            FROM auto_groups ag
            {where_sql}
            ORDER BY n_members DESC, canonical_stem ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v
# Expected: all 71+3+4+4+3 = 85 tests pass (existing + new from Tasks 1, 2, 3, 4)
```

If existing list-endpoint tests fail because they don't expect the new fields, the new fields are additive (the existing tests use `assert 'tier' in g` style checks) — they shouldn't break. If they do, the test was over-asserting (`assert set(g.keys()) == {...}`) and needs to be relaxed.

- [ ] **Step 5: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): list endpoint adds anchor_diversity, n_distinct_contacts, close_to_promotion filter"
```

---

### Task 5: Frontend — types + Tuning page route + skeleton

Add types for the 3 new endpoint responses + 2 list-summary additions. Create the Tuning page that mounts the 3 sections (each as a placeholder loading state for now). Register the route.

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/pages/ExplorerAutoGroupsTuning.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, find the `AutoGroupSummary` interface (added in Plan A Task 10). Update it to include the two new fields:

```typescript
export interface AutoGroupSummary {
  auto_group_id: string;
  canonical_stem: string;
  display_name: string;
  tier: 'confirmed' | 'probable' | 'candidate';
  confidence: number;
  n_anchors: number;
  n_members: number;
  // Plan G additions:
  anchor_diversity?: number;
  n_distinct_contacts?: number;
}
```

(Marked optional `?` so older API responses without the fields don't break TypeScript callers — the new fields will always be present after Task 4 ships.)

After the existing `AutoGroupDetail` interface, append the new tuning types:

```typescript
// ============================================================
// Explorer — Auto-Groups Tuning (Plan G)
// ============================================================

export interface AutoGroupsHistogramBucket {
  lower: number;
  upper: number;
  count: number;
}

export interface AutoGroupsHistogramResponse {
  buckets: AutoGroupsHistogramBucket[];
  tier_confirmed_threshold: number;
  tier_probable_threshold: number;
}

export interface AutoGroupsCloseToPromotionResponse {
  results: AutoGroupSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  from_confidence: number;
  to_confidence: number;
}

export interface AutoGroupsMissedStem {
  token: string;
  n_party_sides: number;
  strongest_phone: string | null;
  token_sides_at_anchor: number | null;
  winner_stem: string | null;
  winner_dominance: number | null;
  anchor_volume: number | null;
}

export interface AutoGroupsMissedStemsResponse {
  results: AutoGroupsMissedStem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  min_n_party_sides: number;
}
```

- [ ] **Step 2: Create the Tuning page skeleton**

`frontend/src/pages/ExplorerAutoGroupsTuning.tsx`:

```typescript
import { Heading, Text } from "@radix-ui/themes";
import { Link } from "react-router-dom";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AutoGroupsHistogram from "../components/explorer/AutoGroupsHistogram";
import AutoGroupsCloseToPromotion from "../components/explorer/AutoGroupsCloseToPromotion";
import AutoGroupsMissedStems from "../components/explorer/AutoGroupsMissedStems";


export default function ExplorerAutoGroupsTuning() {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <Link to="/explorer/auto-groups" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Auto-Groups
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6">Tuning</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          See how the algorithm distributes confidence, find groups close to promotion, and inspect 1-grams that didn't promote.
        </Text>
      </div>

      <div className="flex flex-col gap-8">
        <AutoGroupsHistogram />
        <AutoGroupsCloseToPromotion />
        <AutoGroupsMissedStems />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Stub the 3 child components so the page compiles**

Create `frontend/src/components/explorer/AutoGroupsHistogram.tsx`:

```typescript
import { Heading, Text } from "@radix-ui/themes";

export default function AutoGroupsHistogram() {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
         style={{ background: "var(--gray-2)" }}>
      <Heading size="3">Confidence histogram</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Coming in Task 6.
      </Text>
    </div>
  );
}
```

Create `frontend/src/components/explorer/AutoGroupsCloseToPromotion.tsx`:

```typescript
import { Heading, Text } from "@radix-ui/themes";

export default function AutoGroupsCloseToPromotion() {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
         style={{ background: "var(--gray-2)" }}>
      <Heading size="3">Close to promotion</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Coming in Task 7.
      </Text>
    </div>
  );
}
```

Create `frontend/src/components/explorer/AutoGroupsMissedStems.tsx`:

```typescript
import { Heading, Text } from "@radix-ui/themes";

export default function AutoGroupsMissedStems() {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5"
         style={{ background: "var(--gray-2)" }}>
      <Heading size="3">Stems that didn't promote</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Coming in Task 8.
      </Text>
    </div>
  );
}
```

- [ ] **Step 4: Register the route in `App.tsx`**

In `frontend/src/App.tsx`, find the existing auto-groups lazy imports (Plan A Task 10/11/12 added `ExplorerAutoGroups` and `ExplorerAutoGroupDetail`). Add this lazy import nearby:

```typescript
const ExplorerAutoGroupsTuning = lazy(() => import("./pages/ExplorerAutoGroupsTuning"));
```

Find the existing route registrations for `/explorer/auto-groups` and `/explorer/auto-groups/:id`. Add a new route IMMEDIATELY BEFORE the `/:id` route (otherwise `tuning` will be matched as an `:id`):

```typescript
<Route path="/explorer/auto-groups" element={<ExplorerAutoGroups />} />
<Route path="/explorer/auto-groups/tuning" element={<ExplorerAutoGroupsTuning />} />
<Route path="/explorer/auto-groups/:id" element={<ExplorerAutoGroupDetail />} />
```

- [ ] **Step 5: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

Visit `http://localhost:5174/explorer/auto-groups/tuning`. Verify:
- The page renders.
- "← Auto-Groups" back link present.
- Three section placeholders visible ("Coming in Task 6", "Coming in Task 7", "Coming in Task 8").

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts \
        frontend/src/pages/ExplorerAutoGroupsTuning.tsx \
        frontend/src/components/explorer/AutoGroupsHistogram.tsx \
        frontend/src/components/explorer/AutoGroupsCloseToPromotion.tsx \
        frontend/src/components/explorer/AutoGroupsMissedStems.tsx \
        frontend/src/App.tsx
git commit -m "feat(layer2): tuning page skeleton + types + route"
```

---

### Task 6: Frontend — Confidence histogram component

Replace the placeholder with a clickable Recharts BarChart.

**Files:**
- Modify: `frontend/src/components/explorer/AutoGroupsHistogram.tsx`

- [ ] **Step 1: Verify Recharts is installed**

```bash
cd frontend && grep -c "\"recharts\"" package.json
# Expected: ≥ 1 — recharts is a project dep (used elsewhere)
```

If recharts is not present, install: `npm install recharts` (in `frontend/`).

- [ ] **Step 2: Replace the histogram component**

Replace the entire contents of `frontend/src/components/explorer/AutoGroupsHistogram.tsx`:

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from "recharts";
import { fetchApi } from "../../api/client";
import type { AutoGroupsHistogramResponse, AutoGroupsHistogramBucket } from "../../types";


function bucketColor(b: AutoGroupsHistogramBucket, confirmed: number, probable: number): string {
  if (b.lower >= confirmed) return "var(--jade-9)";
  if (b.lower >= probable)  return "var(--amber-9)";
  return "var(--gray-9)";
}

function bucketLabel(b: AutoGroupsHistogramBucket): string {
  return `${b.lower.toFixed(2)}–${b.upper.toFixed(2)}`;
}


export default function AutoGroupsHistogram() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupsHistogramResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupsHistogramResponse>(
      "/explorer/auto-groups/tuning/histogram",
    ).then(setData).catch(console.error);
  }, []);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Confidence histogram</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  const totalGroups = data.buckets.reduce((sum, b) => sum + b.count, 0);
  const chartData = data.buckets.map((b) => ({
    label: bucketLabel(b),
    count: b.count,
    bucket: b,
  }));

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-2 flex-wrap">
        <Heading size="3">Confidence histogram</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {totalGroups.toLocaleString()} groups, 0.05-wide buckets. Click a bar to filter the list page.
        </Text>
      </div>

      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 30 }}>
            <XAxis dataKey="label" angle={-45} textAnchor="end" tick={{ fontSize: 10 }}
                   interval={0} height={60} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              formatter={(v: number) => [v.toLocaleString(), "groups"]}
              labelFormatter={(label: string) => `confidence ${label}`}
            />
            <ReferenceLine x={`${data.tier_probable_threshold.toFixed(2)}–${(data.tier_probable_threshold + 0.05).toFixed(2)}`}
                           stroke="var(--amber-11)" strokeDasharray="3 3"
                           label={{ value: "probable", position: "top", fontSize: 10 }} />
            <ReferenceLine x={`${data.tier_confirmed_threshold.toFixed(2)}–${(data.tier_confirmed_threshold + 0.05).toFixed(2)}`}
                           stroke="var(--jade-11)" strokeDasharray="3 3"
                           label={{ value: "confirmed", position: "top", fontSize: 10 }} />
            <Bar dataKey="count" cursor="pointer"
                 onClick={(d: { bucket?: AutoGroupsHistogramBucket }) => {
                   if (!d?.bucket) return;
                   const tier = d.bucket.lower >= data.tier_confirmed_threshold
                     ? "confirmed"
                     : d.bucket.lower >= data.tier_probable_threshold
                       ? "probable"
                       : "candidate";
                   nav(`/explorer/auto-groups?tier=${tier}`);
                 }}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={bucketColor(entry.bucket, data.tier_confirmed_threshold, data.tier_probable_threshold)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 4: Browser smoke**

Visit `http://localhost:5174/explorer/auto-groups/tuning`. Verify:
- Histogram bar chart renders with 20 bars covering [0.00, 1.00].
- Bars in [0.00, 0.40) are gray; [0.40, 0.75) amber; [0.75, 1.00] jade.
- Two dashed vertical reference lines visible at the probable + confirmed thresholds.
- Hover a bar → tooltip shows confidence range + group count.
- Click a bar → navigates to `/explorer/auto-groups?tier=<tier>` matching the bar's color zone.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupsHistogram.tsx
git commit -m "feat(layer2): tuning histogram with Recharts + click-to-filter"
```

---

### Task 7: Frontend — Close-to-promotion table

**Files:**
- Modify: `frontend/src/components/explorer/AutoGroupsCloseToPromotion.tsx`

- [ ] **Step 1: Replace the component**

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupsCloseToPromotionResponse } from "../../types";


export default function AutoGroupsCloseToPromotion() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupsCloseToPromotionResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupsCloseToPromotionResponse>(
      "/explorer/auto-groups/tuning/close-to-promotion",
    ).then(setData).catch(console.error);
  }, []);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Close to promotion</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Close to promotion</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Probable groups in confidence [{data.from_confidence.toFixed(2)}, {data.to_confidence.toFixed(2)}). {data.total.toLocaleString()} total.
        </Text>
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">display name</th>
              <th className="text-left p-2 font-medium">stem</th>
              <th className="text-left p-2 font-medium">tier</th>
              <th className="text-right p-2 font-medium">confidence</th>
              <th className="text-right p-2 font-medium">anchors</th>
              <th className="text-right p-2 font-medium">members</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((g) => (
              <tr key={g.auto_group_id}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/auto-groups/${encodeURIComponent(g.auto_group_id)}`)}>
                <td className="p-2 font-mono">{g.display_name}</td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>{g.canonical_stem}</td>
                <td className="p-2"><Badge color="amber">{g.tier}</Badge></td>
                <td className="p-2 text-right">{g.confidence.toFixed(2)}</td>
                <td className="p-2 text-right">{g.n_anchors.toLocaleString()}</td>
                <td className="p-2 text-right">{g.n_members.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Browser smoke**

Visit `/explorer/auto-groups/tuning`. The "Close to promotion" section should now show a table of Probable groups with confidence in [0.70, 0.75). Clicking a row navigates to that group's detail page.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupsCloseToPromotion.tsx
git commit -m "feat(layer2): close-to-promotion table"
```

---

### Task 8: Frontend — Missed stems table

**Files:**
- Modify: `frontend/src/components/explorer/AutoGroupsMissedStems.tsx`

- [ ] **Step 1: Replace the component**

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, TextField } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupsMissedStemsResponse } from "../../types";


export default function AutoGroupsMissedStems() {
  const [data, setData] = useState<AutoGroupsMissedStemsResponse | null>(null);
  const [minSides, setMinSides] = useState<string>("100");

  useEffect(() => {
    const params: Record<string, string | number> = { min_n_party_sides: parseInt(minSides) || 100 };
    fetchApi<AutoGroupsMissedStemsResponse>(
      "/explorer/auto-groups/tuning/missed-stems", params,
    ).then(setData).catch(console.error);
  }, [minSides]);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Stems that didn't promote</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Stems that didn't promote</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Distinctive or position-anchor 1-grams with ≥ N party-sides that failed verification.
          {data.total.toLocaleString()} total.
        </Text>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <Text size="2">Min party-sides:</Text>
        <TextField.Root size="2" value={minSides}
                        onChange={(e) => setMinSides(e.target.value)}
                        style={{ width: 100 }} />
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">token</th>
              <th className="text-right p-2 font-medium">party-sides</th>
              <th className="text-left p-2 font-medium">strongest phone</th>
              <th className="text-right p-2 font-medium">sides at anchor</th>
              <th className="text-left p-2 font-medium">winner stem</th>
              <th className="text-right p-2 font-medium">winner dominance</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row) => (
              <tr key={row.token} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{row.token}</td>
                <td className="p-2 text-right">{row.n_party_sides.toLocaleString()}</td>
                <td className="p-2 font-mono">
                  {row.strongest_phone ? (
                    <Link to={`/explorer/phones/${encodeURIComponent(row.strongest_phone)}`}
                          className="no-underline" style={{ color: "var(--accent-11)" }}>
                      {row.strongest_phone}
                    </Link>
                  ) : <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">
                  {row.token_sides_at_anchor != null ? row.token_sides_at_anchor.toLocaleString() : "—"}
                </td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>
                  {row.winner_stem ?? "—"}
                </td>
                <td className="p-2 text-right">
                  {row.winner_dominance != null ? row.winner_dominance.toFixed(2) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Browser smoke**

Visit `/explorer/auto-groups/tuning`. The "Stems that didn't promote" section should show a table with at least the well-known missed stems from Plan A's run notes (e.g. `ulc`, `advisors`, `nominee`, `kanco`, `ks`, `dd`, `dundee`, `piret`).
- Each row shows the token + n_party_sides + strongest phone + sides at that anchor + winner stem + winner's dominance share.
- The "strongest phone" cell is a clickable link to `/explorer/phones/<phone>`.
- Adjusting the "Min party-sides" input changes the result count.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupsMissedStems.tsx
git commit -m "feat(layer2): missed-stems table with dominance-contest data"
```

---

### Task 9: Frontend — list-page additions (anchor diversity column, distinct contacts column, close-to-promotion filter)

**Files:**
- Modify: `frontend/src/pages/ExplorerAutoGroups.tsx`

- [ ] **Step 1: Modify the list page**

Read the current `frontend/src/pages/ExplorerAutoGroups.tsx`. Locate the state declarations + the table + the filter row.

Add a new state variable next to the existing tier/q/page state:

```typescript
const [closeToPromotion, setCloseToPromotion] = useState(false);
```

Find the `useEffect` that calls `fetchApi`. Update the params object to include the new filter:

```typescript
useEffect(() => {
  const params: Record<string, string | number | boolean> = {
    tier, q, page, per_page: perPage,
  };
  if (closeToPromotion) params.close_to_promotion = "true";
  fetchApi<AutoGroupListResponse>("/explorer/auto-groups", params)
    .then(setData).catch((e) => console.error(e));
}, [tier, q, page, closeToPromotion]);
```

Find the existing filter row UI (the one with the SegmentedControl tier picker, search input, and group-count text). Add a checkbox for close-to-promotion next to the search input:

```typescript
<label className="flex items-center gap-2 text-[13px]">
  <input type="checkbox" checked={closeToPromotion}
         onChange={(e) => { setPage(1); setCloseToPromotion(e.target.checked); }} />
  <Text size="2">Close to promotion (0.70–0.75)</Text>
</label>
```

Find the `<thead>` of the table. Add two new column headers AFTER the existing "members" column:

```typescript
<th className="text-right p-2 font-medium">distinct contacts</th>
<th className="text-right p-2 font-medium">anchor diversity</th>
```

Find the row template (`data?.results.map((g) => (...))`). Add two new `<td>` elements at the end:

```typescript
<td className="p-2 text-right">{g.n_distinct_contacts != null ? g.n_distinct_contacts.toLocaleString() : "—"}</td>
<td className="p-2 text-right">{g.anchor_diversity != null ? g.anchor_diversity : "—"}</td>
```

Find the page header area (where "Auto-Groups" Heading is). Add a small link to the Tuning page next to the heading:

```typescript
<Link to="/explorer/auto-groups/tuning" className="text-[13px] no-underline ml-auto"
      style={{ color: "var(--accent-11)" }}>
  Tuning →
</Link>
```

(Place this inside the existing flex container with `Heading size="6"`. May need to add `ml-auto` or wrap in a flex layout — adjust to taste.)

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Browser smoke**

Visit `http://localhost:5174/explorer/auto-groups`. Verify:
- Table now has two new columns (distinct contacts, anchor diversity).
- "Close to promotion (0.70–0.75)" checkbox appears in the filter row.
- Toggling the checkbox narrows the list to confidence [0.70, 0.75).
- "Tuning →" link visible somewhere in the header area; clicking navigates to `/explorer/auto-groups/tuning`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExplorerAutoGroups.tsx
git commit -m "feat(layer2): list page adds anchor_diversity, distinct_contacts, close-to-promotion filter"
```

---

### Task 10: End-to-end verification on real DB

No code changes. Verify all surfaces load on real data.

- [ ] **Step 1: Backend smoke**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps
app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

print('=== histogram ===')
r = client.get('/api/explorer/auto-groups/tuning/histogram')
total = sum(b['count'] for b in r.json()['buckets'])
print(f'  status={r.status_code}, total groups in histogram={total}')
print(f'  thresholds: probable={r.json()[\"tier_probable_threshold\"]}, confirmed={r.json()[\"tier_confirmed_threshold\"]}')

print('=== close-to-promotion ===')
r = client.get('/api/explorer/auto-groups/tuning/close-to-promotion')
print(f'  status={r.status_code}, total={r.json()[\"total\"]}, window=[{r.json()[\"from_confidence\"]:.2f}, {r.json()[\"to_confidence\"]:.2f})')

print('=== missed-stems ===')
r = client.get('/api/explorer/auto-groups/tuning/missed-stems')
print(f'  status={r.status_code}, total={r.json()[\"total\"]}')
print(f'  first 5: {[t[\"token\"] for t in r.json()[\"results\"][:5]]}')

print('=== list with new columns ===')
r = client.get('/api/explorer/auto-groups', params={'per_page': 1, 'tier': 'confirmed'})
g = r.json()['results'][0]
print(f'  status={r.status_code}, sample={g.get(\"display_name\")}, anchor_diversity={g.get(\"anchor_diversity\")}, n_distinct_contacts={g.get(\"n_distinct_contacts\")}')

print('=== list with close-to-promotion filter ===')
r = client.get('/api/explorer/auto-groups', params={'tier': 'probable', 'close_to_promotion': 'true'})
print(f'  status={r.status_code}, total={r.json()[\"total\"]} probable groups in [0.70, 0.75)')
" 2>&1 | tail -15
```

Expected:
- histogram total ≈ 1,682 groups (Plan A run-notes baseline).
- close-to-promotion total: some realistic count (likely a few dozen).
- missed-stems first 5: tokens like `ulc`, `advisors`, `nominee`, `kanco`, `ks` (or similar — Plan A run notes listed these).
- list endpoint returns `anchor_diversity` (1, 2, or 3) and `n_distinct_contacts` (positive integer).
- close-to-promotion filter narrows the probable list correctly.

- [ ] **Step 2: Browser smoke**

Visit `http://localhost:5174/explorer/auto-groups/tuning`. Verify:
- Confidence histogram renders with 20 bars; gray/amber/jade color zones visible; reference lines at 0.40 and 0.75; click a bar → navigates to `/explorer/auto-groups?tier=<tier>`.
- Close-to-promotion table shows real Probable groups with confidence 0.70–0.75; click row → group detail page.
- Missed-stems table shows real tokens (`ulc`, `advisors`, etc.) with phone, sides count, winner stem, winner dominance.
- "Strongest phone" link → goes to Layer 1 phone silo page.

Visit `http://localhost:5174/explorer/auto-groups`. Verify:
- New columns visible (distinct contacts, anchor diversity).
- Close-to-promotion checkbox narrows the list.
- "Tuning →" link in header navigates to the tuning page.

- [ ] **Step 3: Capture verification notes**

Write to `docs/superpowers/run-notes/2026-04-27-layer-2-plan-g-verification.md`:

```markdown
# Plan G Verification Notes

## Backend smoke
- histogram: <total>
- close-to-promotion (default 0.70–0.75): <total>
- missed-stems: <total>, first 5: <tokens>
- list: anchor_diversity sample = <N>, n_distinct_contacts sample = <N>

## Manual click-through (your turn)
- [pass / fail per item]

## Findings worth flagging for Plan B/C
- <any over-broad stems still surfacing >
- <any close-to-promotion candidates that look like real operators>
- <any missed-stems whose winner_stem suggests a tenure / co-occurrence>
```

- [ ] **Step 4: Commit verification notes**

```bash
git add docs/superpowers/run-notes/2026-04-27-layer-2-plan-g-verification.md
git commit -m "docs: Plan G verification notes"
```

---

## Self-Review

Spec coverage check (against `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` Plan G section):

- ✅ **Confidence histogram with tier reference lines + click-to-filter** — Tasks 1 (backend), 6 (frontend), 9 (list-page navigation target).
- ✅ **Close to promotion table** — Tasks 2 (backend), 7 (frontend).
- ✅ **Stems that didn't promote with dominance-contest data** — Tasks 3 (backend), 8 (frontend).
- ✅ **List-page anchor_diversity column** — Tasks 4 (backend), 9 (frontend).
- ✅ **List-page distinct_contacts column** — Tasks 4 (backend), 9 (frontend).
- ✅ **List-page close-to-promotion filter** — Tasks 4 (backend), 9 (frontend).
- ✅ **Tuning page route at `/explorer/auto-groups/tuning`** — Task 5.
- ✅ **Real-DB verification** — Task 10.
- ✅ **Glossary used strictly** — every task references "anchor", "anchor_diversity", "tier", "stem" per spec; no aliases.

Type consistency check:
- `AutoGroupsHistogramResponse`, `AutoGroupsCloseToPromotionResponse`, `AutoGroupsMissedStemsResponse` defined in Task 5; consumed in Tasks 6, 7, 8.
- `AutoGroupSummary` extended with `anchor_diversity?` and `n_distinct_contacts?` in Task 5; the `?` keeps backward compat (Task 4 always populates them, but the optional marker means existing tests/callers don't break).
- All endpoint paths match between backend (Tasks 1-4) and frontend (Tasks 6-9): `/tuning/histogram`, `/tuning/close-to-promotion`, `/tuning/missed-stems`, `/auto-groups?close_to_promotion=true`.

No placeholders. No "similar to Task N" shortcuts. Every code step shows the actual code.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-layer-2-plan-g-tuning-page.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review. 10 tasks total.

**2. Inline Execution** — Execute tasks here in this session with checkpoints.

Which approach?
