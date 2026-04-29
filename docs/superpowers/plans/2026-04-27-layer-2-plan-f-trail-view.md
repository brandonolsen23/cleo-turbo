# Layer 2 Plan F — Trail View Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` (Plan F section).

**Goal:** Replace the Trail tab placeholder on the auto-group detail page with a single-party evidence visualization. Pick a party (one side of one transaction), see the threads of shared anchors connecting it to its group(s) — with explicit conflict highlighting when threads point at multiple groups.

**Architecture:** New backend endpoint `/parties/:source_id/:side/trail` returns the structured threads (one per anchor on the party + the groups each anchor belongs to). Frontend uses React Flow (a new dep) for a horizontal node-edge layout: party on the left, anchor threads in the middle, groups on the right. URL-driven via `?source_id=...&side=...` on the existing detail page's `?tab=trail`. Entry point from the Parties tab adds a per-row Trail icon.

**Tech Stack:** Python 3.12, FastAPI, SQLite, React 19, Radix UI Themes, **@xyflow/react** (new), TypeScript, react-router-dom.

---

## Glossary (locked from the spec — used strictly)

| Term | Meaning |
|---|---|
| **Party** | One side of one transaction. Identified by `(source_id, side)`. |
| **Trail** | The visualization showing how a party's anchors connect it to one or more auto_groups. |
| **Thread** | One anchor on a party + the groups that anchor belongs to. A party with phone, address, and contact anchors has up to 3 threads. |
| **Anchor** | Phone, address (root or base), or contact_fingerprint. |
| **Primary group** | The single auto_group this party is recorded as a member of (in `auto_group_members`), if any. |
| **All groups** | The union of distinct auto_groups touched by any thread — `primary_group` plus any other groups that show up via shared anchors. When `len > 1`, that's the conflict signal. |
| **Unattached anchor** | A thread whose anchor isn't registered to any auto_group. Renders as a terminating thread to a stub node. |

No new terms beyond these. If new vocabulary is needed mid-implementation, surface as a question rather than inventing.

---

## File Structure

**Backend:**
- Modify: `cleo/web/routes/explorer.py` — add `/parties/:source_id/:side/trail` endpoint.
- Modify: `tests/test_routes_explorer.py` — fixture extensions + tests.

**Frontend (new files):**
- `frontend/src/components/explorer/AutoGroupTrailTab.tsx` — outer tab body. Reads `source_id` and `side` from URL search params; renders empty state when missing, fetches trail and mounts `AutoGroupTrail` when present.
- `frontend/src/components/explorer/AutoGroupTrail.tsx` — React Flow visualization. Pure rendering of trail data (no fetch).

**Frontend (modified):**
- `frontend/package.json` — add `@xyflow/react`.
- `frontend/src/types/index.ts` — add `AutoGroupTrailResponse` and supporting types.
- `frontend/src/components/explorer/AutoGroupPartiesTab.tsx` — add per-row Trail icon link.
- `frontend/src/pages/ExplorerAutoGroupDetail.tsx` — replace the Trail tab placeholder with `<AutoGroupTrailTab />`.

---

## Pre-flight context

**The Trail tab gets two query params:**
- `?tab=trail` — already part of the existing tab shell from Plan D.
- `?source_id=<sid>&side=buyer|seller` — adds the specific party to render.

When `source_id` and `side` are both present, the tab fetches the trail and renders it. When missing, the tab renders an empty state ("Pick a party from the Parties tab to see its evidence trail").

**Trail icon in Parties tab:** Each row in the existing Parties tab gets a small "Trail" icon (e.g., the Phosphor `<TreeStructure />` icon, already used elsewhere in the app). Clicking it navigates to the same detail page with `?tab=trail&source_id=...&side=...`. This does NOT replace the existing row click → SourceViewerDrawer behavior — both are present, the Trail icon is a separate click target inside its own cell so it doesn't trigger row click.

**React Flow integration:** `@xyflow/react` is the modern package. Layout is custom (horizontal): party node positioned at fixed left coords, group nodes stacked on the right. Anchor threads are labeled edges with custom rendering for conflict highlighting.

**Endpoint URL design:** The trail isn't scoped by auto_group_id because a party can touch multiple groups. So the route is `/api/explorer/auto-groups/parties/:source_id/:side/trail` — not nested under `/auto-groups/:id/...`.

---

## Tasks

### Task 1: Backend — `/parties/:source_id/:side/trail` endpoint

Returns the structured trail data for one party.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture**

The existing fixture has AGRP_00001 (kingsett, confirmed) seeded with 3 anchors and party RT1 (buyer) as a member. To exercise:
- A clean trail (RT1 → AGRP_00001 via 3 anchors) — already supported.
- A multi-group conflict — need to seed a SECOND group whose anchors overlap with RT1's anchors. Add:

In `_seeded_db`, after the existing AGRP_00002 insert (find `INSERT INTO auto_groups ... 'AGRP_00002'` near the existing fixture seed):

```python
# AGRP_00004: a confirmed group whose phone anchor overlaps with RT1's phone (4166876700).
# This is a deliberately constructed conflict — RT1 is registered as a member of AGRP_00001
# (kingsett), but its phone anchor would also point at AGRP_00004 (a different stem).
conn.execute("""
    INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                             n_anchors, n_members, discovered_at)
    VALUES ('AGRP_00004', 'rivalstem', 'rivalstem group', 'confirmed', 0.85, 1, 0, '2026-04-27')
""")
conn.execute(
    "INSERT INTO auto_group_anchors VALUES ('AGRP_00004', 'phone', '4166876700', 1.5)"
)
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_trail_returns_party_data(client):
    """RT1 (buyer) is a member of AGRP_00001 (kingsett)."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    assert resp.status_code == 200
    body = resp.json()
    assert body['party']['source_id'] == 'RT1'
    assert body['party']['side'] == 'buyer'
    # Party fields populated from the fixture.
    assert body['party']['phone'] == '4166876700'
    assert body['party']['contact'] == 'rob kumer'
    # brand_phrase should be one of the kingsett-mapped phrases.
    assert 'kingsett' in (body['party']['brand_phrase'] or '').lower()


def test_trail_threads_one_per_anchor(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    # RT1 has phone + contact + address_root + address_base — 4 anchor identities.
    # The trail should produce one thread per non-empty anchor on the party.
    thread_anchors = {(t['anchor_type'], t['anchor_value']) for t in body['threads']}
    assert ('phone', '4166876700') in thread_anchors
    assert ('contact', 'rob kumer') in thread_anchors
    # address_root and address_base both fire because both anchors exist on the party.
    assert ('address_root', '66|wellington') in thread_anchors


def test_trail_thread_groups_for_phone_lists_both_groups(client):
    """The phone 4166876700 is an anchor of BOTH AGRP_00001 (kingsett) and AGRP_00004 (rivalstem).
    The phone thread should list both groups — that's the conflict signal."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    phone_thread = next(t for t in body['threads'] if t['anchor_type'] == 'phone')
    group_ids = {g['auto_group_id'] for g in phone_thread['groups']}
    assert 'AGRP_00001' in group_ids
    assert 'AGRP_00004' in group_ids


def test_trail_returns_primary_group(client):
    """RT1 (buyer) is a member of AGRP_00001 — that's the primary."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    assert body['primary_group'] is not None
    assert body['primary_group']['auto_group_id'] == 'AGRP_00001'
    assert body['primary_group']['stem'] == 'kingsett'


def test_trail_returns_all_groups_for_conflict_visualization(client):
    """all_groups should include every group reachable via any thread — for rendering right-side nodes."""
    resp = client.get('/api/explorer/auto-groups/parties/RT1/buyer/trail')
    body = resp.json()
    all_ids = {g['auto_group_id'] for g in body['all_groups']}
    assert 'AGRP_00001' in all_ids
    assert 'AGRP_00004' in all_ids


def test_trail_404_on_unknown_party(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT-NOPE/buyer/trail')
    assert resp.status_code == 404


def test_trail_404_on_invalid_side(client):
    resp = client.get('/api/explorer/auto-groups/parties/RT1/middleman/trail')
    assert resp.status_code == 400


def test_trail_with_no_primary_group(client):
    """A party that exists in party_fingerprints but isn't a member of any auto_group.
    Should return 200 with primary_group=None and threads still populated for any
    anchors that match registered groups."""
    # The fixture's RT-COSTEM party (added in Plan D Task 1) is at phone 4166876700
    # but is NOT in auto_group_members.
    resp = client.get('/api/explorer/auto-groups/parties/RT-COSTEM/buyer/trail')
    assert resp.status_code == 200
    body = resp.json()
    assert body['primary_group'] is None
    # Should still have a thread for the phone anchor since 4166876700 is a registered anchor.
    thread_types = {t['anchor_type'] for t in body['threads']}
    assert 'phone' in thread_types
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k trail
# Expected: 8 failures
```

- [ ] **Step 4: Implement the endpoint**

Insert into `cleo/web/routes/explorer.py` after the `auto_groups_tuning_missed_stems` endpoint:

```python
# ─────────────────────────────────────────────────────────────
# Single-party evidence trail (Plan F)
# ─────────────────────────────────────────────────────────────

@router.get('/auto-groups/parties/{source_id}/{side}/trail')
def auto_group_party_trail(
    source_id: str, side: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    """For a single party (source_id + side), return:
      - party: the party's data (phone, contact, address, brand_phrase, sale info)
      - threads: one entry per anchor on the party, with the groups that anchor
        is registered to (may be 0, 1, or many)
      - primary_group: the auto_group this party is recorded as a member of (or null)
      - all_groups: union of distinct groups across all threads (for rendering)

    Returns 400 on invalid side, 404 on unknown party.
    """
    if side not in ('buyer', 'seller'):
        raise HTTPException(status_code=400, detail=f'Invalid side: {side!r}')

    # Fetch the party.
    party = db.execute(
        """SELECT pf.source_id, pf.side, pf.phone, pf.contact_fingerprint AS contact,
                  pf.street_number, pf.street_name, pf.street_suffix,
                  pf.suite_type, pf.suite_number, pf.postal, pf.sale_date,
                  t.sale_price,
                  (SELECT pa.atom_value FROM party_atoms pa
                    WHERE pa.source_id = pf.source_id AND pa.side = pf.side
                      AND pa.atom_type = 'brand_phrase'
                    ORDER BY pa.id ASC LIMIT 1) AS brand_phrase
           FROM party_fingerprints pf
           LEFT JOIN transactions t ON t.source_id = pf.source_id
           WHERE pf.source_id = ? AND pf.side = ?""",
        (source_id, side),
    ).fetchone()
    if party is None:
        raise HTTPException(
            status_code=404,
            detail=f'Unknown party: source_id={source_id!r}, side={side!r}',
        )

    # Build the list of (anchor_type, anchor_value) pairs that exist on this party.
    p = dict(party)
    party_anchors: list[tuple[str, str]] = []
    if p['phone']:
        party_anchors.append(('phone', p['phone']))
    if p['contact']:
        party_anchors.append(('contact', p['contact']))
    if p['street_number'] and p['street_name']:
        party_anchors.append(('address_root', f"{p['street_number']}|{p['street_name']}"))
        party_anchors.append((
            'address_base',
            f"{p['street_number']}|{p['street_name']}|{p['street_suffix'] or ''}",
        ))

    # For each anchor, look up groups registered to it.
    threads = []
    for anchor_type, anchor_value in party_anchors:
        rows = db.execute(
            """SELECT aga.auto_group_id, ag.canonical_stem, ag.tier, ag.display_name,
                      aga.score AS score_in_group
               FROM auto_group_anchors aga
               JOIN auto_groups ag ON ag.auto_group_id = aga.auto_group_id
               WHERE aga.anchor_type = ? AND aga.anchor_value = ?
               ORDER BY aga.score DESC""",
            (anchor_type, anchor_value),
        ).fetchall()
        threads.append({
            'anchor_type': anchor_type,
            'anchor_value': anchor_value,
            'groups': [dict(r) for r in rows],
        })

    # Primary group: this party's auto_group_members entry (if any).
    primary_row = db.execute(
        """SELECT agm.auto_group_id, agm.match_score, ag.canonical_stem,
                  ag.display_name, ag.tier
           FROM auto_group_members agm
           JOIN auto_groups ag ON ag.auto_group_id = agm.auto_group_id
           WHERE agm.source_id = ? AND agm.side = ? AND agm.member_type = 'party_side'""",
        (source_id, side),
    ).fetchone()
    primary_group = dict(primary_row) if primary_row else None

    # All groups: union of distinct groups across all threads + primary group.
    seen: dict[str, dict] = {}
    if primary_group:
        seen[primary_group['auto_group_id']] = {
            'auto_group_id': primary_group['auto_group_id'],
            'canonical_stem': primary_group['canonical_stem'],
            'display_name': primary_group['display_name'],
            'tier': primary_group['tier'],
        }
    for t in threads:
        for g in t['groups']:
            if g['auto_group_id'] not in seen:
                seen[g['auto_group_id']] = {
                    'auto_group_id': g['auto_group_id'],
                    'canonical_stem': g['canonical_stem'],
                    'display_name': g['display_name'],
                    'tier': g['tier'],
                }
    all_groups = list(seen.values())

    return {
        'party': {
            'source_id': p['source_id'],
            'side': p['side'],
            'brand_phrase': p['brand_phrase'],
            'sale_date': p['sale_date'],
            'sale_price': p['sale_price'],
            'phone': p['phone'],
            'contact': p['contact'],
            'street_number': p['street_number'],
            'street_name': p['street_name'],
            'street_suffix': p['street_suffix'],
            'suite_type': p['suite_type'],
            'suite_number': p['suite_number'],
            'postal': p['postal'],
        },
        'threads': threads,
        'primary_group': primary_group,
        'all_groups': all_groups,
    }
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k trail
# Expected: 8 passed
```

- [ ] **Step 6: Update the docstring**

Add to the endpoint list at the top of the file:

```
GET /api/explorer/auto-groups/parties/:source_id/:side/trail  — single-party evidence trail
```

- [ ] **Step 7: Smoke test against real DB**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps
import sqlite3
app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

conn = sqlite3.connect('data/cleo.db')
# Pick a party from a Confirmed group
gid = conn.execute(
    \"SELECT auto_group_id FROM auto_groups WHERE tier='confirmed' ORDER BY n_members DESC LIMIT 1\"
).fetchone()[0]
party = conn.execute(
    'SELECT source_id, side FROM auto_group_members WHERE auto_group_id=? AND member_type=\"party_side\" LIMIT 1',
    (gid,),
).fetchone()
sid, side = party
print(f'Smoke: group={gid}, party=({sid}, {side})')

r = client.get(f'/api/explorer/auto-groups/parties/{sid}/{side}/trail')
print(f'  status={r.status_code}')
b = r.json()
print(f'  party.brand_phrase={b[\"party\"][\"brand_phrase\"]}')
print(f'  party.phone={b[\"party\"][\"phone\"]}')
print(f'  threads: {len(b[\"threads\"])} ({[t[\"anchor_type\"] for t in b[\"threads\"]]})')
print(f'  primary_group: {b[\"primary_group\"][\"display_name\"] if b[\"primary_group\"] else None}')
print(f'  all_groups: {[g[\"display_name\"] for g in b[\"all_groups\"]]}')
" 2>&1 | tail -10
```

Expected: 200 status, 3-4 threads (phone + contact + address_root + address_base), primary_group is the kingsett (or whatever) group, all_groups likely 1 entry (no conflict for a Confirmed group's own member).

- [ ] **Step 8: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /parties/:source_id/:side/trail endpoint"
```

---

### Task 2: Frontend — install React Flow + types

Add the dep and the types for the trail response. No UI yet.

**Files:**
- Modify: `frontend/package.json` (via npm install)
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Install React Flow**

```bash
cd frontend && npm install @xyflow/react
```

This adds `@xyflow/react` as a dep and updates `package.json` + `package-lock.json`. Verify install:

```bash
grep -E "\"@xyflow/react\"" frontend/package.json
# Expected: a line with the package + version
```

- [ ] **Step 2: Add types to `frontend/src/types/index.ts`**

Find the existing Plan G tuning types section. Append new Plan F trail types after it:

```typescript
// ============================================================
// Explorer — Auto-Groups Trail (Plan F)
// ============================================================

export interface AutoGroupTrailParty {
  source_id: string;
  side: 'buyer' | 'seller';
  brand_phrase: string | null;
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
}

export interface AutoGroupTrailThreadGroup {
  auto_group_id: string;
  canonical_stem: string;
  display_name: string;
  tier: 'confirmed' | 'probable' | 'candidate';
  score_in_group: number;
}

export interface AutoGroupTrailThread {
  anchor_type: 'phone' | 'address_root' | 'address_base' | 'contact';
  anchor_value: string;
  groups: AutoGroupTrailThreadGroup[];
}

export interface AutoGroupTrailPrimary {
  auto_group_id: string;
  canonical_stem: string;
  display_name: string;
  tier: 'confirmed' | 'probable' | 'candidate';
  match_score: number;
}

export interface AutoGroupTrailGroupSummary {
  auto_group_id: string;
  canonical_stem: string;
  display_name: string;
  tier: 'confirmed' | 'probable' | 'candidate';
}

export interface AutoGroupTrailResponse {
  party: AutoGroupTrailParty;
  threads: AutoGroupTrailThread[];
  primary_group: AutoGroupTrailPrimary | null;
  all_groups: AutoGroupTrailGroupSummary[];
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/index.ts
git commit -m "feat(layer2): add @xyflow/react + Plan F trail types"
```

---

### Task 3: Frontend — Trail visualization component

The pure rendering component — accepts trail data, renders the React Flow graph. No data fetching here.

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupTrail.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useMemo } from "react";
import { ReactFlow, Background, Controls, MarkerType, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Heading, Text, Badge } from "@radix-ui/themes";
import type {
  AutoGroupTrailResponse,
  AutoGroupTrailThread,
} from "../../types";


function partyLabel(p: AutoGroupTrailResponse['party']): string {
  const addr = [p.street_number, p.street_name, p.street_suffix].filter(Boolean).join(" ");
  const lines = [
    p.brand_phrase || `${p.source_id} (${p.side})`,
    p.sale_date ? p.sale_date.slice(0, 10) : null,
    p.sale_price ? `$${(p.sale_price / 1_000_000).toFixed(2)}M` : null,
    addr || null,
    p.contact ? `contact: ${p.contact}` : null,
    p.phone ? `phone: ${p.phone}` : null,
  ].filter(Boolean);
  return lines.join("\n");
}

function threadEdgeColor(thread: AutoGroupTrailThread, primaryGroupId: string | null): string {
  // Conflict: anchor points at >1 group, or points at a group that's NOT primary.
  if (thread.groups.length > 1) return "var(--tomato-9)";
  if (thread.groups.length === 0) return "var(--gray-9)";
  if (primaryGroupId && thread.groups[0].auto_group_id !== primaryGroupId) {
    return "var(--amber-9)";
  }
  return "var(--jade-9)";
}

const tierColor: Record<string, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable: "amber",
  candidate: "gray",
};


export default function AutoGroupTrail({ trail }: { trail: AutoGroupTrailResponse }) {
  const { nodes, edges, hasConflict, hasUnattached } = useMemo(() => {
    const partyId = `party:${trail.party.source_id}:${trail.party.side}`;
    const primaryId = trail.primary_group?.auto_group_id ?? null;

    // Layout: party node on the left at x=0, group nodes stacked on the right at x=600.
    const nodes: Node[] = [{
      id: partyId,
      type: 'default',
      position: { x: 0, y: 0 },
      data: { label: partyLabel(trail.party) },
      style: {
        background: 'var(--gray-2)',
        border: '1px solid var(--gray-6)',
        padding: 10,
        whiteSpace: 'pre-wrap',
        fontSize: 12,
        width: 240,
      },
    }];

    const groupSpacingY = 110;
    const groupCount = trail.all_groups.length;
    const startY = -((groupCount - 1) * groupSpacingY) / 2;
    trail.all_groups.forEach((g, i) => {
      nodes.push({
        id: `group:${g.auto_group_id}`,
        type: 'default',
        position: { x: 600, y: startY + i * groupSpacingY },
        data: {
          label: `${g.display_name}\n[${g.tier}] ${g.canonical_stem}`,
        },
        style: {
          background: g.auto_group_id === primaryId ? 'var(--jade-3)' : 'var(--gray-3)',
          border: `1px solid ${g.auto_group_id === primaryId ? 'var(--jade-9)' : 'var(--gray-6)'}`,
          padding: 10,
          whiteSpace: 'pre-wrap',
          fontSize: 12,
          width: 220,
          fontWeight: g.auto_group_id === primaryId ? 600 : 400,
        },
      });
    });

    // One edge per (thread, group) pair. Color encodes conflict/unattached state.
    const edges: Edge[] = [];
    let unattached = false;
    let conflict = false;

    trail.threads.forEach((thread, threadIdx) => {
      if (thread.groups.length === 0) {
        unattached = true;
        // Add a stub "(unattached)" node + edge so the user can see the dead end.
        const stubId = `unattached:${thread.anchor_type}:${threadIdx}`;
        nodes.push({
          id: stubId,
          type: 'default',
          position: { x: 600, y: startY + (groupCount + threadIdx) * groupSpacingY },
          data: { label: '(no group)' },
          style: {
            background: 'transparent',
            border: '1px dashed var(--gray-9)',
            padding: 6,
            fontSize: 11,
            color: 'var(--gray-9)',
            width: 100,
          },
        });
        edges.push({
          id: `edge:${threadIdx}:unattached`,
          source: partyId,
          target: stubId,
          label: `${thread.anchor_type}: ${thread.anchor_value}`,
          labelStyle: { fontSize: 10, fill: 'var(--gray-11)' },
          style: { stroke: 'var(--gray-9)', strokeDasharray: '4 4' },
          markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--gray-9)' },
        });
        return;
      }
      if (thread.groups.length > 1) conflict = true;
      const color = threadEdgeColor(thread, primaryId);
      thread.groups.forEach((g, gIdx) => {
        edges.push({
          id: `edge:${threadIdx}:${gIdx}`,
          source: partyId,
          target: `group:${g.auto_group_id}`,
          label: `${thread.anchor_type}: ${thread.anchor_value}`,
          labelStyle: { fontSize: 10, fill: color },
          style: { stroke: color, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color },
        });
      });
    });

    return { nodes, edges, hasConflict: conflict, hasUnattached: unattached };
  }, [trail]);

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Evidence trail</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {trail.threads.length} threads, {trail.all_groups.length} groups touched.
        </Text>
        {trail.primary_group && (
          <Badge color={tierColor[trail.primary_group.tier]}>
            primary: {trail.primary_group.display_name}
          </Badge>
        )}
        {hasConflict && (
          <Badge color="tomato">conflict</Badge>
        )}
        {hasUnattached && (
          <Badge color="gray">unattached anchors</Badge>
        )}
      </div>

      <div style={{ width: "100%", height: 480, background: "var(--gray-2)" }}>
        <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false}
                   panOnScroll proOptions={{ hideAttribution: true }}>
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupTrail.tsx
git commit -m "feat(layer2): AutoGroupTrail React Flow visualization component"
```

---

### Task 4: Frontend — Trail tab body component

The outer tab content. Reads `?source_id=&side=` from the URL; renders empty state without them, or fetches trail and mounts `<AutoGroupTrail />` with them.

**Files:**
- Create: `frontend/src/components/explorer/AutoGroupTrailTab.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupTrailResponse } from "../../types";
import AutoGroupTrail from "./AutoGroupTrail";


export default function AutoGroupTrailTab() {
  const [searchParams] = useSearchParams();
  const sourceId = searchParams.get("source_id");
  const side = searchParams.get("side");
  const [trail, setTrail] = useState<AutoGroupTrailResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId || !side) {
      setTrail(null);
      setErr(null);
      return;
    }
    setErr(null);
    fetchApi<AutoGroupTrailResponse>(
      `/explorer/auto-groups/parties/${encodeURIComponent(sourceId)}/${encodeURIComponent(side)}/trail`,
    ).then(setTrail).catch((e) => setErr(String(e)));
  }, [sourceId, side]);

  if (!sourceId || !side) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-8"
           style={{ background: "var(--gray-2)" }}>
        <Heading size="3">Evidence trail</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Pick a party from the Parties tab to see its evidence trail. Click the
          <span className="font-mono">  Trail  </span>
          link on a party row.
        </Text>
      </div>
    );
  }

  if (err) {
    return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  }

  if (!trail) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading trail…</Text>
      </div>
    );
  }

  return <AutoGroupTrail trail={trail} />;
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupTrailTab.tsx
git commit -m "feat(layer2): AutoGroupTrailTab — empty state + trail fetch + render"
```

---

### Task 5: Frontend — wire Trail tab content into the detail page

Replace the existing Trail placeholder with the new component.

**Files:**
- Modify: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`

- [ ] **Step 1: Add the import**

In `frontend/src/pages/ExplorerAutoGroupDetail.tsx`, find the existing imports for `AutoGroupTabPlaceholder` and the other tab components. Add:

```typescript
import AutoGroupTrailTab from "../components/explorer/AutoGroupTrailTab";
```

- [ ] **Step 2: Replace the Trail placeholder**

Find the `<AutoGroupTabs>` body. The current `trail` entry is:

```typescript
trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
```

Replace with:

```typescript
trail:    <AutoGroupTrailTab />,
```

The new component reads its own search params, so no props needed from the parent.

- [ ] **Step 3: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
```

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=trail` (no source_id). Verify:
- Trail tab renders the empty-state card ("Pick a party from the Parties tab to see its evidence trail").

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=trail&source_id=RT100502&side=seller` (with a real party from KingSett). Verify:
- React Flow renders with party node on the left, group node(s) on the right, threads as labeled edges.
- For a Confirmed group's clean party: 1 group on the right, all threads jade-colored.

(`RT100502` is a placeholder; substitute any real source_id from the parties list.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExplorerAutoGroupDetail.tsx
git commit -m "feat(layer2): wire AutoGroupTrailTab into detail page"
```

---

### Task 6: Frontend — Trail icon in the Parties tab

Each row in the Parties tab gets a small Trail link. Clicking it navigates to the same detail page with `?tab=trail&source_id=...&side=...`. Does NOT replace the existing row click → SourceViewerDrawer behavior — the Trail link sits in its own table cell that intercepts the click.

**Files:**
- Modify: `frontend/src/components/explorer/AutoGroupPartiesTab.tsx`

- [ ] **Step 1: Read the current file**

Locate the Parties tab table — specifically the `<tbody>` row map that renders each party. Each row currently has 9 `<td>` cells. We're adding one more on the right.

Imports at the top: add `Link` from react-router-dom (likely already imported):

```typescript
import { Link, useParams } from "react-router-dom";
```

(If `useParams` is already imported, just add `Link`. If both are already imported, no change.)

We need the auto_group_id from the URL to construct the Trail link target. Find the existing `useSourceViewer()` hook or `props` that flows the auto_group_id to this component. The current Parties tab takes `autoGroupId: string` as a prop — use that.

- [ ] **Step 2: Add the column header**

Find the `<thead>` row. After the existing "score" column (or whichever is the rightmost), add:

```typescript
<th className="text-left p-2 font-medium">trail</th>
```

- [ ] **Step 3: Add the per-row Trail cell**

Find the row template `data?.results.map((p) => ( <tr ...>...</tr> ))`. The existing `onClick={() => openSource(p.source_id)}` opens the SourceViewerDrawer. We add ONE more `<td>` at the end. The cell's content is a `<Link>` whose own click handler calls `e.stopPropagation()` so the row click doesn't also fire.

```typescript
<td className="p-2"
    onClick={(e) => e.stopPropagation()}>
  <Link to={`/explorer/auto-groups/${encodeURIComponent(autoGroupId)}?tab=trail&source_id=${encodeURIComponent(p.source_id)}&side=${encodeURIComponent(p.side)}`}
        className="no-underline"
        style={{ color: "var(--accent-11)" }}>
    Trail →
  </Link>
</td>
```

(The `e.stopPropagation()` on the cell's onClick prevents the row click — `openSource(p.source_id)` — from firing when the Trail link is the actual target.)

- [ ] **Step 4: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
```

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=parties`. Verify:
- New "trail" column visible on the right.
- Each row shows "Trail →" link.
- Clicking the Trail link navigates to the Trail tab with the right source_id + side query params (URL changes, Trail tab activates, party gets fetched + visualized).
- Row body click STILL opens the SourceViewerDrawer (Trail link doesn't override that).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/explorer/AutoGroupPartiesTab.tsx
git commit -m "feat(layer2): Trail link on each row in Parties tab"
```

---

### Task 7: Real-DB verification

End-to-end smoke + capture findings.

**Files:** none (verification only)

- [ ] **Step 1: Backend smoke against multiple party types**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps
import sqlite3

app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

conn = sqlite3.connect('data/cleo.db')

# Pick 5 random parties from various groups (Confirmed, Probable, Candidate)
parties = conn.execute(\"\"\"
    SELECT agm.source_id, agm.side, ag.canonical_stem, ag.tier
    FROM auto_group_members agm
    JOIN auto_groups ag ON ag.auto_group_id = agm.auto_group_id
    WHERE agm.member_type = 'party_side'
    GROUP BY ag.tier
    ORDER BY RANDOM()
    LIMIT 5
\"\"\").fetchall()

for sid, side, stem, tier in parties:
    r = client.get(f'/api/explorer/auto-groups/parties/{sid}/{side}/trail')
    body = r.json()
    print(f'[{tier:9s}] {sid}({side}) stem={stem}')
    print(f'  threads={len(body[\"threads\"])}, all_groups={len(body[\"all_groups\"])}')
    if len(body['all_groups']) > 1:
        print(f'  ⚠ CONFLICT: groups={[g[\"display_name\"] for g in body[\"all_groups\"]]}')
" 2>&1 | tail -20
```

Expected: each party returns a trail with threads. Most are clean (1 group in all_groups). Some may show conflicts (multiple groups) — those are the interesting findings.

- [ ] **Step 2: Find a real conflict if one exists**

```bash
python3 -c "
from fastapi.testclient import TestClient
from cleo.web.app import app
from cleo.web import deps
import sqlite3

app.dependency_overrides[deps.get_current_user] = lambda: {'email': 'test'}
client = TestClient(app)

conn = sqlite3.connect('data/cleo.db')

# Find anchors that appear in MULTIPLE groups — those are the natural conflict candidates.
shared_anchors = conn.execute(\"\"\"
    SELECT anchor_type, anchor_value, COUNT(DISTINCT auto_group_id) AS n_groups
    FROM auto_group_anchors
    GROUP BY anchor_type, anchor_value
    HAVING n_groups >= 2
    ORDER BY n_groups DESC
    LIMIT 5
\"\"\").fetchall()

print('Top shared anchors:')
for at, av, n in shared_anchors:
    print(f'  {at}={av}: shared by {n} groups')

# Pick one and find a party at that anchor
if shared_anchors:
    at, av, _ = shared_anchors[0]
    if at == 'phone':
        clause = 'pf.phone = ?'
    elif at == 'contact':
        clause = 'pf.contact_fingerprint = ?'
    elif at == 'address_root':
        clause = \"(pf.street_number || '|' || pf.street_name) = ?\"
    else:
        clause = \"(pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = ?\"
    party = conn.execute(
        f'SELECT source_id, side FROM party_fingerprints pf WHERE {clause} LIMIT 1',
        (av,),
    ).fetchone()
    if party:
        sid, side = party
        r = client.get(f'/api/explorer/auto-groups/parties/{sid}/{side}/trail')
        body = r.json()
        print(f'\\nSample party at conflict anchor: {sid} ({side})')
        print(f'  primary_group: {body[\"primary_group\"][\"display_name\"] if body[\"primary_group\"] else None}')
        print(f'  all_groups: {[g[\"display_name\"] for g in body[\"all_groups\"]]}')
        for t in body['threads']:
            print(f'    {t[\"anchor_type\"]}={t[\"anchor_value\"]}: {len(t[\"groups\"])} group(s)')
" 2>&1 | tail -15
```

Expected: a real party whose phone or contact is shared across multiple groups. Capture the conflict for the run notes.

- [ ] **Step 3: Manual click-through (your turn)**

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=parties` (KingSett). Verify:
- Each row has "Trail →" link.
- Click on a Trail link for any party.
- The detail page switches to the Trail tab.
- React Flow renders with party-left, group-right layout.
- Threads render as labeled edges.
- For a clean Confirmed-group member: 1 group node on the right, jade-colored edges, primary badge.
- If you find a party with shared anchors (e.g., a contact at multiple groups): multiple group nodes, conflict badge, tomato/amber edges to non-primary groups.
- Pan/zoom works.
- Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=trail` (no source_id). Should show empty state.

- [ ] **Step 4: Capture verification notes**

Write to `docs/superpowers/run-notes/2026-04-27-layer-2-plan-f-verification.md`:

```markdown
# Plan F Verification Notes

**Date:** 2026-04-27

## Backend smoke (programmatic)
- 5 random-tier parties: trails returned, thread counts <fill in from output>
- Top shared anchors: <list>
- Sample conflict trail: <party id, primary group, all_groups>

## Manual click-through
- Empty state (no source_id): pass / fail
- Clean Confirmed party trail: pass / fail
- Conflict trail rendering: pass / fail (and what the conflict was)
- Trail link in Parties tab: pass / fail
- Pan/zoom: pass / fail

## Findings
- <any surprising conflicts visible>
- <any missing data — e.g., parties whose threads point at no groups>
- <anything that suggests a tenure or JV signal that Plan B should handle>
```

- [ ] **Step 5: Commit verification notes**

```bash
git add docs/superpowers/run-notes/2026-04-27-layer-2-plan-f-verification.md
git commit -m "docs: Plan F verification notes"
```

---

## Self-Review

Spec coverage check (against `docs/superpowers/specs/2026-04-27-layer-2-verification-ui-design.md` Plan F section):

- ✅ **Backend `/parties/:source_id/:side/trail` endpoint** with party + threads + primary_group + all_groups response shape — Task 1.
- ✅ **8 tests covering** party data, thread shape, conflict (phone shared across 2 groups), primary_group, all_groups union, 404 on unknown party, 400 on invalid side, no-primary-group case (party not in auto_group_members) — Task 1.
- ✅ **Frontend Trail tab body** with empty state when no `source_id`/`side` — Task 4.
- ✅ **React Flow visualization** with party-left, groups-right layout — Task 3.
- ✅ **Conflict highlighting** (tomato edges when thread has >1 group; amber edges when thread points at a non-primary group; jade for primary; gray dashed for unattached) — Task 3.
- ✅ **Trail link on each row of the Parties tab** — Task 6.
- ✅ **Glossary used strictly** — every task uses "party," "thread," "anchor," "primary group" per spec.

Type consistency check:
- `AutoGroupTrailResponse` defined in Task 2; consumed in Tasks 3 (rendering) and 4 (fetch).
- `AutoGroupTrailThread.groups` is `AutoGroupTrailThreadGroup[]` (with `score_in_group`); the rendering edge color logic in Task 3 reads `thread.groups.length`.
- The empty-string `street_suffix` issue: the SQL builds `address_base = "${num}|${name}|${suffix or ''}"` matching the existing convention from Plan D. The trail endpoint adds an `address_base` thread for the same anchor representation.

No placeholders, no "similar to Task N" shortcuts. Every code step shows the actual code.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-layer-2-plan-f-trail-view.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review. 7 tasks total.

**2. Inline Execution** — Execute tasks here in this session with checkpoints.

Which approach?
