# Labeling Tenure-Awareness (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the labeling workspace tenure-aware so contact-based matches carry the signal a human uses: the transaction date and whether a "corporate" co-signal (trade_name / address / party brand) supports the match, instead of relying on sticky personal signals (phone, contact name alone) that follow a person across jobs.

**Architecture:** Expose `transactions.sale_date` through the party view so the UI and training export can see it; add a post-pass over the auto-proposed links that flags contact_name and phone proposals as "caution" unless corroborated by a corporate-category field match on the same pair; show the caution visually in the verdict bar so the human can remove bad proposals quickly.

**Tech Stack:** Python 3.12 + FastAPI + SQLite (backend), React 19 + TypeScript + Radix UI Themes + Phosphor Icons (frontend).

**Scope note:** this plan covers the three refinements the user agreed to (sale_date exposure, corroboration flag, phone demotion). It does NOT cover the optional "contact timeline" sidebar (item 4 from the brainstorm) — that can be a follow-up plan if the flags here aren't sufficient.

---

## File map

**Backend (Python):**
- `cleo/labeling/party_view.py` — add `sale_date` to the returned dict.
- `cleo/web/routes/labeling.py` — include `sale_date` on the `left` and `right` objects in the training export.
- `tests/test_labeling_party_view.py` — fixture needs `sale_date` column; extra assertion.
- `tests/test_labeling_operations.py` — fixture needs `sale_date` column (not used directly but must not break schema).

**Frontend (TypeScript/React):**
- `frontend/src/types/index.ts` — add `sale_date` to `LabelingPartyView`.
- `frontend/src/components/labeling/PartyCard.tsx` — show `sale_date` in the card header.
- `frontend/src/components/labeling/proposals.ts` — extend `PendingLink` with `caution`; add corroboration post-pass (`flagUncorroborated`); call it after `proposeExactLinks` + `proposeLearnedLinks`.
- `frontend/src/pages/LabelingSessionPage.tsx` — invoke `flagUncorroborated` on the combined list before `setPendingLinks`.
- `frontend/src/components/labeling/VerdictBar.tsx` — render caution state on badges (amber outline + "contact only" / "phone only" tag).

No new files. No new DB columns, migrations, or API endpoints — everything needed is already in the DB (`transactions.sale_date`).

---

## Task 1: Backend — expose `sale_date` on party view

**Files:**
- Modify: `cleo/labeling/party_view.py:27-32`, `cleo/labeling/party_view.py:84-95`
- Modify: `tests/test_labeling_party_view.py:13-19` (add column), `tests/test_labeling_party_view.py` (extend first test)
- Modify: `tests/test_labeling_operations.py:8-14` (add column so fixture schema matches)

- [ ] **Step 1: Update the failing test first**

Open `tests/test_labeling_party_view.py`. Change the `CREATE TABLE transactions` block in `_make_db` from:

```python
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
```

to:

```python
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
```

In the first test `test_party_view_aggregates_all_fields`, change the initial INSERT to include a sale_date value, and add a sale_date assertion.

Change:

```python
    conn.execute(
        "INSERT INTO transactions (source_id, buyer_trade_name, buyer_care_of, "
        "buyer_law_firms_json, buyer_companies_json) VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "DH Management Inc", "", json.dumps(["Smith LLP"]),
         json.dumps(["DH Properties"]))
    )
```

to:

```python
    conn.execute(
        "INSERT INTO transactions (source_id, sale_date, buyer_trade_name, buyer_care_of, "
        "buyer_law_firms_json, buyer_companies_json) VALUES (?, ?, ?, ?, ?, ?)",
        ("RT148276", "2005-04-18", "DH Management Inc", "",
         json.dumps(["Smith LLP"]), json.dumps(["DH Properties"]))
    )
```

And add this assertion after the existing ones in the same test:

```python
    assert view["sale_date"] == "2005-04-18"
```

- [ ] **Step 2: Add the same sale_date column to the operations test fixture**

Open `tests/test_labeling_operations.py`. In `_make_db`, change the `CREATE TABLE transactions` block from:

```python
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
```

to:

```python
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
```

No new assertions needed here — this test doesn't exercise sale_date. It just needs a schema that matches production so `get_party_view` doesn't fail on the missing column once we change its SELECT to include sale_date.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_labeling_party_view.py tests/test_labeling_operations.py -v`
Expected: `test_party_view_aggregates_all_fields` fails with `KeyError: 'sale_date'` (view dict has no such key yet). Other tests should still pass.

- [ ] **Step 4: Implement the backend change**

Open `cleo/labeling/party_view.py`. The current fetch is `SELECT * FROM transactions WHERE source_id = ?` which already pulls all columns, including the new one — so the DB read is fine. The change is to actually return the value.

Before the `return { ... }` block (around line 84), add:

```python
    sale_date = tx["sale_date"] if "sale_date" in tx.keys() else None
```

Then add `"sale_date": sale_date,` to the returned dict. The full returned dict becomes:

```python
    return {
        "source_id": source_id,
        "side": side,
        "sale_date": sale_date,
        "party_rows": party_rows,
        "trade_name": trade_name,
        "care_of": care_of,
        "companies_other": companies_other,
        "law_firms": law_firms,
        "contacts": contacts_out,
        "mailing": mailing,
        "phones": phones,
    }
```

The `if "sale_date" in tx.keys() else None` guard keeps it robust if some test fixture omits the column — we return None, don't crash.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_labeling_party_view.py tests/test_labeling_operations.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add cleo/labeling/party_view.py tests/test_labeling_party_view.py tests/test_labeling_operations.py
git commit -m "feat(labeling): expose sale_date in party view

Adds sale_date to the dict returned by get_party_view, sourced from
transactions.sale_date. Consumers (labeling UI card header, training
export) will use it to make contact-match decisions tenure-aware."
```

---

## Task 2: Frontend — show `sale_date` in the PartyCard header

**Files:**
- Modify: `frontend/src/types/index.ts` (find the `LabelingPartyView` interface)
- Modify: `frontend/src/components/labeling/PartyCard.tsx:48-56`

- [ ] **Step 1: Add `sale_date` to the TypeScript type**

Open `frontend/src/types/index.ts`. Find the `LabelingPartyView` interface (search for `export interface LabelingPartyView`). Add `sale_date` after `side`:

```typescript
export interface LabelingPartyView {
  source_id: string;
  side: "buyer" | "seller";
  sale_date: string | null;
  party_rows: { id: number; party_name: string | null; phone: string | null; contact_id: string | null }[];
  trade_name: string | null;
  care_of: string | null;
  companies_other: string[];
  law_firms: string[];
  contacts: { id: string; name: string; role: string | null; phone: string | null; job_title: string | null }[];
  mailing: { display: string; city: string; province: string; postal: string } | null;
  phones: string[];
}
```

- [ ] **Step 2: Show `sale_date` in the PartyCard header**

Open `frontend/src/components/labeling/PartyCard.tsx`. Find the card header block (around lines 48-56):

```tsx
      <div className="px-4 py-2 border-b border-[var(--gray-4)] flex items-center justify-between">
        <Heading size="2">{view.source_id}</Heading>
        <Badge size="1" variant="soft" color={view.side === "buyer" ? "jade" : "amber"}>
          {view.side}
        </Badge>
      </div>
```

Replace with:

```tsx
      <div className="px-4 py-2 border-b border-[var(--gray-4)] flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Heading size="2">{view.source_id}</Heading>
          {view.sale_date && (
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              · {view.sale_date}
            </Text>
          )}
        </div>
        <Badge size="1" variant="soft" color={view.side === "buyer" ? "jade" : "amber"}>
          {view.side}
        </Badge>
      </div>
```

The date appears as a muted string next to the source_id (e.g. `RT62723 · 2005-04-18`).

- [ ] **Step 3: Type-check**

Run: `cd /Users/brandonolsen23/cleo-turbo/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual smoke test**

With both servers running (`localhost:5174`), open any labeling session and run a seed. Verify both party cards show the sale_date next to the source_id in the header. If a transaction genuinely has no sale_date, the header just shows the source_id alone — no "· " visible.

- [ ] **Step 5: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/types/index.ts frontend/src/components/labeling/PartyCard.tsx
git commit -m "feat(labeling): show sale_date in party card header

Humans can now see the transaction date of each compared party
directly in the comparison view. Needed for judging whether a
contact-based match is temporally plausible within a portfolio's
known tenure window for that contact."
```

---

## Task 3: Backend — include `sale_date` in the training export

**Files:**
- Modify: `cleo/web/routes/labeling.py` (find `_build_export` and the `pairs.append` block inside it)

- [ ] **Step 1: Include `sale_date` in the exported `left`/`right` objects**

Open `cleo/web/routes/labeling.py`. Find the `_build_export` function and the block inside its verdict loop that builds `pairs.append({...})`. Currently:

```python
        pairs.append({
            "verdict": v["verdict"],
            "rationale": v["rationale"],
            "left":  {"source_id": v["left_source_id"], "side": v["left_side"],
                      "fields": _export_fields(left)},
            "right": {"source_id": v["source_id"], "side": v["side"],
                      "fields": _export_fields(right)},
            "links": links,
            "seed": seed_info,
            "created_at": v["created_at"],
        })
```

Change to include `sale_date` on both sides (pulled from the party views already fetched):

```python
        pairs.append({
            "verdict": v["verdict"],
            "rationale": v["rationale"],
            "left":  {"source_id": v["left_source_id"], "side": v["left_side"],
                      "sale_date": (left or {}).get("sale_date"),
                      "fields": _export_fields(left)},
            "right": {"source_id": v["source_id"], "side": v["side"],
                      "sale_date": (right or {}).get("sale_date"),
                      "fields": _export_fields(right)},
            "links": links,
            "seed": seed_info,
            "created_at": v["created_at"],
        })
```

The `(left or {}).get("sale_date")` guards against the view being None (which can happen if the underlying transaction was deleted between verdict creation and export — unlikely but cheap to defend).

- [ ] **Step 2: Manually verify the export shape**

With the backend reloaded, hit the export endpoint for any session that has verdicts. Replace `<TOKEN>` and `<SID>`:

```bash
curl -s http://localhost:8099/api/labeling/sessions/<SID>/export \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); p=d['pairs'][0] if d['pairs'] else {}; print(json.dumps({'left': p.get('left'), 'right': p.get('right')}, indent=2))"
```

Expected: printed JSON has `sale_date` on both `left` and `right` objects (value may be null if the underlying RT has no date, but the key must be present).

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add cleo/web/routes/labeling.py
git commit -m "feat(labeling): include sale_date in export pair objects

The training export now carries sale_date on each left/right party so
downstream algorithm design can learn tenure patterns (e.g. same
contact at different addresses across a date gap likely indicates a
job change)."
```

---

## Task 4: Frontend — corroboration flag on auto-proposed contact/phone links

**Files:**
- Modify: `frontend/src/components/labeling/proposals.ts` (entire file — several edits)

This task adds a single post-pass that scans the combined proposals list and flags any `contact_name` or `phone` link that has no corroborating "corporate" link between the same party pair. No other logic changes — exact and learned proposals still run first.

- [ ] **Step 1: Extend `PendingLink` with a `caution` field**

Open `frontend/src/components/labeling/proposals.ts`. Change the existing `PendingLink` type (line 7) from:

```typescript
export type PendingLink = LabelingLinkInput & { auto?: "exact" | "learned" };
```

to:

```typescript
export type PendingLink = LabelingLinkInput & {
  auto?: "exact" | "learned";
  // Set when an auto-proposed link is considered weak on its own and the
  // user should double-check before confirming. "contact_only" = a
  // contact_name match with no corporate co-signal. "phone_only" = a phone
  // match with no corporate co-signal. Personal signals like these can
  // follow an individual across jobs, so we surface them but don't give
  // them the same confidence as a corroborated match.
  caution?: "contact_only" | "phone_only";
};
```

- [ ] **Step 2: Add the `CORPORATE_FIELDS` constant and the corroboration pass**

In the same file, immediately below the `extractValues` function (around line 30) add:

```typescript
/** Field types we treat as "corporate" — brand/entity/location evidence
 * that ties a party to a specific organization. A contact_name or phone
 * match is only strong when at least one of these also matches between
 * the same pair, because people (and their direct phone lines) move
 * between jobs while keeping the same name/number. */
const CORPORATE_FIELDS: ReadonlySet<FieldType> = new Set<FieldType>([
  "party_name", "trade_name", "care_of", "company_other", "law_firm", "address",
]);

function isCorporate(ft: FieldType): boolean {
  return CORPORATE_FIELDS.has(ft);
}

/** Post-pass: mark contact_name and phone links as "caution" when no
 * corporate-category link exists in the same proposals list.
 *
 * Operates on the combined (exact + learned) list because corroboration
 * can come from either kind of proposal. Mutates and returns the same
 * array for convenience. */
export function flagUncorroborated(links: PendingLink[]): PendingLink[] {
  const hasCorporate = links.some(
    (l) => isCorporate(l.from_field_type) || isCorporate(l.to_field_type),
  );
  for (const l of links) {
    if (l.from_field_type === "contact_name" || l.to_field_type === "contact_name") {
      if (!hasCorporate) l.caution = "contact_only";
    } else if (l.from_field_type === "phone" || l.to_field_type === "phone") {
      if (!hasCorporate) l.caution = "phone_only";
    }
  }
  return links;
}
```

Note: the function runs once per party pair and checks if *any* corporate-field link is in the proposal list. That's the right granularity — we're asking "does this pair have any corporate evidence at all?". If yes, contact and phone are trustworthy for this pair. If no, both are flagged.

- [ ] **Step 3: Wire the post-pass into the session page**

Open `frontend/src/pages/LabelingSessionPage.tsx`. Find the import from `../components/labeling/proposals`:

```typescript
import {
  type PendingLink, proposeExactLinks, proposeLearnedLinks,
  computeLearnedPairs, stripAuto,
} from "../components/labeling/proposals";
```

Change to add `flagUncorroborated`:

```typescript
import {
  type PendingLink, proposeExactLinks, proposeLearnedLinks,
  computeLearnedPairs, stripAuto, flagUncorroborated,
} from "../components/labeling/proposals";
```

Find the `loadCandidate` function. It currently has:

```typescript
    if (leftParty) {
      const exact = proposeExactLinks(leftParty, view);
      const learned = proposeLearnedLinks(leftParty, view, learnedPairs, exact);
      setPendingLinks([...exact, ...learned]);
    } else {
      setPendingLinks([]);
    }
```

Change the `if (leftParty)` branch to apply the flag pass before `setPendingLinks`:

```typescript
    if (leftParty) {
      const exact = proposeExactLinks(leftParty, view);
      const learned = proposeLearnedLinks(leftParty, view, learnedPairs, exact);
      setPendingLinks(flagUncorroborated([...exact, ...learned]));
    } else {
      setPendingLinks([]);
    }
```

Find the `reopenVerdict` function — it also rebuilds proposals when reloading a pair. It currently has:

```typescript
      const exact = proposeExactLinks(left, right);
      const learned = proposeLearnedLinks(left, right, learnedPairs, exact);
      setPendingLinks([...exact, ...learned]);
```

Change to:

```typescript
      const exact = proposeExactLinks(left, right);
      const learned = proposeLearnedLinks(left, right, learnedPairs, exact);
      setPendingLinks(flagUncorroborated([...exact, ...learned]));
```

- [ ] **Step 4: Type-check**

Run: `cd /Users/brandonolsen23/cleo-turbo/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/labeling/proposals.ts frontend/src/pages/LabelingSessionPage.tsx
git commit -m "feat(labeling): flag contact_name and phone auto-proposals as caution when uncorroborated

Adds flagUncorroborated post-pass that sets caution='contact_only' or
'phone_only' on auto-proposed links when no corporate-category
(trade_name / care_of / company_other / law_firm / address / party_name)
link exists between the same pair.

Personal signals (contact name, direct phone) follow individuals
across jobs. A match on those alone is not evidence of shared
portfolio — the human should double-check before confirming. The
caution flag is used by VerdictBar to render these with a visual
warning (Task 5). Submit still includes them; the user removes what
they decide is wrong."
```

---

## Task 5: Frontend — visual caution treatment in VerdictBar

**Files:**
- Modify: `frontend/src/components/labeling/VerdictBar.tsx` (the badge rendering block near the bottom)

- [ ] **Step 1: Add `Warning` icon import**

Open `frontend/src/components/labeling/VerdictBar.tsx`. Find the phosphor-icons import line (around line 3):

```typescript
import { CheckCircle, XCircle, SkipForward, Trash, Sparkle } from "@phosphor-icons/react";
```

Change to:

```typescript
import { CheckCircle, XCircle, SkipForward, Trash, Sparkle, Warning } from "@phosphor-icons/react";
```

- [ ] **Step 2: Render the caution state on each badge**

Find the `{pendingLinks.map((l, i) => ( ... ))}` block near the bottom of the component. Currently each `<Badge>` looks like:

```tsx
            <Badge key={i} size="1"
                   variant={l.auto ? "outline" : "soft"}
                   color={l.kind === "exact" ? "jade" : "blue"}>
              {l.auto && <Sparkle size={10} weight={l.auto === "learned" ? "fill" : "regular"} />}
              {l.from_field_type}:{l.from_field_value}
              {" → "}
              {l.to_field_type}:{l.to_field_value}
              {l.auto && <span style={{ marginLeft: 4, opacity: 0.7 }}>· {l.auto}</span>}
              <button className="ml-1 opacity-70 hover:opacity-100"
                      onClick={() => setPendingLinks(pendingLinks.filter((_, j) => j !== i))}>
                <Trash size={10} />
              </button>
            </Badge>
```

Replace the entire `<Badge>` block with:

```tsx
            <Badge key={i} size="1"
                   variant={l.auto ? "outline" : "soft"}
                   color={
                     l.caution ? "amber"
                     : l.kind === "exact" ? "jade"
                     : "blue"
                   }
                   title={
                     l.caution === "contact_only"
                       ? "Contact name match with no corporate co-signal (trade name / address / party brand). Personal names follow people across jobs — double-check this pair is actually the same portfolio."
                       : l.caution === "phone_only"
                       ? "Phone match with no corporate co-signal. Direct/personal phone numbers follow individuals across jobs — double-check."
                       : undefined
                   }>
              {l.caution
                ? <Warning size={10} weight="fill" />
                : l.auto && <Sparkle size={10} weight={l.auto === "learned" ? "fill" : "regular"} />}
              {l.from_field_type}:{l.from_field_value}
              {" → "}
              {l.to_field_type}:{l.to_field_value}
              {l.caution && (
                <span style={{ marginLeft: 4, opacity: 0.8 }}>
                  · {l.caution === "contact_only" ? "contact only" : "phone only"}
                </span>
              )}
              {l.auto && !l.caution && (
                <span style={{ marginLeft: 4, opacity: 0.7 }}>· {l.auto}</span>
              )}
              <button className="ml-1 opacity-70 hover:opacity-100"
                      onClick={() => setPendingLinks(pendingLinks.filter((_, j) => j !== i))}>
                <Trash size={10} />
              </button>
            </Badge>
```

Caution beats auto for icon/tag display: a warning-flagged badge shows the Warning icon and "contact only" / "phone only" tag (no "· exact" or "· learned" suffix), and the color is amber regardless of kind.

- [ ] **Step 3: Update the summary line to mention caution**

Currently the summary line above the badges says "auto — review & remove any wrong ones · Shift+A to clear". Let's widen it to also nudge users when cautions are present.

Find the block:

```tsx
          {pendingLinks.some((l) => l.auto) && (
            <span className="text-[11px] flex items-center gap-1"
                  style={{ color: "var(--gray-9)" }}>
              <Sparkle size={10} /> auto — review &amp; remove any wrong ones · Shift+A to clear
            </span>
          )}
```

Replace with:

```tsx
          {pendingLinks.some((l) => l.auto) && (
            <span className="text-[11px] flex items-center gap-1"
                  style={{ color: "var(--gray-9)" }}>
              <Sparkle size={10} /> auto — review &amp; remove any wrong ones · Shift+A to clear
              {pendingLinks.some((l) => l.caution) && (
                <span style={{ color: "var(--amber-11)", marginLeft: 6 }}>
                  <Warning size={10} weight="fill" /> amber = personal signal without corporate corroboration
                </span>
              )}
            </span>
          )}
```

- [ ] **Step 4: Type-check**

Run: `cd /Users/brandonolsen23/cleo-turbo/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual smoke test**

With both servers running, open a labeling session where the reference party has at least one contact_name or phone value that also appears on a candidate but the two parties share NO corporate field.

Expected: the auto-proposed contact_name or phone badge appears amber-outlined with a Warning icon and "· contact only" (or "· phone only") text. Tooltip on hover explains why.

If the two parties DO share a corporate field (e.g. both have trade_name "KingSett Capital"), the contact/phone badges render in their normal jade/blue colors with the Sparkle icon — no caution.

- [ ] **Step 6: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/labeling/VerdictBar.tsx
git commit -m "feat(labeling): visual caution treatment for uncorroborated contact/phone proposals

Auto-proposed links flagged caution='contact_only' or 'phone_only' now
render as amber-outlined badges with a Warning icon and a descriptive
tag ('contact only' / 'phone only'). Tooltip on hover explains the
signal. The auto-proposal summary line also grows a legend noting the
amber-means-personal-signal convention.

User still reviews every pair. This just makes the weak proposals
visually distinct so they get scrutinized before the user hits Confirm."
```

---

## Task 6: End-to-end smoke test

**Files:** none — verification only.

- [ ] **Step 1: Check both test suites still pass end-to-end**

```bash
cd /Users/brandonolsen23/cleo-turbo
python3 -m pytest tests/test_labeling_party_view.py tests/test_labeling_operations.py tests/test_labeling_audit_parser.py tests/test_labeling_seed_harvester.py -v
```

Expected: all 11 labeling tests pass.

- [ ] **Step 2: Check frontend still type-clean**

```bash
cd /Users/brandonolsen23/cleo-turbo/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Manual golden-path walkthrough**

1. Open an existing labeling session in the browser at `http://localhost:5174/labeling/sessions/2` (or any active session).
2. Verify both party cards show sale_date in the header.
3. Click a pending seed to populate candidates.
4. Open a candidate where the reference and candidate share a `trade_name` AND a `contact_name`. Verify:
   - trade_name badge: jade/solid (auto exact, no caution)
   - contact_name badge: jade/solid (auto exact, no caution) — because trade_name corroborates it
5. Open a different candidate where the reference and candidate share ONLY a phone or ONLY a contact_name (no trade_name, care_of, company_other, law_firm, address, party_name match). Verify:
   - contact_name or phone badge: amber/outline with Warning icon and "· contact only" or "· phone only" suffix
   - Tooltip on hover explains the caution
6. Export the session JSON (top bar Export button). Open the downloaded file. Verify each pair has `sale_date` on both `left` and `right`.

- [ ] **Step 4: If anything fails, diagnose and re-commit fixes before closing this plan.**

---

## Notes for the implementer

- **Do not** introduce a `contact_tenures` table or any kind of explicit tenure declaration UI. Phase 1 is strictly about surfacing existing signal (date) and flagging weak proposals. Explicit tenures are a future plan if the flags here prove insufficient.
- **Do not** change the search/seed backend to filter out contacts with wide date gaps. The human makes that call; the system just surfaces the evidence. Contact-only matches still get proposed (and confirmed if the human decides they're right) — they just render with a warning.
- **Phone is still a valid link target.** You can still click-to-link two phone values manually, and phone is still harvested as a seed. This plan only changes how phone matches are auto-proposed and visually ranked, not whether phone exists as a label dimension.
- **The `caution` flag is frontend-only.** It never reaches the backend. Confirmed links carry only `kind: exact | implied` — the model will learn corroboration patterns from the combination of fields present, not from an explicit caution marker.
- **CORPORATE_FIELDS deliberately excludes contact_role** because role (e.g. "VP", "Attn") isn't a field_type in our schema — it's metadata displayed next to contact_name in the UI. Don't add it.
