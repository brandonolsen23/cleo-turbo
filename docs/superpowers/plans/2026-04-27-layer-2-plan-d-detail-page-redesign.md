# Layer 2 Plan D — Detail-Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` (Plan D scope only).

**Goal:** Replace the existing `/explorer/auto-groups/:id` page with a tabbed verification workbench. Ship Overview / Anchors / Parties tabs end-to-end; render placeholders for Graph and Trail tabs (Plans E and F).

**Architecture:** Three new backend endpoints feed three new frontend tab components. The existing single-page detail layout becomes the Overview tab. The Anchors tab adds anchor *coverage* and *co-stems* with click-through to existing Layer 1 silos. The Parties tab replaces the opaque `source_id | side | match_score` table with readable rows (date, brand phrase, address, contact, anchor signature) and click-through into the existing `SourceViewerDrawer`. Tab state is URL-driven via `?tab=...`.

**Tech Stack:** Python 3.12, FastAPI, SQLite (raw queries via `db.execute`), React 19, Radix UI Themes (`<Tabs>`), TypeScript, react-router-dom.

---

## Glossary (must use strictly per the spec)

| Term | Meaning |
|---|---|
| **Party** | One side of one transaction. Identified by `(source_id, side)`. The thing the algorithm groups. |
| **Group** | An `auto_groups` row. |
| **Anchor** | A phone, address (root or base), or contact_fingerprint that the algorithm has assigned to a group. |
| **Match score** | `auto_group_members.match_score`, range -0.5 to 1.0. |
| **Anchor coverage** | How many of a group's parties touch a specific anchor. |
| **Co-stem** | Another stem whose dominant phrase appears at the same anchor. |
| **Anchor category** | `phone` / `address` (collapses `address_root` + `address_base`) / `contact`. Three total. |
| **Tier** | `confirmed` / `probable` / `candidate`. |

Do not invent alternate names. If you need a new concept, surface it as a question; don't ship a new term.

---

## File Structure

**Backend:**
- Modify: `cleo/web/routes/explorer.py` — add 3 new endpoints (anchors-with-coverage, why-tier, parties).
- Modify: `tests/test_routes_explorer.py` — fixture extensions + tests for all 3 endpoints.

**Frontend (new files):**
- `frontend/src/components/explorer/AutoGroupTabs.tsx` — tab bar component (Radix `<Tabs>` based, URL query-param driven).
- `frontend/src/components/explorer/AutoGroupOverviewTab.tsx` — Overview tab content (refactored from existing detail page + new "Why this tier" panel).
- `frontend/src/components/explorer/AutoGroupAnchorsTab.tsx` — Anchors table with coverage + co-stems + Layer 1 silo click-through.
- `frontend/src/components/explorer/AutoGroupPartiesTab.tsx` — Paginated/filterable/sortable parties table with `SourceViewerDrawer` click-through.
- `frontend/src/components/explorer/AutoGroupTabPlaceholder.tsx` — "Coming in Plan E/F" stub used by Graph and Trail tabs.

**Frontend (modified):**
- `frontend/src/pages/ExplorerAutoGroupDetail.tsx` — restructured to render `AutoGroupTabs` + selected tab body. Existing content moves into `AutoGroupOverviewTab.tsx` (with the Why-tier panel added).
- `frontend/src/types/index.ts` — types for the 3 new endpoint responses + supporting shapes.

---

## Pre-flight context for the implementer

**SourceViewerDrawer integration.** The drawer is mounted globally in `App.tsx`. To open it from the Parties tab, import and use the hook:

```typescript
import { useSourceViewer } from "../source/SourceViewerContext";
const { openSource } = useSourceViewer();
// later: openSource(sourceId);
```

Note: `openSource` takes only `sourceId`, not `(source_id, side)` — the drawer shows the full transaction.

**Existing endpoint to keep in sync.** `GET /api/explorer/auto-groups/:id` continues to return summary + numbered_corps + top_phrases. Anchors and members fields are still populated for now (the existing list endpoint and other consumers may rely on them) — DO NOT remove them. The new endpoints are additive.

**Layer 1 silo click-through targets** (verified to exist):
- `/explorer/phones/<value>` — phone detail
- `/explorer/addresses/roots/<value>` (URL-encoded `<num>|<name>`)
- `/explorer/addresses/bases/<value>` (URL-encoded `<num>|<name>|<suffix>`)
- `/explorer/contacts/<value>`

**Test database.** The `_seeded_db` fixture in `tests/test_routes_explorer.py` already has Plan A's auto_groups + auto_group_anchors + auto_group_members tables populated for AGRP_00001 (kingsett) and AGRP_00002 (starlight). Extend it where needed; don't replace it.

---

## Tasks

### Task 1: Backend — `/anchors-with-coverage` endpoint

For each anchor in a group, return the anchor + its coverage (party count) + its co-stems.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture in `tests/test_routes_explorer.py`**

The existing `_seeded_db` fixture has AGRP_00001 (kingsett) with 3 anchors and 1 party_side member. To exercise coverage and co-stems, we need a few more parties on AGRP_00001 that touch a subset of its anchors, plus a co-stem signal.

Find the line `INSERT INTO auto_group_members (auto_group_id, member_type, source_id, side, match_score) VALUES ('AGRP_00001', 'party_side', 'RT1', 'buyer', 1.0)` in `_seeded_db`. Immediately after it, append:

```python
# Add 3 more parties for AGRP_00001 to exercise coverage
# RT-COV-1: touches phone + address_root + contact (3-anchor coverage)
# RT-COV-2: touches phone only (phone-only coverage)
# RT-COV-3: touches contact only (contact-only coverage)
conn.execute("""
    INSERT INTO party_fingerprints
        (source_id, side, phone, contact_fingerprint, street_number, street_name, street_suffix)
    VALUES ('RT-COV-1', 'seller', '4166876700', 'rob kumer', '40', 'king', 'st')
""")
conn.execute("""
    INSERT INTO party_fingerprints
        (source_id, side, phone, contact_fingerprint, street_number, street_name)
    VALUES ('RT-COV-2', 'seller', '4166876700', 'someone else', '999', 'somewhere')
""")
conn.execute("""
    INSERT INTO party_fingerprints
        (source_id, side, phone, contact_fingerprint, street_number, street_name)
    VALUES ('RT-COV-3', 'seller', '5555555555', 'rob kumer', '888', 'elsewhere')
""")
for sid in ('RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
    conn.execute(
        "INSERT INTO auto_group_members (auto_group_id, member_type, source_id, side, match_score) "
        "VALUES ('AGRP_00001', 'party_side', ?, 'seller', 0.9)",
        (sid,),
    )

# RT-COSTEM: a party at AGRP_00001's phone that ALSO has a starlight phrase mapped.
# Used to verify co-stems detection on the phone anchor.
conn.execute("""
    INSERT INTO party_fingerprints (source_id, side, phone)
    VALUES ('RT-COSTEM', 'buyer', '4166876700')
""")
conn.execute("""
    INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field)
    VALUES ('RT-COSTEM', 'buyer', 'brand_phrase', 'starlight investments', 'party_name')
""")
# Make sure starlight has a stem mapping in this fixture so co-stems can detect it.
conn.execute("""
    INSERT OR IGNORE INTO brand_stem (stem, stem_type, dominant_anchor_type,
                                      dominant_anchor_value, dominance_share, volume)
    VALUES ('starlight', 'distinctive', 'phone', '4162348444', 0.9, 100)
""")
conn.execute("""
    INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence)
    VALUES ('starlight investments', 'starlight', 1.0)
""")
# Same for kingsett — its parties use 'kingsett capital' as the brand phrase.
conn.execute("""
    INSERT OR IGNORE INTO brand_stem (stem, stem_type, dominant_anchor_type,
                                      dominant_anchor_value, dominance_share, volume)
    VALUES ('kingsett', 'distinctive', 'phone', '4166876700', 0.9, 8)
""")
conn.execute("""
    INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence)
    VALUES ('kingsett capital', 'kingsett', 1.0)
""")
# Backfill brand_phrase atoms on the kingsett parties so co-stems has signal to compare against.
for sid in ('RT1', 'RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', 'kingsett capital', 'party_name')",
        (sid, 'buyer' if sid == 'RT1' else 'seller'),
    )
```

Also extend the existing schema block in `_seeded_db` to add `brand_stem` and `brand_stem_phrase_map` if they're not already there — search for `CREATE TABLE IF NOT EXISTS brand_stem` in the fixture; if absent, add:

```sql
CREATE TABLE IF NOT EXISTS brand_stem (
    stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
    dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
    dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
);
CREATE TABLE IF NOT EXISTS brand_stem_phrase_map (
    phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
);
```

Add this to the SQL `executescript` block — same place the other `CREATE TABLE` statements live.

- [ ] **Step 2: Write failing tests for the endpoint**

Append to `tests/test_routes_explorer.py` (in the auto-groups section, after the existing tests):

```python
def test_anchors_with_coverage_returns_per_anchor_coverage(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchors-with-coverage')
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body['anchors'], list)
    # Find the phone anchor
    phone = next(a for a in body['anchors'] if a['anchor_type'] == 'phone')
    assert phone['anchor_value'] == '4166876700'
    # 3 parties touch this phone (RT1, RT-COV-1, RT-COV-2). RT-COV-3 doesn't.
    assert phone['coverage'] == 3


def test_anchors_with_coverage_returns_co_stems(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/anchors-with-coverage')
    body = resp.json()
    phone = next(a for a in body['anchors'] if a['anchor_type'] == 'phone')
    # The phone is shared with a 'starlight' phrase via RT-COSTEM
    co_stems = {c['stem'] for c in phone['co_stems']}
    assert 'starlight' in co_stems


def test_anchors_with_coverage_404_on_unknown(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/anchors-with-coverage')
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k anchors_with_coverage
# Expected: 3 failures — endpoint doesn't exist yet
```

- [ ] **Step 4: Add the endpoint to `cleo/web/routes/explorer.py`**

Find the `# ─── Auto-Groups (Layer 2 Plan A) ───` section. Insert these endpoints immediately after the existing `auto_group_detail` function:

```python
@router.get('/auto-groups/{auto_group_id}/anchors-with-coverage')
def auto_group_anchors_with_coverage(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    # 404 if the group doesn't exist
    exists = db.execute(
        'SELECT 1 FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    anchors = [dict(r) for r in db.execute(
        """SELECT anchor_type, anchor_value, score
           FROM auto_group_anchors
           WHERE auto_group_id = ?
           ORDER BY score DESC""",
        (auto_group_id,),
    )]

    # Coverage per anchor: how many of the group's party_side members touch it.
    for a in anchors:
        a['coverage'] = _coverage_for_anchor(
            db, auto_group_id, a['anchor_type'], a['anchor_value']
        )
        a['co_stems'] = _co_stems_for_anchor(
            db, auto_group_id, a['anchor_type'], a['anchor_value']
        )

    return {'anchors': anchors}


def _coverage_for_anchor(db, auto_group_id: str, anchor_type: str, anchor_value: str) -> int:
    if anchor_type == 'phone':
        clause = 'pf.phone = ?'
    elif anchor_type == 'address_root':
        clause = "(pf.street_number || '|' || pf.street_name) = ?"
    elif anchor_type == 'address_base':
        clause = "(pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = ?"
    elif anchor_type == 'contact':
        clause = 'pf.contact_fingerprint = ?'
    else:
        return 0
    row = db.execute(
        f"""SELECT COUNT(*) AS n
            FROM auto_group_members agm
            JOIN party_fingerprints pf
              ON pf.source_id = agm.source_id AND pf.side = agm.side
            WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side' AND {clause}""",
        (auto_group_id, anchor_value),
    ).fetchone()
    return row['n']


def _co_stems_for_anchor(db, auto_group_id: str, anchor_type: str, anchor_value: str) -> list:
    """Find OTHER stems (not the group's canonical_stem) whose phrases appear on parties at this anchor.

    Returns up to 5 entries: [{stem, n_parties}, ...] sorted by n_parties desc.
    """
    if anchor_type == 'phone':
        clause = 'pf.phone = ?'
    elif anchor_type == 'address_root':
        clause = "(pf.street_number || '|' || pf.street_name) = ?"
    elif anchor_type == 'address_base':
        clause = "(pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = ?"
    elif anchor_type == 'contact':
        clause = 'pf.contact_fingerprint = ?'
    else:
        return []

    rows = db.execute(
        f"""SELECT m.stem AS stem, COUNT(DISTINCT pf.source_id || '|' || pf.side) AS n_parties
            FROM party_fingerprints pf
            JOIN party_atoms pa
              ON pa.source_id = pf.source_id AND pa.side = pf.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            JOIN auto_groups ag ON ag.auto_group_id = ?
            WHERE {clause}
              AND m.stem != ag.canonical_stem
            GROUP BY m.stem
            ORDER BY n_parties DESC
            LIMIT 5""",
        (auto_group_id, anchor_value),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k anchors_with_coverage
# Expected: 3 passed
```

- [ ] **Step 6: Update the docstring at the top of `cleo/web/routes/explorer.py`**

Find the docstring block listing endpoints. Add this line alongside the existing auto-groups entries:

```
GET /api/explorer/auto-groups/:id/anchors-with-coverage  — anchors + coverage + co-stems
```

- [ ] **Step 7: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /anchors-with-coverage endpoint with coverage + co-stems"
```

---

### Task 2: Backend — `/why-tier` endpoint

For each group, explain which anchor categories converged and which didn't. For Probable groups, surface the strongest near-miss anchor in the missing category.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_why_tier_confirmed_lists_three_categories(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/why-tier')
    assert resp.status_code == 200
    body = resp.json()
    assert body['tier'] == 'confirmed'
    assert body['n_categories_passing'] == 3
    cats = {c['category']: c for c in body['categories']}
    assert {'phone', 'address', 'contact'} == set(cats.keys())
    for c in cats.values():
        assert c['passes_threshold'] is True
        assert c['strongest_anchor'] is not None


def test_why_tier_probable_identifies_missing_category(client):
    # AGRP_00002 (starlight, probable) has no anchors in the seed.
    # We need to add at least 2 anchor categories that pass for it to be
    # legitimately probable, but leave 1 category missing so the test exercises
    # the missing-category logic. Inject 2 strong anchors into the fixture
    # before the test client is created — but here we work with what's seeded.
    # If AGRP_00002 has zero anchors, this test verifies the empty case.
    resp = client.get('/api/explorer/auto-groups/AGRP_00002/why-tier')
    assert resp.status_code == 200
    body = resp.json()
    assert body['tier'] == 'probable'
    # n_categories_passing reflects how many categories had a strong anchor.
    # For this fixture, AGRP_00002 has no anchors → 0 passing.
    assert body['n_categories_passing'] == 0
    # All 3 categories should appear, each marked passes_threshold=False
    cats = {c['category'] for c in body['categories']}
    assert cats == {'phone', 'address', 'contact'}
    assert all(c['passes_threshold'] is False for c in body['categories'])


def test_why_tier_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/why-tier')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k why_tier
# Expected: 3 failures
```

- [ ] **Step 3: Implement the endpoint**

Insert into `cleo/web/routes/explorer.py` after the `_co_stems_for_anchor` helper added in Task 1:

```python
ANCHOR_SEEDING_SCORE_THRESHOLD = 1.5  # mirror cleo.discovery_v2.constants
ANCHOR_CORROBORATION_SCORE_THRESHOLD = 0.5  # for near-miss reporting


def _category_of_anchor_type(anchor_type: str) -> str:
    if anchor_type in ('address_root', 'address_base'):
        return 'address'
    return anchor_type


@router.get('/auto-groups/{auto_group_id}/why-tier')
def auto_group_why_tier(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        'SELECT auto_group_id, canonical_stem, tier, confidence FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    # Group anchors that passed the seeding threshold, bucketed by category.
    strong_by_category: dict[str, list] = {'phone': [], 'address': [], 'contact': []}
    for r in db.execute(
        """SELECT anchor_type, anchor_value, score
           FROM auto_group_anchors
           WHERE auto_group_id = ? AND score >= ?
           ORDER BY score DESC""",
        (auto_group_id, ANCHOR_SEEDING_SCORE_THRESHOLD),
    ):
        cat = _category_of_anchor_type(r['anchor_type'])
        strong_by_category[cat].append(dict(r))

    categories_response = []
    for cat in ('phone', 'address', 'contact'):
        anchors_in_cat = strong_by_category[cat]
        if anchors_in_cat:
            categories_response.append({
                'category': cat,
                'passes_threshold': True,
                'strongest_anchor': anchors_in_cat[0],
                'near_miss_anchor': None,
            })
        else:
            # Find the highest-scoring anchor in this category whose dominant_stem
            # matches this group's stem but score < threshold.
            near_miss = _near_miss_anchor(
                db, auto_group_id, summary['canonical_stem'], cat
            )
            categories_response.append({
                'category': cat,
                'passes_threshold': False,
                'strongest_anchor': None,
                'near_miss_anchor': near_miss,
            })

    n_passing = sum(1 for c in categories_response if c['passes_threshold'])

    return {
        'auto_group_id': auto_group_id,
        'canonical_stem': summary['canonical_stem'],
        'tier': summary['tier'],
        'confidence': summary['confidence'],
        'n_categories_passing': n_passing,
        'categories': categories_response,
        'seeding_threshold': ANCHOR_SEEDING_SCORE_THRESHOLD,
        'corroboration_threshold': ANCHOR_CORROBORATION_SCORE_THRESHOLD,
    }


def _near_miss_anchor(db, auto_group_id: str, canonical_stem: str, category: str):
    """Find the strongest anchor in this category whose dominant_stem matches the
    group's canonical_stem but score < ANCHOR_SEEDING_SCORE_THRESHOLD.

    Returns dict with {anchor_type, anchor_value, score} or None.
    """
    if category == 'phone':
        type_clause = "anchor_type = 'phone'"
    elif category == 'address':
        type_clause = "anchor_type IN ('address_root', 'address_base')"
    elif category == 'contact':
        type_clause = "anchor_type = 'contact'"
    else:
        return None

    row = db.execute(
        f"""SELECT anchor_type, anchor_value, score
            FROM anchor_uniqueness
            WHERE dominant_stem = ?
              AND score < ?
              AND {type_clause}
            ORDER BY score DESC
            LIMIT 1""",
        (canonical_stem, ANCHOR_SEEDING_SCORE_THRESHOLD),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k why_tier
# Expected: 3 passed
```

- [ ] **Step 5: Update the explorer.py docstring**

Add to the endpoint list:

```
GET /api/explorer/auto-groups/:id/why-tier  — explains which categories passed/missed for tier assignment
```

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /why-tier endpoint explaining category convergence"
```

---

### Task 3: Backend — `/parties` endpoint (paginated, filterable, sortable)

The largest of the three endpoints. Returns a paginated list of party rows enriched with brand phrase, address, contact, phone, sale_date, sale_price, and the per-party anchor signature (which of the group's anchors this party touches).

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture in `tests/test_routes_explorer.py`**

The fixture needs `transactions` rows so `sale_price` can be enriched, plus a few more parties for AGRP_00001 to exercise pagination/sorting.

Find the existing `_seeded_db` schema. If `CREATE TABLE IF NOT EXISTS transactions` isn't already there (it should be from earlier tests), add:

```sql
CREATE TABLE IF NOT EXISTS transactions (
    source_id TEXT PRIMARY KEY,
    sale_date TEXT,
    sale_price REAL
);
```

Then append seed data after the Task 1 fixture additions:

```python
# Transactions for the existing kingsett parties (sale_price + sale_date)
for sid, date, price in [
    ('RT1',       '2019-04-22', 5_200_000),
    ('RT-COV-1',  '2020-06-01', 8_400_000),
    ('RT-COV-2',  '2021-03-15', 3_100_000),
    ('RT-COV-3',  '2022-09-30',   780_000),
]:
    conn.execute(
        "INSERT OR IGNORE INTO transactions (source_id, sale_date, sale_price) VALUES (?, ?, ?)",
        (sid, date, price),
    )
# Mirror sale_date back onto party_fingerprints (some queries read it from there)
for sid in ('RT1', 'RT-COV-1', 'RT-COV-2', 'RT-COV-3'):
    conn.execute(
        "UPDATE party_fingerprints SET sale_date = (SELECT sale_date FROM transactions WHERE source_id = ?) "
        "WHERE source_id = ?",
        (sid, sid),
    )
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_parties_returns_enriched_rows(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/parties')
    assert resp.status_code == 200
    body = resp.json()
    assert body['total'] >= 4
    first = body['results'][0]
    # Required fields
    for f in ('source_id', 'side', 'match_score', 'sale_date', 'sale_price',
              'phone', 'contact', 'street_number', 'street_name',
              'top_brand_phrase', 'anchor_signature'):
        assert f in first


def test_parties_anchor_signature_lists_matching_group_anchors(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001/parties')
    body = resp.json()
    # RT-COV-1 touches phone + address_root + contact (3 anchors)
    cov1 = next(p for p in body['results'] if p['source_id'] == 'RT-COV-1')
    sig_categories = {entry['category'] for entry in cov1['anchor_signature']}
    assert {'phone', 'address', 'contact'}.issubset(sig_categories)
    # RT-COV-2 touches phone only
    cov2 = next(p for p in body['results'] if p['source_id'] == 'RT-COV-2')
    sig_categories_2 = {entry['category'] for entry in cov2['anchor_signature']}
    assert sig_categories_2 == {'phone'}


def test_parties_filter_by_anchor(client):
    # Show only parties that touch contact 'rob kumer'
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'anchor_type': 'contact', 'anchor_value': 'rob kumer'},
    )
    body = resp.json()
    sids = {p['source_id'] for p in body['results']}
    # RT1 and RT-COV-1 and RT-COV-3 all have rob kumer; RT-COV-2 has someone else.
    assert 'RT-COV-2' not in sids


def test_parties_filter_by_min_match_score(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'min_match_score': 0.95},
    )
    body = resp.json()
    for p in body['results']:
        assert p['match_score'] >= 0.95


def test_parties_pagination(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'per_page': 2, 'page': 1},
    )
    body = resp.json()
    assert len(body['results']) <= 2
    assert body['per_page'] == 2
    assert body['page'] == 1


def test_parties_sort_by_match_score_desc(client):
    resp = client.get(
        '/api/explorer/auto-groups/AGRP_00001/parties',
        params={'sort': 'match_score', 'order': 'desc'},
    )
    body = resp.json()
    scores = [p['match_score'] for p in body['results']]
    assert scores == sorted(scores, reverse=True)


def test_parties_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999/parties')
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k parties
# Expected: 7 failures
```

- [ ] **Step 4: Implement the endpoint**

Insert into `cleo/web/routes/explorer.py` after the why-tier endpoint:

```python
_PARTIES_VALID_SORTS = {
    'date': 'pf.sale_date',
    'match_score': 'agm.match_score',
    'sale_price': 't.sale_price',
}


@router.get('/auto-groups/{auto_group_id}/parties')
def auto_group_parties(
    auto_group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    min_match_score: Optional[float] = Query(None),
    side: Optional[str] = Query(None),
    anchor_type: Optional[str] = Query(None),
    anchor_value: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: str = Query('date'),
    order: str = Query('desc'),
    db=Depends(get_db), user=Depends(get_current_user),
):
    # 404 if the group doesn't exist
    summary = db.execute(
        'SELECT auto_group_id, canonical_stem FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    # Validate sort
    sort_column = _PARTIES_VALID_SORTS.get(sort)
    if sort_column is None:
        raise HTTPException(status_code=400, detail=f'Invalid sort: {sort!r}')
    order_sql = 'DESC' if order.lower() == 'desc' else 'ASC'

    where = ["agm.auto_group_id = ?", "agm.member_type = 'party_side'"]
    params: list = [auto_group_id]

    if min_match_score is not None:
        where.append('agm.match_score >= ?')
        params.append(min_match_score)
    if side in ('buyer', 'seller'):
        where.append('agm.side = ?')
        params.append(side)
    if anchor_type and anchor_value:
        if anchor_type == 'phone':
            where.append('pf.phone = ?')
            params.append(anchor_value)
        elif anchor_type == 'contact':
            where.append('pf.contact_fingerprint = ?')
            params.append(anchor_value)
        elif anchor_type == 'address_root':
            where.append("(pf.street_number || '|' || pf.street_name) = ?")
            params.append(anchor_value)
        elif anchor_type == 'address_base':
            where.append("(pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = ?")
            params.append(anchor_value)
    if q:
        where.append("EXISTS (SELECT 1 FROM party_atoms pa WHERE pa.source_id = agm.source_id AND pa.side = agm.side AND pa.atom_type = 'brand_phrase' AND LOWER(pa.atom_value) LIKE ?)")
        params.append(f'%{q.lower()}%')

    where_sql = ' WHERE ' + ' AND '.join(where)

    # Total count
    total = db.execute(
        f"""SELECT COUNT(*) FROM auto_group_members agm
            JOIN party_fingerprints pf
              ON pf.source_id = agm.source_id AND pf.side = agm.side
            {where_sql}""",
        params,
    ).fetchone()[0]

    offset = (page - 1) * per_page

    # Top brand phrase per party — most-frequent phrase mapped to the group's canonical_stem.
    # Fall back to any brand phrase on the party if no stem-mapped phrase exists.
    rows = db.execute(
        f"""SELECT
              agm.source_id, agm.side, agm.match_score,
              pf.phone, pf.contact_fingerprint AS contact, pf.sale_date,
              pf.street_number, pf.street_name, pf.street_suffix,
              pf.suite_type, pf.suite_number, pf.postal,
              t.sale_price,
              (SELECT pa.atom_value
                 FROM party_atoms pa
                 LEFT JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
                 WHERE pa.source_id = agm.source_id
                   AND pa.side = agm.side
                   AND pa.atom_type = 'brand_phrase'
                 ORDER BY (CASE WHEN m.stem = ? THEN 0 ELSE 1 END), pa.id ASC
                 LIMIT 1) AS top_brand_phrase
            FROM auto_group_members agm
            JOIN party_fingerprints pf
              ON pf.source_id = agm.source_id AND pf.side = agm.side
            LEFT JOIN transactions t ON t.source_id = agm.source_id
            {where_sql}
            ORDER BY {sort_column} {order_sql}, agm.source_id
            LIMIT ? OFFSET ?""",
        [summary['canonical_stem']] + params + [per_page, offset],
    ).fetchall()

    # Pre-load group anchors once so we can compute anchor_signature per row.
    group_anchors = list(db.execute(
        'SELECT anchor_type, anchor_value FROM auto_group_anchors WHERE auto_group_id = ?',
        (auto_group_id,),
    ))

    results = []
    for r in rows:
        d = dict(r)
        d['anchor_signature'] = _anchor_signature_for_party(d, group_anchors)
        results.append(d)

    return {
        'results': results,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


def _anchor_signature_for_party(party: dict, group_anchors: list) -> list:
    """Return the subset of group_anchors that this party's data matches."""
    addr_root = (
        f"{party['street_number']}|{party['street_name']}"
        if party.get('street_number') and party.get('street_name') else None
    )
    addr_base = (
        f"{party['street_number']}|{party['street_name']}|{party.get('street_suffix') or ''}"
        if party.get('street_number') and party.get('street_name') else None
    )
    matches = []
    for a in group_anchors:
        at, av = a['anchor_type'], a['anchor_value']
        if at == 'phone' and party.get('phone') == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'phone'})
        elif at == 'address_root' and addr_root == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'address'})
        elif at == 'address_base' and addr_base == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'address'})
        elif at == 'contact' and party.get('contact') == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'contact'})
    return matches
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k parties
# Expected: 7 passed
```

- [ ] **Step 6: Update the explorer.py docstring**

Add:

```
GET /api/explorer/auto-groups/:id/parties  — paginated, filterable, sortable parties with anchor_signature
```

- [ ] **Step 7: Smoke test against real DB**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps

app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

# Use a real Confirmed group ID — find one
import sqlite3
conn = sqlite3.connect('data/cleo.db')
gid = conn.execute(
    \"SELECT auto_group_id FROM auto_groups WHERE tier='confirmed' ORDER BY n_members DESC LIMIT 1\"
).fetchone()[0]
print('Smoke testing with', gid)

r = client.get(f'/api/explorer/auto-groups/{gid}/parties', params={'per_page': 5})
print('parties status:', r.status_code, '| total:', r.json()['total'])
print('first party anchor_signature size:', len(r.json()['results'][0]['anchor_signature']))

r2 = client.get(f'/api/explorer/auto-groups/{gid}/anchors-with-coverage')
print('anchors-with-coverage anchors:', len(r2.json()['anchors']))
print('first anchor coverage:', r2.json()['anchors'][0]['coverage'])

r3 = client.get(f'/api/explorer/auto-groups/{gid}/why-tier')
print('why-tier categories passing:', r3.json()['n_categories_passing'])
" 2>&1 | tail -10
```

Expected: all three endpoints return 200 with sensible-looking data.

- [ ] **Step 8: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /parties endpoint with filter/sort/pagination + anchor_signature"
```

---

### Task 4: Frontend types + tab shell + detail-page refactor

Add types for the three new endpoint responses. Create the tab shell component. Refactor `ExplorerAutoGroupDetail.tsx` to render tabs with placeholder bodies for now (next tasks fill them in).

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/components/explorer/AutoGroupTabs.tsx`
- Create: `frontend/src/components/explorer/AutoGroupTabPlaceholder.tsx`
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`

- [ ] **Step 1: Add types to `frontend/src/types/index.ts`**

Find the `AutoGroupDetail` interface (added in Plan A Task 10). Append new types after it:

```typescript
// ============================================================
// Explorer — Auto-Groups (Layer 2 Plan D additions)
// ============================================================

export interface AutoGroupCoStem {
  stem: string;
  n_parties: number;
}

export interface AutoGroupAnchorWithCoverage {
  anchor_type: 'phone' | 'address_root' | 'address_base' | 'contact';
  anchor_value: string;
  score: number;
  coverage: number;
  co_stems: AutoGroupCoStem[];
}

export interface AutoGroupAnchorsWithCoverageResponse {
  anchors: AutoGroupAnchorWithCoverage[];
}

export interface AutoGroupWhyTierCategory {
  category: 'phone' | 'address' | 'contact';
  passes_threshold: boolean;
  strongest_anchor: { anchor_type: string; anchor_value: string; score: number } | null;
  near_miss_anchor: { anchor_type: string; anchor_value: string; score: number } | null;
}

export interface AutoGroupWhyTierResponse {
  auto_group_id: string;
  canonical_stem: string;
  tier: 'confirmed' | 'probable' | 'candidate';
  confidence: number;
  n_categories_passing: number;
  categories: AutoGroupWhyTierCategory[];
  seeding_threshold: number;
  corroboration_threshold: number;
}

export interface AutoGroupPartyAnchorSignatureEntry {
  anchor_type: 'phone' | 'address_root' | 'address_base' | 'contact';
  anchor_value: string;
  category: 'phone' | 'address' | 'contact';
}

export interface AutoGroupParty {
  source_id: string;
  side: 'buyer' | 'seller';
  match_score: number;
  sale_date: string | null;
  sale_price: number | null;
  phone: string | null;
  contact: string | null;
  street_number: string | null;
  street_name: string | null;
  street_suffix: string | null;
  suite_type: string | null;
  suite_number: string | null;
  postal: string | null;
  top_brand_phrase: string | null;
  anchor_signature: AutoGroupPartyAnchorSignatureEntry[];
}

export interface AutoGroupPartiesResponse {
  results: AutoGroupParty[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}
```

- [ ] **Step 2: Create the tab placeholder component**

`frontend/src/components/explorer/AutoGroupTabPlaceholder.tsx`:

```typescript
import { Text } from "@radix-ui/themes";

export default function AutoGroupTabPlaceholder({ planName }: { planName: string }) {
  return (
    <div className="p-8 rounded-[var(--card-radius)] border border-[var(--gray-6)]"
         style={{ background: "var(--gray-2)" }}>
      <Text size="3" style={{ color: "var(--gray-9)" }}>
        Coming in {planName}.
      </Text>
    </div>
  );
}
```

- [ ] **Step 3: Create the AutoGroupTabs component**

`frontend/src/components/explorer/AutoGroupTabs.tsx`:

```typescript
import { useSearchParams } from "react-router-dom";
import { Tabs } from "@radix-ui/themes";

export type AutoGroupTabValue = 'overview' | 'anchors' | 'parties' | 'graph' | 'trail';

const VALID_TABS: AutoGroupTabValue[] = ['overview', 'anchors', 'parties', 'graph', 'trail'];

interface Props {
  children: {
    overview: React.ReactNode;
    anchors:  React.ReactNode;
    parties:  React.ReactNode;
    graph:    React.ReactNode;
    trail:    React.ReactNode;
  };
}

export default function AutoGroupTabs({ children }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('tab');
  const active: AutoGroupTabValue = (
    raw && VALID_TABS.includes(raw as AutoGroupTabValue) ? raw : 'overview'
  ) as AutoGroupTabValue;

  return (
    <Tabs.Root value={active}
               onValueChange={(v) => {
                 const next = new URLSearchParams(searchParams);
                 if (v === 'overview') next.delete('tab');
                 else next.set('tab', v);
                 setSearchParams(next, { replace: true });
               }}>
      <Tabs.List>
        <Tabs.Trigger value="overview">Overview</Tabs.Trigger>
        <Tabs.Trigger value="anchors">Anchors</Tabs.Trigger>
        <Tabs.Trigger value="parties">Parties</Tabs.Trigger>
        <Tabs.Trigger value="graph">Graph</Tabs.Trigger>
        <Tabs.Trigger value="trail">Trail</Tabs.Trigger>
      </Tabs.List>

      <div className="mt-5">
        <Tabs.Content value="overview">{children.overview}</Tabs.Content>
        <Tabs.Content value="anchors">{children.anchors}</Tabs.Content>
        <Tabs.Content value="parties">{children.parties}</Tabs.Content>
        <Tabs.Content value="graph">{children.graph}</Tabs.Content>
        <Tabs.Content value="trail">{children.trail}</Tabs.Content>
      </div>
    </Tabs.Root>
  );
}
```

- [ ] **Step 4: Refactor `ExplorerAutoGroupDetail.tsx` to render the tab shell**

Read the current `frontend/src/pages/ExplorerAutoGroupDetail.tsx`. The whole file (header, stat cards, anchors table, top phrases, numbered corps, members table) currently sits in one component.

For Step 4, **only restructure the page to render `<AutoGroupTabs>` with placeholders in every tab body.** Tasks 5–7 will fill in the actual tab content.

Replace the contents of `frontend/src/pages/ExplorerAutoGroupDetail.tsx` with:

```typescript
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupDetail } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AutoGroupTabs from "../components/explorer/AutoGroupTabs";
import AutoGroupTabPlaceholder from "../components/explorer/AutoGroupTabPlaceholder";


const tierColor: Record<string, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable:  "amber",
  candidate: "gray",
};

export default function ExplorerAutoGroupDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AutoGroupDetail | null>(null);
  const [err, setErr]   = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchApi<AutoGroupDetail>(`/explorer/auto-groups/${encodeURIComponent(id)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [id]);

  if (err)  return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <Link to="/explorer/auto-groups" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Auto-Groups
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6" className="font-mono">{data.display_name}</Heading>
        <Badge color={tierColor[data.tier]}>{data.tier}</Badge>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          stem: <span className="font-mono">{data.canonical_stem}</span>
        </Text>
      </div>

      <AutoGroupTabs>
        {{
          overview: <AutoGroupTabPlaceholder planName="Plan D Task 5" />,
          anchors:  <AutoGroupTabPlaceholder planName="Plan D Task 6" />,
          parties:  <AutoGroupTabPlaceholder planName="Plan D Task 7" />,
          graph:    <AutoGroupTabPlaceholder planName="Plan E" />,
          trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
        }}
      </AutoGroupTabs>
    </div>
  );
}
```

- [ ] **Step 5: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors

# Browser smoke (assuming dev servers are up):
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:5174/explorer/auto-groups/AGRP_00001
# Expected: 200
```

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00001` (any real ID). Verify:
- Tabs render (Overview / Anchors / Parties / Graph / Trail).
- Clicking each tab updates the URL with `?tab=...` and shows the right placeholder.
- The display_name + tier badge + stem header still shows above the tabs.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts \
        frontend/src/components/explorer/AutoGroupTabs.tsx \
        frontend/src/components/explorer/AutoGroupTabPlaceholder.tsx \
        frontend/src/pages/ExplorerAutoGroupDetail.tsx
git commit -m "feat(layer2): tab shell for auto-group detail page"
```

---

### Task 5: Frontend — Overview tab

The Overview tab is the existing detail-page content (stat cards, top phrases, numbered corps), MINUS the anchors and members tables (those move to their own tabs in Tasks 6 and 7), PLUS a new "Why this tier" panel that fetches `/why-tier` and renders the structured explanation.

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupOverviewTab.tsx`
- Create: `frontend/src/components/explorer/AutoGroupWhyTierPanel.tsx`
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`

- [ ] **Step 1: Create the Why-tier panel component**

`frontend/src/components/explorer/AutoGroupWhyTierPanel.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupWhyTierResponse } from "../../types";


export default function AutoGroupWhyTierPanel({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupWhyTierResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupWhyTierResponse>(`/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/why-tier`)
      .then(setData).catch(console.error);
  }, [autoGroupId]);

  if (!data) return null;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 mt-5">
      <div className="flex items-baseline gap-2 mb-3 flex-wrap">
        <Heading size="3">Why this tier</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          (seeding threshold: score ≥ {data.seeding_threshold})
        </Text>
      </div>
      <table className="w-full text-[13px]">
        <thead className="bg-[var(--gray-2)]">
          <tr style={{ color: "var(--gray-9)" }}>
            <th className="text-left p-2 font-medium">category</th>
            <th className="text-left p-2 font-medium">strongest anchor</th>
            <th className="text-right p-2 font-medium">score</th>
            <th className="text-left p-2 font-medium">status</th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((c) => (
            <tr key={c.category} className="border-t border-[var(--gray-4)]">
              <td className="p-2 font-medium">{c.category}</td>
              <td className="p-2 font-mono">
                {c.strongest_anchor
                  ? `${c.strongest_anchor.anchor_type}: ${c.strongest_anchor.anchor_value}`
                  : c.near_miss_anchor
                  ? `${c.near_miss_anchor.anchor_type}: ${c.near_miss_anchor.anchor_value} (near-miss)`
                  : "—"}
              </td>
              <td className="p-2 text-right">
                {c.strongest_anchor
                  ? c.strongest_anchor.score.toFixed(2)
                  : c.near_miss_anchor
                  ? c.near_miss_anchor.score.toFixed(2)
                  : "—"}
              </td>
              <td className="p-2">
                {c.passes_threshold
                  ? <Badge color="jade">passes</Badge>
                  : <Badge color="gray">missing</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Create the Overview tab component**

`frontend/src/components/explorer/AutoGroupOverviewTab.tsx`:

```typescript
import { Heading, Text } from "@radix-ui/themes";
import type { AutoGroupDetail } from "../../types";
import AutoGroupWhyTierPanel from "./AutoGroupWhyTierPanel";


export default function AutoGroupOverviewTab({ data }: { data: AutoGroupDetail }) {
  return (
    <>
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Confidence" value={data.confidence.toFixed(2)} />
        <StatCard label="Anchors"    value={data.n_anchors.toLocaleString()} />
        <StatCard label="Parties"    value={data.n_members.toLocaleString()} />
        <StatCard label="Distinct contacts" value={data.n_distinct_contacts.toLocaleString()} />
        <StatCard label="Date range"
                  value={data.min_sale_date && data.max_sale_date
                          ? `${data.min_sale_date.slice(0,7)} → ${data.max_sale_date.slice(0,7)}`
                          : "—"} />
      </div>

      {/* Why this tier */}
      <AutoGroupWhyTierPanel autoGroupId={data.auto_group_id} />

      {/* Top phrases */}
      <Heading size="4" mt="6" mb="2">Top phrases ({data.top_phrases.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">phrase</th>
              <th className="text-right p-2 font-medium">n</th>
            </tr>
          </thead>
          <tbody>
            {data.top_phrases.map((p, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{p.phrase}</td>
                <td className="p-2 text-right">{p.n.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Numbered corps */}
      {data.numbered_corps.length > 0 && (
        <>
          <Heading size="4" mt="6" mb="2">Numbered corps owned ({data.numbered_corps.length})</Heading>
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-3 text-[13px]"
               style={{ background: "var(--gray-2)" }}>
            {data.numbered_corps.map((c, i) => (
              <span key={i} className="inline-block mr-3 mb-2 font-mono">{c.corp_name}</span>
            ))}
          </div>
        </>
      )}
    </>
  );
}


function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <Heading size="5" mt="2">{value}</Heading>
    </div>
  );
}
```

- [ ] **Step 3: Wire Overview tab into the detail page**

Modify `frontend/src/pages/ExplorerAutoGroupDetail.tsx` — replace the `overview` placeholder with the new component:

```typescript
import AutoGroupOverviewTab from "../components/explorer/AutoGroupOverviewTab";
```

Then change the `<AutoGroupTabs>` body:

```typescript
<AutoGroupTabs>
  {{
    overview: <AutoGroupOverviewTab data={data} />,
    anchors:  <AutoGroupTabPlaceholder planName="Plan D Task 6" />,
    parties:  <AutoGroupTabPlaceholder planName="Plan D Task 7" />,
    graph:    <AutoGroupTabPlaceholder planName="Plan E" />,
    trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
  }}
</AutoGroupTabs>
```

- [ ] **Step 4: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00001` (or a real Confirmed group). Verify:
- Stat cards render at top of Overview tab.
- "Why this tier" panel appears below the cards with category rows.
- Top phrases table renders.
- Numbered corps wall renders if non-empty.
- Tabs Anchors/Parties/Graph/Trail still show placeholders.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupOverviewTab.tsx \
        frontend/src/components/explorer/AutoGroupWhyTierPanel.tsx \
        frontend/src/pages/ExplorerAutoGroupDetail.tsx
git commit -m "feat(layer2): Overview tab with Why-this-tier panel"
```

---

### Task 6: Frontend — Anchors tab

Anchors table with `coverage`, `co-stems`, and click-through to existing Layer 1 silos.

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupAnchorsTab.tsx`
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`

- [ ] **Step 1: Create the Anchors tab component**

`frontend/src/components/explorer/AutoGroupAnchorsTab.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type {
  AutoGroupAnchorsWithCoverageResponse,
  AutoGroupAnchorWithCoverage,
} from "../../types";


function silosLinkFor(a: AutoGroupAnchorWithCoverage): string | null {
  if (a.anchor_type === 'phone') return `/explorer/phones/${encodeURIComponent(a.anchor_value)}`;
  if (a.anchor_type === 'address_root') return `/explorer/addresses/roots/${encodeURIComponent(a.anchor_value)}`;
  if (a.anchor_type === 'address_base') return `/explorer/addresses/bases/${encodeURIComponent(a.anchor_value)}`;
  if (a.anchor_type === 'contact') return `/explorer/contacts/${encodeURIComponent(a.anchor_value)}`;
  return null;
}


export default function AutoGroupAnchorsTab({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupAnchorsWithCoverageResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupAnchorsWithCoverageResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchors-with-coverage`,
    ).then(setData).catch(console.error);
  }, [autoGroupId]);

  if (!data) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;
  }

  return (
    <>
      <Heading size="4" mb="2">Anchors ({data.anchors.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">type</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-right p-2 font-medium">score</th>
              <th className="text-right p-2 font-medium">coverage</th>
              <th className="text-left p-2 font-medium">co-stems</th>
              <th className="text-left p-2 font-medium">silo</th>
            </tr>
          </thead>
          <tbody>
            {data.anchors.map((a, i) => {
              const link = silosLinkFor(a);
              return (
                <tr key={i} className="border-t border-[var(--gray-4)]">
                  <td className="p-2">{a.anchor_type}</td>
                  <td className="p-2 font-mono">{a.anchor_value}</td>
                  <td className="p-2 text-right">{a.score.toFixed(2)}</td>
                  <td className="p-2 text-right">{a.coverage.toLocaleString()}</td>
                  <td className="p-2">
                    {a.co_stems.length === 0
                      ? <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                      : a.co_stems.map((c, j) => (
                          <Badge key={j} color="amber" className="mr-1 mb-1">
                            {c.stem} ({c.n_parties})
                          </Badge>
                        ))
                    }
                  </td>
                  <td className="p-2">
                    {link ? (
                      <Link to={link} className="no-underline"
                            style={{ color: "var(--accent-11)" }}>
                        view
                      </Link>
                    ) : (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Wire Anchors tab into the detail page**

Modify `frontend/src/pages/ExplorerAutoGroupDetail.tsx`:

```typescript
import AutoGroupAnchorsTab from "../components/explorer/AutoGroupAnchorsTab";
```

Then update the tab body:

```typescript
<AutoGroupTabs>
  {{
    overview: <AutoGroupOverviewTab data={data} />,
    anchors:  <AutoGroupAnchorsTab autoGroupId={data.auto_group_id} />,
    parties:  <AutoGroupTabPlaceholder planName="Plan D Task 7" />,
    graph:    <AutoGroupTabPlaceholder planName="Plan E" />,
    trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
  }}
</AutoGroupTabs>
```

- [ ] **Step 3: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

Open `http://localhost:5174/explorer/auto-groups/AGRP_00001?tab=anchors` (or a real Confirmed group). Verify:
- Anchors table renders with type / value / score / coverage / co-stems / silo columns.
- Co-stems show as amber badges where present, em-dash otherwise.
- Click "view" link → navigates to the corresponding Layer 1 silo page (e.g. phone detail page renders).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupAnchorsTab.tsx \
        frontend/src/pages/ExplorerAutoGroupDetail.tsx
git commit -m "feat(layer2): Anchors tab with coverage + co-stems + Layer 1 silo links"
```

---

### Task 7: Frontend — Parties tab

Paginated, filterable, sortable parties table with click-through to `SourceViewerDrawer`.

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupPartiesTab.tsx`
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`

- [ ] **Step 1: Create the Parties tab component**

`frontend/src/components/explorer/AutoGroupPartiesTab.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Heading, Text, Button, TextField, Select, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { useSourceViewer } from "../source/SourceViewerContext";
import type {
  AutoGroupPartiesResponse,
  AutoGroupParty,
  AutoGroupAnchorsWithCoverageResponse,
} from "../../types";


function formatAddress(p: AutoGroupParty): string {
  return [p.street_number, p.street_name, p.street_suffix, p.suite_type, p.suite_number]
    .filter(Boolean).join(" ");
}

function formatCurrency(n: number | null): string {
  if (n == null) return "—";
  return `$${(n / 1_000_000).toFixed(2)}M`;
}


export default function AutoGroupPartiesTab({ autoGroupId }: { autoGroupId: string }) {
  const { openSource } = useSourceViewer();
  const [data, setData] = useState<AutoGroupPartiesResponse | null>(null);

  // Filters / sort state
  const [page, setPage] = useState(1);
  const [perPage] = useState(100);
  const [minMatchScore, setMinMatchScore] = useState<string>("");
  const [side, setSide] = useState<"all" | "buyer" | "seller">("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"date" | "match_score" | "sale_price">("date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  // Anchor filter (populated from anchors-with-coverage)
  const [anchorPick, setAnchorPick] = useState<string>("");  // serialized as "type|value"
  const [allAnchors, setAllAnchors] = useState<{ type: string; value: string; label: string }[]>([]);

  useEffect(() => {
    fetchApi<AutoGroupAnchorsWithCoverageResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchors-with-coverage`,
    ).then((res) => {
      setAllAnchors(res.anchors.map((a) => ({
        type: a.anchor_type,
        value: a.anchor_value,
        label: `${a.anchor_type}: ${a.anchor_value}`,
      })));
    }).catch(console.error);
  }, [autoGroupId]);

  useEffect(() => {
    const params: Record<string, string | number> = {
      page, per_page: perPage, sort, order,
    };
    if (minMatchScore) params.min_match_score = parseFloat(minMatchScore);
    if (side !== "all") params.side = side;
    if (q) params.q = q;
    if (anchorPick) {
      const [t, v] = anchorPick.split("|", 2);
      params.anchor_type = t;
      params.anchor_value = v;
    }
    fetchApi<AutoGroupPartiesResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/parties`, params,
    ).then(setData).catch(console.error);
  }, [autoGroupId, page, perPage, minMatchScore, side, q, anchorPick, sort, order]);

  return (
    <>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <TextField.Root size="2" placeholder="brand phrase substring…"
                        value={q}
                        onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 200 }} />

        <Select.Root value={side} onValueChange={(v) => { setPage(1); setSide(v as any); }}>
          <Select.Trigger placeholder="Side" />
          <Select.Content>
            <Select.Item value="all">All sides</Select.Item>
            <Select.Item value="buyer">Buyer</Select.Item>
            <Select.Item value="seller">Seller</Select.Item>
          </Select.Content>
        </Select.Root>

        <TextField.Root size="2" placeholder="min match score…"
                        value={minMatchScore}
                        onChange={(e) => { setPage(1); setMinMatchScore(e.target.value); }}
                        style={{ width: 120 }} />

        <Select.Root value={anchorPick}
                     onValueChange={(v) => { setPage(1); setAnchorPick(v === "ALL" ? "" : v); }}>
          <Select.Trigger placeholder="Anchor filter" />
          <Select.Content>
            <Select.Item value="ALL">All anchors</Select.Item>
            {allAnchors.map((a) => (
              <Select.Item key={`${a.type}|${a.value}`} value={`${a.type}|${a.value}`}>
                {a.label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>

        <Select.Root value={`${sort}:${order}`}
                     onValueChange={(v) => {
                       const [s, o] = v.split(":");
                       setSort(s as any); setOrder(o as any);
                     }}>
          <Select.Trigger placeholder="Sort" />
          <Select.Content>
            <Select.Item value="date:desc">Newest first</Select.Item>
            <Select.Item value="date:asc">Oldest first</Select.Item>
            <Select.Item value="match_score:desc">Match score (high → low)</Select.Item>
            <Select.Item value="match_score:asc">Match score (low → high)</Select.Item>
            <Select.Item value="sale_price:desc">Sale price (high → low)</Select.Item>
            <Select.Item value="sale_price:asc">Sale price (low → high)</Select.Item>
          </Select.Content>
        </Select.Root>

        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} parties
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">date</th>
              <th className="text-left p-2 font-medium">side</th>
              <th className="text-left p-2 font-medium">brand phrase</th>
              <th className="text-left p-2 font-medium">address</th>
              <th className="text-left p-2 font-medium">contact</th>
              <th className="text-left p-2 font-medium">phone</th>
              <th className="text-right p-2 font-medium">price</th>
              <th className="text-left p-2 font-medium">signature</th>
              <th className="text-right p-2 font-medium">score</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((p) => (
              <tr key={`${p.source_id}|${p.side}`}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => openSource(p.source_id)}>
                <td className="p-2">{p.sale_date?.slice(0, 10) || "—"}</td>
                <td className="p-2">{p.side}</td>
                <td className="p-2 font-mono">{p.top_brand_phrase || "—"}</td>
                <td className="p-2">{formatAddress(p) || "—"}</td>
                <td className="p-2">{p.contact || "—"}</td>
                <td className="p-2 font-mono">{p.phone || "—"}</td>
                <td className="p-2 text-right">{formatCurrency(p.sale_price)}</td>
                <td className="p-2">
                  {p.anchor_signature.length === 0
                    ? <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                    : p.anchor_signature.map((s, i) => (
                        <Badge key={i} color="jade" className="mr-1">{s.category}</Badge>
                      ))
                  }
                </td>
                <td className="p-2 text-right">{p.match_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button size="1" variant="soft" disabled={page === 1}
                  onClick={() => setPage(page - 1)}>Previous</Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button size="1" variant="soft" disabled={page === data.pages}
                  onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Wire Parties tab into the detail page**

Modify `frontend/src/pages/ExplorerAutoGroupDetail.tsx`:

```typescript
import AutoGroupPartiesTab from "../components/explorer/AutoGroupPartiesTab";
```

Update the tab body:

```typescript
<AutoGroupTabs>
  {{
    overview: <AutoGroupOverviewTab data={data} />,
    anchors:  <AutoGroupAnchorsTab autoGroupId={data.auto_group_id} />,
    parties:  <AutoGroupPartiesTab autoGroupId={data.auto_group_id} />,
    graph:    <AutoGroupTabPlaceholder planName="Plan E" />,
    trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
  }}
</AutoGroupTabs>
```

- [ ] **Step 3: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00001?tab=parties` (or a real Confirmed group). Verify:
- Parties table renders with date / side / brand phrase / address / contact / phone / price / signature / score columns.
- Filter dropdown for anchor selection lists the group's anchors.
- Search input by brand phrase substring narrows the list.
- Sort dropdown reorders results (try "Match score high → low" and verify ordering).
- Side toggle (All / Buyer / Seller) narrows the list.
- Clicking a row opens the SourceViewerDrawer for that source_id.
- Pagination works for groups with >100 parties.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupPartiesTab.tsx \
        frontend/src/pages/ExplorerAutoGroupDetail.tsx
git commit -m "feat(layer2): Parties tab with filter/sort/pagination + SourceViewerDrawer"
```

---

### Task 8: End-to-end verification on real DB

No code changes. Verify all three tabs work against a real Confirmed group.

- [ ] **Step 1: Pick a real group**

```bash
sqlite3 -column -header data/cleo.db "
SELECT auto_group_id, canonical_stem, n_anchors, n_members
FROM auto_groups WHERE tier='confirmed'
ORDER BY n_members DESC LIMIT 5"
```

Pick one (e.g., `AGRP_NNNNN` for kingsett).

- [ ] **Step 2: Verify Overview tab**

Visit `http://localhost:5174/explorer/auto-groups/<picked-id>`. Confirm:
- Stat cards show real numbers.
- Why-this-tier panel shows 3 categories all marked "passes" (or 2 + a near-miss for a Probable group).
- Top phrases include the canonical operator name (e.g., "kingsett capital" for kingsett).
- Numbered corps wall renders if non-empty.

- [ ] **Step 3: Verify Anchors tab**

Click "Anchors" tab. Confirm:
- All anchors from the group render.
- Coverage shows non-zero values for at least the highest-scoring anchors.
- At least one anchor has co-stems visible (any operator with sub-brands like Skyline, KingSett's SREIT, etc.).
- Click "view" on a phone anchor → /explorer/phones/<phone> loads.
- Click "view" on an address anchor → /explorer/addresses/roots/... loads.
- Click "view" on a contact anchor → /explorer/contacts/<contact> loads.

- [ ] **Step 4: Verify Parties tab**

Click "Parties" tab. Confirm:
- Table renders with up to 100 rows.
- Sort dropdown changes the order.
- Anchor filter dropdown lists the group's anchors; picking one narrows the list.
- Search by brand phrase substring narrows the list.
- Row click opens SourceViewerDrawer with the actual transaction.
- Pagination works.

- [ ] **Step 5: Capture findings**

If anything looks wrong (empty co-stems where you expect them, misformatted addresses, prices not loading), capture details. If all four checks pass, the plan is done.

- [ ] **Step 6: Commit a verification note**

```bash
mkdir -p docs/superpowers/run-notes
cat > docs/superpowers/run-notes/2026-04-27-layer-2-plan-d-verification.md <<'EOF'
# Plan D Verification Notes

Group tested: [auto_group_id]

Overview tab: [pass / issues found]
Anchors tab: [pass / issues found]
Parties tab: [pass / issues found]

Layer 1 silo click-throughs verified: phone, address_root, address_base, contact: [yes / specifics].

SourceViewerDrawer click-through: [pass / issues found].
EOF
# Edit with actual findings, then:
git add docs/superpowers/run-notes/2026-04-27-layer-2-plan-d-verification.md
git commit -m "docs: Plan D verification notes"
```

---

## Self-Review

Spec coverage check (against `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` Plan D section):

- ✅ **Tab structure (Overview / Anchors / Parties / Graph / Trail)** — Tasks 4 (shell), 5 (Overview), 6 (Anchors), 7 (Parties); Graph/Trail are placeholders per spec.
- ✅ **Why this tier panel** — Task 5 Step 1.
- ✅ **Anchor coverage column** — Task 1 backend, Task 6 frontend.
- ✅ **Co-stems column** — Task 1 backend, Task 6 frontend.
- ✅ **Click-through to Layer 1 silos** — Task 6 `silosLinkFor`.
- ✅ **Parties table with brand phrase / address / contact / phone / signature** — Task 3 backend, Task 7 frontend.
- ✅ **Filterable parties** — Task 7 has min_match_score, side, anchor, q (brand phrase substring) filters.
- ✅ **Sortable parties** — Task 7 sort dropdown supports date / match_score / sale_price.
- ✅ **SourceViewerDrawer click-through** — Task 7 Step 1 uses `useSourceViewer().openSource(sourceId)`.
- ✅ **URL-driven tab state (`?tab=...`)** — Task 4 `AutoGroupTabs.tsx` uses `useSearchParams`.
- ✅ **Default tab = Overview when no `?tab=`** — Task 4.
- ✅ **Glossary used strictly** — every task uses "party," "group," "anchor," "match score," etc.; no "member" references except in legacy SQL column names that we don't rename in this plan.

Type consistency check:
- `AutoGroupAnchorWithCoverage` returned by `/anchors-with-coverage` — used in Task 6, type defined in Task 4.
- `AutoGroupParty` returned by `/parties` — used in Task 7, type defined in Task 4.
- `AutoGroupWhyTierResponse` returned by `/why-tier` — used in Task 5, type defined in Task 4.
- `useSourceViewer().openSource(sourceId)` — verified against `frontend/src/components/source/SourceViewerContext.tsx`.

No placeholders or "similar to Task N" shortcuts.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-layer-2-plan-d-detail-page-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. 8 tasks total.

**2. Inline Execution** — Execute tasks here in this session in order, with checkpoints for review at logical breakpoints.

Which approach?
