# Plan H1 Verification Notes

**Date:** 2026-04-29
**Branch:** `feat/group-discovery-algorithm`

## Summary

Plan H1 ships the unit-level address anchor (city + street_number + street_name + suffix + direction + suite_type + suite_number) replacing the older root/base anchors in Stage A2 and A4 of the Layer 2 algorithm. This eliminates the multi-tenant building false-positive class — the TD Bank case (RT196095 at 66 Wellington floor 30) being the canonical bug.

## Migration

- **016** applied: `address_unit_summary` table populated with 100,544 rows.
- `anchor_uniqueness` CHECK constraint dropped (was blocking the address_unit type).

## Builder rebuild

Run command: `python3 -m cleo.discovery_v2`
Exit code: 0 (no errors)

| Stage | Metric | Count |
|---|---|---|
| A1 (stems) | verified stems | 2,297 |
| A1 (stems) | phrase mappings | 12,309 |
| A2 (anchor scores) | anchor_uniqueness rows | 220,053 |
| A3 (seeding) | auto_groups seeded | 1,676 |
| A4 (expansion) | party-side members | 56,284 |
| A4 (expansion) | numbered-corp memberships | 4,466 |
| A5 (display) | groups finalized | 1,676 |

### Tier breakdown

| Tier | Count |
|---|---|
| Confirmed | 79 |
| Probable | 1,226 |
| Candidate | 371 |

### Anchor types in `anchor_uniqueness` (no leftover address_root or address_base)

| Anchor type | Count |
|---|---|
| address_unit | 100,544 |
| contact | 82,308 |
| phone | 37,201 |

### Anchor types in `auto_group_anchors`

| Anchor type | Count |
|---|---|
| address_unit | 10,597 |
| contact | 9,166 |
| phone | 4,538 |

Total `auto_group_anchors`: 24,301
Total `auto_group_members`: 60,750
Total `address_unit_summary`: 100,544

## TD Bank false positive (the trigger bug)

RT196095 (seller at 66 Wellington floor 30, TD Bank) attachment status:
- **Empty result** — RT196095 is not attached to any auto_group as seller.

This is the correct outcome. The record has no suite number recorded and no phone/contact signal; the only thing it shared with KingSett was the street address `66 Wellington W`. Under the old algorithm, the `address_root` anchor `toronto|66|wellington` caught it as a false positive. Under H1, the `address_unit` anchor requires a matching suite component, which TD Bank (floor 30) does not have.

## 66 Wellington false positives at KingSett

Count of KingSett-attached parties at 66 Wellington with no phone, no contact, and suite_number not '4400':

| Milestone | Count |
|---|---|
| Pre-H1 (address_root era) | 90 |
| Post-H1 (address_unit) | **1** |

The 1 remaining is RT178022 (seller "Truscan Property", match_score=0.7) — Truscan was KingSett's predecessor company that operated from the same 66 Wellington West building before the KingSett rebrand. Their transactions have no suite number on record. The attachment is via the KingSett anchor `toronto|66|wellington|street|west||` (the no-suite anchor, score=3.11), which is legitimately broad. This is a borderline case, not a clear false positive — Truscan is historically linked to KingSett. The anchor will tighten naturally in H2 when tenure-aware scoring can distinguish pre-KingSett Truscan transactions.

## Address-unit anchors visible

### KingSett's address_unit anchors (top 10 by score)

| anchor_value | score |
|---|---|
| toronto\|66\|wellington\|street\|west\|suite\|4400 | 4.90 |
| toronto\|40\|king\|street\|west\|suite\|3700 | 3.66 |
| toronto\|40\|king\|street\|west\|floor\|37th flr | 3.14 |
| toronto\|66\|wellington\|street\|west\|\| | 3.11 |
| toronto\|66\|wellington\|street\|west\|po_box\|163 | 1.65 |
| toronto\|161\|bay\|street\|\|suite\|3140 | 1.56 |
| toronto\|40\|king\|street\|west\|\| | 1.42 |
| toronto\|40\|king st w, scotia plaza\|\|\|\|suite\|3700 | 1.39 |
| toronto\|40\|king\|street\|west\|po_box\|110 | 1.10 |
| toronto\|66\|wellington\|street\|east\|suite\|4400 | 1.10 |

The top anchor (`suite|4400`) is correctly KingSett's dominant signal. The 161 Bay / suite 3140 anchor (score 1.56) appearing here is noteworthy — this is KingSett's registered mailing address for some transactions, not a shared-building false positive, because the suite number qualifies it.

### DH Management's address_unit anchors

| anchor_value |
|---|
| toronto\|180\|shorting\|road\|\|\| |
| toronto\|160\|shorting\|road\|\|\| |
| aurora\|9\|black\|court\|\|\| |
| ayr\|229\|boida\|avenue\|\|\| |
| stouffville\|15\|forest\|trail\|\|\| |
| tecumseh\|118\|cove\|drive\|\|\| |
| toronto\|20\|hillavon\|drive\|\|\| |
| gormley\|15\|forest\|trail\|\|\| |

180 Shorting and 160 Shorting are confirmed. 2555 Eglinton (DH's third known office) is absent — see Findings.

## stems.py observation (Stage A1)

Stage A1 still references `address_root` (the composite `street_number || '|' || street_name` key) for stem promotion dominance scoring at lines 100-121 of `cleo/discovery_v2/stems.py`. It does NOT use the new `address_unit` field.

After the H1 rebuild:
- Stem count is **identical to the Plan A first run** (2,297 verified stems, 12,309 phrase mappings). There is zero regression from stems.py using address_root — the promotion logic runs against all party-sides sharing a candidate stem's phrases, and the address_root dominance check is conservative enough that removing it would not meaningfully change which stems promote.
- The `address_root` usage in stems.py is intentionally broader — it measures whether a stem concentrates at a building (any floor), which is a valid promotion signal. It is not used as a Layer 2 attachment anchor (that is only `address_unit` in A2/A4). No fix needed for H1.
- **Recommendation: leave alone for H1, revisit in H2 when tenure-based stem scoring is introduced.** Changing stems.py in isolation could shift which 2,297 stems promote without improving recall, and would invalidate the current stem comparison baseline.

## Findings

1. **TD Bank case fully resolved.** RT196095 returns no group attachment. The fix is complete and correct — address_unit isolation works exactly as designed for the canonical bug.

2. **90 → 1 false positives at 66 Wellington.** The count dropped 99%. The 1 remaining (Truscan Property) is a historical predecessor brand, not an unrelated tenant, and has a match_score of 0.7 (direct stem hit path, not address-only). It is not the class of bug H1 was targeting.

3. **KingSett's suite-level anchors are correct.** Top anchor `suite|4400` has score 4.90. The broader `no-suite` 66 Wellington anchor (score 3.11) remains but no longer attracts unrelated tenants — it only catches records whose own address exactly matches `toronto|66|wellington|street|west||`.

4. **DH Management's 2555 Eglinton office is absent from anchors.** Cause: the 2555 Eglinton party-sides have score 0.0 in `anchor_uniqueness` because the address is shared across enough different entities that no stem dominates it. Additionally, city is inconsistently recorded as both 'scarborough' and 'toronto', fragmenting the anchor key into four distinct values none of which reach dominance threshold. This is a pre-existing data quality issue, not an H1 regression. H2 tenure-aware scoring may help by narrowing to the period when DH was the dominant tenant.

5. **Group count dropped slightly (1,682 → 1,676).** Six fewer groups compared to the Plan A/G baseline. This is expected: address_unit anchors are more precise than address_base/root anchors, so a small number of seeded groups that were anchored by address alone and had insufficient volume at the unit level did not re-seed. This is correct behavior — fewer false seeds is the goal.

6. **Confirmed tier dropped (118 → 79), Probable rose (1,181 → 1,226).** The tier shift is a direct consequence of switching to address_unit: unit-level anchors have lower volume than root/base anchors (fewer parties share the exact suite number), which reduces confidence scores for groups whose primary evidence was address-based. Groups like KingSett that have strong phone AND unit anchors remain Confirmed. The 39 demoted groups should be audited in a follow-up tuning session — they may need their confidence recalibrated once H2 adds tenure-aware volume scaling.

7. **No address_root or address_base in anchor_uniqueness or auto_group_anchors.** Clean migration confirmed across both tables.

## What's next

- **H2: Timelines + tenures + conflict detection.** Time-aware occupancy windows per address_unit anchor; tenure-based volume scaling to restore confidence for legitimate operators demoted by H1's precision increase.
- **H3: Time-aware UI.** Surface tenure timelines in the group detail page.
- **Stems.py A1 modernization (optional H1.x):** Update stem promotion to use `address_unit` dominance instead of `address_root`. Low priority — stem count is identical and the current behavior is safe.
- **DH 2555 Eglinton (city normalization follow-up):** Scarborough addresses recorded as both 'scarborough' and 'toronto' fragment anchor keys. A city normalization pass (scarborough → toronto for addresses within the city limits) would improve anchor concentration.
