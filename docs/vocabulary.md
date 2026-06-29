# Cleo Vocabulary

The user-facing vocabulary we use across the app, code comments, plans, and conversation. **Don't invent parallel terms.** If you find yourself reaching for "operator", "auto_group", "cluster", "phase / wave / stage" in something a user might read — stop. Use the words below.

(Internal-only code identifiers like `auto_groups` table or `discovery_v2` module are fine — those are historical and not user-facing. The rule is about the language we *speak in* when describing what things are.)

## Core nouns

### Group
A person or corporation that controls assets. The CRE-professional generic term for "buying or selling entity."

- A single-property individual is a Group (e.g., Jim Bobo owning 5 properties under his own name = Jim Bobo is the Group).
- A corporate operator is a Group (RioCan, Cachet Estate Homes, Mattamy).
- When Jim Bobo signs as CFO of JB Holdings, JB Holdings is the Group — not Jim Bobo personally.

### Transaction
One property changing hands at one moment in time, with two Parties (buyer + seller). Cleo has Transactions from two sources:

- **RT Transaction** — a Realtrack record. Each RT is one event with its own ID like `RT198864`. RT is event-stream — one row per sale event.
- **GW Transaction** — a GeoWarehouse record. GW is property-history shaped, not event-stream: each GW record is anchored by `PIN` / `ARN` / Address and lists the current party ownership PLUS all past transaction parties for that parcel (when available). GW Transactions don't have RT IDs but they still produce the same Party Name / Contact / Phone / Address signals that drive Group matching.

When the user says "Transaction" or "RT" they usually mean an RT record specifically. When the data ambiguously comes from either source, say "RT Transaction" or "GW Transaction" to be unambiguous. The Group-matching rules apply equally across both sources — a Party Name appearing on an RT Transaction and on a GW Transaction is the same matching signal.

### Party (or Party Side)
The buyer or seller side of a single Transaction. Two Parties per Transaction:
- Transferor (seller) side
- Transferee (buyer) side

### Party Name
Any name that appears within a Party. Realtrack puts these across multiple JSON fields (`party_name`, `trade_name`, `care_of`, `company_name`) but **for matching purposes they are all equivalent Party Names**. The exception is `law_firms_json` — law firms are not Party Names for matching.

A single Party can have multiple Party Names (e.g., `Southside Construction Management Ltd` + `Southside Group` on the same side).

### Contact
The named human on a Party (first + last name).

### Phone
Phone number on a Party.

### Address
Mailing/contact address on a Party.

## Matching philosophy

Goal: figure out which Parties belong to the same Group. The three high-confidence matchers, in order of trustworthiness:

1. **Exact Party Name match anywhere** — "Southside Group" appears on RT198864 AND RT197301 → those Parties belong to the same Group. Strongest signal because unique brand names rarely have non-matching duplicates.
2. **Exact Contact match** (first + last name) — 99% unique in CRE Ontario. The same name across two Parties is almost always the same person.
3. **Exact Address match where no suite/unit** ("345 Main St, Waterford") — 99% unique because two unrelated Groups won't share the same non-unit address.

## Hard cases (handle manually, not algorithmically)

- **Suite/unit/floor addresses** — multi-tenant offices, can belong to different Groups
- **Law firms** — excluded from Party Name matching
- **JV / partnership Transactions** — two Groups on one Party Side
- **Realtrack input errors** — typos, missing suite numbers, wrong street direction, misspelled company names

## What this vocabulary replaces

| Don't say | Say instead |
|---|---|
| operator | Group |
| auto_group / cluster | Group |
| party-side member | Party |
| brand_phrase | Party Name |
| signer | Contact |
| canonical_stem / brand stem | (no user-facing equivalent — internal only) |
| Phase A / Wave 2 / Stage Z | (internal milestone names — fine in dev docs, not in conversation about the product) |

Internal table names like `auto_groups`, `transaction_parties`, `party_atoms`, `brand_token_summary` are fine — they are implementation, not vocabulary. When discussing the meaning of these tables with the user, translate to the vocabulary above.
