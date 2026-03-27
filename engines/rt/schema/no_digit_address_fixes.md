# [HISTORICAL] No-Digit Address Line Fixes

> **STATUS: COMPLETED.** All fixes implemented on 2026-03-24. Reduced from 528 to 252. This document is kept for reference only — do NOT use it to guide current development.

528 address lines with no digit found across 126,106 classified records.
After investigation, ~280 are correct (General Delivery, "One..." word-numbers, real street names).
~200 are misclassified and fixable. ~50 are genuinely ambiguous.

**Benchmark:** 86 fixtures must pass after all fixes.

---

## FIX 1: PO Box regex matching "CP Tower" — 26 records

**Root cause:** PO_BOX_REGEX includes "CP" for French postal boxes (e.g., "CP 650"). But the pattern `CP\s*\S` matches "CP Tower", "CPP Investment Board", "CPI Corp" — anything starting with "CP". Layer 1.8 catches them as address_line before Layer 3.4 (building keywords) can see "Tower" or "Centre".

**Traced:** `_classify_single_line("CP Tower, TD Centre")` → PO_BOX_REGEX matches "CP T..." → address_line.

**Fix:** Change the "CP" pattern in PO_BOX_REGEX to require a space then a digit: `CP\s+\d`. "CP 650" still matches. "CP Tower" does not.

**Files:** `classifier/dictionaries.py` — PO_BOX_REGEX
**Test:** "CP Tower, TD Centre" → building_name. "CP 650" → address_line.

---

## FIX 2: Add company keywords — ~100 records

**Root cause:** Company/institution names without any matching keyword fall through to Layer 4.1 (street-name-only) because they contain words that happen to be street suffixes ("Park", "Lane", "Glen", "Court", "St").

**Missing keywords to add to COMPANY_KEYWORDS:**
```
Infrastructure, Lodges, Lodge, Estates, Estate,
Hospital, Printing, Club, Golf, Topsoil,
Storage, Wire, Packers, Express, Manor (as company),
Volkswagen, Volkswagon, Audi
```

**Why these:** Each one appears in the data as part of a company/institution name that's currently being caught as a street-name address:
- "Central Park Lodges" (22) — "Park" suffix, missing "Lodges"
- "Gold Park Estates" (11) — "Park" suffix, missing "Estates"
- "Angus Glen Golf Club" (6) — "Glen" suffix, missing "Club" and "Golf"
- "St Joseph Printing" (5) — "St" suffix, missing "Printing"
- "St Catharines General Hospital" (4) — "St" suffix, missing "Hospital"

Once these keywords exist in COMPANY_KEYWORDS, Layer 3.5 catches them BEFORE Layer 4.1 can match the street suffix.

**Files:** `classifier/dictionaries.py` — COMPANY_KEYWORDS
**Test:** "Central Park Lodges" → company_name. "St Catharines General Hospital" → company_name.

---

## FIX 3: Case-insensitive building context keyword check — 9 records

**Root cause:** `_has_building_keyword()` checks BUILDING_CONTEXT_KEYWORDS ("Court", "Square") using `re.search()` WITHOUT `re.IGNORECASE`. So "court" (lowercase) in "As court appointed receiver" doesn't match "Court".

Layer 4.1 (street-name-only) has a guard: `if not _has_building_keyword(stripped)`. The guard should block "As court appointed receiver" because "Court" is a building context keyword. But the case-sensitive check fails, so the guard passes, and it goes to address_line.

**Traced:** `_has_building_keyword("As court appointed receiver")` → False (case mismatch). Should be True.

**Fix:** Add `re.IGNORECASE` to the BUILDING_CONTEXT_KEYWORDS check in `_has_building_keyword()`:
```python
if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
```

**Files:** `classifier/contacts.py` — `_has_building_keyword()` function
**Test:** "As court appointed receiver" → building_name (not address_line).

---

## FIX 4: Reorder Layer 4 — move & pattern before street-name-only — ~40 records

**Root cause:** Layer 4.1 (street-name-only) runs BEFORE Layer 4.5 (& pattern for law firm detection). Lines with "Green" match the street suffix check first:
- "Active Green & Ross" → "Green" matches suffix → address_line (wrong, should be law firm)
- "Beament Green" → "Green" matches suffix → address_line (wrong)

If the & pattern ran first, "Active Green & Ross" would be caught as a law firm.

**Fix:** Reorder within Layer 4:
```
OLD:                          NEW:
4.1 Street-name-only         4.1 International address (digit at end)
4.2 International address    4.2 Acronym
4.3 Acronym                  4.3 Mr & Mrs pattern
4.4 Mr & Mrs pattern         4.4 & pattern (law firm vs couple)  ← MOVED UP
4.5 & pattern                4.5 First name match
4.6 First name match         4.6 Not-a-name words
4.7 Not-a-name words         4.7 "The" + proper noun
4.8 "The" + proper noun      4.8 Street-name-only  ← MOVED DOWN (last resort)
4.9 Clean text default       4.9 Clean text default
```

Street-name-only becomes a LAST RESORT in Layer 4 — only catches lines that didn't match any other pattern. This prevents street suffixes from stealing law firms, companies, and building names.

**Files:** `classifier/contacts.py` — Layer 4 section ordering
**Test:** "Active Green & Ross" → law_firm. "University Ave" → still address_line.

---

## FIX 5: Add "and" to & pattern check — ~10 records

**Root cause:** Layer 4 & pattern only checks for `&` and `, `. Lines using "and" instead of "&" are missed:
- "Green and Spiegel" (5) — uses "and" → not caught by & pattern → falls to street-name-only → "Green" suffix → address_line

**Fix:** Add ` and ` (with spaces) to the & pattern condition:
```python
if '&' in stripped or ' and ' in lower or (', ' in stripped and not stripped.endswith(',')):
```

**Files:** `classifier/contacts.py` — Layer 4 & pattern
**Test:** "Green and Spiegel" → law_firm. "Green and Gold" → law_firm (not address).

---

## FIX 6: Add word-numbers Two through Ten — 3 records

**Root cause:** Only "One" is handled in Layer 2.3. "Three Tyco Park", "Three Lakes Dr", "Seven Star Express Line" have word-numbers that aren't caught.

**Fix:** Expand Layer 2.3:
```python
if re.match(r'^(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\s+', stripped) \
   and STREET_SUFFIX_REGEX.search(stripped):
    return ('address_line', {'line': stripped})
```

**Files:** `classifier/contacts.py` — Layer 2.3
**Test:** "Three Lakes Dr" → address_line. "Seven Star Express Line" → address_line.

---

## FIX 7: Province check — skip Q.C. legal designation — 2 records

**Root cause:** "William K. Andrews, Q.C." — after comma: "Q.C." → strip periods + collapse spaces → "QC" → matches Quebec province. City part "William K. Andrews" has no corporate suffix.

Q.C. (Queen's Counsel) is a legal designation, not a province. It always has periods. Quebec abbreviation never has periods in this data.

**Fix:** In the comma city/province check, BEFORE stripping periods, check: if the text after the comma is exactly "Q.C." or contains ".C." → skip province match. This is a legal designation, not a province.

```python
# Skip Q.C. legal designation
if 'Q.C.' in after_last_comma or '.C.' in after_last_comma:
    pass  # don't match as province
```

**Files:** `classifier/contacts.py` — Layer 3.1 comma city/province check
**Test:** "William K. Andrews, Q.C." → law_firm (Q.C. keyword). "Gatineau, QC" → city_province (no periods).

---

## FIX 8: No-comma province — skip if first word is a first name — 4 records

**Root cause:** "Larry Himmelfarb CA" — last word "CA" matches California. No-comma province check passes because "Larry Himmelfarb" has no company/building keywords.

But "Larry" IS a common first name. A person's name followed by a 2-letter professional designation (CA = Chartered Accountant) should not be classified as city/province.

**Fix:** In the no-comma province check, add a guard: if the first word is a common first name AND the line is ≤3 words → skip province match.

```python
first_word = words[0].rstrip('.,')
if first_word in COMMON_FIRST_NAMES and len(words) <= 3:
    pass  # likely a person + designation, not city + province
```

**Files:** `classifier/contacts.py` — Layer 3.1 no-comma province check
**Test:** "Larry Himmelfarb CA" → contact_name (first name match). "Infrastructure Ontario" → still caught by company keyword (Fix 2).

---

## FIX 9: Add "Blk" to building keywords — 4 records

**Root cause:** "Ferguson Blk, Queens Park" — "Blk" is an abbreviation for "Block" (a building). Not in BUILDING_KEYWORDS (we have "Bldg" but not "Blk").

**Fix:** Add "Blk" to BUILDING_KEYWORDS.

**Files:** `classifier/dictionaries.py` — BUILDING_KEYWORDS
**Test:** "Ferguson Blk, Queens Park" → building_name.

---

## Implementation Order

1. FIX 1 (CP regex) — highest single impact, 26 records
2. FIX 2 (company keywords) — biggest total impact, ~100 records
3. FIX 3 (case-insensitive building context) — 9 records
4. FIX 4 (reorder Layer 4) — ~40 records, structural change
5. FIX 5 (add "and" to & pattern) — ~10 records
6. FIX 6 (word-numbers) — 3 records
7. FIX 7 (Q.C. designation) — 2 records
8. FIX 8 (first name + designation guard) — 4 records
9. FIX 9 (Blk keyword) — 4 records

After all fixes: re-run full dataset, cross-check, verify 86 fixtures pass.

---

## Expected Results

| Category | Before | After |
|----------|--------|-------|
| No-digit address lines | 528 | ~280 |
| Legitimate (General Delivery, One..., real streets) | ~280 | ~280 |
| Misclassified (fixable) | ~200 | ~0 |
| Genuinely ambiguous (Queen's Park, Fast Lane) | ~50 | ~50 |
