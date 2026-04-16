# Group Discovery Algorithm — Design Spec

**Date:** 2026-04-15
**Status:** Draft — pending implementation plan

## 1. Problem Statement

Cleo's database contains 136,266 groups across 124,544 transactions. Many of these groups are SPVs (special purpose vehicles) belonging to larger portfolios. A single investor like DH Property Management operates through 27+ SPVs — each property owned by a separate corporation. The current system treats each SPV as independent with no knowledge of shared ownership.

Portfolio discovery is Cleo's core value proposition. A realtor who can identify that DH Property Management controls 27 properties worth $420M across industrial and retail has a massive prospecting advantage. Today this requires hours of manual cross-referencing. The goal is to encode Brandon's decision-making process into an algorithm that automates this discovery.

### 1.1 What the Pipeline Currently Captures vs. Loses

**Currently captured:**
- Each SPV name becomes its own GRP_ record
- Contact names from Attn/Pres lines become CON_ records linked to the first party
- Mailing addresses stored in `transaction_mailing_addresses`
- Trade names stored as `seller_trade_name` / `buyer_trade_name` on transactions
- Care-of entities stored as `seller_care_of` / `buyer_care_of`

**Currently lost (not used for linking):**
- Trade names never become groups or linking signals (9,770 unique trade names exist)
- Care-of entities classified but not linked (4,172 unique care-of entities)
- Phone numbers not used for cross-entity matching (e.g., 416-234-8444 appears on 611 groups)
- Address matching not performed (22,210 addresses have 2+ groups)
- Contact cross-referencing not done (11,362 contacts appear on 3+ transactions across 2+ groups)

### 1.2 Scale of the Opportunity

| Metric | Count |
|---|---|
| Total groups | 136,266 |
| Addresses with 2+ groups | 22,210 |
| Addresses with 2 groups (pair clusters) | 12,812 |
| Addresses with 3-10 groups | 7,334 |
| Addresses with 10-29 groups | 971 |
| Addresses with 30+ groups (likely office towers) | 252 |
| Contacts on 3+ TXs, same group (distinctive) | 2,215 |
| Contacts on 3+ TXs, 2+ groups (portfolio operators) | 11,362 |
| Unique trade names | 9,770 |
| Unique care-of entities | 4,172 |

## 2. Architecture: Evidence Layer + Merge Output (Approach C)

The algorithm produces real `group_merges` entries as output — the same mechanism used for manual merges today. No sandbox, no promotion step. A thin evidence layer stores audit trails and supports the iterative development workflow.

### 2.1 Why Not a Sandbox

A parallel "discovery" schema with its own tables creates two representations of the same truth. The promotion step (sandbox → real merge) adds complexity without value. The daily drip mode becomes awkward: new transaction → discovery → sandbox → promote → merge. Simpler to write merges directly.

### 2.2 New Tables (CRM-category, never rebuilt by compiler)

**`discovery_evidence`** — Every signal the algorithm found
- `id` INTEGER PRIMARY KEY
- `run_id` TEXT — which run produced this
- `signal_type` TEXT — 'contact', 'address', 'phone', 'trade_name', 'care_of', 'name_fragment', 'entity'
- `signal_value` TEXT — the normalized signal value
- `source_group_id` TEXT — FK to groups
- `target_group_id` TEXT — FK to groups (the other side of the link)
- `source_id` TEXT — transaction where signal was found
- `rule_id` TEXT — which rule confirmed this (e.g., '4a', '4b', etc.)
- `confidence` REAL — 0.0-1.0
- `iteration` INTEGER — which expansion pass found this
- `created_at` TEXT

**`discovery_runs`** — Metadata per algorithm run
- `run_id` TEXT PRIMARY KEY
- `mode` TEXT — 'full', 'incremental', 'validate'
- `started_at` TEXT
- `completed_at` TEXT
- `stats_json` TEXT — clusters found, merges executed, suggestions created, etc.
- `diff_json` TEXT — what changed since previous run
- `config_json` TEXT — rule parameters used for this run

**`discovery_exclusions`** — Manually flagged false positives
- `id` INTEGER PRIMARY KEY
- `exclusion_type` TEXT — 'address', 'contact', 'phone', 'group_pair', 'entity'
- `exclusion_value` TEXT — the value to exclude (e.g., a law firm address)
- `reason` TEXT — why this was excluded
- `created_by` TEXT
- `created_at` TEXT

**`discovery_ground_truth`** — Known-correct portfolios for validation
- `id` INTEGER PRIMARY KEY
- `portfolio_name` TEXT — human-readable label (e.g., "DH Property Management")
- `anchor_group_id` TEXT — the target/parent group
- `member_group_ids_json` TEXT — JSON array of all GRP_ IDs that belong
- `notes` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### 2.3 Execution Modes

- **`--validate`**: Runs algorithm, compares output to `discovery_ground_truth`, reports precision/recall per portfolio. Does NOT execute merges. Used during development.
- **`--execute`**: Runs algorithm on full dataset, executes auto-confirmed merges, writes suggestions for review. The bulk sort.
- **`--incremental`**: Processes only new/changed transactions since last run. Matches against existing clusters. The daily drip.
- **`--dry-run`**: Like `--execute` but writes a report file instead of merging. For previewing before committing.

### 2.4 Relationship to Existing Systems

- **Suggested Links (group detail page)**: Stays as-is. Discovery suggestions can additionally surface here for groups with pending suggestions.
- **Group merges**: Discovery's output. Same `group_merges` table, same merge execution logic, same unmerge capability.
- **Group analytics**: Refreshed after discovery merges, same as after manual merges.

## 3. The Algorithm

### 3.1 Key Structural Insight: SPVs vs. Management Companies

Each RT transaction typically has TWO types of company names on one side:
- **The SPV** — a property-specific entity (e.g., "Niagara Falls Shopping Centre Inc"). Rarely appears on more than 1-2 transactions.
- **The management/parent company** — the entity that operates the portfolio (e.g., "DH Management Inc"). Appears across many transactions alongside different SPVs.

The management company is the **bridge entity** that connects SPVs. The algorithm must distinguish between these: a company name appearing on 3+ transactions alongside different co-parties is likely a management company, not an SPV.

Management companies appear in multiple fields:
- As a second party name on the transaction (`transaction_parties`)
- As a trade name (`seller_trade_name` / `buyer_trade_name`)
- As a care-of entity (`seller_care_of` / `buyer_care_of`)
- Embedded in mailing address lines (e.g., "DH Management, 160 Shorting Rd")

### 3.2 Signal Types

| Signal | Source Table/Field | Normalization | Notes |
|---|---|---|---|
| Contact | `transaction_parties.contact_id` → `contacts` | Name fingerprint (existing) | Need fuzzy matching for variants (Nina Wine / Nina Hagler Wine / Nina Hagler-Wine) |
| Address | `transaction_mailing_addresses` | Strip entity prefixes, normalize street/city/postal | "DH Management, 160 Shorting Rd" → extract both trade name AND address |
| Phone | `contacts.phone` | Strip formatting, normalize to 10 digits | Watch for near-misses (416-365-5055 vs 416-265-5055) |
| Management Company | `transaction_parties` (multi-party), trade names, care-of | Normalize like group names | The primary bridge signal |
| Name Fragment | First two significant words of `groups.normalized_name` | Uppercase, strip legal suffixes | "DH Management" from "DH Management Inc" |
| Entity (shared) | `transaction_parties.group_id` | Existing group normalization | Same GRP_ appearing on transactions with different contacts |

### 3.3 Pipeline Steps

**Step 0: Signal Extraction**
Runs after compiler rebuild (or on new transactions in incremental mode). Extracts raw signals from the main DB into `discovery_evidence`:
- All mailing addresses, normalized and deduplicated
- All contacts with date ranges per group (first/last transaction date)
- All phones, normalized
- All trade names and care-of entities
- All name fragments
- Classification of company names as likely-SPV vs. likely-management-company

**Step 1: Anchor Seeding (Exact Match Clustering)**
Find groups that share identical signals:
- Same normalized mailing address
- Same contact
- Same phone
- Same management company name

These become initial anchor clusters. Each anchor has a set of member groups and confirmed signals.

**Step 2: Name Fragment Expansion**
For each cluster, extract distinctive name fragments (first two significant words). Search globally for other groups matching those fragments. A name fragment is "distinctive" if it appears on fewer than N groups (threshold TBD, likely 10-20). Common prefixes excluded: "Estate of", "Bank of", "City of", "Corporation of", etc.

Name fragment alone is NOT enough to confirm — it only identifies candidates for further signal matching.

**Step 3: Contact Tenure Establishment**
For each contact, determine their tenure per group:
- First and last transaction date with that group
- If a contact appears on 2+ groups with clean date partitioning (Group A: 2005-2015, Group B: 2016-2025, no overlap), detect as career change and assign separate tenures
- Distinctiveness check: a contact whose appearances all cluster into a single anchor is "distinctive" (safe to use as a standalone signal within tenure). A contact split across unrelated anchors requires a second signal.
- Manual tenure overrides via `discovery_manual_tenures` (future)

**Step 4: Anchor-Based Extension (Rule Hierarchy)**
The core matching pass. Use confirmed anchors to discover new SPVs. Rules require at least two independent signals unless the contact is empirically distinctive.

| Rule | Signals Required | Confidence | Action |
|---|---|---|---|
| 4a | Management company match + Contact match | 100% | Auto-confirm |
| 4b | Contact match + Address match | 99% | Auto-confirm |
| 4c | Management company match + Address match | High | Auto-confirm |
| 4d | Management company match + Phone match | High | Auto-confirm |
| 4e | Distinctive contact alone (within tenure) | High | Auto-confirm |
| 4f | Contact + distinctive name fragment (within tenure) | High | Auto-confirm |
| 4g | Phone match + name fragment or address | Medium | Auto-confirm |
| 4h | Contact (within tenure) + address change bridged by management company | High | Confirm + register address change |
| 4i | Address alone (confirmed cluster address, no red flags, SPV-pattern name) | Medium-High | **Suggest only** — never auto-confirm |
| 4j | Single signal only (address alone, phone alone, name fragment alone) | None | No action |

**Key rule: address alone NEVER auto-confirms.** An address is a location, not an identity. It becomes a high-confidence suggestion when the surrounding context is clean (long cluster history at that address, SPV-pattern entity name, no red flags), but requires human review.

**Red flags that downgrade address-only suggestions:**
- Address has 10+ unrelated groups (likely office building)
- The unknown contact has transaction history with a different address/cluster
- Entity name matches known law firm, broker, or property management company serving multiple clients
- Transaction date is outside the active date range of that address for the cluster

**Key rule: management company + contact is the strongest pair.** This is because SPVs sometimes use the property address (not the management office) as the mailing address, so address can be unreliable. But a matching management company name + matching contact is unambiguous.

**Step 5: Iterative Reprocessing**
After Step 4, anchors have grown — new addresses confirmed, new contacts added, new name variants discovered. Run Step 4 again with the expanded signal set. Repeat until convergence (no new confirmations).

Critical: only auto-confirmed outputs (4a-4h) feed into the next iteration. Suggestions (4i) and no-actions (4j) never become anchors without human confirmation.

Typically converges in 2-3 iterations. This is what enables the DH portfolio to grow across address eras:
- Iteration 1: Seed at 180 Shorting, Dan Hagler. Pulls in ~15 modern transactions.
- Iteration 2: Dan Hagler bridges to 160 Shorting (2002-2012 era). Youthdale Ltd bridges to Nina Wine. 416-265-2859 confirms Nina's transactions.
- Iteration 3: Dan Hagler bridges to 2555 Eglinton (1997-2001 era). All 36 transactions confirmed.

**Step 6: Cluster Splitting**
After convergence, review each cluster for internal inconsistency. If a cluster's transactions partition into two groups with zero contact/address/phone/entity overlap, split it.

Example: "Canadian Commercial" matches 30 entities, but 15 cluster around Donald Darroch + 20 Bay St and 15 around Charles Miller + 484 Waterloo St. Zero bridges between the two groups. Split into two independent clusters.

Splitting criteria: within a cluster, find connected components using contact + address + phone links. Each disconnected component becomes its own cluster.

**Step 7: Scoring and Output**
Each cluster gets a confidence score based on:
- Number of confirmed entities
- Number of independent signal types supporting it
- Depth of evidence chain (direct vs. multi-hop)
- Internal consistency of contacts, addresses, and name patterns

Output:
- Auto-confirmed merges → execute directly into `group_merges`
- Suggestions → write to suggestion queue for review UI
- Evidence trails → write to `discovery_evidence`
- Run log → write to `discovery_runs` with diff from previous run

## 4. The DH Property Management Case Study

Reference implementation — the algorithm must replicate Brandon's manual discovery of this 30+ SPV portfolio.

### 4.1 Portfolio Summary

- **Total transactions:** 36 (27 Dan Hagler, 9 Nina Wine)
- **Total portfolio value:** ~$420M across 27 years (1997-2024)
- **Unique SPVs:** 28 (each property-specific corporation)
- **Management company variants:** DH Management Inc, DH Management, DH Property Management, DH Property Management Inc

### 4.2 Signal Coverage

| Signal | Coverage | Notes |
|---|---|---|
| Contact (Dan Hagler or Nina Wine) | 36/36 (100%) | Every transaction has one |
| Mailing address (3 eras) | 36/36 (100%) | Eglinton → 160 Shorting → 180 Shorting |
| Phone | 26/36 (72%) | 10 older transactions lack phone |
| Trade/management company name | 18/36 (50%) | Only present when RT captures italic tag |

### 4.3 Address Evolution (3 Eras)

1. **1997-2001:** 2555 Eglinton Ave E, Ste 212/222, Scarborough, M1K 5J1 (c/o "Youthdale Ltd")
2. **2002-2012:** 160 Shorting Rd, Toronto, M1S 3S6 (Dan bought the Shorting Rd complex in Dec 2001 — RT23898 — and moved operations there)
3. **2013-present:** 180 Shorting Rd, Toronto, M1S 3S7 (operating as "DH Property Management")

Dan Hagler's contact continuity bridges all three eras. Without him appearing at both old and new addresses, the algorithm would see three separate clusters.

### 4.4 Dan Hagler ↔ Nina Wine Bridge

Nina Wine (also "Nina Hagler Wine", "Nina Hagler-Wine") is connected to the DH portfolio through 4 independent signals:
1. **Shared entity:** Youthdale Ltd appears on Dan Hagler transactions (DH-17, DH-18) AND Nina Wine transactions (Nina-3)
2. **Shared address:** 180 Shorting Rd on both
3. **Shared phone:** 416-265-2859 on DH-3 (Dan) and Nina-3 through Nina-8
4. **Shared trade name:** DH Management / DH Property Management on both

Nina auto-confirms through the Youthdale Ltd bridge + phone overlap. She does NOT rely on address alone.

### 4.5 The Isshak Scenario (False Positive Prevention)

John Isshak listed as Pres of "DH Property Management Inc" for a Windsor property. Different phone, different address, different city. Corp name matches exactly but nothing else does.

Algorithm behavior: management company name alone = Rule 4j (no action). Correctly NOT linked. Would need a matching contact, address, or phone to trigger any rule.

### 4.6 Ground Truth for Validation

All 36 transactions and their SPVs should be recorded in `discovery_ground_truth` as the first test case. The algorithm must find all 36 within 3 iterations. Expected validation results:
- Precision: 100% (no false positives)
- Recall: 100% (all 36 found)

Additional ground truth portfolios to build: RioCan, Canadian Commercial, Starlight/Drimmer.

## 5. Failure Modes and Mitigations

### 5.1 Professional Service Addresses
Law firm and broker addresses are stored in `discovery_exclusions`. Any address with 30+ groups is flagged for review. The 10-29 range (971 addresses) is flagged but may include legitimate large portfolios.

Exclusion is explicit (a curated list), not count-based. This prevents accidentally excluding legitimate large portfolios like Drimmer's 3280 Bloor St (305 groups).

### 5.2 Semi-Distinctive Names (Cluster Splitting)
When a name fragment matches two genuinely separate entities, Step 6 handles this by checking for internal disconnects. If the contact/address graph has disconnected components, it splits.

### 5.3 Cold-Start Sparsity
Entities with only 1 transaction have nothing to cluster against. The algorithm correctly produces no result. Portfolios worth discovering have multiple transactions by definition.

### 5.4 Temporal Boundary Fuzziness
When a contact changes jobs, gap detection prevents false bridging. Clean date-range partition breaks the chain.

### 5.5 Address Changes Without Name Continuity
If a portfolio changes address AND name AND contact simultaneously, no signals bridge the gap. The algorithm correctly treats these as separate. Manual input can bridge them later.

### 5.6 Address-Only False Positives
Prevented by design: address alone NEVER auto-confirms (Rule 4i = suggest only). Red flag checks further filter suggestions: high group count at address, unknown contact with separate history, known professional service address.

## 6. Development Workflow

### 6.1 Iterate → Run → Compare → Correct → Re-run

1. Populate `discovery_ground_truth` with known portfolios (DH, RioCan, Canadian Commercial, Drimmer)
2. Run algorithm in `--validate` mode
3. Compare output to ground truth: precision and recall per portfolio
4. Identify missed links or false positives
5. Adjust rules, re-run, compare again
6. Repeat until validation passes

### 6.2 The AI Role

Two complementary functions:
- **Claude (development partner):** Analyzes algorithm output, traces why clusters formed, spots where rules are too loose or too tight, suggests refinements. Works from the evidence trail in `discovery_evidence`.
- **Signal analytics (built into the system):** Queries that surface patterns not yet encoded as rules. E.g., "top 20 phone numbers shared across 5+ groups that the algorithm isn't currently using." Helps Brandon discover new signal types.

### 6.3 Lifecycle

1. **Build & iterate** — refine algorithm against known portfolios until trusted
2. **Bulk run** — process all 136K groups with `--execute`, auto-merge high-confidence clusters
3. **Daily drip** — new transactions come in daily, algorithm runs in `--incremental` mode, auto-sorts into existing or new groups
4. **Continuous improvement** — when errors spotted in the app, trace back to the rule, fix it, re-run. Every improvement benefits all future incoming data.

## 7. Frontend: Discovery Review Page

A new `/discovery` page in the Cleo frontend with three views.

### 7.1 Cluster List View (Landing Page)
All discovered portfolio clusters, ranked by size and confidence:
- Anchor name (e.g., "DH Property Management")
- Member count (number of SPVs/groups in cluster)
- Total portfolio value (sum of member properties)
- Confidence score
- Status: auto-confirmed / needs review / flagged error

Filterable by status, confidence range, portfolio size.

### 7.2 Cluster Detail View
Click into a cluster to see the full evidence chain (similar to the RT Inspector page):
- Left side: member groups with their transactions, addresses, contacts, phones
- Right side: evidence — which signals connected them, which rule fired, what confidence
- Visual lines showing which signals bridge which groups
- Actions: "Confirm cluster" / "Flag error on this link" / "Exclude this group"
- For large clusters (Drimmer = 664 groups): paginated/filtered view

### 7.3 Ground Truth Comparison View
During development, shows known portfolios side-by-side with algorithm output:
- Expected vs. found member counts
- Missing members (false negatives)
- Unexpected members (false positives)
- Per-member evidence summary

### 7.4 Integration with Group Detail Page
Discovery suggestions surface in the existing Suggested Links card on group detail pages. When the algorithm has pending suggestions for a group, they appear alongside the existing address/contact/phone suggestions with richer evidence context.

## 8. Phased Rollout

### Phase 1: Foundation
- Step 0 (signal extraction) + Step 1 (exact match clustering)
- Ground truth table with DH portfolio
- `--validate` mode
- Basic cluster list + detail views in frontend
- Signal analytics queries

### Phase 2: Name + Contact Expansion
- Step 2 (name fragments) + Step 3 (contact tenure)
- Add RioCan, Canadian Commercial to ground truth
- Iterate rules against expanded test cases

### Phase 3: Full Extension
- Steps 4-5 (rule hierarchy + iterative expansion)
- Full rule set with confidence scoring
- Review UI with evidence visualization
- Add Drimmer to ground truth (stress test for scale)

### Phase 4: Production + Drip
- Step 6 (cluster splitting) + Step 7 (scoring/output)
- `--execute` mode for bulk sort
- `--incremental` mode for daily drip
- Manual exclusions and corrections
- Continuous improvement loop

## 9. Open Questions

1. **30+ group threshold:** Should address exclusion be purely list-based (curated exclusions) or also include a count heuristic as a safety net?
2. **Trade names as entities:** Should trade names that appear ONLY in the `<em>` tag and never as a party name become "virtual entities" in the discovery system, or only function as linking signals?
3. **Phone confidence:** Currently "medium" (requires one other signal). Data shows phones are very reliable (416-234-8444 = Drimmer on 611 groups). Should phone be elevated?
4. **Contact tenure persistence:** Should confirmed tenures be CRM data (survives rebuilds) or discovery-layer data (rebuilt each run)?
5. **Name fragment exclusion list:** What prefixes beyond "Estate of", "Bank of", "City of", "Corporation of" should be excluded?
6. **Near-miss phone matching:** 416-365-5055 vs 416-265-5055 (one digit). Should the algorithm detect near-miss phones or is exact match sufficient?
7. **Address normalization depth:** How aggressively to normalize? "160 Shorting" vs "180 Shorting" are different addresses at the same complex. Should adjacent street numbers at the same postal code be treated as potentially related?
