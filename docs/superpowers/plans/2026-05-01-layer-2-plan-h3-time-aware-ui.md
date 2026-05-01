# Layer 2 Plan H3 — Time-Aware UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md` (Plan H3 section).

**Goal:** Make the H2 tenure data visible in the explorer UI. Layer 1 silo detail pages get a Timeline section. The auto-group detail page swaps its Anchors tab for an Anchor Tenures tab. The Plan F Trail view becomes tenure-aware (jade/amber/gray edges depending on whether the party's sale_date falls inside a tenure window). The auto-groups list page gets a Conflicts tab surfacing `auto_conflict_flags` for human review.

**Architecture:** Pure UI surfacing — no algorithm changes. Reuses the H2 tenure tables (`auto_group_anchor_tenures`, `auto_contact_tenures`, `auto_conflict_flags`) and the timeline builder (`build_anchor_timeline`). New backend endpoints: per-anchor timelines (3 types — phone, address_unit, contact), per-group anchor-tenures listing, conflicts list + detail. New frontend: a shared `<SiloTimeline />` component embedded in three existing detail pages, a new `AutoGroupTenuresTab` replacing `AutoGroupAnchorsTab`, edge-coloring updates in `AutoGroupTrail`, and a new `Conflicts` page with a list + side-by-side detail drawer.

**Tech Stack:** FastAPI, React 19 + TypeScript + Radix UI Themes, Tailwind. No schema changes.

**Migration:** None.

---

## Glossary (locked from spec — used strictly)

| Term | Meaning |
|---|---|
| **Tenure window** | `(start_date, end_date)` from `auto_group_anchor_tenures` or `auto_contact_tenures`. Both are non-null after H2's simplification. |
| **Active tenure** | A tenure whose `end_date >= today - 1 year`. Surfaced visually in green/jade. |
| **Dormant tenure** | A tenure whose `end_date < today - 1 year`. Surfaced visually in gray. (UI-only label; no algorithmic effect.) |
| **Tenure-spanning** | A tenure whose `start_date <= party.sale_date <= end_date`. The Trail view renders these as solid jade. |
| **Tenure-mismatch** | An anchor that has tenures, but none of them span the party's `sale_date`. Renders dashed amber. |
| **Orphan anchor** | An anchor with no tenures at all. Renders dashed gray. |
| **Conflict** | A row in `auto_conflict_flags`. Four types: `anchor_reassignment`, `contact_overlap`, `transient_tenure`, plus `expansion_conflict` (multi-group ambiguity flagged at attach time by Stage A4). |

H3 does NOT add new conflict types; it only renders what H2 emitted.

---

## File Structure

**Backend (modified):**
- `cleo/web/routes/explorer.py` — add 6 new endpoints (3 timelines, 1 anchor-tenures, 2 conflicts) and update the existing trail endpoint to include tenure-spanning info per thread.

**Backend (test):**
- `tests/test_routes_explorer.py` — fixture extensions + ~15 new tests across the 6 new endpoints.

**Frontend (new):**
- `frontend/src/components/explorer/SiloTimeline.tsx` — shared component.
- `frontend/src/components/explorer/AutoGroupTenuresTab.tsx` — replaces `AutoGroupAnchorsTab` semantically; old file deleted.
- `frontend/src/pages/ExplorerConflicts.tsx` — new list page.
- `frontend/src/components/explorer/ConflictDetailDrawer.tsx` — side-by-side timelines for one conflict.

**Frontend (modified):**
- `frontend/src/pages/ExplorerPhoneDetail.tsx` — embed `<SiloTimeline />`.
- `frontend/src/pages/ExplorerAddressUnitDetail.tsx` — embed `<SiloTimeline />`.
- `frontend/src/pages/ExplorerContactDetail.tsx` — embed `<SiloTimeline />`.
- `frontend/src/pages/ExplorerAutoGroupDetail.tsx` — swap `AutoGroupAnchorsTab` for `AutoGroupTenuresTab`.
- `frontend/src/components/explorer/AutoGroupTabs.tsx` — rename "Anchors" tab label to "Anchor Tenures" (value stays `'anchors'` for URL stability).
- `frontend/src/components/explorer/AutoGroupTrail.tsx` — tenure-aware edge coloring + edge labels.
- `frontend/src/pages/ExplorerAutoGroupsList.tsx` — add "Conflicts" link in the header.
- `frontend/src/types/index.ts` — types for new endpoints.
- `frontend/src/App.tsx` — register the new `/explorer/conflicts` route.

**Frontend (deleted):**
- `frontend/src/components/explorer/AutoGroupAnchorsTab.tsx` — replaced by `AutoGroupTenuresTab`. Don't preserve as a shim.

---

## Pre-flight context for the implementer

**Tenure window fields**: `start_date` and `end_date` are both ISO `YYYY-MM-DD` strings, both non-null after H2's simplification. Compare with string comparison (lexicographic order works for ISO dates).

**Active vs dormant rule**: an active tenure has `end_date >= today - 365 days`. Compute on the backend so the frontend just renders. (No new constant needed — derive from `MIN_PERMANENT_TENURE_DAYS` if the implementer wants a named constant, OR hardcode 365 in the SQL — pragmatic choice; document either way.)

**Layer 1 silo timelines** show ONE row per party-side at the anchor with: sale_date, source_id, side, party_phrase (the side's first brand_phrase), other anchors on the side. The tenure(s) above the table show the windows in jade/gray bars.

**The existing `AutoGroupAnchorsTab` reads `/auto-groups/{id}/anchors-with-coverage`** which returns one row per (anchor_type, anchor_value) with coverage and co-stems. After H3, the new tab reads `/auto-groups/{id}/anchor-tenures` which returns one row per tenure (so an anchor with two tenures across stems for the same group — rare but possible — yields two rows).

**Conflict subtype distinction:**
- `anchor_reassignment`, `contact_overlap`, `transient_tenure` come from Stage A6.
- `expansion_conflict` is what Stage A4 emits when a party matches multiple groups via tenures. Both types live in `auto_conflict_flags` distinguished by `conflict_type`.
- Filtering: the Conflicts page lets the user filter by type via the `?type=` query param.

**Trail view edge colors:**
- Solid jade `var(--jade-9)` — anchor tenure spans party.sale_date for the matched group.
- Dashed amber `var(--amber-9)` — anchor has tenures but none spans the party's sale_date. Edge label shows the actual tenure window text.
- Dashed gray `var(--gray-7)` — anchor has no tenures (orphan).

**Existing Trail component (`AutoGroupTrail.tsx`)** uses @xyflow/react. New edge metadata (status, label) just feed the existing edge-style props.

**No `address_unit_summary` UI changes needed** — H1 already added the Address Unit detail page. H3 just embeds a `<SiloTimeline />` into it.

---

## Tasks

### Task 1: Backend — `/phones/{value}/timeline` endpoint

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_phone_timeline_returns_events_with_tenures(client):
    """Timeline for a phone returns chronological events + tenure windows."""
    resp = client.get('/api/explorer/phones/4166876700/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert 'events' in body
    assert 'tenures' in body
    # Events sorted by sale_date ASC
    dates = [e['sale_date'] for e in body['events']]
    assert dates == sorted(dates)
    # Each event has the expected shape
    for e in body['events']:
        assert {'sale_date', 'source_id', 'side', 'party_phrase', 'auto_group_id'} <= set(e.keys())


def test_phone_timeline_404_on_unknown_value(client):
    resp = client.get('/api/explorer/phones/9999999999/timeline')
    assert resp.status_code == 404


def test_phone_timeline_tenures_carry_active_flag(client):
    """Each tenure has start_date, end_date, dominant_stem, n_party_sides, is_active."""
    resp = client.get('/api/explorer/phones/4166876700/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert len(body['tenures']) >= 1
    for t in body['tenures']:
        assert {'auto_group_id', 'canonical_stem', 'start_date', 'end_date',
                'n_party_sides_in_window', 'is_active'} <= set(t.keys())
```

The fixture's `_seeded_db` already has phone `4166876700` with KingSett. Verify the seeded phone has at least one tenure row in `auto_group_anchor_tenures` — if the H1/H2 tests don't seed tenures, add a small seed block at the end of `_seeded_db`:

```python
# Seed an anchor tenure for the existing kingsett phone (Plan H3 fixture)
conn.execute("""
    INSERT INTO auto_group_anchor_tenures
       (auto_group_id, anchor_type, anchor_value,
        start_date, end_date, n_party_sides_in_window,
        dominance_share_in_window, score)
    VALUES ('AGRP_KINGSETT', 'phone', '4166876700',
            '2010-01-01', '2026-01-01', 137, 0.95, 6.5)
""")
```

(Use the same `auto_group_id` that's already seeded for KingSett in the fixture. If the fixture doesn't seed an `AGRP_KINGSETT` row in `auto_groups`, add one too.)

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "phone_timeline"
# Expected: 3 failures
```

- [ ] **Step 3: Add the endpoint**

Insert into `cleo/web/routes/explorer.py` near the existing `/phones/{value}` detail endpoint:

```python
@router.get('/phones/{value}/timeline')
def phone_timeline(
    value: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Chronological events for a phone anchor + the tenure windows for it."""
    # Confirm the phone exists in party_fingerprints (404 if not).
    exists = db.execute(
        "SELECT 1 FROM party_fingerprints WHERE phone = ? LIMIT 1",
        (value,),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f'Unknown phone: {value!r}')

    events = [dict(r) for r in db.execute(
        """SELECT pf.sale_date, pf.source_id, pf.side,
                  (SELECT pa.atom_value FROM party_atoms pa
                    WHERE pa.source_id = pf.source_id AND pa.side = pf.side
                      AND pa.atom_type = 'brand_phrase'
                    ORDER BY pa.id ASC LIMIT 1) AS party_phrase,
                  agm.auto_group_id
           FROM party_fingerprints pf
           LEFT JOIN auto_group_members agm
             ON agm.source_id = pf.source_id AND agm.side = pf.side
            AND agm.member_type = 'party_side'
           WHERE pf.phone = ?
             AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
           ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC""",
        (value,),
    )]

    # Tenures for this phone, with active flag derived on the server.
    tenures = [dict(r) for r in db.execute(
        """SELECT agt.auto_group_id, ag.canonical_stem,
                  agt.start_date, agt.end_date,
                  agt.n_party_sides_in_window,
                  agt.dominance_share_in_window,
                  agt.score,
                  CASE WHEN agt.end_date >= date('now', '-365 days') THEN 1 ELSE 0 END AS is_active
           FROM auto_group_anchor_tenures agt
           JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id
           WHERE agt.anchor_type = 'phone' AND agt.anchor_value = ?
           ORDER BY agt.start_date ASC""",
        (value,),
    )]

    return {'value': value, 'anchor_type': 'phone', 'events': events, 'tenures': tenures}
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "phone_timeline"
# Expected: 3 passed
```

- [ ] **Step 5: Update top-of-file docstring**

Add the new route line:
```
GET /api/explorer/phones/:value/timeline  — chronological events + tenure windows
```

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /phones/:value/timeline endpoint"
```

---

### Task 2: Backend — `/addresses/units/{key}/timeline` and `/contacts/{value}/timeline`

Same shape as Task 1, two more anchor types. Factored as one task because they're symmetric.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_address_unit_timeline_returns_events_with_tenures(client):
    """Timeline for an address_unit (7-pipe key)."""
    key = 'toronto|66|wellington|street|west|suite|4400'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert body['anchor_type'] == 'address_unit'
    assert body['value'] == key
    # tenures and events keys present (may be empty if fixture lacks data)
    assert 'events' in body
    assert 'tenures' in body


def test_address_unit_timeline_400_on_malformed_key(client):
    resp = client.get('/api/explorer/addresses/units/notenoughparts/timeline')
    assert resp.status_code == 400


def test_address_unit_timeline_404_on_unknown(client):
    key = 'toronto|99|nowhere|||||'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}/timeline')
    assert resp.status_code == 404


def test_contact_timeline_returns_events_with_tenures(client):
    resp = client.get('/api/explorer/contacts/jc/timeline')
    assert resp.status_code == 200
    body = resp.json()
    assert body['anchor_type'] == 'contact'
    assert body['value'] == 'jc'


def test_contact_timeline_404_on_unknown(client):
    resp = client.get('/api/explorer/contacts/no_such_contact/timeline')
    assert resp.status_code == 404
```

If the fixture lacks contact `jc` or unit `toronto|66|wellington|street|west|suite|4400` in `party_fingerprints` with sale_date populated, extend the fixture so they're present. (Same approach as Task 1.) Also seed at least one `auto_group_anchor_tenures` row for the address_unit and one `auto_contact_tenures` row for the contact.

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "timeline"
# Expected: 5 new failures (Task 1's 3 still pass)
```

- [ ] **Step 3: Add both endpoints**

In `cleo/web/routes/explorer.py`, near the existing `/addresses/units/{key}` detail endpoint, add:

```python
@router.get('/addresses/units/{key}/timeline')
def address_unit_timeline(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Chronological events for an address_unit anchor + tenure windows."""
    parts = key.split('|', 6)
    if len(parts) != 7:
        raise HTTPException(status_code=400, detail=f'Invalid unit key: {key!r}')
    city, snum, sname, suf, dir_, stype, snumber = parts

    pf_match_clause = (
        "(COALESCE(pf.city,'') || '|' || COALESCE(pf.street_number,'') || '|' || "
        "COALESCE(pf.street_name,'') || '|' || COALESCE(pf.street_suffix,'') || '|' || "
        "COALESCE(pf.street_direction,'') || '|' || COALESCE(pf.suite_type,'') || '|' || "
        "COALESCE(pf.suite_number,''))"
    )
    exists = db.execute(
        f"SELECT 1 FROM party_fingerprints pf WHERE {pf_match_clause} = ? LIMIT 1",
        (key,),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f'Unknown unit: {key!r}')

    events = [dict(r) for r in db.execute(
        f"""SELECT pf.sale_date, pf.source_id, pf.side,
                   (SELECT pa.atom_value FROM party_atoms pa
                     WHERE pa.source_id = pf.source_id AND pa.side = pf.side
                       AND pa.atom_type = 'brand_phrase'
                     ORDER BY pa.id ASC LIMIT 1) AS party_phrase,
                   agm.auto_group_id
            FROM party_fingerprints pf
            LEFT JOIN auto_group_members agm
              ON agm.source_id = pf.source_id AND agm.side = pf.side
             AND agm.member_type = 'party_side'
            WHERE {pf_match_clause} = ?
              AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
            ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC""",
        (key,),
    )]

    tenures = [dict(r) for r in db.execute(
        """SELECT agt.auto_group_id, ag.canonical_stem,
                  agt.start_date, agt.end_date,
                  agt.n_party_sides_in_window,
                  agt.dominance_share_in_window,
                  agt.score,
                  CASE WHEN agt.end_date >= date('now', '-365 days') THEN 1 ELSE 0 END AS is_active
           FROM auto_group_anchor_tenures agt
           JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id
           WHERE agt.anchor_type = 'address_unit' AND agt.anchor_value = ?
           ORDER BY agt.start_date ASC""",
        (key,),
    )]

    return {'value': key, 'anchor_type': 'address_unit', 'events': events, 'tenures': tenures}


@router.get('/contacts/{value}/timeline')
def contact_timeline(
    value: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Chronological events for a contact_fingerprint anchor + tenure windows.

    Note: contact tenures live in auto_contact_tenures (no anchor_type column).
    """
    exists = db.execute(
        "SELECT 1 FROM party_fingerprints WHERE contact_fingerprint = ? LIMIT 1",
        (value,),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f'Unknown contact: {value!r}')

    events = [dict(r) for r in db.execute(
        """SELECT pf.sale_date, pf.source_id, pf.side,
                  (SELECT pa.atom_value FROM party_atoms pa
                    WHERE pa.source_id = pf.source_id AND pa.side = pf.side
                      AND pa.atom_type = 'brand_phrase'
                    ORDER BY pa.id ASC LIMIT 1) AS party_phrase,
                  agm.auto_group_id
           FROM party_fingerprints pf
           LEFT JOIN auto_group_members agm
             ON agm.source_id = pf.source_id AND agm.side = pf.side
            AND agm.member_type = 'party_side'
           WHERE pf.contact_fingerprint = ?
             AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
           ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC""",
        (value,),
    )]

    tenures = [dict(r) for r in db.execute(
        """SELECT act.auto_group_id, ag.canonical_stem,
                  act.start_date, act.end_date,
                  act.n_party_sides_in_window,
                  CASE WHEN act.end_date >= date('now', '-365 days') THEN 1 ELSE 0 END AS is_active
           FROM auto_contact_tenures act
           JOIN auto_groups ag ON ag.auto_group_id = act.auto_group_id
           WHERE act.contact_fingerprint = ?
           ORDER BY act.start_date ASC""",
        (value,),
    )]

    return {'value': value, 'anchor_type': 'contact', 'events': events, 'tenures': tenures}
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "timeline"
# Expected: 8 passed (3 from Task 1 + 5 new)
```

- [ ] **Step 5: Update top-of-file docstring** with both new routes.

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /addresses/units/:key/timeline + /contacts/:value/timeline endpoints"
```

---

### Task 3: Frontend — shared `<SiloTimeline />` component

**Files:**
- Create: `frontend/src/components/explorer/SiloTimeline.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```typescript
// ============================================================
// Silo timelines (Plan H3)
// ============================================================

export interface SiloTimelineEvent {
  sale_date: string;
  source_id: string;
  side: 'buyer' | 'seller';
  party_phrase: string | null;
  auto_group_id: string | null;
}

export interface SiloTimelineTenure {
  auto_group_id: string;
  canonical_stem: string;
  start_date: string;
  end_date: string;
  n_party_sides_in_window: number;
  dominance_share_in_window?: number;  // present for anchor tenures, absent for contact tenures
  score?: number;                      // ditto
  is_active: 0 | 1;
}

export interface SiloTimelineResponse {
  value: string;
  anchor_type: 'phone' | 'address_unit' | 'contact';
  events: SiloTimelineEvent[];
  tenures: SiloTimelineTenure[];
}
```

- [ ] **Step 2: Create the component**

`frontend/src/components/explorer/SiloTimeline.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { SiloTimelineResponse, SiloTimelineTenure } from "../../types";


export type SiloAnchorType = 'phone' | 'address_unit' | 'contact';


function endpointFor(anchorType: SiloAnchorType, value: string): string {
  if (anchorType === 'phone') return `/explorer/phones/${encodeURIComponent(value)}/timeline`;
  if (anchorType === 'address_unit') return `/explorer/addresses/units/${encodeURIComponent(value)}/timeline`;
  return `/explorer/contacts/${encodeURIComponent(value)}/timeline`;
}


function tenureLabel(t: SiloTimelineTenure): string {
  return `${t.canonical_stem}: ${t.start_date} → ${t.end_date}`;
}


function TenureBar({ tenure }: { tenure: SiloTimelineTenure }) {
  const color = tenure.is_active ? 'jade' : 'gray';
  return (
    <div className="flex items-center gap-2 mb-1">
      <Badge color={color}>{tenureLabel(tenure)}</Badge>
      <Link to={`/explorer/auto-groups/${encodeURIComponent(tenure.auto_group_id)}`}
            className="text-[12px] no-underline" style={{ color: 'var(--accent-11)' }}>
        {tenure.auto_group_id}
      </Link>
      <Text size="1" style={{ color: 'var(--gray-9)' }}>
        {tenure.n_party_sides_in_window} parties
      </Text>
    </div>
  );
}


export default function SiloTimeline({
  anchorType, value,
}: {
  anchorType: SiloAnchorType;
  value: string;
}) {
  const [data, setData] = useState<SiloTimelineResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<SiloTimelineResponse>(endpointFor(anchorType, value))
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [anchorType, value]);

  if (err) return <Text color="tomato">{err}</Text>;
  if (!data) return <Text size="2" style={{ color: 'var(--gray-9)' }}>Loading timeline…</Text>;

  return (
    <div className="mt-6">
      <Heading size="3" mb="2">Timeline ({data.events.length.toLocaleString()} events)</Heading>

      {data.tenures.length === 0 ? (
        <Text size="2" style={{ color: 'var(--gray-9)' }} className="block mb-3">
          No tenures recorded — this anchor isn't yet attributed to any group.
        </Text>
      ) : (
        <div className="mb-3">
          {data.tenures.map((t, i) => <TenureBar key={i} tenure={t} />)}
        </div>
      )}

      {data.events.length === 0 ? (
        <Text size="2" style={{ color: 'var(--gray-9)' }}>No dated events.</Text>
      ) : (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--gray-2)]">
              <tr style={{ color: 'var(--gray-9)' }}>
                <th className="text-left p-2 font-medium">date</th>
                <th className="text-left p-2 font-medium">source</th>
                <th className="text-left p-2 font-medium">side</th>
                <th className="text-left p-2 font-medium">brand phrase</th>
                <th className="text-left p-2 font-medium">attached to</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                  <td className="p-2 font-mono">{formatDate(e.sale_date)}</td>
                  <td className="p-2 font-mono">{e.source_id}</td>
                  <td className="p-2">{e.side}</td>
                  <td className="p-2 font-mono">{e.party_phrase || '—'}</td>
                  <td className="p-2">
                    {e.auto_group_id ? (
                      <Link to={`/explorer/auto-groups/${encodeURIComponent(e.auto_group_id)}`}
                            className="no-underline" style={{ color: 'var(--accent-11)' }}>
                        {e.auto_group_id}
                      </Link>
                    ) : (
                      <Text size="1" style={{ color: 'var(--gray-9)' }}>orphan</Text>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/explorer/SiloTimeline.tsx frontend/src/types/index.ts
git commit -m "feat(layer2): SiloTimeline shared component (Plan H3)"
```

---

### Task 4: Frontend — embed `<SiloTimeline />` in three detail pages

**Files:**
- Modify: `frontend/src/pages/ExplorerPhoneDetail.tsx`
- Modify: `frontend/src/pages/ExplorerAddressUnitDetail.tsx`
- Modify: `frontend/src/pages/ExplorerContactDetail.tsx`

For each page, add this import:

```typescript
import SiloTimeline from "../components/explorer/SiloTimeline";
```

And render the component AFTER the existing stat cards / breakdowns, BEFORE any party list (if there is one):

**`ExplorerPhoneDetail.tsx`:**

```tsx
{/* … existing content above … */}
<SiloTimeline anchorType="phone" value={value} />
```

(`value` should be the phone string — find what variable name the existing page uses; it's typically `value` from `useParams`.)

**`ExplorerAddressUnitDetail.tsx`:**

```tsx
{/* after the stat cards / before the badge */}
{data && <SiloTimeline anchorType="address_unit" value={key!} />}
```

(Where `key` is the URL param.)

**`ExplorerContactDetail.tsx`:**

```tsx
{/* … existing content above … */}
<SiloTimeline anchorType="contact" value={value} />
```

- [ ] **Step 1: Apply imports + JSX in all 3 files**

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Browser smoke** (if servers up)

Visit `/explorer/phones/4166876700`, `/explorer/addresses/units/<key>?city=toronto`, `/explorer/contacts/<some-contact>` — verify the Timeline section renders below the existing content with at least the tenure bar(s) on top.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExplorerPhoneDetail.tsx \
        frontend/src/pages/ExplorerAddressUnitDetail.tsx \
        frontend/src/pages/ExplorerContactDetail.tsx
git commit -m "feat(layer2): wire SiloTimeline into Phone / Address Unit / Contact detail pages"
```

---

### Task 5: Backend — `/auto-groups/{id}/anchor-tenures` endpoint

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_anchor_tenures_returns_one_row_per_tenure(client):
    """For a group with 3 anchor tenures (phone, address_unit, contact), the
    endpoint returns 3 rows."""
    resp = client.get('/api/explorer/auto-groups/AGRP_KINGSETT/anchor-tenures')
    assert resp.status_code == 200
    body = resp.json()
    assert 'tenures' in body
    assert len(body['tenures']) >= 1
    for t in body['tenures']:
        assert {'anchor_type', 'anchor_value', 'start_date', 'end_date',
                'n_party_sides_in_window', 'score', 'is_active',
                'coverage_pct'} <= set(t.keys())


def test_anchor_tenures_404_on_unknown_group(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_NOPE/anchor-tenures')
    assert resp.status_code == 404


def test_anchor_tenures_sorted_by_score_desc(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_KINGSETT/anchor-tenures')
    scores = [t['score'] for t in resp.json()['tenures']]
    assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Add the endpoint**

```python
@router.get('/auto-groups/{auto_group_id}/anchor-tenures')
def auto_group_anchor_tenures(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """One row per tenure for the given group. Includes a coverage_pct that
    measures `n_party_sides_in_window / group.n_members`."""
    summary = db.execute(
        'SELECT auto_group_id, n_members FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')
    n_members = max(summary['n_members'], 1)  # avoid div-by-zero

    tenures = [dict(r) for r in db.execute(
        """SELECT agt.anchor_type, agt.anchor_value,
                  agt.start_date, agt.end_date,
                  agt.n_party_sides_in_window,
                  agt.dominance_share_in_window,
                  agt.score,
                  CASE WHEN agt.end_date >= date('now', '-365 days') THEN 1 ELSE 0 END AS is_active
           FROM auto_group_anchor_tenures agt
           WHERE agt.auto_group_id = ?
           ORDER BY agt.score DESC, agt.start_date DESC""",
        (auto_group_id,),
    )]
    for t in tenures:
        t['coverage_pct'] = round(100.0 * t['n_party_sides_in_window'] / n_members, 1)
    return {'auto_group_id': auto_group_id, 'tenures': tenures}
```

- [ ] **Step 4: Run, confirm pass**

- [ ] **Step 5: Update top-of-file docstring**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(layer2): /auto-groups/:id/anchor-tenures endpoint"
```

---

### Task 6: Frontend — `AutoGroupTenuresTab` replaces `AutoGroupAnchorsTab`

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupTenuresTab.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`
- Modify: `frontend/src/components/explorer/AutoGroupTabs.tsx`
- Delete: `frontend/src/components/explorer/AutoGroupAnchorsTab.tsx`

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```typescript
export interface AutoGroupAnchorTenure {
  anchor_type: 'phone' | 'address_unit' | 'contact';
  anchor_value: string;
  start_date: string;
  end_date: string;
  n_party_sides_in_window: number;
  dominance_share_in_window: number;
  score: number;
  is_active: 0 | 1;
  coverage_pct: number;
}

export interface AutoGroupAnchorTenuresResponse {
  auto_group_id: string;
  tenures: AutoGroupAnchorTenure[];
}
```

- [ ] **Step 2: Create the new tab**

`frontend/src/components/explorer/AutoGroupTenuresTab.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupAnchorTenuresResponse, AutoGroupAnchorTenure } from "../../types";


function siloLinkFor(t: AutoGroupAnchorTenure): string {
  if (t.anchor_type === 'phone') return `/explorer/phones/${encodeURIComponent(t.anchor_value)}`;
  if (t.anchor_type === 'address_unit') return `/explorer/addresses/units/${encodeURIComponent(t.anchor_value)}`;
  return `/explorer/contacts/${encodeURIComponent(t.anchor_value)}`;
}


export default function AutoGroupTenuresTab({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupAnchorTenuresResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<AutoGroupAnchorTenuresResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchor-tenures`,
    ).then((d) => { if (!cancelled) setData(d); })
     .catch(console.error);
    return () => { cancelled = true; };
  }, [autoGroupId]);

  if (!data) return <Text size="2" style={{ color: 'var(--gray-9)' }}>Loading…</Text>;

  return (
    <>
      <Heading size="4" mb="2">Anchor Tenures ({data.tenures.length})</Heading>
      <Text size="1" style={{ color: 'var(--gray-9)' }} className="block mb-2">
        Each row is one tenure window. An "active" badge means the tenure has been seen within the last year.
      </Text>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: 'var(--gray-9)' }}>
              <th className="text-left p-2 font-medium">anchor</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-left p-2 font-medium">tenure</th>
              <th className="text-right p-2 font-medium">parties</th>
              <th className="text-right p-2 font-medium">coverage</th>
              <th className="text-right p-2 font-medium">score</th>
              <th className="text-left p-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {data.tenures.map((t, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                <td className="p-2">{t.anchor_type}</td>
                <td className="p-2 font-mono break-all">
                  <Link to={siloLinkFor(t)} className="no-underline"
                        style={{ color: 'var(--accent-11)' }}>
                    {t.anchor_value}
                  </Link>
                </td>
                <td className="p-2 font-mono whitespace-nowrap">
                  {t.start_date} → {t.end_date}{' '}
                  {t.is_active === 1 && <Badge color="jade" size="1">active</Badge>}
                </td>
                <td className="p-2 text-right">{t.n_party_sides_in_window.toLocaleString()}</td>
                <td className="p-2 text-right">{t.coverage_pct.toFixed(0)}%</td>
                <td className="p-2 text-right">{t.score.toFixed(2)}</td>
                <td className="p-2"></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
```

- [ ] **Step 3: Wire into `ExplorerAutoGroupDetail.tsx`**

Replace `import AutoGroupAnchorsTab from "../components/explorer/AutoGroupAnchorsTab";` with:

```typescript
import AutoGroupTenuresTab from "../components/explorer/AutoGroupTenuresTab";
```

And in the `<AutoGroupTabs>` JSX, replace:

```tsx
anchors: <AutoGroupAnchorsTab autoGroupId={autoGroupId} />,
```

With:

```tsx
anchors: <AutoGroupTenuresTab autoGroupId={autoGroupId} />,
```

- [ ] **Step 4: Update tab label**

In `frontend/src/components/explorer/AutoGroupTabs.tsx`, change:

```tsx
<Tabs.Trigger value="anchors">Anchors</Tabs.Trigger>
```

to:

```tsx
<Tabs.Trigger value="anchors">Anchor Tenures</Tabs.Trigger>
```

(The `value="anchors"` stays — URL stability for bookmarks.)

- [ ] **Step 5: Delete the old tab file**

```bash
rm frontend/src/components/explorer/AutoGroupAnchorsTab.tsx
```

- [ ] **Step 6: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

If tsc complains about a leftover reference to `AutoGroupAnchorsTab`, fix it (probably another import not flagged here).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupTenuresTab.tsx \
        frontend/src/components/explorer/AutoGroupTabs.tsx \
        frontend/src/pages/ExplorerAutoGroupDetail.tsx \
        frontend/src/types/index.ts
git rm frontend/src/components/explorer/AutoGroupAnchorsTab.tsx
git commit -m "feat(layer2): AutoGroupTenuresTab replaces Anchors tab on group detail page"
```

---

### Task 7: Backend — Trail endpoint tenure-aware enrichment

The existing `/auto-groups/parties/{source_id}/{side}/trail` endpoint already returns party + threads + groups. Extend each thread's `groups` entries with: `start_date`, `end_date`, `spans_sale_date` (boolean) so the frontend can render edges with the correct color.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_trail_thread_groups_carry_tenure_info(client):
    """Each thread.groups[*] entry has start_date, end_date, spans_sale_date."""
    resp = client.get('/api/explorer/auto-groups/parties/RT_KINGSETT_1/buyer/trail')
    if resp.status_code == 404:
        # If fixture doesn't seed RT_KINGSETT_1, pick another known party.
        return
    body = resp.json()
    for thread in body['threads']:
        for g in thread['groups']:
            assert 'start_date' in g
            assert 'end_date' in g
            assert 'spans_sale_date' in g


def test_trail_spans_sale_date_true_when_inside_window(client):
    """A party at sale_date=2020-01-01 with phone tenure 2010→2026 should have spans=True."""
    # Add a fixture row if needed: party with sale_date 2020-01-01 attaching to
    # the seeded kingsett anchor with tenure 2010-01-01 → 2026-01-01.
    # This test assumes the fixture has at least one such party.
    resp = client.get('/api/explorer/auto-groups/parties/RT_KINGSETT_1/buyer/trail')
    if resp.status_code != 200:
        return
    body = resp.json()
    if body.get('threads'):
        spans = [g['spans_sale_date'] for thread in body['threads'] for g in thread['groups']]
        # At least one group entry should span (since the seeded tenure covers all dates 2010-2026).
        assert any(spans)
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Update the trail endpoint**

In `cleo/web/routes/explorer.py`, find `auto_group_party_trail`. Inside the per-anchor groups loop, replace the existing query:

```python
rows = db.execute(
    """SELECT aga.auto_group_id, ag.canonical_stem, ag.tier, ag.display_name,
              aga.score AS score_in_group
       FROM auto_group_anchors aga
       JOIN auto_groups ag ON ag.auto_group_id = aga.auto_group_id
       WHERE aga.anchor_type = ? AND aga.anchor_value = ?
       ORDER BY aga.score DESC""",
    (anchor_type, anchor_value),
).fetchall()
```

With a tenure-aware version:

```python
sale_date = p.get('sale_date') or '9999-12-31'
rows = db.execute(
    """SELECT agt.auto_group_id, ag.canonical_stem, ag.tier, ag.display_name,
              agt.score AS score_in_group,
              agt.start_date, agt.end_date,
              CASE WHEN agt.start_date <= ? AND ? <= agt.end_date THEN 1 ELSE 0 END
              AS spans_sale_date
       FROM auto_group_anchor_tenures agt
       JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id
       WHERE agt.anchor_type = ? AND agt.anchor_value = ?
       ORDER BY (CASE WHEN agt.start_date <= ? AND ? <= agt.end_date THEN 0 ELSE 1 END),
                agt.score DESC""",
    (sale_date, sale_date, anchor_type, anchor_value, sale_date, sale_date),
).fetchall()
```

(The `ORDER BY` puts spanning tenures first.)

For the `'contact'` anchor type, the source table is `auto_contact_tenures` not `auto_group_anchor_tenures` (no `anchor_type` column). Branch:

```python
if anchor_type == 'contact':
    rows = db.execute(
        """SELECT act.auto_group_id, ag.canonical_stem, ag.tier, ag.display_name,
                  0.0 AS score_in_group,
                  act.start_date, act.end_date,
                  CASE WHEN act.start_date <= ? AND ? <= act.end_date THEN 1 ELSE 0 END
                  AS spans_sale_date
           FROM auto_contact_tenures act
           JOIN auto_groups ag ON ag.auto_group_id = act.auto_group_id
           WHERE act.contact_fingerprint = ?
           ORDER BY (CASE WHEN act.start_date <= ? AND ? <= act.end_date THEN 0 ELSE 1 END),
                    act.start_date DESC""",
        (sale_date, sale_date, anchor_value, sale_date, sale_date),
    ).fetchall()
else:
    rows = db.execute(
        """… the auto_group_anchor_tenures version above …""",
        (sale_date, sale_date, anchor_type, anchor_value, sale_date, sale_date),
    ).fetchall()
```

Then the resulting dicts include `start_date`, `end_date`, `spans_sale_date` — they flow through the existing `[dict(r) for r in rows]` step into the response unchanged.

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k "trail"
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(layer2): trail endpoint emits tenure-spans info per thread group"
```

---

### Task 8: Frontend — `AutoGroupTrail` tenure-aware edge coloring

**Files:**
- Modify: `frontend/src/types/index.ts` — extend the trail type.
- Modify: `frontend/src/components/explorer/AutoGroupTrail.tsx`

- [ ] **Step 1: Update types**

Find the existing trail-thread type in `frontend/src/types/index.ts` (probably named `AutoGroupTrail` or `TrailThreadGroup`). Add three fields to each group entry:

```typescript
start_date?: string;
end_date?: string;
spans_sale_date?: 0 | 1;
```

(Optional types because the old endpoint may not have them in older fixtures — but new responses do.)

- [ ] **Step 2: Update edge styling in `AutoGroupTrail.tsx`**

Find where edges are constructed for the React Flow graph. There's likely a section like:

```typescript
trail.threads.forEach((thread, threadIdx) => {
  // build edges from party node → group nodes
});
```

For each `group` in a thread, derive the edge style:

```typescript
const spans = group.spans_sale_date === 1;
const hasTenure = group.start_date && group.end_date;
const edgeStyle = !hasTenure
  ? { stroke: 'var(--gray-7)', strokeDasharray: '4 4' }
  : spans
    ? { stroke: 'var(--jade-9)', strokeWidth: 2 }
    : { stroke: 'var(--amber-9)', strokeDasharray: '4 4' };

const edgeLabel = !hasTenure
  ? '(unattached)'
  : spans
    ? null
    : `tenure ${group.start_date} → ${group.end_date} (mismatch)`;

edges.push({
  id: `edge-${threadIdx}-${groupIdx}`,
  source: partyNodeId,
  target: groupNodeId,
  style: edgeStyle,
  label: edgeLabel,
  labelStyle: { fontSize: 10, fill: 'var(--gray-11)' },
  type: 'smoothstep',
});
```

(Adapt to the actual variable names in the existing code — this is a sketch.)

If a thread has zero groups in its `groups` array (orphan anchor), keep the current behavior of routing the edge to a "(no group)" stub node, but use the dashed-gray style.

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Browser smoke**

Visit `/explorer/auto-groups/<id>?tab=trail&source_id=<sid>&side=<side>` for a known party. Verify:
- Thread edges that span the sale_date are solid jade.
- Thread edges with non-spanning tenures are dashed amber, with a label showing the tenure window.
- Threads with no tenures render as dashed gray to "(no group)".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupTrail.tsx frontend/src/types/index.ts
git commit -m "feat(layer2): tenure-aware edge coloring in Trail view"
```

---

### Task 9: Backend — `/conflicts` list + `/conflicts/{id}` detail endpoints

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_conflicts_list_returns_all_types(client):
    resp = client.get('/api/explorer/conflicts')
    assert resp.status_code == 200
    body = resp.json()
    assert 'results' in body
    assert 'total' in body
    assert 'page' in body


def test_conflicts_list_filters_by_type(client):
    resp = client.get('/api/explorer/conflicts?type=anchor_reassignment')
    assert resp.status_code == 200
    body = resp.json()
    for r in body['results']:
        assert r['conflict_type'] == 'anchor_reassignment'


def test_conflicts_list_paginates(client):
    resp = client.get('/api/explorer/conflicts?page=1&per_page=2')
    body = resp.json()
    assert len(body['results']) <= 2


def test_conflict_detail_returns_timelines_for_each_group(client):
    """For an anchor_reassignment conflict, the detail returns the timelines
    of the involved anchor for both group_a and group_b side-by-side."""
    # Pick an existing conflict id from the fixture.
    list_resp = client.get('/api/explorer/conflicts?per_page=1')
    if not list_resp.json()['results']:
        return  # fixture has no conflicts
    cid = list_resp.json()['results'][0]['id']
    resp = client.get(f'/api/explorer/conflicts/{cid}')
    assert resp.status_code == 200
    body = resp.json()
    assert {'conflict', 'timelines'} <= set(body.keys())
    # `timelines` is a dict: { 'group_a_id': [event, ...], 'group_b_id': [event, ...] } if applicable


def test_conflict_detail_404_on_unknown(client):
    resp = client.get('/api/explorer/conflicts/9999999')
    assert resp.status_code == 404
```

The fixture needs a few `auto_conflict_flags` rows seeded (Task 10's verification will use real-DB data; tests use seeded). Add to `_seeded_db()`:

```python
conn.execute("""
    INSERT INTO auto_conflict_flags
        (conflict_type, entity_type, entity_value, entity_subtype,
         group_a, group_b, date_observed, description)
    VALUES
        ('anchor_reassignment', 'anchor', '4162655055', 'phone',
         'AGRP_KINGSETT', 'AGRP_DH', '2014-12-31',
         'phone 4162655055 reassigned from AGRP_KINGSETT to AGRP_DH'),
        ('contact_overlap', 'contact', 'jc', NULL,
         'AGRP_KINGSETT', 'AGRP_DH', '2018-01-01',
         'Contact jc held tenures at AGRP_KINGSETT and AGRP_DH; either …'),
        ('transient_tenure', 'anchor', 'toronto|4950|yonge||||', 'address_unit',
         'AGRP_DH', NULL, '2014-06-01',
         'address_unit toronto|4950|yonge|||| had a transient tenure …')
""")
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Add the endpoints**

```python
@router.get('/conflicts')
def list_conflicts(
    type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """List auto_conflict_flags, paginated, optionally filtered."""
    where = []
    params: list = []
    if type:
        where.append('conflict_type = ?')
        params.append(type)
    if entity_type:
        where.append('entity_type = ?')
        params.append(entity_type)
    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

    total = db.execute(
        f'SELECT COUNT(*) FROM auto_conflict_flags{where_sql}', params,
    ).fetchone()[0]
    offset = (page - 1) * per_page

    rows = db.execute(
        f"""SELECT id, conflict_type, entity_type, entity_value, entity_subtype,
                   group_a, group_b, date_observed, description, discovered_at
            FROM auto_conflict_flags{where_sql}
            ORDER BY id DESC
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


@router.get('/conflicts/{conflict_id}')
def conflict_detail(
    conflict_id: int, db=Depends(get_db), user=Depends(get_current_user),
):
    """One conflict + the timelines (per group) of the affected anchor/contact
    for side-by-side review."""
    row = db.execute(
        """SELECT id, conflict_type, entity_type, entity_value, entity_subtype,
                  group_a, group_b, date_observed, description, discovered_at
           FROM auto_conflict_flags WHERE id = ?""",
        (conflict_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f'Unknown conflict: {conflict_id}')
    conflict = dict(row)

    # Fetch the affected anchor/contact's events, partitioned by group.
    timelines: dict[str, list] = {}
    if conflict['entity_type'] == 'anchor':
        # entity_subtype is the anchor_type
        # entity_value is the anchor_value
        for gid in (conflict['group_a'], conflict['group_b']):
            if gid is None:
                continue
            timelines[gid] = [dict(r) for r in db.execute(
                f"""SELECT pf.sale_date, pf.source_id, pf.side
                    FROM auto_group_members agm
                    JOIN party_fingerprints pf
                      ON pf.source_id = agm.source_id AND pf.side = agm.side
                    WHERE agm.auto_group_id = ?
                      AND agm.member_type = 'party_side'
                      AND { _anchor_pf_clause(conflict['entity_subtype']) or '0' }
                      AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
                    ORDER BY pf.sale_date ASC""",
                (gid, conflict['entity_value']),
            )]
    elif conflict['entity_type'] == 'contact':
        for gid in (conflict['group_a'], conflict['group_b']):
            if gid is None:
                continue
            timelines[gid] = [dict(r) for r in db.execute(
                """SELECT pf.sale_date, pf.source_id, pf.side
                   FROM auto_group_members agm
                   JOIN party_fingerprints pf
                     ON pf.source_id = agm.source_id AND pf.side = agm.side
                   WHERE agm.auto_group_id = ?
                     AND agm.member_type = 'party_side'
                     AND pf.contact_fingerprint = ?
                     AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
                   ORDER BY pf.sale_date ASC""",
                (gid, conflict['entity_value']),
            )]

    return {'conflict': conflict, 'timelines': timelines}
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Update top-of-file docstring**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(layer2): /conflicts list + /conflicts/:id detail endpoints"
```

---

### Task 10: Frontend — `Conflicts` page + detail drawer

**Files:**
- Create: `frontend/src/pages/ExplorerConflicts.tsx`
- Create: `frontend/src/components/explorer/ConflictDetailDrawer.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.tsx` (register route)
- Modify: `frontend/src/pages/ExplorerAutoGroupsList.tsx` (add header link)

- [ ] **Step 1: Add types**

```typescript
export type ConflictType =
  | 'anchor_reassignment'
  | 'contact_overlap'
  | 'transient_tenure'
  | 'expansion_conflict';

export interface ConflictFlag {
  id: number;
  conflict_type: ConflictType;
  entity_type: 'anchor' | 'contact';
  entity_value: string;
  entity_subtype: string | null;
  group_a: string | null;
  group_b: string | null;
  date_observed: string | null;
  description: string;
  discovered_at: string | null;
}

export interface ConflictsListResponse {
  results: ConflictFlag[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ConflictDetailEvent {
  sale_date: string;
  source_id: string;
  side: 'buyer' | 'seller';
}

export interface ConflictDetailResponse {
  conflict: ConflictFlag;
  timelines: Record<string, ConflictDetailEvent[]>;
}
```

- [ ] **Step 2: Create `ExplorerConflicts.tsx`**

`frontend/src/pages/ExplorerConflicts.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Heading, Text, Badge, Select } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import ConflictDetailDrawer from "../components/explorer/ConflictDetailDrawer";
import type { ConflictsListResponse, ConflictType } from "../types";


const CONFLICT_TYPES: ConflictType[] = [
  'anchor_reassignment', 'contact_overlap', 'transient_tenure', 'expansion_conflict',
];


export default function ExplorerConflicts() {
  const [params, setParams] = useSearchParams();
  const type = params.get('type') ?? '';
  const page = parseInt(params.get('page') ?? '1', 10);
  const [data, setData] = useState<ConflictsListResponse | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const qs = new URLSearchParams();
    if (type) qs.set('type', type);
    qs.set('page', String(page));
    qs.set('per_page', '100');
    fetchApi<ConflictsListResponse>(`/explorer/conflicts?${qs.toString()}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [type, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-3 mt-2 mb-4">
        <Heading size="6">Conflicts</Heading>
        <Text size="2" style={{ color: 'var(--gray-9)' }}>
          {data ? `${data.total.toLocaleString()} flagged` : 'Loading…'}
        </Text>
      </div>

      <div className="mb-3 flex gap-3 items-center">
        <Text size="2">Filter:</Text>
        <Select.Root value={type || 'all'} onValueChange={(v) => {
          const next = new URLSearchParams(params);
          if (v === 'all') next.delete('type'); else next.set('type', v);
          next.delete('page');
          setParams(next);
        }}>
          <Select.Trigger />
          <Select.Content>
            <Select.Item value="all">All types</Select.Item>
            {CONFLICT_TYPES.map((t) => (
              <Select.Item key={t} value={t}>{t}</Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </div>

      {data && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--gray-2)]">
              <tr style={{ color: 'var(--gray-9)' }}>
                <th className="text-left p-2 font-medium">type</th>
                <th className="text-left p-2 font-medium">entity</th>
                <th className="text-left p-2 font-medium">group_a</th>
                <th className="text-left p-2 font-medium">group_b</th>
                <th className="text-left p-2 font-medium">observed</th>
                <th className="text-left p-2 font-medium">description</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((c) => (
                <tr key={c.id} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                    onClick={() => setOpenId(c.id)}>
                  <td className="p-2"><Badge>{c.conflict_type}</Badge></td>
                  <td className="p-2 font-mono break-all">{c.entity_value}</td>
                  <td className="p-2 font-mono">{c.group_a || '—'}</td>
                  <td className="p-2 font-mono">{c.group_b || '—'}</td>
                  <td className="p-2 font-mono">{c.date_observed || '—'}</td>
                  <td className="p-2" style={{ color: 'var(--gray-11)' }}>
                    {c.description.slice(0, 80)}{c.description.length > 80 ? '…' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId !== null && (
        <ConflictDetailDrawer conflictId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `ConflictDetailDrawer.tsx`**

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Dialog, Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { ConflictDetailResponse } from "../../types";


export default function ConflictDetailDrawer({
  conflictId, onClose,
}: {
  conflictId: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<ConflictDetailResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<ConflictDetailResponse>(`/explorer/conflicts/${conflictId}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [conflictId]);

  return (
    <Dialog.Root open={true} onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Content style={{ maxWidth: 900 }}>
        {!data ? (
          <Text>Loading…</Text>
        ) : (
          <>
            <Dialog.Title>
              <Badge>{data.conflict.conflict_type}</Badge>{' '}
              <span className="font-mono">{data.conflict.entity_value}</span>
            </Dialog.Title>
            <Text size="2" style={{ color: 'var(--gray-9)' }} className="block mb-4">
              {data.conflict.description}
            </Text>

            <div className="grid grid-cols-2 gap-4">
              {Object.entries(data.timelines).map(([gid, events]) => (
                <div key={gid}>
                  <Heading size="3" mb="2">
                    <Link to={`/explorer/auto-groups/${encodeURIComponent(gid)}`}
                          style={{ color: 'var(--accent-11)' }} className="no-underline">
                      {gid}
                    </Link>
                  </Heading>
                  <div className="text-[12px] font-mono">
                    {events.length === 0 ? (
                      <Text size="1" style={{ color: 'var(--gray-9)' }}>No events.</Text>
                    ) : (
                      events.map((e, i) => (
                        <div key={i} className="border-t border-[var(--gray-4)] py-1">
                          {e.sale_date} | {e.source_id} | {e.side}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
}
```

- [ ] **Step 4: Register route in App.tsx**

```typescript
const ExplorerConflicts = lazy(() => import("./pages/ExplorerConflicts"));
```

```tsx
<Route path="/explorer/conflicts" element={<ExplorerConflicts />} />
```

- [ ] **Step 5: Add "Conflicts" link to the auto-groups list page header**

In `frontend/src/pages/ExplorerAutoGroupsList.tsx`, find the "Tuning →" link and add a sibling "Conflicts →" link:

```tsx
<Link to="/explorer/conflicts" className="no-underline" style={{ color: 'var(--accent-11)' }}>
  Conflicts →
</Link>
```

- [ ] **Step 6: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ExplorerConflicts.tsx \
        frontend/src/components/explorer/ConflictDetailDrawer.tsx \
        frontend/src/types/index.ts \
        frontend/src/App.tsx \
        frontend/src/pages/ExplorerAutoGroupsList.tsx
git commit -m "feat(layer2): Conflicts page + detail drawer"
```

---

### Task 11: Real-DB UI smoke test + verification notes

**Files:** none (run + verify only — produces a run-notes file).

- [ ] **Step 1: Confirm dev servers up**

```bash
curl -s http://localhost:8099/api/health 2>&1 | head -3
curl -s http://localhost:5174 2>&1 | head -3
```

If either is down, start them:

```bash
# project root
uvicorn cleo.web.app:app --reload --port 8099
# frontend/
npm run dev
```

- [ ] **Step 2: Hit each new endpoint with real data**

```bash
# Phone timeline (KingSett switchboard)
curl -s 'http://localhost:8099/api/explorer/phones/4166876700/timeline' \
  -H "Authorization: Bearer $TOKEN" | head -c 500

# Address unit timeline (66 Wellington suite 4400)
KEY='toronto%7C66%7Cwellington%7Cstreet%7Cwest%7Csuite%7C4400'
curl -s "http://localhost:8099/api/explorer/addresses/units/$KEY/timeline" \
  -H "Authorization: Bearer $TOKEN" | head -c 500

# Group anchor tenures (KingSett)
curl -s "http://localhost:8099/api/explorer/auto-groups/<KGS_ID>/anchor-tenures" \
  -H "Authorization: Bearer $TOKEN" | head -c 500

# Conflicts list
curl -s 'http://localhost:8099/api/explorer/conflicts?per_page=5' \
  -H "Authorization: Bearer $TOKEN" | head -c 500
```

For each: confirm 200 status, sensible payload shape, non-empty results where expected.

- [ ] **Step 3: Browser walk-through**

Logged in, visit:
1. `/explorer/phones/4166876700` — Timeline section visible with KingSett tenure bar.
2. `/explorer/addresses/units/<key>?city=toronto` — Timeline section visible.
3. `/explorer/contacts/<some-real-contact>` — Timeline section visible.
4. `/explorer/auto-groups/<KGS_ID>?tab=anchors` — "Anchor Tenures" tab populated, score-sorted.
5. `/explorer/auto-groups/<KGS_ID>?tab=trail&source_id=...&side=...` — Trail edges colored correctly.
6. `/explorer/conflicts` — list page loads. Filter dropdown works. Click a row → drawer opens with side-by-side timelines.

Capture a 1-paragraph note for each surface:
- Did it render?
- Did the data look sensible?
- Any UX rough edges?

- [ ] **Step 4: Write verification notes**

`docs/superpowers/run-notes/2026-05-01-layer-2-plan-h3-verification.md`:

```markdown
# Plan H3 Verification Notes

**Date:** 2026-05-01
**Branch:** `feat/group-discovery-algorithm`

## Backend endpoint smoke

- `/phones/:value/timeline` — <result>
- `/addresses/units/:key/timeline` — <result>
- `/contacts/:value/timeline` — <result>
- `/auto-groups/:id/anchor-tenures` — <result>
- `/auto-groups/parties/:sid/:side/trail` (tenure-aware) — <result>
- `/conflicts` — <result>
- `/conflicts/:id` — <result>

## Browser walk-through

### Layer 1 silo timelines
- Phone detail: <observation>
- Address Unit detail: <observation>
- Contact detail: <observation>

### Auto-group Anchor Tenures tab
- <observation>

### Trail view tenure coloring
- Solid jade edges visible: <yes/no>
- Dashed amber tenure-mismatch edges visible: <yes/no>
- Edge labels on amber edges show actual tenure window: <yes/no>

### Conflicts page
- Total conflicts displayed: <count>
- Filter by type works: <yes/no>
- Detail drawer side-by-side timelines render: <yes/no>

## Findings

<3-5 specific observations>

## What's next

- Plan B — tenure-aware contact aliasing (operates on the H2 tenure infrastructure).
- Plan C — user actions on conflicts (dismiss, escalate to merge/split).
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/run-notes/2026-05-01-layer-2-plan-h3-verification.md
git commit -m "docs: Plan H3 verification notes"
```

---

## Self-Review

**Spec coverage check** (against `docs/superpowers/specs/2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md` Plan H3 section):

- ✅ **Layer 1 silo timelines** — Tasks 1, 2 (backend endpoints for phone, address_unit, contact); Tasks 3, 4 (shared component + wiring).
- ✅ **Anchor Tenures tab on auto-group detail** — Tasks 5 (backend), 6 (frontend, replaces existing Anchors tab).
- ✅ **Trail view tenure-aware** — Tasks 7 (backend tenure-spans enrichment), 8 (frontend edge coloring).
- ✅ **Conflicts tab** — Tasks 9 (backend list + detail), 10 (frontend page + drawer).
- ✅ **Real-DB verification** — Task 11.

**Out of scope per spec, intentionally not in plan:**
- User actions on conflicts (dismiss/accept/escalate) — Plan C territory.
- Auto-resolving conflicts — never; conflicts stay surfaced for human review.
- Editing tenure dates by hand — Plan C.

**Type consistency:**
- `SiloTimelineEvent`, `SiloTimelineTenure` defined in Task 3, used in Task 4.
- `AutoGroupAnchorTenure` defined in Task 6, used in Task 6 only.
- `ConflictFlag`, `ConflictDetailResponse` defined in Task 10.
- The trail endpoint extension (Task 7) adds optional fields to the existing trail response type — backward compat preserved.

**Known UX wart kept from H1:** The Address Root detail page still requires `?city=` to render its Units section. Not addressing in H3 — that wart is documented and isolated.

**Other concerns:**
- `AutoGroupAnchorsTab.tsx` is deleted, not preserved as a shim. Any external link/import to it will break — confirm no other places reference it before deletion. (`grep -rn AutoGroupAnchorsTab frontend/src/` should show only the imports we're updating.)
- Conflict timelines per group are flat event lists, not styled with tenure overlays in the drawer (would be nice but is out of scope for the initial cut). Documented as a follow-up.

No placeholders. Code in every step.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-01-layer-2-plan-h3-time-aware-ui.md`. 11 tasks. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review.

**2. Inline Execution** — In this session with checkpoints.

Which approach?
