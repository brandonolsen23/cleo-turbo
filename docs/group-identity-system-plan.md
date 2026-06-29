# Group Identity System — Implementation Plan

This document captures the design and phased rollout of the unified Group identity system that replaces the parallel `groups` (legacy SPV) + `auto_groups` (clustering output) duality with a single, user-facing Group concept backed by `auto_groups`.

## Background

The system has two parallel concepts today:

- **136,266 legacy `groups`** (one per SPV, keyed by `normalized_name`). Populated by the compiler from clean-data. Properties / contacts / transactions reference these via foreign key.
- **1,756 `auto_groups`** (the real-world rollups — RioCan, Kingsett, Starlight). Built by `discovery_v2`. Currently only surfaced in Explorer.

The user's mental model is one unified Group concept. A "Group" is a real-world entity. Some are big (RioCan with 29 SPVs underneath); most are small (family offices owning 1-3 properties). The current dual-table system creates UI fragmentation and forces users to think about plumbing they shouldn't have to.

## Goal

A single Group concept (backed by `auto_groups`) that covers 100% of party-sides. The legacy `groups` table stays as internal plumbing — the compiler still writes to it, but the UI and API never expose it directly.

Three principles:

1. **Every party-side belongs to exactly one auto_group.** No orphans. Single-SPV "standalone" groups are first-class.
2. **User assertions are load-bearing.** Manual edits (detach, attach, rename, merge) survive across `discovery_v2` rebuilds.
3. **Identity signals beat inferred signals.** Defining n-grams, address+suite anchors, and rare-contact direct matches are primary attribution. Tenure-window matching is a tiebreaker only — historical experience shows it's unreliable when realtrack data entry is inconsistent or families have gaps between transactions.

## Phase structure

```
                ┌─────────────────────────────────┐
                │ Phase A: 100% coverage          │
                │  discovery_v2 + standalone pass │
                └──────────────┬──────────────────┘
                               │
                               ▼
                ┌─────────────────────────────────┐
                │ Phase B: Lookup + Contacts      │
                │  legacy_to_auto_group_map       │
                │  contacts.current_auto_group_id │
                │  API resolve_auto_group helper  │
                └──────────────┬──────────────────┘
                               │
                               ▼
                ┌─────────────────────────────────┐
                │ Phase C: Edit operations        │
                │  auto_group_user_edits table    │
                │  5 API endpoints                │
                │  apply_user_edits stage         │
                │  provenance on members          │
                └─────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────────┐
        │ Phase D (deferred): Frontend cutover             │
        │  /groups, /properties, /contacts use AGRP_*      │
        │  Legacy GRP_* URL redirects                      │
        │  CRM data bulk-migrated                          │
        └──────────────────────────────────────────────────┘
```

A → B → C is a linear dependency. Phase D is deferred until A+B+C produce clean, verified data via the API.

---

## Phase A — 100% auto_groups coverage

**Goal:** every party-side has an auto_group home. No orphans.

### Deliverables

1. **Schema migration**: extend `auto_groups.tier` CHECK constraint to include `'standalone'`. This new tier means "single-entity group, not a clustering result." Confidence is 0 for standalone (not a meaningful score for these).

2. **New code**: `cleo/discovery_v2/standalone_coverage.py`. Final stage in the discovery_v2 orchestrator, runs after clustering, expansion, force-attach, and conflict detection. For each legacy group not already represented in any auto_group:
   - Create a new auto_group with:
     - `canonical_stem` = legacy group's `normalized_name` (already deduped — two "23465023 Ontario Inc" entries become one)
     - `display_name` = legacy group's `display_name`
     - `tier` = `'standalone'`
     - `confidence` = 0
     - `n_anchors` = 0
   - Attach every party-side for that legacy group as a `party_side` member with `match_score = 1.0`
   - Skip if any party-side is already attached to another auto_group (clustering wins by precedence)

3. **Orchestrator update**: register the new stage in `cleo/discovery_v2/auto_groups.py` to run after the existing stages.

4. **Run discovery_v2 end-to-end**.

### Verification

- `COUNT(*) FROM auto_group_members WHERE member_type = 'party_side'` equals `COUNT(*) FROM party_fingerprints`
- Every legacy group has at least one corresponding auto_group_member row
- Spot-check 5 random legacy groups → confirm they appear in auto_groups (either via clustering or as a new standalone)

### Output (expected)

- ~1,756 clustered auto_groups + ~130k standalone auto_groups = ~133k total
- 100% party-side coverage

### Risks

Minimal. Read-only with respect to legacy data; only adds rows to `auto_groups` + `auto_group_members`.

---

## Phase B — Lookup table + Contact migration

**Goal:** the bridge that lets the API translate between legacy IDs and auto_group IDs. Migrate contacts' group assignment.

### Deliverables

1. **New table `legacy_to_auto_group_map`**:
   ```sql
   CREATE TABLE legacy_to_auto_group_map (
       legacy_group_id  TEXT PRIMARY KEY REFERENCES groups(id),
       auto_group_id    TEXT NOT NULL REFERENCES auto_groups(auto_group_id),
       coverage_pct     REAL,   -- % of legacy group's party-sides that landed in this auto_group
       source           TEXT NOT NULL CHECK (source IN ('clustered','standalone','user_attached')),
       computed_at      TEXT DEFAULT (datetime('now'))
   );
   ```

2. **Builder function** that joins `auto_group_members` → `transaction_parties` → `groups` and picks the dominant auto_group per legacy group. Recomputed at end of every `discovery_v2` run.

3. **Schema add**: `contacts.current_auto_group_id TEXT` column (alongside existing `current_group_id` for backward compatibility).

4. **One-shot migration**:
   ```sql
   UPDATE contacts SET current_auto_group_id = (
     SELECT auto_group_id FROM legacy_to_auto_group_map
     WHERE legacy_group_id = contacts.current_group_id
   );
   ```

5. **API helper function**: `resolve_auto_group(legacy_group_id) -> auto_group_id`. Used by every endpoint that needs to translate from legacy to auto.

6. **`/api/contacts/{id}` detail** updated to show `current_auto_group` (display_name + AGRP_id) instead of legacy group.

7. **Compiler hook**: after each compiler run, recompute the contact → auto_group mapping for any contacts whose `current_group_id` changed.

### Verification

- Every legacy group has a row in `legacy_to_auto_group_map`
- Every contact with `current_group_id` has a populated `current_auto_group_id`
- API returns auto_group_id for contact's employer

### Output

Contacts display their employer as the auto_group (e.g. "RioCan" instead of "RioCan Holdings Inc"). Other CRM tables (deals, lists, group_notes, etc.) keep their legacy FKs through this phase — bulk-migrated in Phase D.

### Risks

Low. Adding a column + populating it. Existing legacy `current_group_id` stays in place as a fallback.

---

## Phase C — Edit operations

**Goal:** user can correct mistakes and rename groups; edits survive forever.

### Deliverables

1. **New table `auto_group_user_edits`** — everything in one table for one audit trail:
   ```sql
   CREATE TABLE auto_group_user_edits (
       id                   INTEGER PRIMARY KEY AUTOINCREMENT,
       edit_type            TEXT NOT NULL CHECK (edit_type IN
                              ('detach','attach','rename','merge','split','create')),
       auto_group_id        TEXT NOT NULL,
       source_id            TEXT,                    -- for detach/attach: the party-side
       side                 TEXT,
       target_auto_group_id TEXT,                    -- for attach (move target) and merge
       new_display_name     TEXT,                    -- for rename and create
       new_canonical_stem   TEXT,                    -- for create
       edited_by            TEXT NOT NULL,
       edited_at            TEXT DEFAULT (datetime('now')),
       notes                TEXT,
       is_active            INTEGER DEFAULT 1
   );
   ```

2. **API endpoints**:

   | Endpoint | Effect |
   |---|---|
   | `POST /api/auto-groups/{id}/parties/detach` | Remove `(source_id, side)` from this auto_group. Party-side falls back to its standalone auto_group. |
   | `POST /api/auto-groups/{id}/parties/attach` | Force-attach `(source_id, side)` to this auto_group; if it's already in another, detach from there first. |
   | `PATCH /api/auto-groups/{id}` | Update `display_name`. Algorithm-computed name preserved but user name takes precedence. |
   | `POST /api/auto-groups/{id}/merge` | Take a `target_auto_group_id`, move all members of source into target, mark source as merged. |
   | `POST /api/auto-groups` | Create a new auto_group from scratch. |

3. **Discovery_v2 final stage**: `cleo/discovery_v2/apply_user_edits.py`. Runs AFTER all algorithmic stages (including standalone coverage). Reads `auto_group_user_edits WHERE is_active=1` and applies each:
   - **detach**: `DELETE FROM auto_group_members` then INSERT into the standalone auto_group
   - **attach**: DELETE existing rows for that `(source_id, side)` across all groups, INSERT to target
   - **rename**: After Stage A5 sets the algorithmic display_name, override with the user's name
   - **merge**: Move all members of source → target, mark source's tier as 'merged'
   - **create**: INSERT the auto_group row if it doesn't exist (idempotency guarantee)

4. **API behavior on edit**: edits are immediately reflected (write directly to `auto_group_members` at the same time as inserting into `auto_group_user_edits`). The discovery_v2 stage is the durability layer that re-applies after a rebuild.

5. **Provenance column** on `auto_group_members`: add `attached_by TEXT` — values like `'algorithm'`, `'defining_brand'`, `'user_edit'`. UI can show "this attachment came from a user edit" with a revert button.

### Verification

- User edits persist across `discovery_v2` rebuilds (insert a test edit, run discovery, verify it's still in effect)
- Detach actually removes the party-side from the auto_group
- Attach actually moves the party-side to the target
- Rename actually changes display_name

### Risks

Medium. The "edits survive rebuilds" guarantee depends on `apply_user_edits` running correctly. Regression test required.

---

## Phase D — Frontend cutover (deferred)

Out of scope for the initial implementation. Scope:

- `/groups`, `/properties`, `/contacts` pages use auto_groups exclusively
- URLs use `AGRP_*` IDs
- Legacy `GRP_*` URL redirects so bookmarks don't break
- CRM data (deals, lists, group_notes, etc.) bulk-migrated from `GRP_*` FKs to `AGRP_*`
- Search by exact `AGRP_*` ID

---

## Future architecture: rule library (post-C)

After A+B+C land, we'll build a Rule abstraction so new identity patterns (family office detection, brokerage rollup, etc.) can be added without code refactors. Key design points:

- Rules are discrete modules in `cleo/discovery_v2/rules/`
- Each rule has: name, version, priority, `detect_candidates(conn)` function
- Rules write to a staging table; a reconcile step picks winners by priority
- `auto_group_members.attached_by` tracks provenance (which rule attached this row)
- Shadow-mode runner: test a new rule's output without committing it
- Override mechanism (`auto_group_user_edits`) is the safety net — every rule's mistakes are fixable in one click

### Signal classes ranked by reliability

| Signal class | Use as |
|---|---|
| Defining n-gram (1-6 gram, user-marked) | Primary identity — force-attach |
| Direct address+suite at single-tenant building | Primary identity — force-attach |
| Rare contact fingerprint + clear pattern (e.g. multiple unbranded SPVs) | Suggestion — surface to review tray |
| Phone number with high stem dominance | Primary identity for the time window |
| Contact tenure window matching | TIEBREAKER only — never primary basis |
| Generic shared address (multi-tenant CBD tower) | Ignored entirely as attribution signal |

---

## Open questions / decisions to revisit

- Should standalone auto_groups have a `legacy_group_id` reference column for fast reverse-lookup? Currently the bridge is the `legacy_to_auto_group_map` table.
- Should the `merge` edit operation be reversible (mark `is_active=0` to unmerge), or is it a one-way operation?
- For the future Rule library: how to expose the "shadow mode" results to the user — Explorer page, dedicated review queue, both?

---

## Status

- 2026-05-13: Plan finalized. Starting Phase A.
