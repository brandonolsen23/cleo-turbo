# Attribution Contract — transaction_credits + property_holdings

**Status:** PINNED 2026-07-21, revised to v2 same day after spot-check review
(Bauer/Valentini/Windsor cases) · Source: `cleo-linking-derivation-audit.md` §8–10
**Principle:** Attribution is a fact about the data. It is computed ONCE, at compile,
with provenance. Endpoints only read. No surface re-implements credit or ownership rules.

## The two rules, in one breath

1. **Credits are strictly what's printed.** A principal is credited on a transaction
   only if Realtrack literally named them on it. No rollups, no inference.
2. **Ownership follows the property's timeline, not the principal's.** You own a
   property if and only if you were a named buyer on its most recent transaction.
   Every sale closes ALL open holdings on that property except those of its named
   buyers — whoever the seller was. The close is a property event, never an
   attribution: "the property traded," not "they sold."

Why v2 dropped the same-property via-entity rollup (v1 rule 4): spot checks showed it
backdates involvement (Valentini credited as buyer on a 2012 deal, joined the entity
2013), manufactures activity for long-retired people (Bauer "active" 2026, last real
appearance 2007), and inherits pairing quality forever. The property-timeline rule
gives the desired outcome — phantom "still owns" rows disappear — without attributing
unnamed transactions to anyone. Company-to-company transfer untangling is explicitly
deferred; a shell-to-shell sale truthfully moves entity-level ownership.

## Ledger 1 — transaction_credits

One row per (transaction, side, principal). Built by the compiler ledger pass
(`cleo/compiler/credit_ledger.py`, Pass 8), rebuilt on every compile.

```
transaction_credits(
  source_id, side,
  principal_type   TEXT,   -- 'contact' | 'entity' | 'auto_group' | 'unknown'
  principal_id     TEXT,
  basis            TEXT,   -- 'named' | 'member' | 'manual'
  via_entity_id    TEXT,   -- reserved (always NULL in v2)
  PRIMARY KEY (source_id, side, principal_type, principal_id)
)
```

Rules:

1. **Entity named:** party row with `group_id` → (`entity`, gid, `named`).
2. **Contact named:** party row with `contact_id` → (`contact`, cid, `named`).
3. **Unknown principal:** party row with neither ("Named Individual(s)") →
   (`unknown`, `(unnamed)`, `named`). Carried, never dropped, never holds.
4. **Auto-group member:** `auto_group_members` party_side row →
   (`auto_group`, agid, `member`). Skipped gracefully if discovery tables absent.
5. **`manual`:** reserved for CRM assertions. No writer yet.

There is NO rollup basis in v2. `entity_named_elsewhere` is gone: person-facing
counts, last-activity, and timelines derive from `named` credits only.

## Property identity

`property_key` = `transactions.property_id` when resolved. When unresolved, the
address key `addr:<lower(trim(display_address))>|<lower(trim(city))>` is used ONLY
if the address starts with a digit. Legal-description and number-less addresses
("Conc 1", "Plan 43m-1947", "Yonge Street") get NO property identity: their
transactions earn credits but never open or close holdings. Rationale: the Windsor
"Conc 1" collision — 281 unresolved txns share that literal address across 119
cities, and distinct parcels within one city collapse onto one key, chaining
unrelated buys/sells into one holdings walk. Improved parcel resolution recovers
these transactions naturally (they gain a property_id).

## Ledger 2 — property_holdings

```
property_holdings(
  property_key,
  principal_type, principal_id,
  acquired_source_id, acquired_date,   -- NULL acquired = owned before our data
  disposed_source_id, disposed_date,   -- NULL disposed = currently owned
  acquired_basis,                      -- 'named' | 'member' | 'manual'
  disposed_basis                       -- 'named' | 'property_traded' | NULL
)
```

### The walk (per property, chronological — (sale_date, source_id) order)

For each transaction T on the property, with B = principals holding a `named`/`member`
buyer credit on T and S = principals with a seller credit on T:

1. Close every open holding on the property whose principal is NOT in B.
   `disposed_basis` = `named` if the principal is in S, else `property_traded`.
2. A principal in S with no open holding gets a pre-closed row
   (acquired NULL, `disposed_basis`=`named`): they owned it before our data starts.
   `property_traded` never creates rows — it only closes real ones.
3. Every principal in B without an open holding opens one (acquired = T).
   A principal in both B and S (self-transfer, Saherdid's 2017 shape) keeps their
   open holding untouched — original acquisition date survives.
4. Transactions with ONLY unknown-principal parties still run step 1: a sale with
   suppressed names still means the property moved.

**Owned** = `disposed_source_id IS NULL`. `disposed_basis='property_traded'` is the
outreach signal: bought, never named on a sell, but the asset is no longer theirs.

### Known limitation — partial-interest sales

A sale of a partial interest closes co-owners' holdings even though they still hold
the balance (JV/institutional deals). Accepted for v2; candidate flag: closes where
sale price is far below the property's prior trade. Do not silently "fix" this with
heuristics — surface it.

### manual_owner_links

Active `relationship='owns'` links resolved to a property mirror in as OPEN holdings
(`acquired_basis`=`manual`) when no derived open holding already exists. Conflict
policy vs GW/MPAC stays "flag, don't overwrite." Manual holdings are not closed by
the walk (they are assertions of CURRENT ownership, re-validated every compile by
Pass 7's conflict logic).

## Sequencing status

1. ✅ Spec pinned; revised to v2 same day.
2. ✅ Ledgers built additively (compiler Pass 8); NOTHING reads them yet.
   Reconciliation report extended with credit/holding counts.
3. ⬜ Parity report: ledger vs every current surface. Diffs are the bug inventory.
4. ⬜ Repoint contact surfaces; DELETE the 2026-07-21 contacts.py endpoint patch.
   Transaction tables gain the "property since traded (date, not named)" marker
   from holdings — one join.
5. ⬜ Repoint properties.current_owner_* (deletes the building-size owner bug) and
   groups.property_count (open holdings — kills ever-bought inflation).
6. ⬜ AGRP unified pass reads holdings; add discovery-staleness marker.
7. ⬜ Tests: Gladwin-shape fixture asserting credits, holdings, and surface numbers.

## Named acceptance tests

**Saherdid Mohamed (CON_14995)** — the trigger case. Named buyer 2215 Gladwin
(RT126161, 2017); named BOTH sides of RT125638/RT126004/RT126011 (2017 self-
transfers). Required: credits = 7, all `named`. Holdings: Gladwin closed by RT189166
(2024-12-19) and 889 Brock closed by RT149090 (2020-01-31), both
`disposed_basis`=`property_traded`; Fairview + Watters stay OPEN (self-transfer keeps
them); owned = 2. Last named activity stays 2017 — the 2024 sale appears on his
timeline as a property event, not his transaction.

**Manfred Bauer (CON_23464)** — staleness case. 23 named credits 1996–2007, none
after. His 2003 Yonge St holding (via 2024385 Ontario Inc buy) closes on the 2026
Manulife sale as `property_traded`. He shows NO 2026 activity.

**George Valentini (CON_02363)** — retroactivity case. Named only on the 2016
Scotia Plaza sell (pre-closed row, `named`). NO holding and NO credit from the 2012
$1.27B buy he wasn't named on.

Any change to credit or holding rules must keep all three green.
