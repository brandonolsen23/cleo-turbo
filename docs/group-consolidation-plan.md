# Group Consolidation Infrastructure — Implementation Plan

## The Problem

Brandon wants to look at a contact like Dan Hagler, see that he's transacted under 6 different corp names, and consolidate all of those into one parent group (DH Property Management Inc.) — even if that parent name doesn't appear in any transaction data. This consolidation must survive full database recompiles.

## Critical Discovery: ID Stability Is Broken

**Before anything else in this plan can work, the ID stability mechanism needs to be fixed.**

### How it works today (broken)

The compiler's execution order in `writer.py`:

```
1. drop_derived_tables(conn)     ← drops groups, contacts, properties
2. create_all_tables(conn)       ← recreates them EMPTY
3. registry = IDRegistry(conn)
4. registry.load()               ← reads from EMPTY tables → maps are {}
5. Pass 1: Groups                ← every group gets a NEW sequential ID
6. Pass 2: Contacts              ← every contact gets a NEW sequential ID
7. Pass 3: Properties            ← every property gets a NEW sequential ID
```

The `load()` method reads existing mappings from the `groups`, `contacts`, and `properties` tables — but those tables were just dropped and recreated empty. So every compile, every entity gets a **brand new ID**. The only thing that persists is the counter value (stored in `app_meta`), which means IDs never collide, but they're never stable either.

**Compile 1:** "DH PROPERTY MANAGEMENT" → GRP_00042
**Compile 2:** "DH PROPERTY MANAGEMENT" → GRP_00543 (different!)

### Why this hasn't been noticed

The full compiler has likely only been run once (initial data load). All subsequent updates go through the GW watcher (which does incremental DB updates, bypassing the compiler) or the RT watcher (which appends new records). Nobody has done a full recompile with existing CRM data yet.

### What breaks on a full recompile

Every CRM table that references a group, contact, or property ID becomes orphaned:

- `deals.group_id` and `deals.property_id` → point to IDs that no longer exist
- `group_contacts.group_id` and `group_contacts.contact_id` → orphaned
- `group_merges.source_group_id` and `group_merges.target_group_id` → orphaned
- `contact_notes.contact_id` → orphaned
- `group_notes.group_id` → orphaned
- `list_members.member_id` → orphaned
- `group_analytics.group_id` → orphaned

**This is a data-loss bug.** It must be fixed before the planned reprocessing.

### The fix: Persist ID mappings in a system table

Create a new system table (never dropped):

```sql
CREATE TABLE IF NOT EXISTS id_mappings (
    entity_type TEXT NOT NULL,   -- 'property', 'contact', 'group'
    anchor_key  TEXT NOT NULL,   -- ARN, fingerprint, or normalized_name
    entity_id   TEXT NOT NULL,   -- PRO_NNNNN, CON_NNNNN, GRP_NNNNN
    created_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (entity_type, anchor_key)
);
```

Modify `IDRegistry.load()` to read from `id_mappings` instead of the derived tables. Modify `get_or_create_*` methods to write new mappings to `id_mappings`. On the first run after this change, backfill `id_mappings` from the current derived tables before dropping them.

After this fix:
- **Compile 1:** "DH PROPERTY MANAGEMENT" → GRP_00042, stored in `id_mappings`
- **Compile 2:** `load()` reads `id_mappings`, finds the mapping → GRP_00042 again. Stable.

---

## Architecture Overview

With ID stability fixed, here's the full system:

```
┌─────────────────────────────────────────────────────────────┐
│                    SYSTEM TABLES (never dropped)            │
│                                                             │
│  id_mappings        ← anchor → stable ID (NEW)             │
│  app_meta           ← ID counters + config                  │
│  group_overrides    ← manually-created groups (NEW)         │
│  group_merges       ← merge audit trail (exists)            │
│  group_analytics    ← materialized metrics (exists)         │
│  users, audit_log   ← system (exists)                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    CRM TABLES (never dropped)               │
│                                                             │
│  deals              ← references group/property IDs         │
│  group_contacts     ← manual contact-group links            │
│  group_notes        ← user notes                            │
│  contact_notes      ← user notes                            │
│  lists, list_members ← user lists                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                DERIVED TABLES (rebuilt by compiler)          │
│                                                             │
│  groups, contacts, properties, transactions,                │
│  transaction_parties, group_names, etc.                      │
│                                                             │
│  IDs are STABLE because id_mappings persists the mapping.   │
│  CRM tables always point to valid IDs.                      │
└─────────────────────────────────────────────────────────────┘
```

### Compiler Flow (revised)

```
1.  Load ID mappings from id_mappings table
2.  drop_derived_tables()
3.  create_all_tables()
4.  Pass 1: Groups (from transaction data)
5.  Pass 1b: Inject user-created groups from group_overrides     ← NEW
6.  Pass 1c: Apply active merges from group_merges               ← EXISTS (enhanced)
7.  Pass 2: Contacts
8.  Pass 3: Properties + Transactions + Transaction Parties
9.  Pass 4-6: POIs, GW, PIN Bridge
10. Rebuild FTS
11. Save ID counters + mappings
12. Refresh group analytics
13. Generate reconciliation report                                ← NEW
```

---

## Implementation Plan

### Phase 0: Fix ID Stability (PREREQUISITE)

**Goal:** Make entity IDs truly stable across recompiles. Must be done before any reprocessing.

#### 0.1 — Create `id_mappings` system table

**File:** `cleo/database/schema.py`

Add to `SYSTEM_TABLES`:
```sql
CREATE TABLE IF NOT EXISTS id_mappings (
    entity_type TEXT NOT NULL,
    anchor_key  TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (entity_type, anchor_key)
);
CREATE INDEX IF NOT EXISTS idx_id_mappings_entity
    ON id_mappings(entity_id);
```

#### 0.2 — Backfill migration script

**File:** `cleo/migrations/backfill_id_mappings.py` (new)

One-time script that reads the current `properties`, `contacts`, and `groups` tables and populates `id_mappings`:

```python
def backfill(conn):
    """Run ONCE before switching to the new IDRegistry. Populates id_mappings from current derived tables."""
    conn.execute("CREATE TABLE IF NOT EXISTS id_mappings (...)")

    # Properties: arn → PRO_ID
    conn.execute("""
        INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id)
        SELECT 'property', arn, id FROM properties WHERE arn IS NOT NULL
    """)
    # Contacts: fingerprint → CON_ID
    conn.execute("""
        INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id)
        SELECT 'contact', name_fingerprint, id FROM contacts WHERE name_fingerprint IS NOT NULL
    """)
    # Groups: normalized_name → GRP_ID
    conn.execute("""
        INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id)
        SELECT 'group', normalized_name, id FROM groups WHERE normalized_name IS NOT NULL
    """)
    conn.commit()
    counts = conn.execute("SELECT entity_type, COUNT(*) FROM id_mappings GROUP BY entity_type").fetchall()
    for et, c in counts:
        print(f"  {et}: {c:,} mappings")
```

**Run this before the next full compile.** It captures the current ID assignments so they persist.

#### 0.3 — Modify IDRegistry to use `id_mappings`

**File:** `cleo/compiler/reconciler.py`

Change `load()`:
```python
def load(self):
    # Load counters from app_meta (unchanged)
    for prefix in ['PRO', 'CON', 'GRP']:
        row = self.conn.execute(
            "SELECT value FROM app_meta WHERE key = ?",
            (f'next_{prefix.lower()}_id',)
        ).fetchone()
        self._counters[prefix] = int(row[0]) if row else 1

    # Load mappings from id_mappings (SYSTEM table, survives drops)
    for row in self.conn.execute(
        "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'property'"
    ):
        self._maps['property'][row[0]] = row[1]
    for row in self.conn.execute(
        "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'contact'"
    ):
        self._maps['contact'][row[0]] = row[1]
    for row in self.conn.execute(
        "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'group'"
    ):
        self._maps['group'][row[0]] = row[1]
```

Change `get_or_create_*` methods to persist new mappings:
```python
def get_or_create_group_id(self, normalized_name):
    if normalized_name in self._maps['group']:
        return self._maps['group'][normalized_name]
    new_id = self._next_id('GRP')
    self._maps['group'][normalized_name] = new_id
    # Persist immediately to id_mappings
    self.conn.execute(
        "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) VALUES (?, ?, ?)",
        ('group', normalized_name, new_id)
    )
    return new_id
```

Same pattern for `get_or_create_property_id` and `get_or_create_contact_id`.

#### 0.4 — Reorder compiler to load BEFORE drop

**File:** `cleo/compiler/writer.py`

Change from:
```python
drop_derived_tables(conn)
create_all_tables(conn)
registry = IDRegistry(conn)
registry.load()
```

To:
```python
registry = IDRegistry(conn)
registry.load()          # reads from id_mappings (system table, not dropped)
drop_derived_tables(conn)
create_all_tables(conn)
```

#### 0.5 — Verification

After implementing, verify:
1. Run backfill migration
2. Run compiler
3. Check that all IDs match previous values: `SELECT im.entity_id, g.id FROM id_mappings im JOIN groups g ON im.anchor_key = g.normalized_name WHERE im.entity_type = 'group' AND im.entity_id != g.id` → should return 0 rows
4. Check CRM integrity: `SELECT gc.group_id FROM group_contacts gc LEFT JOIN groups g ON gc.group_id = g.id WHERE g.id IS NULL` → should return 0 rows

---

### Phase 1: Group Overrides (User-Created Groups)

**Goal:** Allow manually-created groups that don't come from transaction data to survive recompiles.

#### 1.1 — Create `group_overrides` CRM table

**File:** `cleo/database/schema.py`

Add to `CRM_TABLES`:
```sql
CREATE TABLE IF NOT EXISTS group_overrides (
    group_id         TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    normalized_name  TEXT NOT NULL UNIQUE,
    created_by       TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    notes            TEXT
);
```

This table stores groups that exist because a human said so. The compiler will ensure these groups exist in the `groups` table after Pass 1.

#### 1.2 — Add `POST /api/groups` endpoint (create manual group)

**File:** `cleo/web/routes/groups.py`

```python
class CreateGroupRequest(BaseModel):
    display_name: str
    notes: Optional[str] = None

@router.post("")
def create_group(req: CreateGroupRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Create a manually-defined group that persists across recompiles."""
    normalized = normalize_group_name(req.display_name)
    if not normalized:
        raise HTTPException(400, "Invalid group name")

    # Check if this normalized name already exists
    existing = db.execute(
        "SELECT id FROM groups WHERE normalized_name = ?", (normalized,)
    ).fetchone()
    if existing:
        raise HTTPException(409, f"Group already exists: {existing['id']}")

    # Allocate a stable ID through the registry
    # (read current counter from app_meta, increment, persist)
    counter_row = db.execute("SELECT value FROM app_meta WHERE key = 'next_grp_id'").fetchone()
    next_id = int(counter_row[0]) if counter_row else 1
    group_id = f"GRP_{next_id:05d}"
    db.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) VALUES ('next_grp_id', ?, datetime('now'))",
        (str(next_id + 1),)
    )

    # Write to id_mappings (permanent)
    db.execute(
        "INSERT INTO id_mappings (entity_type, anchor_key, entity_id) VALUES ('group', ?, ?)",
        (normalized, group_id)
    )

    # Write to group_overrides (permanent)
    db.execute(
        "INSERT INTO group_overrides (group_id, display_name, normalized_name, created_by, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, req.display_name, normalized, user["username"], req.notes)
    )

    # Write to groups (derived, so it's usable immediately)
    db.execute(
        "INSERT INTO groups (id, display_name, normalized_name, status, property_count, transaction_count, contact_count) "
        "VALUES (?, ?, ?, 'pool', 0, 0, 0)",
        (group_id, req.display_name, normalized)
    )

    db.commit()
    return {"id": group_id, "display_name": req.display_name, "normalized_name": normalized}
```

#### 1.3 — Compiler Pass 1b: Inject overrides

**File:** `cleo/compiler/writer.py`

After Pass 1 (groups from transaction data), before merge application:

```python
# ================================================================
# Pass 1b: Inject user-created groups from group_overrides
# ================================================================
overrides = conn.execute("SELECT group_id, display_name, normalized_name FROM group_overrides").fetchall()
if overrides:
    print(f'  Injecting {len(overrides)} user-created group(s)...')
    for ov in overrides:
        gid, display, normalized = ov[0], ov[1], ov[2]
        if normalized not in group_data:
            # Group doesn't exist in transaction data — create it
            group_data[normalized] = {
                'id': gid,
                'display_name': display,
                'normalized_name': normalized,
                'names': set(),
                'tx_count': 0,
                'property_arns': set(),
            }
            conn.execute(
                "INSERT OR IGNORE INTO groups (id, display_name, normalized_name, status, property_count, transaction_count) "
                "VALUES (?, ?, ?, 'pool', 0, 0)",
                (gid, display, normalized)
            )
        else:
            # Group exists in transaction data but user created an override —
            # ensure it uses the override's ID (which is the stable one from id_mappings)
            if group_data[normalized]['id'] != gid:
                # This would only happen if somehow two different IDs got assigned.
                # The id_mappings should prevent this, but log it for safety.
                print(f'    WARNING: override {gid} vs data {group_data[normalized]["id"]} for {normalized}')
    conn.commit()
```

---

### Phase 2: Enhanced Merge Application in Compiler

**Goal:** Make the existing merge phase more robust.

#### 2.1 — Handle missing merge targets

The current merge application code (writer.py lines 109-145) assumes the target group exists in `group_data`. With `group_overrides` (Phase 1), user-created targets will exist. But we should still handle edge cases:

```python
# ================================================================
# Apply active group merges (from CRM layer)
# ================================================================
active_merges = conn.execute(
    "SELECT source_group_id, target_group_id FROM group_merges WHERE unmerged_at IS NULL"
).fetchall()
if active_merges:
    print(f'  Applying {len(active_merges)} active group merge(s)...')
    redirect = {}
    for m in active_merges:
        redirect[m[0]] = m[1]
    # Resolve chains
    for src in list(redirect.keys()):
        target = redirect[src]
        visited = {src}
        while target in redirect and target not in visited:
            visited.add(target)
            target = redirect[target]
        redirect[src] = target

    orphaned_merges = []
    for src, tgt in redirect.items():
        # Verify target exists in groups table
        target_exists = conn.execute("SELECT id FROM groups WHERE id = ?", (tgt,)).fetchone()
        if not target_exists:
            orphaned_merges.append((src, tgt))
            continue

        conn.execute(
            "INSERT OR IGNORE INTO group_names (group_id, name, normalized, source_id) "
            "SELECT ?, name, normalized, source_id FROM group_names WHERE group_id = ?",
            (tgt, src)
        )
        conn.execute("UPDATE groups SET status = 'merged' WHERE id = ?", (src,))

    # Update group_data dict so Pass 2/3 use redirected IDs
    for norm, g in group_data.items():
        if g['id'] in redirect:
            g['id'] = redirect[g['id']]

    if orphaned_merges:
        print(f'  WARNING: {len(orphaned_merges)} orphaned merge(s) — target group does not exist:')
        for src, tgt in orphaned_merges:
            print(f'    {src} → {tgt} (target missing)')

    conn.commit()
```

#### 2.2 — Preserve CRM status across recompiles

When the compiler creates a group in Pass 1, it always sets `status = 'pool'`. But the user may have promoted a group to `'engaged'`. The status lives in the derived `groups` table and gets wiped.

**Fix:** Add a `group_status_overrides` mechanism. When a user promotes a group (sets status to 'engaged'), store that in a CRM table. The compiler applies these after Pass 1.

Option A (simple): Add a `status` column to `group_overrides`. After Pass 1, apply:
```sql
UPDATE groups SET status = go.status
FROM group_overrides go
WHERE groups.id = go.group_id AND go.status IS NOT NULL
```

Option B (more general): Create a small CRM table `group_status`:
```sql
CREATE TABLE IF NOT EXISTS group_status_overrides (
    group_id TEXT PRIMARY KEY,
    status   TEXT NOT NULL,
    set_by   TEXT,
    set_at   TEXT DEFAULT (datetime('now'))
);
```

When `POST /groups/{id}/promote` is called, insert/update this table in addition to updating the derived `groups` table. The compiler applies these after Pass 1.

**Recommendation:** Option B. It's cleaner, doesn't conflate "user-created groups" with "user-set status on any group", and works for groups that came from transaction data too.

#### 2.3 — Same issue: HQ address, website, hubspot_id

These fields are on the derived `groups` table and get wiped on recompile. Same pattern as status:

```sql
CREATE TABLE IF NOT EXISTS group_field_overrides (
    group_id    TEXT PRIMARY KEY,
    status      TEXT,
    hq_address  TEXT,
    website     TEXT,
    hubspot_id  TEXT,
    updated_by  TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

After Pass 1, apply all non-NULL fields from this table onto the freshly-created `groups` rows. This replaces the separate `group_status_overrides` idea — it's one table for all user-set fields on groups.

**Same pattern needed for contacts:** Email, mobile, phone, job_title are editable on the contact detail page but live on the derived `contacts` table. These also get wiped on recompile.

```sql
CREATE TABLE IF NOT EXISTS contact_field_overrides (
    contact_id  TEXT PRIMARY KEY,
    email       TEXT,
    mobile      TEXT,
    phone       TEXT,
    job_title   TEXT,
    contact_type TEXT,
    status      TEXT,
    updated_by  TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

---

### Phase 3: Contact-Centric Group Consolidation UI

**Goal:** The original feature request — look at a contact, see all their affiliated groups, consolidate into one.

#### 3.1 — New API endpoint: affiliated groups for a contact

**File:** `cleo/web/routes/contacts.py`

```python
@router.get("/{contact_id}/affiliated-groups")
def contact_affiliated_groups(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """
    Returns all groups this contact has been associated with across all transactions,
    including property counts, transaction counts, and the relationship type.
    """
    contact = db.execute("SELECT id, display_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        raise HTTPException(404, "Contact not found")

    # Groups this contact appeared alongside in transaction_parties
    rows = db.execute("""
        SELECT DISTINCT
            g.id, g.display_name, g.normalized_name, g.status,
            g.property_count, g.transaction_count, g.contact_count,
            CASE WHEN c.current_group_id = g.id THEN 1 ELSE 0 END as is_current_group,
            COUNT(DISTINCT tp.source_id) as shared_transactions
        FROM transaction_parties tp_contact
        JOIN transactions t ON tp_contact.source_id = t.source_id
        JOIN transaction_parties tp_group ON t.source_id = tp_group.source_id
            AND tp_group.group_id IS NOT NULL
            AND tp_group.side = tp_contact.side
        JOIN groups g ON tp_group.group_id = g.id
        JOIN contacts c ON c.id = ?
        WHERE tp_contact.contact_id = ?
            AND g.status != 'merged'
        GROUP BY g.id
        ORDER BY shared_transactions DESC
    """, (contact_id, contact_id)).fetchall()

    return {
        "contact": dict(contact),
        "affiliated_groups": [dict(r) for r in rows],
    }
```

This returns every group the contact has transacted under, how many transactions they share, whether it's the contact's current group, and the group's stats.

#### 3.2 — Frontend: ConsolidateGroupsModal

**File:** `frontend/src/components/ui/ConsolidateGroupsModal.tsx` (new)

Three-step modal, accessible from the contact detail page:

**Step 1 — Select groups to consolidate:**
- Shows all affiliated groups from the API (step 3.1)
- Each group row shows: name, property count, transaction count, shared transactions with this contact
- Checkboxes for multi-select
- Groups already marked as "merged" are excluded (handled by API)

**Step 2 — Choose or create target:**
- Two options:
  - **Use existing group:** Select one of the checked groups as the target (the others merge into it)
  - **Create new group:** Text field to type a new group name. Calls `POST /api/groups` to create it.
- If creating new: the modal calls the create endpoint, gets back the GRP_ID, then proceeds

**Step 3 — Preview and confirm:**
- Shows: "Merging [Group A, Group B, Group C] → [Target Group]"
- Combined totals: properties, transactions, contacts
- Warning: "This will affect N other contacts who are also associated with these groups"
- Lists the other affected contacts (from `group_contacts` and `contacts.current_group_id` on the source groups)
- Confirm button calls `POST /api/group-merges/merge`

After confirmation: refresh the contact detail page. The contact now shows one group instead of many.

#### 3.3 — Frontend: Contact detail page changes

**File:** `frontend/src/pages/ContactDetailPage.tsx`

Add to the existing page:
- New data fetch: `GET /contacts/{id}/affiliated-groups`
- If affiliated groups count > 1, show a section below the Group Card:
  - "Associated with N groups" with a summary line
  - "Consolidate" button that opens the ConsolidateGroupsModal
- The existing Group Card continues to show the `current_group_id` group

#### 3.4 — Enhance merge preview with affected contacts

**File:** `cleo/web/routes/group_merges.py`

New endpoint for merge impact preview:

```python
@router.post("/preview")
def merge_preview(req: MergeRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Preview what a merge would affect without executing it."""
    affected_contacts = set()
    affected_properties = set()
    affected_transactions = set()

    for sid in req.source_ids:
        # Contacts
        for r in db.execute("SELECT id, display_name FROM contacts WHERE current_group_id = ?", (sid,)):
            affected_contacts.add((r[0], r[1]))
        for r in db.execute(
            "SELECT c.id, c.display_name FROM group_contacts gc JOIN contacts c ON gc.contact_id = c.id WHERE gc.group_id = ?",
            (sid,)
        ):
            affected_contacts.add((r[0], r[1]))
        # Properties
        for r in db.execute("SELECT id, display_address FROM properties WHERE current_owner_group_id = ?", (sid,)):
            affected_properties.add((r[0], r[1]))
        # Transactions
        for r in db.execute("SELECT DISTINCT source_id FROM transaction_parties WHERE group_id = ?", (sid,)):
            affected_transactions.add(r[0])

    return {
        "source_count": len(req.source_ids),
        "target_id": req.target_id,
        "affected_contacts": [{"id": c[0], "name": c[1]} for c in affected_contacts],
        "affected_properties": len(affected_properties),
        "affected_transactions": len(affected_transactions),
    }
```

---

### Phase 4: Post-Compile Reconciliation Report

**Goal:** After every compile, generate a report of what changed so the user can catch and fix issues.

#### 4.1 — Pre-compile snapshot

Before `drop_derived_tables()`, capture the current state:

```python
# Snapshot current state for reconciliation report
pre_compile = {
    'groups': {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
        "SELECT id, display_name, status, property_count FROM groups"
    )},
    'merge_targets': {r[0]: r[1] for r in conn.execute(
        "SELECT source_group_id, target_group_id FROM group_merges WHERE unmerged_at IS NULL"
    )},
}
```

#### 4.2 — Post-compile diff

After the compile completes, compare:

```python
def generate_reconciliation_report(conn, pre_compile):
    report = {
        'disappeared_groups': [],   # was in pre, not in post
        'new_groups': [],           # in post, not in pre
        'orphaned_merges': [],      # merge target doesn't exist
        'property_count_swings': [],# significant property count changes
        'orphaned_crm_refs': [],    # CRM tables pointing to non-existent entities
    }

    post_groups = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
        "SELECT id, display_name, status, property_count FROM groups"
    )}

    for gid, (name, status, props) in pre_compile['groups'].items():
        if gid not in post_groups and status != 'merged':
            report['disappeared_groups'].append({
                'id': gid, 'name': name, 'was_property_count': props
            })

    for gid, (name, status, props) in post_groups.items():
        if gid not in pre_compile['groups']:
            report['new_groups'].append({
                'id': gid, 'name': name, 'property_count': props
            })

    # Check CRM integrity
    for table, col in [
        ('deals', 'group_id'), ('deals', 'property_id'),
        ('group_contacts', 'group_id'), ('group_contacts', 'contact_id'),
        ('group_notes', 'group_id'), ('contact_notes', 'contact_id'),
        ('list_members', 'member_id'),
    ]:
        # ... check for orphaned references

    return report
```

#### 4.3 — Output format

Write the report to `data/reconciliation_report.json` after each compile. Print a summary to stdout:

```
Reconciliation Report:
  Groups: 2,847 (12 new, 0 disappeared)
  Orphaned merges: 0
  CRM integrity: OK (0 orphaned references)
  Property count swings: 3 groups changed by >50%
    GRP_00042 "DH PROPERTY MANAGEMENT": 8 → 11 properties
```

If there are orphaned CRM references, print a WARNING in red. This is the "trust mechanism" — you can always verify integrity after a compile.

---

### Phase 5: Edge Cases and Safety

#### 5.1 — Parser fix changes a group name (the "456 Hangle Rd S" problem)

**Scenario:** "456 Hangle Rd S" was incorrectly parsed as a party name. User merged GRP_00099 ("456 HANGLE RD S") into GRP_NEW. Parser is fixed. Recompile happens.

**What happens with this system:**
1. `id_mappings` still has: `('group', '456 HANGLE RD S', 'GRP_00099')`
2. But no transaction produces "456 Hangle Rd S" anymore, so GRP_00099 is never created in Pass 1
3. `group_merges` still has: GRP_00099 → GRP_NEW (active)
4. Merge phase: tries to redirect GRP_00099 → GRP_NEW, but GRP_00099 doesn't exist in `groups`. No-op.
5. The 3 transactions that USED to be under "456 Hangle Rd S" now produce a different party name (e.g., "Hagler Holdings Ltd" → GRP_00042). These properties end up under GRP_00042.
6. **Reconciliation report flags:** "GRP_00099 ('456 HANGLE RD S') disappeared. Was merged into GRP_NEW. Merge is now orphaned." And: "GRP_00042 ('HAGLER HOLDINGS') gained 3 properties."

**User action:** Look at the report, see the issue, merge GRP_00042 into GRP_NEW. Takes 30 seconds.

**This is the correct behavior.** We can't auto-fix this because we don't know that GRP_00042 should also go to GRP_NEW — only the user knows that. The system's job is to make the situation visible and easy to fix.

#### 5.2 — Contact fingerprint changes

Less likely but possible: if name parsing changes, "Dan Hagler" might become "Daniel Hagler". Different fingerprint, different CON_ ID. The old `contact_notes` and `group_contacts` entries point to the old CON_ ID.

Same solution: reconciliation report flags orphaned CRM references. User manually handles it (or we build a contact merge feature later — separate project).

#### 5.3 — Concurrent access during compile

The compiler drops and recreates tables. If the frontend is running during a compile, API requests will fail or return empty data.

**Mitigation:** Not in scope for this plan, but worth noting. Options include: compile to a temp DB then swap, or add a "maintenance mode" flag. For now, just don't use the UI during a compile.

#### 5.4 — Unmerge after a recompile

The unmerge endpoint currently just marks the merge as inactive and sets the source group's status back to 'pool'. It relies on a compiler rebuild to actually restore the property/contact assignments. This works correctly with the new system — the next compile will see the merge is inactive, won't apply the redirect, and the source group gets rebuilt naturally from transaction data.

---

## Implementation Order and Dependencies

```
Phase 0: Fix ID Stability          ← MUST be done first, before any reprocessing
  0.1 Create id_mappings table
  0.2 Backfill migration (one-time)
  0.3 Modify IDRegistry
  0.4 Reorder compiler
  0.5 Verify

Phase 1: Group Overrides           ← Required for "create new parent group" workflow
  1.1 Create group_overrides table
  1.2 POST /api/groups endpoint
  1.3 Compiler Pass 1b

Phase 2: Enhanced Compiler          ← Required for CRM data to survive recompiles
  2.1 Robust merge application
  2.2 group_field_overrides table + compiler application
  2.3 contact_field_overrides table + compiler application

Phase 3: Contact Consolidation UI   ← The actual feature the user wants
  3.1 GET /contacts/{id}/affiliated-groups endpoint
  3.2 ConsolidateGroupsModal component
  3.3 Contact detail page changes
  3.4 Merge preview endpoint

Phase 4: Reconciliation Report      ← Trust mechanism
  4.1 Pre-compile snapshot
  4.2 Post-compile diff
  4.3 Output format
```

Phases 0-2 are infrastructure. Phase 3 is the feature. Phase 4 is the safety net.

Phases 0-2 should be built and tested before the planned full reprocessing. Phase 3 can be built in parallel. Phase 4 should be ready before the reprocessing happens.

---

## Files Modified (Summary)

| File | Changes |
|------|---------|
| `cleo/database/schema.py` | Add `id_mappings`, `group_overrides`, `group_field_overrides`, `contact_field_overrides` to SYSTEM/CRM tables |
| `cleo/compiler/reconciler.py` | `load()` reads from `id_mappings`; `get_or_create_*` writes to `id_mappings` |
| `cleo/compiler/writer.py` | Reorder load/drop; add Pass 1b (overrides), enhance merge phase, add field override application, add reconciliation report |
| `cleo/database/group_merge_ops.py` | No changes needed (already correct) |
| `cleo/web/routes/groups.py` | Add `POST /` (create manual group) |
| `cleo/web/routes/contacts.py` | Add `GET /{id}/affiliated-groups` |
| `cleo/web/routes/group_merges.py` | Add `POST /preview` |
| `cleo/migrations/backfill_id_mappings.py` | New — one-time migration |
| `frontend/src/pages/ContactDetailPage.tsx` | Add affiliated groups section, consolidate button |
| `frontend/src/components/ui/ConsolidateGroupsModal.tsx` | New — three-step consolidation workflow |
| `frontend/src/types/index.ts` | Add types for affiliated groups, merge preview, create group |

## Open Questions

1. **Should we add a "contact merge" feature too?** For cases where the same person appears with different name spellings. Not required for the current ask but related infrastructure.

2. **Should the reconciliation report be viewable in the UI?** Or is stdout + JSON file sufficient for now?

3. **How should the "Consolidate" button appear for contacts with only 1 affiliated group?** Hidden entirely, or disabled with a tooltip?

4. **Should we track which user-set field overrides came from which source?** E.g., "email was set manually by Brandon" vs "email came from HubSpot sync." Could matter later for conflict resolution.
