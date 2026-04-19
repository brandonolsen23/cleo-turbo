# Cleo Turbo — Definitions Dictionary

> Canonical reference for all terminology used in Cleo. Every module, UI label, API route,
> variable name, and conversation between team members should use these terms consistently.
> When in doubt, defer to this document.
>
> Last updated: 2026-03-26

---

## System Architecture

### Data Engine

The backend processing system that takes raw scraped/fetched data and turns it into clean, structured, parcel-linked records. Each data source has its own engine (RT Engine, OSM Engine, etc.) that runs data through a series of **stages**. Each stage reads from the previous stage's output and writes to its own folder. Stages are independent — you can re-run any stage without affecting the others.

The Data Engine produces **Clean Records** — the single source of truth for all downstream layers.

### Stages

Each engine runs its source data through stages. Not every source uses every stage — each source defines its own stage sequence. The full set of stages across all sources:

1. **Extract** — Raw source files to structured JSON. For Realtrack, this parses detail HTML, export JSON, and results HTML, then assembles them into one record per source ID. Other sources may have simpler extraction.
2. **Classify** — Categorize extracted data into typed fields. For Realtrack, this is the 4-layer contact classification system that identifies addresses, companies, law firms, people, postal codes, etc. from raw text lines. Not all sources need this stage.
3. **Normalize** — Source-agnostic address decomposition and expansion. Breaks addresses into components (street number, name, suffix, direction, suite). Expands abbreviations to long form (St → Street, ON → Ontario). Expands range and list addresses into individual searchable variations. Generates search keys and geocode-ready strings. Normalizes PIN/ARN for API queries.
4. **Resolve Parcels** — Link records to provincial parcel data. Query by ARN (20-digit) first, address fallback. Returns parcel polygon boundary and MPAC address data. This is the step that connects a transaction to a physical piece of land.
5. **Compile** — Merge all stage outputs into a single Clean Record per source ID. This is the final output of the engine, written to `clean-data/`.

### Stage Sequence by Source

| Source | Extract | Classify | Normalize | Resolve Parcels | Compile |
|--------|---------|----------|-----------|-----------------|---------|
| **Realtrack** | HTML → structured JSON | 4-layer contact classification | Address decomposition + expansion | ARN/address → parcel polygon | Merge all stages |
| **OSM** | POI dump → structured JSON | — | — | Coords → spatial parcel match | Merge |
| **GeoWarehouse** | GW export → structured JSON | — | Address normalization | PIN/ARN → parcel polygon | Merge |
| **Brand** | Store locator → structured JSON | — | Address normalization | Coords/address → parcel match | Merge |

### Clean Record

A single unified JSON record that merges all engine stage outputs for one source record. Contains the complete cleaned data — transaction details, decomposed addresses, search keys, and parcel data. Identified by a **source_id** (RT196880, BR_00001, GW00001, OSM_00001). Clean Records live in `clean-data/` and are the portable, rebuildable layer. If you blow away the database, the Compiler rebuilds it from Clean Records.

### Compiler

Reads all `clean-data/` folders, links records across sources via parcel, builds relational tables, assigns persistent IDs (PRO_, CON_, GRP_), and writes to the database. The Compiler is the bridge between the JSON file layer and the queryable database.

The Compiler rebuilds derived tables on every run but **preserves all existing IDs** through Reconciliation (matching by ARN, name fingerprint, etc.) and **never overwrites user-entered data** (status, email, notes, group assignments).

### Database

SQLite database that the app queries. Contains both derived tables (rebuilt by Compiler) and CRM tables (persistent, user-curated). The database is the performance layer — you can't efficiently search 126K JSON files, but you can query a database in milliseconds.

**Derived tables** (rebuilt by Compiler, IDs persist via Reconciliation):
| Table | Keyed by | Description |
|---|---|---|
| `properties` | PRO_ ID (anchored to ARN) | One per parcel — transaction history, assessment data, tenants. Includes `gw_municipality` from GW data. |
| `transactions` | RT source_id | One per sale — price, date, parties, addresses, site metadata (pin_display, arn_display, parcel_method, location, surface_rights_only, more_info_url) |
| `contacts` | CON_ ID (anchored to name fingerprint) | Every person seen across all transactions. Status: **pool** or **engaged** |
| `groups` | GRP_ ID (anchored to normalized name) | Every company seen across all transactions. Status: **pool** or **engaged** |
| `transaction_parties` | CON_ ID + RT source_id | Who appeared on what transaction, on which side, under which group |
| `transaction_mailing_addresses` | source_id + side | Seller/buyer mailing addresses from RT (display, components, city, province, postal) |
| `transaction_brokers` | source_id | Brokerages involved in the transaction |
| `transaction_broker_agents` | broker_id | Individual agents within a brokerage |
| `pois` | OSM/BR source_id | Brand locations from OSM and store locators |
| `gw_assessments` | GW source_id | GeoWarehouse property assessment data — includes registry metadata (land_registry_status, registration_type, lro), municipality, and quality flags (has_mpac_data, is_active, address_parsed, parcel_resolved) |
| `gw_sales_history` | gw_id | Historical sale records from GeoWarehouse (date, amount, type, party_to) |

**CRM tables** (persistent, never rebuilt by Compiler):
| Table | Keyed by | Description |
|---|---|---|
| `deals` | DEAL_ ID | Active deal tracking |
| `lists` | LST_ ID | Prospecting target lists |
| `group_contacts` | GRP_ ID + CON_ ID | Manual association history — who works for whom, current vs former |
| `contact_notes` | CON_ ID + timestamp | Manual notes, meeting context |
| `group_notes` | GRP_ ID + timestamp | Manual notes on companies |

### Pool vs Engaged

Every contact and group gets a stable ID (CON_, GRP_) the moment the Compiler first sees them. The difference between pool and engaged is a status flag — not a different table or ID system.

- **Pool** — the full map, grey territory. Visible in search, shows on transaction/property views, linked to parcels and companies. But not synced to HubSpot, doesn't appear in your CRM contact list by default. These are the tens of thousands of people and companies the engine has surfaced from transaction data.
- **Engaged** — coloured territory. You've made contact, they're in HubSpot, they're in your active CRM. Trackable with deals, lists, notes.

Promotion from pool to engaged is just flipping the status. All relationships (transactions, properties, group associations) are already there. Nothing needs to be re-linked.

A contact can become engaged by:
- You manually promoting them from the pool
- Importing them from HubSpot (matched to existing pool record by name)
- Manually creating them (if they're not in the pool at all)

### Source

The origin system that a record came from. Four active sources:
- **Realtrack** — Transaction data from Realtrack.com (126K records)
- **Brand** — Store locator data from commercial brand websites
- **GeoWarehouse** — MPAC property assessment records
- **OSM** — OpenStreetMap branded POI data

### Source ID

The unique identifier for a record within its source. Format varies by source:
- Realtrack: `RT` + digits (e.g. `RT196880`)
- Brand: `BR_` + 5 digits (e.g. `BR_00001`)
- GeoWarehouse: `GW` + 5 digits (e.g. `GW00001`)
- OSM: `OSM_` + 5 digits (e.g. `OSM_00001`)

Use `source_id` as the generic variable name everywhere. Never use `rt_id` as a generic term.

### Raw Data

Scraped or fetched files in their original format — HTML pages, JSON dumps, CSV exports. Stored in `raw-data/` organized by source. Raw data is read-only — engines never modify it. If you re-scrape, you overwrite the raw data and re-run the engine.

---

## Folder Structure

```
cleo-turbo/
├── raw-data/                   Scraped/fetched raw data (read-only)
│   ├── rt/                     Realtrack HTML pages
│   ├── osm/                    OSM POI dumps
│   ├── geowarehouse/           GW exports
│   └── brand/                  Brand store locator data
│
├── engines/                    One engine per data source
│   └── rt/                     Realtrack engine
│       ├── parsers/            Extract stage
│       ├── classifier/         Classify stage
│       ├── address_normalizer/ Normalize stage
│       ├── parcel_resolver/    Resolve Parcels stage
│       ├── pipeline/           Intermediate stage outputs
│       ├── fixtures/           Approved test cases
│       └── schema/             Design docs and plans
│
├── clean-data/                 Final engine output (JSON files, rebuildable)
│   ├── rt/                     One JSON per RT source_id
│   ├── parcels/                One JSON per ARN
│   ├── osm/                    One JSON per OSM source_id
│   └── geowarehouse/           One JSON per GW source_id
│
├── app/                        The web application
│   ├── compiler/               Reads clean-data/, links across sources, writes to DB
│   ├── database/               SQLite — derived tables + CRM tables
│   └── web/                    FastAPI + frontend
│
└── docs/                       Architecture docs, this file
```

**Rules:**
1. Every engine reads from `raw-data/` and writes intermediate outputs to its own `pipeline/` folder.
2. Every engine writes its final output to `clean-data/{source}/`.
3. The Compiler reads from `clean-data/` and writes to the database. It never reads raw-data or pipeline.
4. The web app reads from the database only — never from JSON files directly.
5. If you delete a stage's output, re-run the stage. Nothing else breaks.
6. If you delete the database, re-run the Compiler. CRM data would be lost — back up the database.
7. Re-running an engine means re-running the Compiler afterward to pick up changes.

---

## Principles

1. **Source data is truth.** If the engine output disagrees with the raw source, the raw source wins. Fix the engine.
2. **Stable IDs are the spine.** ARN, RT ID, contact fingerprint, Group ID. Everything references these. They survive rebuilds.
3. **Extraction captures facts, not interpretations.** The Extract stage records what the source says. Classification and judgment happen in later stages.
4. **Editorial data is sacred.** CRM tables (deals, notes, group assignments, engaged status) are never destroyed by an engine rebuild. They reference stable anchors that survive any rebuild.
5. **Groups are manual.** The system can surface candidates ("Lee Greenwood appears on 12 transactions under 8 different entity names") but the grouping decision is always a human choice. See "Why Groups Are Manual Only" below.
6. **The system can always be rebuilt.** Raw data → engines → clean-data → Compiler → database. Delete any derived layer and rebuild it. Only CRM data (Layer 3) requires backup.
7. **Each component is replaceable.** If you want to swap out the geocoder, replace one engine stage. If you want to drop OSM data, delete `clean-data/osm/` and remove the Compiler's OSM reader. Nothing else changes.

---

## Views (Read-Only Data Displays)

Views are pages that display data derived from Clean Records. They do not create or modify business data — they are windows into the data. Users can navigate from a View into CRM to take action.

### Dashboard

Overview of the entire dataset — summary statistics, recent activity, market insights.

### Properties (View)

Browse and search the property registry. Filterable by city, brand category, price range. Each row links to a Property Detail page showing full transaction history, tenants, parcel info, and current owner.

### Transactions (View)

Browse historical real estate transactions. Every exchange of real estate recorded in the system, regardless of whether you or Jamie are involved.

### Map (View)

Geographic visualization of properties, with layers for parcels, tenants, and transaction activity.

---

## CRM (Business Layer)

CRM is the category of all user-curated business activities. It sits on top of the database and is where prospecting, relationship management, and deal tracking happen. CRM tables are **persistent** — they must survive Data Engine rebuilds (see Reconciliation).

The CRM doesn't contain its own copy of contacts and groups. It works with the same `contacts` and `groups` tables that the Compiler builds. The difference is **status** — pool contacts/groups are engine-derived and untouched; engaged contacts/groups have been activated into the CRM through user action.

### Group

A company, partnership, trust, or individual that participates in real estate transactions — buying, selling, leasing, or owning property. Replaces the former terms "entity", "party", and "owner" (as a noun for the concept).

Examples: RioCan REIT, Goldmanco, an individual person who buys/sells property.

**ID format:** `GRP_NNNNN` (e.g. `GRP_00001`)

**Status:** `pool` or `engaged`

A Group is identified by one or more **known names** — the various legal names, trade names, and registration names that appear across transactions. These names are linked together manually to form a single Group.

A Group can be an **Owner** of one or more properties (see Owner below). But "Group" is the entity; "Owner" is the role.

All Groups get a GRP_ ID the moment the Compiler first sees them. Pool groups are visible in search and on transaction views but are not actively tracked. Engaged groups are in your CRM — trackable with deals, contacts, and notes.

Maps to HubSpot: **Companies** (engaged groups only sync to HubSpot)

#### Why Groups Are Manual Only

The V3 problem: auto-linking entities by shared contacts creates runaway chains. Entity A shares a contact with Entity B. Entity B shares a different contact with Entity C. Auto-linking produces A-B-C as one group, even though A and C have nothing to do with each other. The result is massive, meaningless groups that require more work to untangle than they save.

The fix: groups are editorial. A human decides "these contacts and these entities belong together under this parent company name." The system can surface candidates ("Lee Greenwood appears on 12 transactions under 8 different entity names") but the grouping decision is always manual.

### Contact

An individual person. Period. There is one unified Contact table in the system. Whether someone appears as a buyer contact on a Realtrack transaction, a seller representative, or someone you cold-called — they are one Contact.

**ID format:** `CON_NNNNN` (e.g. `CON_00001`)

**Status:** `pool` or `engaged`

All Contacts get a CON_ ID the moment the Compiler first sees them. Pool contacts are visible and searchable — you can see their name, phone, transactions, and company associations. But they're not in your active CRM. Engaged contacts have been promoted through user action and are synced to HubSpot.

A Contact becomes engaged by:
- You manually promoting them from the pool
- Importing them from HubSpot (matched to existing pool record by name)
- Manually creating them (if they're not in the pool at all)

**Name fingerprint:** The stable anchor for a Contact is a normalized first+last name combination — uppercase, trimmed, whitespace collapsed. "Lee Greenwood" appearing on 47 transactions over 20 years is the same human. Within Ontario CRE, name collisions are rare enough that this works as a practical identifier. Can be enhanced with disambiguation signals (same phone number, same address pattern, same associated companies) if collisions arise.

Contacts are associated with Groups. A Contact can move between Groups over time (e.g. Derek Hull moved from H&R REIT to Goldmanco). The system tracks the **association history** — which Group a Contact was associated with on which transaction, and whether they are currently active with that Group. Former associations are visually de-emphasized ("formerly with") but never deleted from the underlying data.

Contact types:
| Type | Description |
|---|---|
| Buyer | Acquired property in a transaction |
| Seller | Disposed of property in a transaction |
| Lessee | Leased property |
| Lessor | Leased property to a tenant |
| Agent | Individual real estate sales representative (see Agent definition) |
| Professional | Non-agent professionals — appraisers, lawyers, accountants, etc. |
| Personal | Someone from your personal circle, not from transaction data |

Contact fields (maps to HubSpot):
| Cleo Field | HubSpot Field | Description |
|---|---|---|
| first_name | firstname | First name |
| last_name | lastname | Last name |
| email | email | Email address |
| phone | phone | Primary phone |
| mobile | mobilephone | Mobile phone |
| job_title | jobtitle | Job title |
| company_name | company | Current company (Group display name) |
| address | address | Street address |
| city | city | City |
| province | state | Province/state |
| postal_code | zip | Postal code |
| type | type_of_contact | buyer, seller, lessee, lessor, agent, professional, personal |
| status | — | pool or engaged |
| source | — | How this contact entered the system (transaction, hubspot, manual) |

HubSpot is the external CRM. Cleo fields **map to** HubSpot fields — the systems stay in sync, but Cleo uses its own terminology and field names. Cleo is the source of truth for transaction-derived data; HubSpot is the source of truth for manually entered CRM enrichment (notes, email threads, sequences). Sync is bidirectional where fields overlap. **Only engaged contacts and groups sync to HubSpot.**

### Deal

A transaction that you or Jamie are actively working on. A Deal associates a Property, one or more Groups, one or more Contacts, and tracks progress through deal stages. Distinct from a **Transaction** (which is a historical fact in the data).

**ID format:** `DEAL_NNNNN` (e.g. `DEAL_00001`)

Deal lifecycle phases:
| Phase | What's happening | HubSpot Stage |
|---|---|---|
| **Prospecting** | Outbound — identifying targets, making connections, stirring things up | Long Shot |
| **Nurturing** | Uncovering deals from what you've stirred up prospecting | Priority Deal / Mandate |
| **Negotiating** | Pushing the most promising opportunities forward — offers, counter-offers | Viable Deal → In Negotiation |
| **Under Contract** | Conditional agreement signed, not yet firm | Under Contract |
| **Firm** | Conditions waived, deal is going to close | Firm |
| **Closed** | Money in the bank, paperwork wrap-up, post-close process | Closed |
| **Lost** | Deal fell through at any stage | Lost |

The phases after Negotiating (Under Contract → Firm → Closed) are **transaction management** — making sure what's been agreed to contractually gets fulfilled. Not a separate category, just the later stages of the same Deal.

Deal fields (maps to HubSpot):
| Cleo Field | HubSpot Field | Description |
|---|---|---|
| name | dealname | Deal name (typically the property address) |
| stage | dealstage | Current stage in the pipeline |
| amount | amount | Expected deal value |
| close_date | closedate | Expected or actual close date |
| deal_owner | hubspot_owner_id | Jamie or Brandon |
| description | description | Deal notes and context |
| next_step | hs_next_step | Next action required |
| priority | hs_priority | Priority level |
| lost_reason | closed_lost_reason | Why the deal was lost |

### Pipeline

The progression of Deals through lifecycle phases. "Fill the pipeline", "load the boat", "pipeline is drying up" — this always refers to the **sales pipeline** of active Deals, never the Data Engine.

The pipeline has a natural flow: **Prospecting → Nurturing → Negotiating → Under Contract → Firm → Closed**. Deals move forward (or fall out as Lost) through these phases.

### List

A saved, named collection of Properties, Groups, and/or Contacts for a specific purpose — typically prospecting campaigns. Used to organize outreach targets.

**ID format:** `LST_NNNNN` (e.g. `LST_00001`)

### Prospecting

The activity of identifying and reaching out to potential deal opportunities. Replaces the former term "outreach." Prospecting turns discoveries from Views into potential Deals in the Pipeline.

---

## Property & Parcel Terms

### Property

A unique real estate parcel in Ontario, identified by a 20-digit ARN. One ARN = one Property. Properties are a read-only derived layer rebuilt from Clean Records — they are NOT manually created.

**ID format:** `PRO_NNNNN` (e.g. `PRO_00001`)

**Stable anchor:** The 20-digit ARN. Property IDs must be persistent across Data Engine rebuilds (see Reconciliation).

### Owner

The Group that currently owns a Property. "Owner" is a **role**, not an entity type. It refers to the buyer from the most recent transaction on a Property. A Group "is an Owner" of properties — it is not "an Owner" as a category of thing.

Usage:
- "RioCan REIT owns 67 properties" (correct)
- "Show me all Owners with 10+ properties" (correct — filtering Groups by the Owner role)
- "Open the Owner page" (incorrect — it's the Groups page)

### Parcel

The provincial assessment parcel polygon from MPAC, identified by a 20-digit ARN. The physical land boundary. Every Property corresponds to exactly one Parcel. The parcel is the **universal linker** — it connects transactions, POIs, and GeoWarehouse data to the same physical piece of land.

### ARN (Assessment Roll Number)

The 20-digit provincial identifier for a parcel of land in Ontario. Assigned by MPAC. This is the single most stable identifier in the system — it never changes for a given piece of land. All property-level references in CRM should anchor to ARN.

**API format:** Strip spaces, right-pad zeros to 20 digits. `21 10 100 025 27110` → `21101000252711000000`

### PIN (Property Identification Number)

An alternative parcel identifier used by GeoWarehouse and Ontario land registry. 9 digits without dash. Can be used to look up the corresponding ARN.

**API format:** Strip dash, keep 9 digits. `14024-0032` → `140240032`

### Site

The physical characteristics of a property — legal description, site area, frontage, depth, zoning code, building square footage. Not a standalone entity, just a group of fields on a Transaction or Property.

### Tenant

A commercial brand or business occupying a Property. Derived from brand store locators and OSM data, not from lease records. A Property can have multiple Tenants.

---

## Transaction Terms

### Transaction

Any exchange of real estate recorded in the system. A historical fact parsed from Realtrack data. Contains seller, buyer, sale date, sale price, consideration breakdown, site details, and broker information.

A Transaction is **not** something you or Jamie are working on — that's a Deal.

### Consideration

The financial breakdown of a Transaction — cash, assumed debt, chattels, chargees, and the verbatim description from the land registry.

### Transferor / Transferee

Ontario Land Registry terminology for seller and buyer, respectively. Used only at the Extract stage internally. Renamed to **Seller** and **Buyer** at the Classify stage. You will never see these terms in the UI or in conversation.

---

## People Associated with Transactions

### Buyer

The party acquiring a property in a Transaction. A structured object with `name` (the company or individual), `contact` (the named individual, if the buyer is a company), `phone`, and `address`.

### Seller

The party disposing of a property in a Transaction. Same structure as Buyer.

### Brokerage

The real estate firm that facilitated a Transaction (e.g. Re/Max, CBRE, Colliers). A company, not an individual.

### Agent

The individual real estate sales representative or broker who facilitated a Transaction, working at a Brokerage. Replaces the ambiguous term "broker" when referring to a person (as opposed to the firm).

### Party Names vs Contact Names

In the extraction stage, transaction participants are captured as two separate things:

**Party names:** The legal entity on the transaction. This is whoever is registered as the transferor or transferee. It could be:
- A company: "ACME Corp Ltd"
- An individual: "Bente & David Firestone"
- A trust: "RBC Trust for RRIFZ046669"
- An estate: "Estate of Ivy Peacock"
- A government entity: "Her Majesty the Queen in right of Ontario..."
- A generic placeholder: "Named Individual(s)"

**Contact names:** People with role prefixes who represent the party. Extracted from lines that begin with Attn:, Pres:, VP:, c/o, Dir:, Sec:, etc. They are people, not entities.

The distinction matters because:
- Party names are what appears on the land registry. They are the legal fact.
- Contact names are the humans associated with the party. They are the people you call.
- An individual can be both: if "Bente & David Firestone" are the sellers with no company, they appear as the party name. There is no separate contact. They ARE the party.
- Classification (is this party name a company or a person?) happens in the Classify stage, not the Extract stage. Extraction records what the source says without judgment.

### Where the Branded Identifier Lives

For any given transaction side (buyer or seller), the branded portfolio identifier — the thing that tells you *who actually owns the property* — can appear in any of **four** fields that RT's HTML surfaces. Never assume it lives in only one. All four must be captured, stored, and considered together when extracting ownership or clustering signals.

| Field | Clean-data path | DB column | What it holds | Example |
|---|---|---|---|---|
| **Party name** | `buyer.parties[].name` / `seller.parties[].name` | `transaction_parties.party_name` | The legal entity on the registry. For branded portfolios this *is* the brand (e.g., "RioCan Holdings Inc"). For SPV portfolios it's the per-property shell (e.g., "West Ridge Orillia Inc"). | "RioCan Holdings Inc" |
| **Trade name** | `buyer.trade_name` / `seller.trade_name` | `transactions.{buyer,seller}_trade_name` | A single management-company / brand name associated with the party. Common in SPV portfolios where the registered entity is a shell and the brand sits here. | "DH Management Inc" |
| **Care of** | `buyer.care_of` / `seller.care_of` | `transactions.{buyer,seller}_care_of` | The "c/o" routing — where mail for this party actually goes. Often the management company's name. | "DH Property Management" |
| **Companies** | `buyer.companies[]` / `seller.companies[]` | `transactions.{buyer,seller}_companies_json` | Additional management-company or brand names extracted from the contact block (e.g., a title line like "Pres, RioCan REIT"). Zero-to-many. | `["RioCan REIT"]` |

Two concrete examples:

- **RioCan** (branded): `party_name = "RioCan Holdings Inc"` — the brand is already on the registry. `trade_name`, `care_of`, `companies` often empty.
- **DH Management** (SPV-style): `party_name = "West Ridge Orillia Inc"` (a shell), `trade_name = "DH Management Inc"` or `care_of = "DH Property Management"` — the brand lives in a different column per transaction.

**Law firms live in a separate field** (`buyer.law_firms[]` / `transactions.{buyer,seller}_law_firms_json`) and are **not** branded-identifier data — they identify the lawyer representing the party on the deal, not the owner. Never mix them into ownership or management-company signals.

Any signal extraction, ownership lookup, clustering algorithm, or UI surface that claims to identify "who owns this property" must read from **all four** of the branded fields per side. Reading only `party_name` misses every SPV-style portfolio; reading only `trade_name` misses every branded-entity portfolio.

---

## What You See at Each Level

### Looking at a Property (PRO_)

- Parcel polygon on a map
- Every transaction (RT) involving this property, in chronological order
- Current and previous owners (from transaction buyer/seller names)
- ARN, PIN, legal description, acreage
- Any Group associations (via contacts on its transactions)
- Tenants (from OSM/Brand data matched to this parcel)
- GeoWarehouse assessment data (if available)

### Looking at a Transaction (RT)

- Seller side: party names, contact names, addresses, law firms
- Buyer side: party names, contact names, addresses, law firms
- Property details: address, PIN, ARN, parcel polygon
- Sale date, sale price, consideration breakdown
- Broker/agent information

### Looking at a Contact (CON_)

- Pool or engaged status
- Every transaction they appear on, which side (seller/buyer), under what company name
- Which Groups they belong to (from group_contacts associations)
- Their most recent transaction suggests their current company affiliation
- Total transaction volume across all their appearances
- Contact details (phone, address — from RT data; email, notes — from CRM enrichment)

### Looking at a Group (GRP_)

- Pool or engaged status
- All known names (the various legal/trade names linked to this group)
- All contacts and their roles within the group
- All transactions where any group contact appears
- All properties involved across those transactions
- Total transaction volume
- Notes, HQ address, website (CRM enrichment, engaged groups only)

---

## ID Format Reference

| Entity | Format | Example | Persistent? | Stable Anchor | Status |
|---|---|---|---|---|---|
| Property | `PRO_NNNNN` | PRO_00001 | Yes (via ARN map) | 20-digit ARN | — |
| Group | `GRP_NNNNN` | GRP_00001 | Yes | Normalized name set | pool / engaged |
| Contact | `CON_NNNNN` | CON_00001 | Yes | Name fingerprint | pool / engaged |
| Deal | `DEAL_NNNNN` | DEAL_00001 | Yes | — | CRM only |
| List | `LST_NNNNN` | LST_00001 | Yes | — | CRM only |
| Parcel | 20-digit ARN | 00260010120100000000 | Yes (provincial) | — | — |
| RT Source | `RT` + digits | RT196880 | Yes (external) | — | — |
| Brand Source | `BR_NNNNN` | BR_00001 | Yes | — | — |
| GW Source | `GW` + 5 digits | GW00001 | Yes | — | — |
| OSM Source | `OSM_NNNNN` | OSM_00001 | Yes | — | — |

---

## Reconciliation

When the Data Engine produces new Clean Records (e.g. after improving the classification or address normalization), the downstream persistent layers (Properties, Groups, Contacts, Deals) must be reconciled — not rebuilt from scratch.

**The principle:** Data Engine improvements improve data quality. CRM data accumulates business value. The two must coexist. A new engine run should never destroy CRM work.

**Stable anchors for reconciliation:**
- Properties anchor to **ARN** (never changes)
- Groups anchor to **normalized name sets** (deterministic, with manual linking)
- Contacts anchor to **name fingerprint + associated Group + transaction context**
- Deals anchor to **ARN + Group** (the property and the counterparty)

**After every engine rebuild, a reconciliation step:**
1. Properties: Match new Clean Records to existing PRO_IDs via ARN. New ARNs get new IDs. No ID is ever reassigned.
2. Groups: Match new buyer/seller names against known_names in the Group registry. New names get new GRP_IDs. Merged names keep existing GRP_IDs.
3. Contacts: Match new contact names against existing Contact records. Surface new contacts for review.
4. Deals: Validate ARN and Group references. Flag any orphaned references.
5. Report: Show what changed, what's new, what needs attention.

---

## Deprecated Terms

These terms should no longer be used. If you encounter them in code, they should be migrated.

| Deprecated Term | Replacement | Notes |
|---|---|---|
| Entity | **Group** | Frontend UI labels, TypeScript types |
| Party | **Group** | Legacy party module |
| Owner (as entity type) | **Group** | "Owner" is now a role, not a category |
| Pipeline (for data processing) | **Data Engine** | "Pipeline" is reserved for CRM deal stages |
| Outreach | **Prospecting** | The activity of finding and contacting targets |
| Broker (person) | **Agent** | The individual. "Brokerage" for the firm. |
| rt_id (as generic) | **source_id** | Use `rt_id` only for actual Realtrack IDs |
| Parse (stage name) | **Extract** | The first engine stage |
| Parcelled (stage name) | **Resolve Parcels** | Clearer name for parcel resolution stage |
| Compiled Record | **Clean Record** | Final engine output in `clean-data/` |
| Versioned Store | — | Removed for now. Stages just overwrite. May revisit later. |
| Connection (CXN_) | — | Dropped. Activity tracking handled by HubSpot. |
| contact_pool (table) | **contacts** with status | One table, pool vs engaged is a status flag, not a separate table |
| group_pool (table) | **groups** with status | Same — one table with status flag |

---

## Conceptual Model

```
RAW DATA (scraped/fetched, read-only)
  raw-data/rt/             Realtrack HTML pages
  raw-data/osm/            OSM POI dumps
  raw-data/geowarehouse/   GW property exports
  raw-data/brand/          Brand store locator data
       │
       ▼
DATA ENGINES (one per source, each writes to clean-data/)
  Realtrack ──→ Extract → Classify → Normalize → Resolve Parcels → Compile
  Brand ──────→ Extract → Normalize → Resolve Parcels → Compile
  GeoWarehouse→ Extract → Normalize → Resolve Parcels → Compile
  OSM ────────→ Extract → Resolve Parcels → Compile
                                                              │
                                                       Clean Records
                                                    (clean-data/ JSON files)
                                                              │
                                                              ▼
                                                         COMPILER
                                              (links across sources,
                                               assigns IDs, writes to DB)
                                                              │
                                                              ▼
                                                          DATABASE
                                                          (SQLite)
                                    ┌────────────────────────┴────────────────────────┐
                                    │                                                 │
                            DERIVED TABLES                                   CRM TABLES
                         (rebuilt by Compiler)                          (persistent, user-curated)
                                    │                                                 │
                         properties (PRO_)                                 deals (DEAL_)
                         transactions (RT)                                 lists (LST_)
                         contacts (CON_) ←── pool/engaged ──→             group_contacts
                         groups (GRP_)   ←── pool/engaged ──→             contact_notes
                         transaction_parties                               group_notes
                         pois
                         property_pois
                         gw_assessments
                                    │                                                 │
                                    └────────────────────────┬────────────────────────┘
                                                              │
                                                              ▼
                                                           WEB APP
                                    ┌─────────────────────────┴──────────────────────┐
                                    │                                                │
                              VIEWS (read-only)                            CRM (user actions)
                              ├─ Dashboard                                 ├─ Promote pool → engaged
                              ├─ Properties                                ├─ Create/manage Deals
                              ├─ Transactions                              ├─ Build Lists
                              └─ Map                                       ├─ Assign Contacts to Groups
                                    │                                      └─ Add notes
                                    │                                                │
                                    └──── Navigate into CRM ────────────────────────→│
                                    │←─── CRM enriches Views ──────────────────────│
```

The arrows between Views and CRM are bidirectional:
- From a Property View, you can promote a pool contact to engaged, create a Deal, or add to a List
- CRM data (deal stage, engaged status, notes) enriches what you see in Views

### The Universal Linker

The **parcel** (identified by ARN) is the thing that connects all data sources:
- An RT transaction happened **on a parcel** (linked by ARN/PIN from the transaction)
- An OSM POI sits **on a parcel** (linked by coords falling inside the polygon)
- GeoWarehouse data describes **a parcel** (linked by PIN/ARN directly)
- A brand store occupies **a parcel** (linked by coords from store locator)

Every data source ultimately connects to physical land. The parcel polygon is how.
