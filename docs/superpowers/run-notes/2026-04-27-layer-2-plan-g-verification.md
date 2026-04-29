# Plan G Verification Notes

**Date:** 2026-04-27
**Branch:** `feat/group-discovery-algorithm`

## Backend smoke (programmatic)

### Histogram
- Total groups: 1,682 (matches auto_groups table exactly)
- Threshold metadata returned: probable=0.40, confirmed=0.75
- Top 5 buckets by count:
  - **[0.70, 0.75): 408 groups** ← the close-to-promotion zone is the largest single bucket
  - [0.55, 0.60): 394 groups
  - [0.40, 0.45): 310 groups
  - [0.65, 0.70): 198 groups
  - [0.50, 0.55): 110 groups

**Tuning insight:** dropping the Confirmed threshold from 0.75 to 0.70 would promote 408 groups in one move. Whether that's right depends on how many of the 408 are real operators — see close-to-promotion data below.

### Close to promotion (default 0.70–0.75)
- Total: 408 groups
- Top 5 by confidence (all sit at 0.749–0.750, literally a rounding away from Confirmed):
  - gpm real property 10 (0.750, 226 members)
  - 9695443 canada (0.750, 31 members)
  - dacon corp (0.749, 16 members)
  - 1364674 ontario (0.749, 14 members)
  - synercapital real estate investment services (0.749, 21 members)

Notable: real operator names appear in this queue ("gpm real property", "synercapital real estate investment services", "dacon corp"). Tuning lever: lowering the threshold by 0.001 would already promote 2 of the top 5.

### Missed stems (default min_n_party_sides=100)
- Total: 18 missed stems
- Top 8 with dominance contests:
  - **ulc** (531 sides) lost to **pure** at phone 4164798590 (Pure Industrial REIT phone, 0.90 share)
  - **advisors** (432 sides) lost to **optrust** at phone 4163620045 (OPB Realty Advisors, 0.09 share — close contest)
  - **nominee** (306 sides) lost to **investments** at phone 4163046000 (0.05 share — close contest)
  - **kanco** (231 sides) lost to **starlight** at phone 4162348444 (Starlight switchboard, 0.65 share)
  - **ks** (198 sides) lost to **kingsett** at phone 4166876700 (KingSett switchboard, 0.98 share — total dominance)
  - **ferme** (174 sides) lost to **deliduc** at phone 6136792346 (1.00 — total wipeout)
  - **quebec** (170 sides) — no winner stem at any phone (place-name token, doesn't concentrate)
  - **authority** (164 sides) — no winner stem (institutional/government)

**Tuning insights:**
- `ks`/`kingsett` and `ulc`/`pure` are clean cases of secondary stems losing to dominant primaries at shared phones — the verified-promotion rule is working as designed.
- `nominee`/`investments` is a low-dominance loss (0.05) — that's a phone where investments barely won. This means lowering the dominance threshold below 0.6 might not help here (neither side dominates).
- `kanco`/`starlight` (0.65 share) — a real close call. If we wanted Kanco to surface as its own stem, the algorithm would need to recognize it as a sub-brand or co-stem, not just lose the dominance contest.
- `quebec`/`authority` have no winning stem because they're place/institutional tokens that don't concentrate at any one phone. Algorithmically correct that they didn't promote.

### List with new columns
Top 5 Confirmed groups (sample):
- kingsett capital — anchor_diversity=3, distinct_contacts=**215**
- conundrum capital — anchor_diversity=3, distinct_contacts=78
- bonnefield farmland ontario iii — anchor_diversity=3, distinct_contacts=57
- transglobe property management — anchor_diversity=3, distinct_contacts=**7**
- menkes developments — anchor_diversity=3, distinct_contacts=28

**Standout finding:** transglobe has 276 parties but only 7 distinct contacts. That's an unusually low contact-to-member ratio (2.5%). Worth investigating whether the algorithm has correctly grouped Transglobe parties or whether the small contact set is an artifact of how Transglobe routes its transactions through a small staff.

### List with close_to_promotion filter
- 408 probable groups in [0.70, 0.75) — matches the histogram bucket exactly. Internal consistency check passes.

## Plan G scope coverage

- ✅ `/tuning/histogram` endpoint (Task 1)
- ✅ `/tuning/close-to-promotion` endpoint (Task 2)
- ✅ `/tuning/missed-stems` endpoint (Task 3)
- ✅ List endpoint extended with `anchor_diversity`, `n_distinct_contacts`, `close_to_promotion` filter (Task 4)
- ✅ Frontend types + Tuning page route + skeleton (Task 5)
- ✅ Confidence histogram component with Recharts + click-to-filter (Task 6)
- ✅ Close-to-promotion table (Task 7)
- ✅ Missed-stems table with adjustable min-sides input (Task 8)
- ✅ List page additions: 2 new columns + close-to-promotion checkbox + Tuning link (Task 9)

## Test count
- Plan G tests added: 14 (3 histogram + 4 close-to-promotion + 4 missed-stems + 3 list extensions)
- Total `tests/test_routes_explorer.py` count: 85 passing
- Backend stack: all green

## Manual click-through (your turn)

Visit `http://localhost:5174/explorer/auto-groups/tuning` in a logged-in browser session and verify:

1. **Histogram** — 20 bars covering [0.00, 1.00], gray/amber/jade color zones, dashed reference lines at 0.40 and 0.75.
2. **Click a bar** — navigates to `/explorer/auto-groups?tier=<tier>` matching the bar's color zone.
3. **Hover a bar** — tooltip shows confidence range and group count.
4. **Close to promotion table** — populated with real probable groups; row click opens the group detail page.
5. **Missed stems table** — populated with the 18 missed stems; the "strongest phone" link navigates to the Layer 1 phone silo page.
6. **Adjust the "Min party-sides" input** — list updates as you type.

Visit `http://localhost:5174/explorer/auto-groups` and verify:
1. **Two new columns** visible (distinct contacts, anchor diversity).
2. **"Close to promotion (0.70–0.75)" checkbox** — toggling narrows the list.
3. **"Tuning →" link** in the header — navigates to the tuning page.

If any flow fails, capture details and we'll fix as a follow-up.

## What's next

- **Plan F — Trail view** (single-party evidence threads with multi-group conflict highlighting). Smaller-scoped than D or G.
- **Plan E — Graph view** (radial node-edge diagram of one group's anchors and parties). Most ambitious; recommend last among the three remaining UI plans.
- **Plan B — Tenure & Anti-evidence** (algorithm extension; original Layer 2 design).
- **Plan C — Cascade & user actions** (algorithm extension; original Layer 2 design).
