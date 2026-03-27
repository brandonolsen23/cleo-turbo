# [HISTORICAL] Classifier Restructure Plan

> **STATUS: COMPLETED.** This plan was executed on 2026-03-24. The 4-layer system is now live in `classifier/contacts.py`. This document is kept for reference only — do NOT use it to guide current development.

This document defined the restructure of `classifier/contacts.py` from the ad-hoc rule sequence into a layered, principled classification system.

**Backup:** `~/cleo-engine-backup-2026-03-24/`
**Benchmark:** 66 fixtures (all must pass after restructure)

---

## Why Restructure

The current classifier was built incrementally — each bug fix added a gate, exception, or special case on top of the existing flow. This has led to:

1. **Rule ordering conflicts** — the same word ("Court", "Square") is both a street suffix and a building keyword. Whichever rule runs first wins, and the order wasn't designed for this.
2. **Definitive patterns being overridden** — "PO Box 2110, Station Main" gets caught by company keywords ("Station") before the PO Box pattern can fire.
3. **No-digit address leaks** — "Commerce Court West" matches the street-name-only rule because "Court" is a street suffix, even though it has no digit and is clearly a building name.
4. **Company names misclassified as city/province** — "Sobeys Ontario" matches the no-comma province check because "Ontario" is a province and there's no corporate suffix guard.
5. **Ad-hoc gates** — `_is_obvious_address`, `_has_building_kw` checks were added mid-stream to fix specific cases, making the flow hard to follow.

## Design Principle

**Definitive patterns first. Eliminate what it CAN'T be. Then classify by what it COULD be.**

Each layer is more certain than the next. Once a line is classified at a higher layer, lower layers never see it.

---

## The Four Layers

### LAYER 1 — DEFINITIVE PATTERNS

These patterns are 100% certain. Nothing else in the dataset matches them. No context needed, no dictionaries needed. Pure regex/exact-match.

**Order within Layer 1:**

```
1.1  Postal code        ^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$  (+ malformed variants)
1.2  US ZIP code        ^\d{5}(-\d{4})?$
1.3  Phone number       \d{3}-\d{3}-\d{4} | \d{6}-\d{4} | \d{3}-\d{7}
1.4  Country            "USA", "USA - NNNNN", exact country name match
1.5  Contact prefix     Attn:, Pres:, VP:, ASO:, etc. (case insensitive)
     → then validate name part against Layer 3 dictionaries
1.6  c/o prefix         ^c/o\s+ (case insensitive)
     → then classify remainder through ALL layers (recursive)
1.7  Trust reference    ^(as trustee for|in trust for)
1.8  PO Box / RR        ^(PO Box|P.O. Box|Box|FGPO Box|CP)\s+\d | ^R.R.\s*#?\d
1.9  General Delivery   ^General Delivery$
```

**Why PO Box moves to Layer 1:** PO Box is a definitive address pattern. It should NEVER be overridden by a company keyword. "PO Box 2110, Station Main" — the PO Box pattern is unmistakable. "Station" as a company keyword is a weak signal. Definitive beats weak. Always.

**Why contact prefix and c/o are in Layer 1:** The prefix itself (Attn:, c/o) is definitive. What FOLLOWS the prefix needs further classification, but the prefix detection belongs here.

### LAYER 2 — STRUCTURAL ADDRESS PATTERNS

These identify addresses by their structure (digits, suffixes, position). They run BEFORE any keyword dictionaries to prevent keywords from stealing address lines.

**Order within Layer 2:**

```
2.1  Digit + street suffix         ^\d.* + \b(St|Ave|Rd|...)\b → ADDRESS
2.2  Digit start, no suffix        ^\d → ADDRESS (weaker, but still structural)
2.3  "One" + street suffix         ^One\s+ ... → ADDRESS
2.4  Suite/Unit/Floor/Station       ^(Suite|Ste|Unit|Floor|...) → MODIFIER
2.5  ", RR" in line                 address with rural route at end
```

**What's NOT in Layer 2:**
- "Street-name-only" (no digit) — this was the source of the "Commerce Court West" bug. Without a digit, a street suffix alone is NOT a definitive address signal. This moves to Layer 4 where it can be weighed against building keywords.

### LAYER 3 — KEYWORD DICTIONARIES

These use keyword lists to classify. Order matters because some keywords overlap. Each check includes guards to prevent false positives.

**Order within Layer 3:**

```
3.1  Corporate suffix (Inc., Ltd., Corp., etc.)  → COMPANY
     This is first because corporate suffixes are legally definitive.
     Guard: not if already caught by Layer 2 as address.

3.2  Law firm keywords (LLP, Barristers, Solicitors, etc.)  → LAW FIRM
     Priority over generic company because LLP is both a corporate
     suffix and a legal indicator. Law firm is more specific.

3.3  City + Province (comma + known province at end)  → CITY/PROVINCE
     Guards:
     - NOT if line also has a corporate suffix
     - NOT if line also has a company keyword (catches "Sobeys Ontario")
     - NOT if line also has a building keyword
     The no-comma variant ("Sobeys Ontario") needs the SAME guards.

3.4  Building keyword (Tower, Centre, Plaza, etc.)  → BUILDING NAME
     Guard: NOT if line starts with digit + street suffix (Layer 2 caught it)
     This runs BEFORE company keywords so "TD Bank Tower" → building, not company.

3.5  Company keywords (Bank, Properties, Hotel, etc.)  → COMPANY
     Guard: NOT if line also has a building keyword (building wins)
     Guard: NOT if already caught by Layer 2 as address

3.6  Department keywords (Department, Division, etc.)  → COMPANY
     Guard: NOT if has corporate suffix (that's a company, not dept)
     Guard: NOT if already caught by Layer 2 as address

3.7  Not-a-name words (Junction, Canada, Blue, Vice, etc.)  → COMPANY
     Only for remaining unclassified lines.
```

**Key change: Building keywords (3.4) now run BEFORE company keywords (3.5).** This fixes "Toronto-Dominion Bank Tower" — "Tower" (building) takes priority over "Bank" (company) when both match and there's no corporate suffix.

**Key change: City/Province (3.3) now checks company keywords.** This fixes "Sobeys Ontario" — if any word in the line is a company keyword, don't trust the province match.

### LAYER 4 — CONTEXTUAL / DEFAULT

These handle remaining text using context, patterns, and defaults. Weakest signals.

**Order within Layer 4:**

```
4.1  Street-name-only (has suffix, short, NO digit, NO building keyword)
     This is where "University Ave" gets caught — has a suffix, no digit,
     and "University" is not a building keyword. But "Commerce Court West"
     does NOT match because "Court" IS a building keyword (caught in 3.4).
     Guard: NOT if ANY word is a building keyword.

4.2  International address (digit at end, short line: "Hertzweg 3")
     Guard: NOT if starts with Suite/Unit/Floor (modifier check first)

4.3  Acronym (2-6 uppercase letters) → COMPANY

4.4  "Mr &" or "Mr & Mrs" pattern → PERSON

4.5  & pattern (law firm vs couple detection)
     All parts single words, no shared surname → LAW FIRM
     First names + shared surname → PERSON (couple)

4.6  First name match (first word in COMMON_FIRST_NAMES, ≤3 words) → CONTACT NAME

4.7  "The" + proper noun → BUILDING NAME

4.8  Clean text default → CONTACT NAME
     (second pass look-ahead may promote to law_firm)
```

---

## Second Pass — Line Joining

After all lines are classified individually, the second pass joins lines that belong together:

```
JOINING RULES:
- law_firm + law_firm → join ("Farber & Robillard" + "Barristers & Solicitors")
- company_name + law_firm → join (promote to law_firm)
- untitled contact_name + law_firm → join (promote to law_firm)
- care_of + law_firm → join (update care_of type to law_firm)
- titled contact_name + law_firm → do NOT join (Attn: Barry Schwartz stays separate)
```

---

## Third Pass — Assembly

Map classified lines into the output structure:

```
postal → address.postal
phone → phone
country → address.country (+ ZIP if present)
contact_name → contacts[]
care_of (address type) → address.lines only, no care_of
care_of (other types) → care_of
city_province → address.city + address.province
law_firm → law_firms[]
company_name → companies[]
address_line → address.lines[]
address_modifier → address.modifiers[]
building_name → address.building_names[]
trust_reference → trust_references[]
other → other_lines[]
```

---

## Changes From Current Code

| What | Current | After Restructure |
|------|---------|-------------------|
| PO Box check | Rule 11 (after company keywords) | Layer 1.8 (before everything) |
| Street-name-only | Rule 11 (before building check) | Layer 4.1 (after building check, with building keyword guard) |
| Building keywords | Rule 13 (after address catch-all) | Layer 3.4 (before company keywords) |
| Company keywords | Rule 9 (with ad-hoc building gate) | Layer 3.5 (clean — building check already ran) |
| City/Province | Rule 7 (corporate suffix guard only) | Layer 3.3 (corporate suffix + company keyword + building keyword guards) |
| Address gate | Ad-hoc `_is_obvious_address` variable | Layer 2 runs first — no gate needed |
| c/o sub-classification | Recursive call to same function | Same recursive call, but layers prevent misclassification |

## Validation

After restructure:
1. All 66 fixtures must pass
2. Re-run crosscheck.py on 5000 records
3. No-digit address lines should drop to near zero (only "General Delivery" and legitimate street-name-only like "University Ave")
4. "Sobeys Ontario" must NOT classify as city_province
5. "PO Box 2110, Station Main" must classify as address, not company
6. "Commerce Court West" must classify as building, not address
7. "Toronto-Dominion Bank Tower" must classify as building, not company

---

## Files Changed

- `classifier/contacts.py` — full rewrite of `_classify_single_line` using 4-layer structure
- `classifier/dictionaries.py` — no changes (dictionaries stay the same)
- `classifier/classify.py` — no changes (orchestrator stays the same)
- `schema/classification_logic.md` — update to reflect new layer structure
