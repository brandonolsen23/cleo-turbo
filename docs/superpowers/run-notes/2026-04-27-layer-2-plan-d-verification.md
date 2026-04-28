# Plan D Verification Notes

**Date:** 2026-04-27
**Group tested:** AGRP_00584 (kingsett, confirmed, 721 parties, 31 anchors)

## Backend (programmatic smoke via TestClient)

All three new endpoints respond on real data with consistent shapes:

| Endpoint | Status | Result |
|---|---|---|
| `/anchors-with-coverage` | 200 | 31 anchors. Top anchor (phone 4166876700) covers 307/721 parties; 5 co-stems present. |
| `/why-tier` | 200 | tier=confirmed, n_categories_passing=3 (all phone/address/contact pass). |
| `/parties` (default) | 200 | total=721. First row: RT197263 seller, kingsett capital, $5.60M, 3-entry signature (address×2 + phone). |
| `/parties?anchor_type=phone&anchor_value=4166876700` | 200 | filtered total=307 — internally consistent with the anchor's coverage. |
| `/parties?sort=match_score&order=desc` | 200 | First 5 scores: [1.0, 1.0, 1.0, 1.0, 1.0] — sorted desc verified. |

Internally consistent: the phone-anchor coverage from `/anchors-with-coverage` (307) matches the filtered total from `/parties` (307). The signature output in `/parties` correctly enumerates the matching group anchors per row.

## Frontend (server-up checks only — JWT-gated paths require an interactive session)

- Vite dev server on port 5174: HTTP 200 on `/explorer/auto-groups/AGRP_00584`.
- TypeScript: `npx tsc --noEmit` clean across all Plan D commits.
- New files served by Vite (verified individually as commits landed).

## Manual click-through verification (your turn)

The interactive flows below need a logged-in browser session. Please verify and note any issues:

1. **Overview tab**: stat cards render with real numbers; "Why this tier" panel shows 3 category rows all marked "passes"; top phrases include `kingsett capital`; numbered corps wall renders.
2. **Anchors tab**: 31 rows; coverage column non-zero on top anchors; at least one row has co-stems badges; "view" links navigate to `/explorer/phones/4166876700`, `/explorer/addresses/roots/40|king`, `/explorer/contacts/<contact>`.
3. **Parties tab**:
   - 9 columns render (date, side, brand phrase, address, contact, phone, price, signature, score).
   - Brand-phrase substring search narrows the list.
   - Side dropdown (All/Buyer/Seller) narrows the list.
   - Anchor filter dropdown lists the 31 group anchors; picking one narrows results.
   - Sort dropdown reorders.
   - Pagination controls appear (721 / 100 = 8 pages).
   - **Row click → SourceViewerDrawer opens** with the actual transaction.

If any of the manual flows above fail, capture details (URL, what failed, console errors) — those need fix-up tasks.

## Plan D scope coverage

- ✅ Three backend endpoints shipped with full test coverage (71/71 tests pass).
- ✅ Frontend tab shell with URL-driven state (`?tab=`).
- ✅ Overview tab (stat cards + Why-tier panel + top phrases + numbered corps).
- ✅ Anchors tab (coverage + co-stems + Layer 1 silo links).
- ✅ Parties tab (filter + sort + pagination + SourceViewerDrawer click-through).
- ✅ Graph + Trail tabs render placeholders pointing at Plan E / Plan F.

## What's next

When you've spot-checked the click-through flows in the browser, the next sub-projects are:

- **Plan E — Graph view** (radial node-edge diagram of one group's anchors and parties).
- **Plan F — Trail view** (single-party evidence threads with conflict highlighting).
- **Plan G — Tuning page + list-page filters** (confidence histogram, "close to promotion" queue, missed-stem diagnostics).

E and F can ship in either order. G is independent of D/E/F.
