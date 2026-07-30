# RT → Compiled: Field Disposition Ledger

**Purpose.** For every RT clean field, state its real cardinality, what the
compiler *currently* does with it (verified), and what it *should* do (decision
for Brandon). This is the check the flow-view coverage audit does **not** do:
the audit proves every field renders and every compiled field has a wire
(stage-rendering completeness); this ledger proves every clean field actually
*lands* somewhere in Compiled (field-reachability). They are different, and the
second one is where data loss hides.

Status: descriptive columns verified against `data/cleo.db` and the clean corpus
(n = 126,498 RT records). **DECISION** column is unfilled, that's the work.

---

## The core finding (verified, not a diagram artifact)

`RT176319` carries 5 property addresses in clean:

| # | address |
|---|---|
| 0 | 3273 Port Severn Road |
| 1 | 3279 Port Severn Road |
| 2 | 3291 Port Severn Road |
| 3 | 3101 Stonewall Lane |
| 4 | 2748 Marine Drive |

Compiled kept only `display_address = 3273 Port Severn Road`, resolved the whole
transaction to **one** ARN (`43510400093610100000`), **one** PIN (`58599-0005`),
`pin_multiple = 0`, and **one** property (`PRO_31373`). Addresses 1-4 appear in
no transaction column, no child table, and did not become their own properties.
They are dropped. The deal is unfindable by 4 of its 5 addresses.

Two defects in one record: (a) 4 addresses silently dropped; (b) a multi-parcel
assembly flagged `pin_multiple = 0`.

This is not rare. **24% of RT records (29,858) have more than one property
address**; the max is 14.

---

## Cardinality inventory - every multi-valued field (full corpus, n = 126,498)

| field | max | records >1 | current disposition | flag |
|---|---:|---:|---|---|
| photos.street_photo_urls | 45 | 44,297 | `photos_json` blob | blob |
| consideration.charges | 19 | 15,232 | `charges_json` blob (+ `transaction_credits`?) | blob |
| **property.addresses** | **14** | **29,858** | **[0] -> `display_address`; rest DROPPED** | **LOSS** |
| seller.parties | 11 | 8,008 | `transaction_parties` rows | rows OK |
| broker.brokers[].agents | 9 | 9,843 | `transaction_broker_agents` rows | rows OK |
| property.addresses[].search_keys | 9 | 127,562 | not in Compiled | LOSS (parse aid) |
| buyer.parties | 8 | 6,447 | `transaction_parties` rows | rows OK |
| property.addresses[].variations | 8 | 11,277 | not in Compiled | LOSS (parse aid) |
| broker.brokers | 4 | 4,629 | `transaction_brokers` rows | rows OK |
| buyer.address.search_keys | 4 | 106,975 | not in Compiled | LOSS (parse aid) |
| buyer.companies | 4 | 118 | `buyer_companies_json` blob | blob |
| buyer.contacts | 4 | 1,086 | `transaction_parties` (person rows) | rows OK |
| seller.address.original_lines | 4 | 3,093 | not in Compiled | LOSS (parse aid) |
| seller.address.search_keys | 4 | 79,563 | not in Compiled | LOSS (parse aid) |
| seller.companies | 4 | 186 | `seller_companies_json` blob | blob |
| buyer.address.original_lines | 3 | 3,221 | not in Compiled | LOSS (parse aid) |
| photos.aerial_photo_urls | 3 | 31,486 | `photos_json` blob | blob |
| seller.contacts | 3 | 1,162 | `transaction_parties` (person rows) | rows OK |
| buyer.address.building_names | 2 | 117 | not in Compiled | LOSS |
| buyer.law_firms | 2 | 2 | `buyer_law_firms_json` blob | blob |
| seller.address.building_names | 2 | 109 | not in Compiled | LOSS |
| seller.law_firms | 2 | 8 | `seller_law_firms_json` blob | blob |

Note: `charges` appears both as a `charges_json` blob and (likely) normalized
into `transaction_credits`. Which is authoritative needs a 2-minute confirm.

---

## The three dispositions (currently inconsistent, that's the bug)

- **A - normalized to child rows (queryable, GOOD):** parties, mailing addresses,
  brokers, agents. The right pattern. Survives rebuilds, joinable, filterable.
- **B - JSON blob on the transaction (present, not queryable):** companies,
  law firms, photos, charges, multi-PINs. Retained but you can't filter/join on
  it. This is the `street_number` problem: kept, but useless as a query key.
- **C - flattened to [0], remainder dropped (LOSS):** property addresses, and
  all address parse-aids (search_keys, variations, original_lines,
  building_names).

There is **no `transaction_addresses` child table**, even though there is a
`transaction_mailing_addresses` one. Property/parcel addresses are the one
multi-valued entity the compiler never normalized. That single omission is the
core finding.

---

## Recommended target per field (decisions for Brandon)

| field | recommend | why | DECISION |
|---|---|---|---|
| property.addresses[1..N] | new `transaction_addresses` child table, 1 row/address, parsed + geocodable | stop the loss; enables per-parcel anchoring on assembly deals | |
| multi-parcel resolution | resolve each address->ARN; set `pin_multiple` truthfully; consider 1 property per parcel | RT176319 should be >=4 parcels, not 1 | |
| address.search_keys / variations | retain (on the address child row) | these are exactly the filter/search keys you lose otherwise | |
| seller/buyer.companies | promote blob -> child rows | company names are match-keys; you join on these for owner ID | |
| seller/buyer.law_firms | keep as blob (or child) | rarely a query key; low priority | |
| consideration.charges | pick one home (child rows), retire the duplicate blob | mortgage/charge analysis wants rows | |
| photos.* | blob is fine | never a query key | |
| address.original_lines / building_names / modifiers | retain if cheap, else document as intentionally terminal | decide, don't drop by accident | |

---

## Open questions the decisions turn on

1. **Multi-address = what, exactly?** Portfolio sale, assembly, or one legal
   parcel with multiple civic addresses? The answer changes whether N addresses
   become N properties or 1 property with N addresses. Sample the 29,858 to see
   the mix before deciding.
2. **Grain of a "property" on an assembly deal.** One `properties` row per ARN is
   right; the question is how a transaction fans out to multiple ARNs.
3. **Which blobs earn promotion to child rows.** Criterion: is it ever a
   join/filter key (company names, PINs = yes; photos, law firms = no)?

Once these are settled per field, the same ledger becomes the spec for
(a) fixing the compiler and (b) the demand-first Compiled -> App-Facing contract.

---

## Multi-address deep-dive (verified 2026-07-24, n = 29,858 multi-address RT records)

Composition of the "multi-address" population:

| what it actually is | share |
|---|---:|
| all legal/other - ONE parcel, legal description fragmented into fake addresses | 39% |
| all civic - TRUE multiple civic addresses (mall: 113/115/117 Dundas St E) | 30% |
| mixed civic + legal | 17% |
| other/unlabelable | 12% |

Current compiler resolves **65% of multi-address transactions to ZERO properties**
(dark). Multi-address is where resolution is worst, and legal-description
contamination is the likely cause: the resolver chokes on `Conc Jg` / `Part Lot 12`
entries treated as civic addresses.

**Consequence for design:** do NOT build a naive "one address = one parcel" fan-out.
That would mint phantom parcels from legal-description fragments on 39%+ of records.
The address array must be **typed** first.

### The typed-address model (do-it-once contract)

1. **Classify each entry:** `civic` | `legal_description` | `unit/level` | `other`.
2. **Recombine, don't fragment:** legal fragments (`Conc Jg` + `Part Lot 12`) reassemble
   into ONE legal-description string for one parcel. Unit/level refs attach to parent.
3. **Geocode every civic entry AND its variations** (`115`, `117`, `115-117`); all become
   search keys on the record.
4. **Resolve to ARN(s):** civic via geocode->ARN; legal via legal-description->PIN/ARN
   (GeoWarehouse). Collect the set of **distinct** ARNs.
5. **PRO_ grain = distinct ARN.** Many addresses -> one ARN = ONE property (mall). Many
   distinct ARNs = many properties (true assembly). **Address multiplicity feeds
   search/geocode; only ARN multiplicity splits PRO_.** (Answers "two PRO_IDs or one":
   only if the resolver returns separate ARNs.)
6. **Unresolved addresses stay as rows, flagged for GW. Never dropped.**

### The one trap to avoid

A mall spanning 3 ARNs that trades as ONE investment asset should NOT be forced into one
PRO_ by making PRO_ coarser than a parcel. PRO_ = parcel (ARN), deterministically.
"These 3 parcels are one asset" is a **judgment/grouping layer above Compiled**, exactly
like owner groups (AGRP_). Keep Compiled deterministic; assemble assets upstairs.

### Making it right "every time," not "this once"

Enforce a build-time invariant: every clean field must have a declared disposition, and any
new/unmapped clean field **fails the build**. That converts the one-time field-reachability
audit into a permanent guard, so a future clean-schema change can't silently reintroduce a
drop.
