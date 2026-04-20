# Party Link Labeling Tool — Design

**Date:** 2026-04-20
**Status:** Spec approved (pending final user review)
**Author:** Brandon Olsen (with AI co-design)

## Purpose

Build an in-app labeling tool that lets Brandon capture, at field level, how he manually decides whether two transaction parties belong to the same portfolio. The output is a training-quality dataset of labeled party pairs — positive and negative — with field-level link annotations. That dataset becomes the ground truth the next discovery algorithm is designed against and evaluated on.

The problem the tool solves: doing this labeling by hand (in Realtrack + a notes doc) is too slow to produce enough data for an AI-designed algorithm to be reliable. Existing app features (group merge, discovery clusters, group compare) are group-to-group and merge-oriented; this task is party-to-party and label-oriented, so it needs a purpose-built surface.

## Scope

**In scope:**
- New data model for sessions, verdicts, field-level links, search seeds, reviewed parties.
- Backend API under `/api/labeling` for session lifecycle, seed queue, search, verdict capture, export.
- Frontend page at `/labeling` (landing) and `/labeling/sessions/{id}` (workspace).
- Audit-file parser that reads `docs/discovery-audit/{YYYY-MM-DD}/*.md` and surfaces anchor candidates.
- JSON export endpoint shaped for downstream algorithm design.

**Out of scope:**
- Implementing the discovery algorithm itself (this tool produces the data; the algorithm is a separate project).
- Auto-merging groups in the production DB. Labels are intentionally decoupled from the `groups` / `group_merges` tables.
- Fixing RT parser gaps. If a field that's visible in the HTML isn't captured by the parser, we surface the raw HTML fragment as an escape hatch and flag parser gaps for separate follow-up.

## Key concepts

- **Party** — one side (buyer or seller) of one RT transaction. Identified by `(source_id, side)`. All `transaction_parties` rows on that side plus the transaction-level fields (trade_name, care_of, companies_json, law_firms_json), mailing address, contacts, and phones aggregate into a single "party" view.
- **Session** — one portfolio investigation. Starts from one Anchor party. Accumulates confirmed parties, rejected parties, field-level link records, and a search-seed queue. Intended to be long-running; pause and resume is first-class.
- **Seed** — a search term extracted from a confirmed party's field value (a trade_name, a contact name, a phone, etc.), used to surface other RT parties that might belong to the same portfolio. Seeds auto-populate when a party is confirmed; user picks which seed to run next. Deduped per session on `(term, field_type)`.
- **Verdict** — a user decision on a party: `confirmed` (in the portfolio) or `rejected` (not). Records the field-level links the user drew, the rationale, and which seed surfaced the party.
- **Link** — a field-level edge between a field on one party and a field on another party, classified as `exact` (identical string) or `implied` (same entity despite different text — e.g. "DH Management Inc" ↔ "DH Property Management"). The link is the core training signal; it captures the reasoning a human used.

## Workflow

1. User opens `/labeling`, sees the 8 audit files as cards with progress.
2. User opens an audit → browses distinct parties the audit lists → picks one as **Anchor** → new session is created.
3. Server pre-populates the seed queue by harvesting all field values from the anchor (party_name, trade_name, care_of, company_other, law_firm, contact_name, address, phone).
4. User enters the session workspace. Left sidebar shows the seed queue + confirmed/rejected lists. Main area is empty until a seed is picked.
5. User picks a seed from the queue. Server runs the search across all RT parties (excluding anything already reviewed in this session), returns a candidate list shown in column 4. The reference party (column 2) flips to show the party that first contributed this seed.
6. User clicks a candidate → it loads into column 3. User reads both parties side by side, clicks field anchors to draw link lines (exact or implied) between matching fields, writes a rationale, and clicks **Confirm** or **Reject**.
7. On **Confirm**: verdict saved, links saved, candidate's field values auto-harvested as new seeds (deduped). Candidate appears in the Confirmed list. Column 3 auto-advances to the next unreviewed candidate in the list.
8. On **Reject**: verdict saved with rationale, no links. Candidate appears in the Rejected list. Column 3 advances.
9. When the candidate list is exhausted, seed is marked `done`. User picks next seed. Loop until no pending seeds remain.
10. User clicks **Export** at any time to download the training dataset JSON.

## UI layout

**Route:** `/labeling/sessions/{id}` — add to `FULL_BLEED_ROUTES` in `components/layout/AppLayout.tsx`.

**Top bar** (slim): session name · anchor ref · counts (confirmed / rejected / pending seeds) · `[Export]` `[Pause]`.

**Body — four columns:**

| Col | Contents |
|-----|----------|
| 1 — Session state | Ad-hoc search box at top. Seed queue grouped by state (pending / in-progress / done / skipped). Confirmed list. Rejected list (collapsed). |
| 2 — Reference party (left pane) | Full party block: structured field rows, one per value. Anchor dot on right edge of each row. `[raw HTML ▾]` accordion at bottom. |
| 3 — Candidate party (right pane) | Same structure mirrored. Anchor dot on left edge of each row. |
| 4 — Candidate list | Results from the current seed's search. Click row → load into column 3. Already-reviewed rows marked and sorted last. |

**Link drawing mechanics:**
- Mode toggle below the panes: `Exact ●` (solid line) / `Implied ○` (dashed line). Keys: `E` / `I`.
- Click a dot on the left pane, then a dot on the right pane → link created in current mode.
- An SVG overlay draws lines between field anchors; drawn links are also listed in a table below with per-link delete.
- Visual style: card-based panes with labeled rows and connector dots on inner edges, same language as `PipelineFlowView` used by `PipelineTracePage`. See reference images embedded in the brainstorming session (database-schema-style linking UI).

**Action bar (bottom):** Rationale text field · `[Confirm] (C)` · `[Reject] (R)` · `[Skip] (S)`.

**Landing route `/labeling`:** grid of cards, one per audit file (parsed from `docs/discovery-audit/*/README.md` + file list), showing audit metadata, row/group counts from the markdown, and any active sessions started from that audit.

**Audit browse route `/labeling/audits/{slug}`:** shows the audit's signal + caveats + a table of distinct parties with "Start session from this party" action per row.

## Data model

Five new CRM-style tables (persistent, never touched by the compiler). Added via a new migration in `cleo/database/migrations/`. Added to the CRM-table list in `CLAUDE.md`.

### `labeling_sessions`
```
id                  TEXT PRIMARY KEY       -- LBL_NNNNN
name                TEXT NOT NULL
audit_slug          TEXT                   -- nullable, e.g. "05-huntington"
anchor_source_id    TEXT NOT NULL
anchor_side         TEXT NOT NULL          -- 'buyer' | 'seller'
status              TEXT NOT NULL          -- 'active' | 'paused' | 'done'
created_by          TEXT NOT NULL
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
completed_at        TEXT                   -- set when status transitions to 'done'
```

The `status='done'` transition is a user action via `PATCH /sessions/{id}`, not automatic. The server stamps `completed_at` at that moment.

### `labeling_verdicts`
```
id                  INTEGER PRIMARY KEY
session_id          TEXT NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE
source_id           TEXT NOT NULL
side                TEXT NOT NULL
verdict             TEXT NOT NULL          -- 'confirmed' | 'rejected'
left_source_id      TEXT NOT NULL          -- the party shown on the left when verdict was made
left_side           TEXT NOT NULL
seed_id             INTEGER                -- nullable: null means ad-hoc search or anchor review
rationale           TEXT
created_by          TEXT NOT NULL
created_at          TEXT NOT NULL
UNIQUE (session_id, source_id, side)       -- one verdict per party per session
```

### `labeling_links`
```
id                  INTEGER PRIMARY KEY
verdict_id          INTEGER NOT NULL REFERENCES labeling_verdicts(id) ON DELETE CASCADE
from_field_type     TEXT NOT NULL          -- see field_type enum below
from_field_value    TEXT NOT NULL
to_field_type       TEXT NOT NULL
to_field_value      TEXT NOT NULL
kind                TEXT NOT NULL          -- 'exact' | 'implied'
created_at          TEXT NOT NULL
```
Links only exist when `verdict = 'confirmed'`.

### `labeling_seeds`
```
id                              INTEGER PRIMARY KEY
session_id                      TEXT NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE
term                            TEXT NOT NULL
field_type                      TEXT NOT NULL
state                           TEXT NOT NULL  -- 'pending' | 'in_progress' | 'done' | 'skipped'
first_contributed_by_source_id  TEXT NOT NULL
first_contributed_by_side       TEXT NOT NULL
completed_at                    TEXT
created_at                      TEXT NOT NULL
UNIQUE (session_id, term, field_type)
```

### `labeling_reviewed_index`
```
session_id          TEXT NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE
source_id           TEXT NOT NULL
side                TEXT NOT NULL
reviewed_at         TEXT NOT NULL
PRIMARY KEY (session_id, source_id, side)
```
Populated whenever a party enters column 3, regardless of whether it received a verdict. Excludes parties from future candidate lists in this session.

### Field type enum (seeds + links)
- `party_name`
- `trade_name`
- `care_of`
- `company_other` — from `companies_json`
- `law_firm` — from `law_firms_json`
- `contact_name` — from contacts table (`display_name`)
- `address` — mailing display
- `phone`

`contact_role` (Attn / Pres / Trustee / etc.) is displayed as metadata next to `contact_name` but is not a link target.

## API

All under `/api/labeling`. Register in `cleo/web/app.py` as `labeling` tag. Each endpoint takes `db=Depends(get_db)` and `user=Depends(get_current_user)`.

### Session management
- `GET  /sessions` — list sessions with progress (confirmed/rejected/seeds-remaining)
- `POST /sessions` — create. Body: `{ anchor_source_id, anchor_side, name, audit_slug? }`. Server creates the session, fetches anchor party, harvests fields into seeds.
- `GET  /sessions/{id}` — session summary
- `PATCH /sessions/{id}` — update name/status
- `DELETE /sessions/{id}` — cascade delete

### Party fetch (shared)
- `GET /party/{source_id}/{side}` — returns aggregated party view:
  - `party_rows` (all transaction_parties rows on this side)
  - `trade_name`, `care_of`
  - `companies_other[]`, `law_firms[]`
  - `contacts[]` (name, role, phone, job_title)
  - `mailing` (display, street, city, province, postal)
  - `phones[]` (deduplicated union)
  - `raw_html_fragment` (from raw-data/rt for the side, best-effort — escape hatch for parser gaps)

### Seed queue
- `GET   /sessions/{id}/seeds?state=pending|in_progress|done|skipped`
- `POST  /sessions/{id}/seeds` — manually add a seed
- `PATCH /sessions/{id}/seeds/{seed_id}` — change state
- `POST  /sessions/{id}/seeds/{seed_id}/search` — runs the seed's search, returns candidate parties, marks seed in_progress

### Search (generic)
- `POST /search` — body: `{ term, field_type?, session_id }`. Returns `(source_id, side)` pairs matching the term across all field types, excluding entries in `labeling_reviewed_index` for the session. Powers both seed execution and ad-hoc searches.

### Verdicts
- `POST   /sessions/{id}/verdicts` — body: `{ source_id, side, verdict, left_source_id, left_side, seed_id?, rationale, links: [{ from_field_type, from_field_value, to_field_type, to_field_value, kind }] }`. Validation: on `verdict='rejected'`, `rationale` is required and `links` must be empty; on `verdict='confirmed'`, `links` must have ≥1 entry, `rationale` is optional. On `confirmed`, server auto-harvests this party's field values as new seeds (deduped).
- `GET    /sessions/{id}/verdicts` — list (paginated)
- `GET    /sessions/{id}/verdicts/{verdict_id}` — single with links
- `DELETE /sessions/{id}/verdicts/{verdict_id}` — undo. Deletes the verdict and its links. Does **not** remove any seeds that were contributed by this party — seeds are cheap to keep, and the user can mark unneeded seeds `skipped` in the queue. This avoids a harder "did any other confirmed party contribute this same term" rollback that our schema doesn't track.

### Reviewed index
- `POST /sessions/{id}/reviewed` — idempotent mark-seen, called when a party enters column 3.

### Audit integration
- `GET /audits` — scan `docs/discovery-audit/*/`, return audit files with per-session progress.
- `GET /audits/{slug}/parties` — parse the markdown table, return distinct `(source_id, side)` parties + associated display fields.

### Export
- `GET /sessions/{id}/export` — JSON training dataset (see Export format below).
- `GET /export/all` — concatenation across all sessions with `status = 'done'`.

## Export format

```json
{
  "session": {
    "id": "LBL_00001",
    "name": "DH Management",
    "audit_slug": "05-huntington",
    "anchor": { "source_id": "RT184886", "side": "buyer" },
    "created_at": "...",
    "completed_at": "..."
  },
  "pairs": [
    {
      "verdict": "confirmed",
      "rationale": "Same management company + same address + same contact",
      "left":  { "source_id": "RT184886", "side": "buyer", "fields": { /* all field_type values */ } },
      "right": { "source_id": "RT148276", "side": "buyer", "fields": { /* all field_type values */ } },
      "links": [
        { "from_field_type": "trade_name",   "from_value": "DH Management Inc", "to_field_type": "trade_name",   "to_value": "DH Management Inc", "kind": "exact" },
        { "from_field_type": "contact_name", "from_value": "Dan Hagler",        "to_field_type": "contact_name", "to_value": "Dan Hagler",        "kind": "exact" },
        { "from_field_type": "address",      "from_value": "180 Shorting Rd...", "to_field_type": "address",     "to_value": "180 Shorting Rd...", "kind": "exact" },
        { "from_field_type": "phone",        "from_value": "416-265-5055",       "to_field_type": "phone",       "to_value": "416-265-5055",       "kind": "exact" }
      ],
      "seed": { "term": "DH Management", "field_type": "trade_name" },
      "created_at": "..."
    },
    {
      "verdict": "rejected",
      "rationale": "Different Huntington — chain restaurant, not the REIT",
      "left":  { "source_id": "...", "side": "...", "fields": { ... } },
      "right": { "source_id": "...", "side": "...", "fields": { ... } },
      "links": [],
      "seed": { "term": "Huntington", "field_type": "party_name" }
    }
  ],
  "stats": {
    "confirmed_count": 47,
    "rejected_count": 9,
    "seeds_processed": 34,
    "seeds_skipped": 2
  }
}
```

Design notes for the export:
- Each pair is a **standalone training example**. Full fields on both sides, all links, verdict, rationale, seed context. Self-contained — no cross-referencing required.
- **Rejected pairs carry full field data too.** Negative examples are as important as positive ones; the model should see which fields were *available* and the human chose not to link.
- **Seed context on each pair** tells the model why the pair was surfaced (a shared field value the human chose to investigate).
- **Field values are raw strings.** No normalization in the export — the downstream model / algorithm is free to normalize however it wants.

## Testing

Unit tests:
- `labeling_seeds` dedup on `(session_id, term, field_type)` insert.
- Verdict creation on `confirmed` auto-harvests fields as seeds; fields already seeded from a prior party are not duplicated.
- Verdict deletion removes seeds only when no other confirmed party contributes the same `(term, field_type)`.
- Search excludes parties in `labeling_reviewed_index` for the given session.
- Audit markdown parser extracts the correct `(source_id, side)` set from the fixture.

Integration tests:
- Full session lifecycle: create from audit → confirm 3 parties → reject 1 → export. Verify export shape and counts.
- Undo path: confirm a party → delete verdict → verify seeds correctly rolled back (or retained if still contributed by others).

Manual verification (per UI golden path):
- Create session from Huntington audit, anchor on first buyer.
- Pick a seed, confirm a candidate with 3 links of mixed kind, observe new seeds appearing.
- Reject a candidate with rationale, observe it in rejected list.
- Use ad-hoc search, confirm a hit outside the audit.
- Refresh the page mid-session; verify state fully reconstructs from the DB.

## Open items (not blocking design approval)

- **Parser-gap audit.** Before heavy labeling begins, do a quick read of the RT parser vs a couple of RT HTML detail pages. Any field visible in the HTML but not in the structured extract should be flagged — the `raw_html_fragment` escape hatch mitigates but doesn't eliminate the cost of missing fields.
- **Anchor-self review.** Decide whether the anchor party itself appears as a "pre-confirmed" row or is implicit. Current design: implicit (anchor doesn't need a verdict against itself).
- **Multi-user concurrency.** Current design assumes a single labeller per session. If that changes later, add row-level locks on seed state.
