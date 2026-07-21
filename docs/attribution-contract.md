# Attribution Contract — transaction_credits + property_holdings

**Status:** PINNED 2026-07-21 · Source: `cleo-linking-derivation-audit.md` §8–10
**Principle:** Attribution is a fact about the data. It is computed ONCE, at compile,
with provenance. Endpoints only read. No surface re-implements credit or ownership rules.

## Why this exists

The audit found seven divergent definitions of "who was on this deal" / "who owns what,"
written by four layers on different schedules. Verified damage: 7,067 contacts with
phantom holdings (9,181 sale txns, 7,668 properties), seller-side credit structurally
undercounted (117,286 buyer-side vs 66,532 seller-side direct links), a properties
owner-update bug gated on building size, and `groups.property_count` that never
decrements on sale. This contract collapses all of them onto two compiler-built ledgers.

## Ledger 1 — transaction_credits

One row per (transaction, side, principal). Built by the compiler ledger pass
(`cleo/compiler/credit_ledger.py`), rebuilt on every compile.

```
transaction_credits(
  source_id, side,
  principal_type   TEXT,   -- 'contact' | 'entity' | 'auto_group' | 'unknown'
  principal_id     TEXT,
  basis            TEXT,   -- 'named' | 'entity_named_elsewhere' | 'member' | 'manual'
  via_entity_id    TEXT,   -- GRP the credit flows through (NULL for named)
  PRIMARY KEY (source_id, side, principal_type, principal_id)
)
```

### Credit rules, in order

1. **Entity named:** every `transaction_parties` party row with a `group_id` →
   (`entity`, group_id, `named`).
2. **Contact named:** every party row with a `contact_id` → (`contact`, contact_id, `named`).
3. **Unknown principal:** a party row with NEITHER id ("Named Individual(s)" — real side,
   suppressed name) → (`unknown`, `(unnamed)`, `named`). Carried, never dropped, never
   rolls up, never opens holdings.
4. **Rollup (same-property scope — the shipped v1):**
   - A contact C is *paired* with entity E when any tp rows share (source_id, side)
     with C's contact row and E's party row.
   - C earns (`contact`, C, `entity_named_elsewhere`, via_entity_id=E) on every
     transaction T where E is a party, C is NOT named on T, and T's property_key is one
     C is directly named on. Side of the credit = E's side on T.
   - Same-property scope prevents crediting unrelated deals of large entities.
     Entity-wide rollup is a future one-function flip, measured as a report first (§9.1
     of the audit). The schema does not change either way.
5. **Auto-group member:** every `auto_group_members` party_side row →
   (`auto_group`, auto_group_id, `member`). Skipped gracefully if discovery tables
   are absent (fresh DBs, test fixtures).
6. **`manual`:** reserved for CRM assertions. No writer yet.

`property_key` everywhere = `COALESCE(transactions.property_id,
'addr:' || lower(trim(display_address)) || '|' || lower(trim(city)))` — identical to the
AGRP unified pass. Transactions with neither identity earn credits but no holdings.

## Ledger 2 — property_holdings

Ownership rule materialized. Built from credits + transactions in the same pass.

```
property_holdings(
  property_key,
  principal_type, principal_id,
  acquired_source_id, acquired_date,   -- NULL acquired = owned before our data starts
  disposed_source_id, disposed_date,   -- NULL disposed = currently owned
  basis                                -- 'derived' | 'manual'
)
```

### Holding rules

Walk each (property_key, principal)'s credited transactions in (sale_date, source_id)
order:

- **Buyer-side credit, no open holding** → open a holding (acquired = that txn).
- **Buyer-side credit, holding already open** → no-op (keep earliest acquisition).
- **Seller-side credit, open holding** → close it (disposed = that txn).
- **Seller-side credit, no open holding** → insert a pre-closed holding
  (acquired NULL, disposed = that txn). Preserves "latest side is seller ⇒ not owned"
  without inventing an acquisition.
- **Within a single transaction, the seller credit processes BEFORE the buyer credit.**
  A principal credited on both sides of one deal (self-transfer between their entities —
  Saherdid's 2017 RT125638/RT126004/RT126011 shape) closes the prior holding and
  immediately reopens, staying the owner.
- **Owned** = `disposed_source_id IS NULL`. **Sold** = closed. Tenure = disposed − acquired.
- `unknown` principals never hold. Undated transactions sort first (empty string), so a
  dated sale still closes them.

### manual_owner_links

Active `relationship='owns'` links upsert an OPEN holding (basis `manual`,
principal_type `entity`, acquired NULL) for the resolved property. This is the single
door for human ownership assertions; conflict policy vs GW/MPAC stays "flag, don't
overwrite" (audit §9.3, matching Pass 7's existing behavior). While `properties` is
still patched directly by Pass 7, the ledger row is written in parallel — the patch
path is deleted at repoint time, not before.

## Sequencing status

1. ✅ Spec pinned (this doc).
2. ✅ Ledgers built additively by the compiler; NOTHING reads them yet.
   Reconciliation report extended with credit/holding counts.
3. ⬜ Parity report: ledger vs every current surface. Diffs are the bug inventory.
4. ⬜ Repoint contact surfaces; DELETE the 2026-07-21 contacts.py endpoint patch.
5. ⬜ Repoint properties.current_owner_* (deletes the building-size owner bug) and
   groups.property_count (open holdings).
6. ⬜ AGRP unified pass reads holdings; add discovery-staleness marker.
7. ⬜ Tests: Gladwin-shape fixture asserting credits, holdings, and surface numbers.

## Named acceptance test — Saherdid Mohamed (CON_14995)

The case that triggered the audit. Bought 2215 Gladwin Crescent (PRO_11375) named as
attn; his entities later sold WITHOUT naming him. Required ledger outcomes:

- `entity_named_elsewhere` seller credits exist for the 2024 Gladwin sale (~$36.8M)
  and the 2020 Brock Road sale (RT149090, ~$26.7M).
- Both corresponding holdings are CLOSED (disposed set); owned count drops 4 → 2.
- Direct (`named`) credit count stays 7; merged credits 9.
- Last activity moves to 2024-12-19.

Any change to credit or holding rules must keep this case green.
