# [HISTORICAL] Classifier Fixes Plan — Post Full-Run Cross-Check

> **STATUS: COMPLETED.** All fixes in this plan were implemented on 2026-03-24. This document is kept for reference only — do NOT use it to guide current development.

Based on cross-checking all 126,106 classified records against all dictionaries.
Each fix includes the root cause, the exact change, and which files are affected.

**Benchmark:** 86 fixtures must pass after all fixes.
**Backup:** `~/cleo-engine-v1-classified-70/`

---

## FIX 1: Contact prefix validator — check NOT_A_PERSON regardless of sub-type

**Root cause:** "Attn: 1107444 Ontario Inc" — the name part "1107444 Ontario Inc" starts with digits, so `_classify_single_line` returns `address_line` (Layer 2 catches it before Layer 3 sees "Inc"). The contact prefix validator only reclassifies if sub-type is `company_name` with corporate suffix. Since sub-type is `address_line`, the check is skipped entirely. The name stays as a contact.

**Fix:** In `contacts.py`, in the contact prefix handler (Layer 1.5), BEFORE checking the sub-type, check NOT_A_PERSON_REGEX directly on the name text. If the name contains Inc, Ltd, Corp, etc., reclassify as company_name regardless of what the recursive classifier returned.

```
Current logic:
  1. Run sub-classifier on name
  2. If sub-type is law_firm/trust → reclassify
  3. If sub-type is company_name AND has corporate suffix → reclassify
  4. Otherwise → contact_name

New logic:
  1. Check NOT_A_PERSON_REGEX on name text directly
     → If match AND has corporate suffix → company_name (DONE, skip sub-classifier)
     → If match AND has law keyword → law_firm (DONE)
  2. Run sub-classifier on name (only if step 1 didn't match)
  3. If sub-type is law_firm/trust → reclassify
  4. If sub-type is company_name AND has corporate suffix → reclassify
  5. Otherwise → contact_name
```

**Files:** `classifier/contacts.py` — Layer 1.5 block
**Records affected:** 1
**Test:** "Attn: 1107444 Ontario Inc" → company_name

---

## FIX 2: Add "Dept" and typo variants to NOT_A_PERSON_WORDS

**Root cause:** "Real Estate Dept" comes through a contact prefix. The validator checks NOT_A_PERSON_REGEX which has "Department" but not "Dept". So it stays as contact_name.

**Fix:** Add to NOT_A_PERSON_WORDS in `dictionaries.py`:
```
Dept, Deptartment (typo), Realty, Estate (when combined with Real)
```

**Files:** `classifier/dictionaries.py` — NOT_A_PERSON_WORDS list
**Records affected:** 3
**Test:** "Attn: Real Estate Dept" → company_name

---

## FIX 3: Remove bare "QC" from LAW_FIRM_KEYWORDS

**Root cause:** "QC" was added for Queen's Counsel ("William K. Andrews, Q.C."). But "QC" also means Quebec. Layer 3.2 (law firm) runs before Layer 3.3 (city/province), so "Gatineau, QC" → law_firm instead of city_province.

**Fix:** In `dictionaries.py`, remove "QC" from LAW_FIRM_KEYWORDS. Keep "Q.C." (with periods). Queen's Counsel always has periods. Quebec never does.

**Also:** The law firm keyword check in `contacts.py` uses `any(kw in stripped for kw in LAW_FIRM_KEYWORDS)`. "Q.C." with periods will still match as a substring. Verify this works correctly.

**Files:** `classifier/dictionaries.py` — LAW_FIRM_KEYWORDS list
**Records affected:** 131
**Test:** "Gatineau, QC" → city_province. "William K. Andrews, Q.C." → law_firm.

---

## FIX 4: Fix "CO" matching corporate suffix "Co"

**Root cause:** CORPORATE_SUFFIX_ANYWHERE_REGEX is case-insensitive. "CO" (Colorado abbreviation) matches `\bCo\.?` pattern. Layer 3.1 runs before Layer 3.3, so "Denver, CO" → company_name instead of city_province.

**Fix:** For lines with a comma + known province/state as the last element, check city/province BEFORE corporate suffix. This is a targeted fix:

In `contacts.py`, BEFORE the Layer 3.1 corporate suffix check, add a "comma + province" pre-check:
```
If the line has a comma AND the text after the last comma (stripped, period-stripped)
matches a known province/state AND the text before the comma does NOT have a
corporate suffix → return city_province immediately.
```

This catches "Denver, CO" (comma + CO = Colorado) before "CO" can match as corporate suffix "Co".

It does NOT affect "Acme Co." (no comma + province pattern) or "Something, Ontario Inc" (has corporate suffix after province — guard catches it).

**Alternatively:** Move the FULL Layer 3.3 city/province check to run BEFORE Layer 3.1 corporate suffix. This is a bigger change but cleaner. The comma + known province is a STRONGER signal than a case-insensitive two-letter suffix match.

**Recommendation:** Move Layer 3.3 before Layer 3.1. The comma + province pattern is structurally definitive for lines that match it. Corporate suffix check runs after and catches everything else.

**New Layer 3 order:**
```
3.1  City + Province (comma + known province) → CITY/PROVINCE  [moved up]
3.2  Corporate suffix → COMPANY
3.3  Law firm keywords → LAW FIRM
3.4  Building keywords → BUILDING
3.5  Company keywords → COMPANY
3.6  Department keywords → COMPANY
```

**Files:** `classifier/contacts.py` — Layer 3 ordering
**Records affected:** 14
**Test:** "Denver, CO" → city_province. "Acme Co." → company_name. "Denver, CO Inc" → company_name (guard catches it).

---

## FIX 5: Collapse spaces after stripping periods in province check

**Root cause:** "Victoria, B. C." — after stripping periods: "B C" (with space). "B C" is not in ALL_PROVINCES_STATES (we have "BC"). The space prevents the match.

**Fix:** In `contacts.py`, in the city/province check, after replacing periods, also collapse multiple spaces and remove all spaces from the province candidate before matching:

```python
after_noperiod = after_clean.replace('.', '').replace(' ', '').strip()
```

"B. C." → strip periods → "B C" → strip spaces → "BC" → match.

**Files:** `classifier/contacts.py` — Layer 3 city/province check (both comma and no-comma variants)
**Records affected:** 17+
**Test:** "Victoria, B. C." → city_province. "Victoria, B.C." → city_province. "Toronto, Ontario" → city_province (unchanged).

---

## FIX 6a: Expand malformed postal detection

**Root cause:** ~100 other_lines are clearly postal codes with typos: "LoB 1J0" (lowercase L instead of uppercase), "M#H 5S9" (# instead of digit), "L$l 9G3" ($ instead of digit), "L4V !R9" (! instead of digit).

**Fix:** Add a broader malformed postal check in Layer 1.1. After the existing checks:
```
If the line is 5-8 characters (after stripping spaces/dashes),
AND it's a mix of letters and digit-like characters,
AND it doesn't match any other pattern,
→ classify as postal (malformed).
```

The key insight: these are SHORT strings (6-7 chars) with a mix of letters and characters that LOOK like digits. No company name, address, or person name is 6 characters with this pattern.

**Also:** Some postals have wrong capitalization: "NoM 2S0", "LoB 1J0" — the current regex requires uppercase first letter. Make the check case-insensitive.

**Files:** `classifier/contacts.py` — Layer 1.1 postal section
**Records affected:** ~100
**Test:** "LoB 1J0" → postal. "M#H 5S9" → postal.

---

## FIX 6b: Add typo contact prefixes

**Root cause:** ~80 other_lines are contact names with misspelled prefixes that aren't in our prefix list.

**Typo prefixes to add to CONTACT_PREFIXES_WITH_COLON in dictionaries.py:**
```
Atth:, Atnn:, Attm:, Annt:, Arttn:, Attb:, Atn:,
COO:, GM:, SO:, RSO:, CP: (when followed by name, not postal),
Reeve:, Chief:, Pastor:, Chairman:, Clerk:,
Executrix:, Tres:, Pares:, Presx:, Presw:,
Prees:, Ptres:, Prres:, Prews:, Peres:, Ptes:,
Sttn:, Aaso:, Presa:, Principal:
```

**Also add to CONTACT_PREFIXES_NO_COLON:**
```
Atn (catches "Atn Mike Brennan" without colon)
```

**Also add to _TITLE_MAP in contacts.py:**
```
atth → attn, atnn → attn, attm → attn, annt → attn, arttn → attn,
attb → attn, atn → attn, aaso → aso,
coo → coo, gm → gm, so → so, rso → rso,
reeve → reeve, chief → chief, pastor → pastor,
chairman → chair, clerk → clerk,
executrix → executor, tres → treas,
pares → pres, presx → pres, presw → pres,
prees → pres, ptres → pres, prres → pres,
prews → pres, peres → pres, ptes → pres,
sttn → attn, presa → pres, principal → principal
```

**Files:** `classifier/dictionaries.py` — prefix lists. `classifier/contacts.py` — title map.
**Records affected:** ~80
**Test:** "Atth: Steve Partridge" → contact_name, title=attn.

---

## FIX 6c: UK/European postal codes and international addresses

**Root cause:** ~30 other_lines are international postal codes and addresses:
- UK postals: "PE22 9AS", "SW1A 2AH", "TW11 9HJ", "UB10 8GB", "EC2Y 9H7", "RG42 6NG", "TN16 1QE"
- European: "CH - 8004 Zurich - Switzerland", "D-80333 Munich", "NL-2950 AE Alblasserdan"

**Fix:** Add UK postal code pattern to Layer 1.1:
```
UK format: one or two letters + one or two digits + optional space + digit + two letters
Pattern: ^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$
```

Add European address patterns to country/address detection:
```
^(CH|D|NL|F|A)\s*-?\s*\d+ → international address with country prefix
```

**Files:** `classifier/dictionaries.py` — new UK_POSTAL_REGEX. `classifier/contacts.py` — Layer 1.1.
**Records affected:** ~30
**Test:** "PE22 9AS" → postal. "CH - 8004 Zurich - Switzerland" → address or country.

---

## FIX 6d: PO Box variants and c/o typos

**Root cause:** Several PO Box and c/o variants not caught:
- "P O Box 128" (space between P and O)
- "PO Box1112" (no space after Box)
- "PO Box SS1" (letters instead of digits after Box)
- "F. G. PO Box 81192" / "FG PO Box 81192" (prefix before PO Box)
- "Clearview PO Box 2142" / "Manulife PO Box 19569" / "Kilbride PO Box 163" (location before PO Box)
- "c/oMr Skip Bettridge" (no space after c/o)
- "c//o Iain MacDonald" (double slash)
- "c/i Timothy D Seegmiller" (typo)

**Fix:** Expand PO_BOX_REGEX in `dictionaries.py`:
```python
# Current: ^(PO Box|P\.O\. Box|Box|FGPO Box|CP)\s+\d
# New: also catch P O Box, PO Box without space, PO Box with letters,
#      and PO Box with location prefix
^(P\s?\.?\s?O\s?\.?\s?Box|Box|FGPO Box|FG PO Box|F\. G\. PO Box|CP)\s*\S
```

Also catch PO Box ANYWHERE in line (not just at start):
```
\bP\s?\.?\s?O\s?\.?\s?Box\b → if this appears anywhere, it's an address
```

Expand c/o matching in contacts.py Layer 1.6:
```python
# Current: ^c/o\s+
# New: also catch c/oName (no space), c//o, c/i
^c\s*/?\s*[/oi]\s*
```

**Files:** `classifier/dictionaries.py` — PO_BOX_REGEX. `classifier/contacts.py` — c/o pattern.
**Records affected:** ~30
**Test:** "P O Box 128" → address. "c/oMr Skip Bettridge" → care_of.

---

## FIX 7: Eliminate department type entirely

**Root cause:** `_classify_single_line` returns `('department', ...)` which `classify_contacts` reroutes to companies. This is a two-step indirection that adds confusion.

**Fix:**
1. In `contacts.py`, change Layer 3.6 to return `('company_name', ...)` directly instead of `('department', ...)`
2. Remove the `elif line_type == 'department':` handler from the assembly pass
3. Merge DEPARTMENT_KEYWORDS into COMPANY_KEYWORDS in `dictionaries.py`
4. Remove DEPARTMENT_KEYWORDS as a separate list
5. Remove 'department' from all type references in `contacts.py`

**Files:** `classifier/dictionaries.py`, `classifier/contacts.py`
**Records affected:** 0 (behavior unchanged, just cleaner code)
**Test:** All 86 fixtures still pass.

---

## FIX 8: Eliminate trust_references field

**Root cause:** trust_references is still a separate field in the output. Brandon directed: fold into companies.

**Fix:**
1. In `contacts.py` Layer 1.7, change trust reference to return `('company_name', {'name': stripped})` instead of `('trust_reference', {'text': stripped})`
2. Remove `'trust_references': []` from the result dict in `classify_contacts`
3. Remove the `elif line_type == 'trust_reference':` handler from the assembly pass
4. Remove 'trust_reference' from all type references
5. Keep TRUST_REFERENCE_REGEX in dictionaries (still need to detect them, just classify as company)

**Files:** `classifier/contacts.py`
**Records affected:** Small — trust references now appear in companies instead of separate field
**Test:** All fixtures still pass. Any fixture with trust_references needs to be updated (moved to companies).

---

## FIX 9: Clean up crosscheck.py

**Root cause:** crosscheck.py still references "departments" in its expected dictionary.

**Fix:** Remove "departments" from the expected dict and from `extract_field_texts`. Remove "trust_references" similarly if that field is eliminated.

**Files:** `crosscheck.py`

---

## FIX 10: Update documentation

**Fix:** Update `schema/classification_logic.md` to reflect:
- 4-layer structure
- Merged departments → companies
- Merged trust_references → companies
- New Layer 3 ordering (city/province before corporate suffix)
- All new prefixes and keywords
- UK postal patterns

**Files:** `schema/classification_logic.md`

---

## Final Layer 3 Order After All Fixes

```
LAYER 3 — KEYWORD DICTIONARIES (after all fixes applied):

3.1  City + Province (comma + known province)    ← MOVED UP from 3.3
     Structurally definitive: comma + known province is stronger
     than a coincidental corporate suffix match like "CO".
     Guards: NOT if corporate suffix AFTER province.

3.2  Corporate suffix (Inc., Ltd., Corp., etc.)  ← was 3.1
     Still definitive for lines that reach it, but city/province
     no longer falls through to here.

3.3  Law firm keywords (LLP, Barristers, Q.C.)   ← was 3.2
     "QC" removed. Only "Q.C." with periods matches.

3.4  Building keywords (Tower, Centre, Plaza)    ← unchanged
3.5  Company keywords (Bank, Hotel, etc.)        ← unchanged
     DEPARTMENT_KEYWORDS merged into COMPANY_KEYWORDS.
     No separate department type or routing.
```

## Implementation Order

1. FIX 7 (eliminate department type) — cleanup, no behavior change
2. FIX 8 (eliminate trust_references) — cleanup, update fixtures
3. FIX 3 (remove "QC" from law firm keywords) — biggest impact, 131 records
4. FIX 4 (city/province before corporate suffix) — 14 records
5. FIX 5 (collapse spaces in province check) — 17 records
6. FIX 1 (contact prefix NOT_A_PERSON check) — 1 record
7. FIX 2 (add "Dept" to NOT_A_PERSON) — 3 records
8. FIX 6b (typo contact prefixes) — ~80 records
9. FIX 6a (malformed postal detection) — ~100 records
10. FIX 6d (PO Box and c/o variants) — ~30 records
11. FIX 6c (UK/European postals) — ~30 records
12. FIX 9 (crosscheck cleanup)
13. FIX 10 (documentation)
14. Re-run full dataset + crosscheck
15. Run all fixtures — must pass

**Why this order:** Cleanups first (no risk), then high-impact fixes, then edge cases. Each fix can be tested independently against fixtures before moving to the next.
