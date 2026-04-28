# Layer 2 Plan A — First-Run Verification Notes

**Date:** 2026-04-27
**Branch:** `feat/group-discovery-algorithm`
**Build trigger:** `python -m cleo.discovery_v2` (Layer 1 + Layer 2 in one pass)

## Headline numbers

| Metric | Count |
|---|---|
| Verified stems (`brand_stem`) | 2,297 |
| Phrase mappings (`brand_stem_phrase_map`) | 12,309 |
| Anchor scores (`anchor_uniqueness`) | 283,885 |
| Auto-groups (`auto_groups`) | 1,682 |
| Auto-group anchors (`auto_group_anchors`) | 29,199 |
| Auto-group members (`auto_group_members`) | 71,827 |

### Tier breakdown

| Tier | Count |
|---|---|
| Confirmed | 118 |
| Probable | 1,181 |
| Candidate | 383 |

### Anchor distribution

| Anchor type | Count |
|---|---|
| Contact | 9,184 |
| Address base | 7,829 |
| Address root | 7,645 |
| Phone | 4,541 |

## Success criteria

- **≥50 Confirmed groups**: ✅ 118.
- **Known top-10 operators surface**: ✅
  - **Confirmed**: KingSett (820 members), Conundrum (514), Bonnefield (394), Transglobe (276), Menkes (260), Richcraft (253), CanFirst (244), CAPREIT (234), Castlepoint (212), Fieldgate (207), Goldmanco (196).
  - **Probable**: Metrus (794), RioCan (761), Starlight (693), Skyline (577), Loblaw (522), Minto (441), Cadillac Fairview (398), Berkshire (393), Greenpark (350), Mattamy (342).
- **Multi-tenant building (161 Bay) does NOT seed a group alone**: ✅ The two groups touching 161 Bay (`abacus` and `conundrum`) each have 4 and 10 anchors with only 2–3 at 161 Bay; address alone never seeded.
- **Common-name contacts (Michael Smith, John Smith, etc.) do not seed groups**: ✅ Only 2 cases found across all ~80k contacts (`john smith → northridge candidate`, `michael miller → 571419 candidate`), both demoted to candidate tier.
- **Berkshire mega-cluster failure mode does not recur**: ✅ `berkshire` is a clean Probable group at 393 members, anchored to 75 Scarsdale + the operator phone.

## Tuning observations

These are not bugs — they're real algorithmic behaviors the user wanted surfaced for tuning.

### Over-broad stems at the top

The top 4 groups by member count are not real operators:

| Stem | Members | Display name | Why over-broad |
|---|---|---|---|
| `investments` | 3,623 | marlin spring investments | Position-anchor token that's distinctive enough to clear promotion. Many SPVs end in "investments." |
| `ontario` | 3,040 | ontario superior court of justice | Place-name token that surfaced because 60%+ of party-sides at the court address share "ontario" in their phrase. |
| `farms` | 3,008 | grace farms | Same pattern — "farms" is a position-anchor that clusters at one anchor (probably Bonnefield's address or a farmland-equity broker). |
| `enterprises` | 773 | morgan mae enterprises | Position-anchor that promoted off a single dominant anchor. |

**Fix path:** Either tighten stem promotion (require higher dominance) or add a deny-list of position-anchor tokens that are too generic. The current 0.6 dominance threshold lets these through because the cluster *is* dominant — just the cluster itself doesn't represent a real operator family.

### Notable distinctive 1-grams that DIDN'T promote

These tokens have ≥100 party-sides each but didn't get verified stems:

| Token | n_party_sides | Likely reason |
|---|---|---|
| `ulc` | 531 | Unlimited liability company suffix — cross-border tax structures, scattered across many operators. |
| `advisors` | 432 | Generic suffix; clusters across many real estate advisors. |
| `nominee` | 306 | SPV trustee role; appears across many operators. |
| `kanco` | 231 | Likely lost dominance contest at its anchors. |
| `ks` | 198 | KingSett SPV prefix — overshadowed by `kingsett` at the same phone. |
| `dd` | 162 | Daniel Drimmer's SPV prefix — overshadowed by `starlight` at 4162348444. |
| `dundee` | 123 | Dream's predecessor brand — overshadowed by `dream` at 4163653535. |
| `piret` | 120 | Pure Industrial REIT acronym — overshadowed by `pure`. |
| `mgr` | 158 | Generic management acronym. |
| `h&r` | 132 | Spelling variants ("h&r", "h & r") split the dominance. |
| `cob` | 127 | Continuance/conversion abbreviation. |

This is the "verified-promotion is doing exactly what it's supposed to" finding. **Each operator's primary stem dominates; secondary brand families (DD, KS, Dundee, PIRET) lose the dominance contest and don't get their own stems.** The user can decide whether they want secondary stems by relaxing the rule (e.g., promote a stem if it's the primary stem at *any* anchor, not just *the* dominant one) — but that's a Plan B/C decision, not a Plan A fix.

### Confidence formula behavior

- The Confirmed tier requires confidence ≥ 0.75 AND 3 anchor categories (phone + address + contact). Only 118 of 1,682 groups clear this.
- Probable tier (1,181 groups) is the bulk; many real operators sit here because they're missing a contact anchor (no human name in `transaction_parties.contact_id` rows for those transactions).
- Candidate tier (383 groups) catches edge cases: a single strong phone + 1 corroborating low-score contact.

### Stem extraction artifacts

A few stems emerged from algorithmic shapes rather than from real operators:

- `railway` (324 members, "canadian national railway") — railway-corporate disposals.
- `fairview` (398, "the cadillac fairview corp") — Cadillac Fairview is real, but `fairview` got promoted as the stem.
- `walton` (276, "walton international group") — real operator.
- `morguard` (313, "morguard investments") — real operator.

All defensible.

## Performance

Total Layer 2 build wall-time: **~30 seconds** (after Layer 1 finishes).

- Stage A1 (stems): ~5s
- Stage A2 (anchor scores): ~3s
- Stage A3 (seeding): ~1s
- Stage A4 (expansion): ~20s
- Stage A5 (display + counts): 0.4s (down from 16+ minutes after the bulk-query refactor in commit `5fee652`)

The expansion stage is the dominant cost — a Python double-loop scoring 250k party-sides × 1,682 groups. Acceptable for now per the code review's "S-1" suggestion. If scale doubles, the inverted-index optimization (anchor_value → [group_ids]) becomes attractive.

## What to act on (priority order)

1. **Tune over-broad stems** — `investments`, `ontario`, `farms`, `enterprises` at the top of the list aren't real operator groups. Options: add a deny-list of generic position-anchor tokens, or tighten the dominance threshold beyond 0.6.
2. **Decide policy on secondary stems** — Should `dd`, `ks`, `dundee`, `piret` get their own stems even when they're not dominant? Plan B can revisit; Plan A's rule is "dominance wins" and that's working correctly.
3. **Spot-check the 118 Confirmed groups** by clicking through `/explorer/auto-groups` (default tier filter = Confirmed) and confirming each represents a real operator. Estimated 30 minutes of UI work.
4. **Watch for false positives in Probable tier** — 1,181 groups is a lot to review. Recommended: skim the top 50 by member count, deeper review of ones that look surprising.

## What stayed within scope

- Plan A shipped end-to-end: schema (migration 015) + 5 builder stages + API endpoints + read-only UI tab/list/detail.
- All 22 unit tests pass; 54 explorer route tests pass.
- No changes to existing Groups / Contacts / Properties / Transactions tables or pages — Layer 2 lives entirely in `auto_*` tables and `/explorer/auto-groups`.

Plan B (tenure inference + anti-evidence) and Plan C (cascade UI + user actions) are next, when the user is ready.
