# Cleo Engine — Current State Reference

**Last updated:** 2026-03-24
**Fixtures:** 106 (90 classified, 16 structural) — all passing
**Dataset:** 126,106 records processed, zero errors

This is the single source of truth for the engine's current state. If the code disagrees with this document, investigate — one of them needs updating.

---

## Pipeline Overview

```
Source HTML (126K files in ~/cleo-facts/cleo-data/rt/)
    ↓
Step 1: Structural Extraction (run_pipeline.py)
    → parsers/detail.py, export.py, results.py
    → assembler.py (joins by position, cross-checks address/price/date)
    → Output: pipeline/assembled/  (one JSON per record)
    ↓
Step 2: Classification (run_classifier.py, parallel, ~25s for 126K)
    → classifier/classify.py orchestrates all section classifiers
    → Output: pipeline/classified/  (one JSON per record)
    ↓
Step 3: Load into database (FUTURE — not built yet)
```

---

## Classified Output Schema

Every classified record has this exact shape:

```json
{
  "rt_id": "RT101601",
  "source_folder": "Peel_Region/industrial/p032",
  "position": 32,
  "join_verified": true,

  "header": {
    "sale_date": "2014-07-17",
    "sale_price": 2550000,
    "city": "Brampton",
    "region": "Peel Region",
    "transaction_note": "",
    "address_entries": [
      {
        "lines": ["247 SUMMERLEA RD"],
        "type": "street_address",
        "geocodable": true
      }
    ]
  },

  "seller": {
    "parties": [{"name": "1707416 Ontario Inc"}],
    "phone": "905-789-9500",
    "trade_name": "",
    "contacts": [{"name": "Jinder Buttar", "title": "attn"}],
    "care_of": null,
    "law_firms": [],
    "companies": [],
    "address": {
      "lines": ["14 Big Moe Cres"],
      "modifiers": [],
      "building_names": [],
      "city": "Brampton",
      "province": "Ontario",
      "postal": "L6P 1J7",
      "country": ""
    },
    "other_lines": []
  },

  "buyer": {
    "parties": [{"name": "2414408 Ontario Inc"}],
    "phone": "",
    "trade_name": "",
    "contacts": [{"name": "Imran Mohammad", "title": "pres"}],
    "care_of": null,
    "law_firms": [],
    "companies": [],
    "address": {
      "lines": ["147 Whitwell Dr"],
      "modifiers": [],
      "building_names": [],
      "city": "Brampton",
      "province": "Ontario",
      "postal": "L6P 1L2",
      "country": ""
    },
    "other_lines": []
  },

  "site": {
    "pin": "14024-0032",
    "pin_multiple": false,
    "acreage": 1.95,
    "legal_description": "Plan 43R-13471, Part 1\nPlan 43R-14107, Part 1",
    "location": "E side Summerlea Rd, S of Imperial Ct",
    "surface_rights_only": false
  },

  "arn": "21 10 100 025 27110",

  "description": {
    "description": "Industrial Bldg - 20 ft clr; 18,750 sf on about 1.95 Ac\n...",
    "more_info_url": ""
  },

  "consideration": {
    "cash": 2550000,
    "debt": 0,
    "chattels": null,
    "other": null,
    "charges": [
      {
        "chargee": "Royal Bank of Canada",
        "principal": 2550000,
        "rate": "Prime plus 5.0% per annum.",
        "registered": "07/17/2014",
        "due": "on demand"
      }
    ]
  },

  "broker": {
    "brokers": []
  },

  "photos": {
    "street_photo_urls": [...],
    "aerial_photo_urls": [],
    "standalone_photo_url": ""
  },

  "export": { ... },
  "results": { ... }
}
```

### Field Reference — Seller/Buyer

| Field | Type | Description |
|-------|------|-------------|
| `parties` | array of `{name}` | Legal entities on the transaction. Phone extracted separately. |
| `phone` | string | Phone number (XXX-XXX-XXXX, XXXXXX-XXXX, or XXX-XXXXXXX) |
| `trade_name` | string | DBA / trade name from `<em>` tag |
| `contacts` | array of `{name, title}` | Named people with title prefix (attn, pres, vp, aso, dir, etc.) |
| `care_of` | object or null | `{type: "person"|"company"|"law_firm"|"address", text: "..."}` |
| `law_firms` | array of strings | Legal offices identified by keywords (LLP, Barristers, Q.C., etc.) |
| `companies` | array of strings | Corporate entities, organizations, departments, government bodies |
| `address.lines` | array of strings | Geocodable street address lines |
| `address.modifiers` | array of strings | Suite/Unit/Floor/Station references |
| `address.building_names` | array of strings | Building/complex names (NOT geocodable) |
| `address.city` | string | City name |
| `address.province` | string | Province or state |
| `address.postal` | string | Canadian postal code, US ZIP, or UK postal |
| `address.country` | string | Country (only for international addresses) |
| `other_lines` | array of strings | Lines that escaped all classification (~60 across 126K records) |

### Field Reference — Header

| Field | Type | Description |
|-------|------|-------------|
| `sale_date` | string | ISO format YYYY-MM-DD |
| `sale_price` | integer | Price in dollars, no decimals |
| `city` | string | Municipality from Realtrack |
| `region` | string | Region from Realtrack |
| `transaction_note` | string | Portfolio, Power of Sale, Related Parties, etc. |
| `address_entries` | array | Each entry: `{lines, type, geocodable}` |

Address entry types: `street_address` (geocodable=true), `legal_description` (false), `street_name` (false), `highway` (false), `unit_only` (false), `name_only` (false), `location_qualifier` (false).

Geocodability rule: starts with a digit = geocodable. No digit = not geocodable.

### Field Reference — Site

| Field | Type | Description |
|-------|------|-------------|
| `pin` | string | Property Identification Number |
| `pin_multiple` | boolean | True if PIN ends with "+" (multiple PINs) |
| `acreage` | float or null | Property size in acres |
| `legal_description` | string | Plan/Lot/Conc references, newline-separated |
| `location` | string | Relative location description |
| `surface_rights_only` | boolean | Rare flag for surface-only rights |

### Field Reference — Consideration

| Field | Type | Description |
|-------|------|-------------|
| `cash` | integer or null | Cash component |
| `debt` | integer or null | Assumed/VTB debt component |
| `chattels` | integer or null | Personal property value |
| `other` | integer or null | Other consideration |
| `charges` | array | Mortgage/charge entries: `{chargee, principal, rate, registered, due}` |

---

## 4-Layer Classification System

File: `classifier/contacts.py`

Each contact line passes through 4 layers in order. Once classified, it's done.

### Layer 1 — Definitive Patterns (100% certain)

These are regex/exact-match patterns that cannot be anything else.

| # | Check | Result |
|---|-------|--------|
| 1.1 | Canadian postal: `A1A 1A1` pattern | postal |
| 1.2 | US ZIP: `NNNNN` or `NNNNN-NNNN` | postal |
| | UK postal: `A9 9AA` variants | postal |
| | Malformed postal: 6 chars, letter-digit mix | postal |
| | Standalone province name | city_province |
| 1.3 | Phone: `NNN-NNN-NNNN`, `NNNNNN-NNNN`, `NNN-NNNNNNN` | phone |
| 1.4 | Country: `USA - NNNNN`, exact country name | country |
| | European prefix: `CH-`, `D-`, `NL-` + digits | address_line |
| 1.5 | Contact prefix: `Attn:`, `Pres:`, `VP:`, etc. | contact_name |
| | → then validates name part: NOT_A_PERSON check first | → company if Inc/Ltd/Dept |
| | → then recursive sub-classify for strong non-person types | → law_firm if LLP/etc |
| 1.6 | c/o prefix: `c/` followed by content | care_of |
| | → recursive sub-classify of content | → type: address/company/law_firm/person |
| 1.7 | Trust reference: "as trustee for", "in trust for" | company_name |
| 1.8 | PO Box / RR / General Delivery | address_line |
| | PO Box anywhere in line | address_line |

### Layer 2 — Structural Address Patterns

| # | Check | Result |
|---|-------|--------|
| 2.1 | Digit + street suffix | address_line |
| 2.2 | Digit start, no suffix | address_line |
| 2.3 | Word-number (One-Ten) + street suffix | address_line |
| 2.4 | Suite/Unit/Floor/Station keywords at start | address_modifier |

### Layer 3 — Keyword Dictionaries

Order matters. Each check includes guards to prevent false positives.

| # | Check | Guards | Result |
|---|-------|--------|--------|
| 3.1 | Comma + known province/state | NOT if corporate suffix in CITY part. Skip Q.C. designation. | city_province |
| | No-comma: last word = province | NOT if corp suffix, company keyword, building keyword, or first word is a first name (≤3 words) | city_province |
| 3.2 | Corporate suffix (Inc, Ltd, Corp, etc.) | If also has law firm keyword → law_firm instead | company_name |
| 3.3 | Law firm keywords (LLP, Barristers, Q.C., etc.) | | law_firm |
| 3.4 | Building keywords (Tower, Centre, Plaza, etc.) | | building_name |
| 3.5 | Company keywords (Bank, Hotel, Properties, etc.) | | company_name |
| | "Trust" at end of line | | company_name |
| | "City of X" / "Town of X" | | company_name |

### Layer 4 — Contextual / Default

Weakest signals. Street-name-only is LAST RESORT.

| # | Check | Result |
|---|-------|--------|
| 4.1 | International address (digit at end, ≤3 words) | address_line |
| 4.2 | All-caps acronym (2-6 chars) | company_name |
| 4.3 | "Mr &" / "Mr & Mrs" pattern | contact_name |
| 4.4 | `&` or `and` pattern: LastName & LastName → law firm. FirstName & FirstName LastName → couple | law_firm or contact_name |
| 4.5 | First word = common first name, ≤3 words | contact_name |
| 4.6 | Not-a-name word detected | company_name |
| 4.7 | "The" + proper noun | building_name |
| 4.8 | Street suffix, ≤4 words, no building keyword | address_line |
| 4.9 | Clean text, ≤5 words | contact_name |

### Second Pass — Line Joining

After individual classification, adjacent lines are joined:

| Line type | + Next line type | Result |
|-----------|-----------------|--------|
| company_name / law_firm / untitled contact | law_firm | Join into one law_firm |
| care_of | law_firm | Join, update care_of type to law_firm |
| titled contact (Attn:, Pres:, etc.) | law_firm | Do NOT join |

### Third Pass — Assembly

Maps classified types into the output structure (contacts, companies, law_firms, address, etc.). c/o with address type goes directly to address.lines (no care_of record created).

---

## Complete Dictionary Lists

All dictionaries live in `classifier/dictionaries.py`. This is the ONLY file to edit when adding keywords.

### Contact Prefixes (with colon)
```
Attn:, Att:, Attan:, Atttn:, Atth:, Atnn:, Attm:, Annt:, Arttn:, Attb:,
Pres:, Press:, Presd:, PresL, Pares:, Presx:, Presw:, Prees:, Ptres:,
Prres:, Prews:, Peres:, Ptes:, Presa:,
VP:, ASO:, ASP:, AASO:, Dir:, Co-Pres:, Mayor:, Warden:,
Treas:, Tres:, Sec:, CFO:, CEO:, COO:, SVP:,
Chair:, Chairman:, Trustee:, Executor:, Executrix:,
Bishop:, Pastor:, Counsel:, Mgr:, GM:,
Clerk:, Reeve:, Chief:, Principal:, SO:, RSO:, CP:,
AKA:, Pres., Pres;, Attn;, Sttn:,
Mr:, Mr., Mrs:, Mrs., Ms:, Ms., Dr:, Dr., Attention, Pre:, Pred:, Prs:
```

### Contact Prefixes (without colon)
```
Attn, Att, Atn, Pres, ASO, Mr, Mrs, Ms, Dr
```

### Phone Patterns
```
NNN-NNN-NNNN, NNNNNN-NNNN, NNN-NNNNNNN (+ optional x/ext extension)
```

### Corporate Suffixes
```
Inc., Inc, Corp., Corp, Ltd., Ltd, Limited, LLC, LP, Co., Foundation,
Association, Holdings, ULC
```

### Law Firm Keywords
```
LLP, Barristers, Solicitors, Barrister, Solicitor, Law Office, Law Firm,
Notary, Notaire, Avocats, Attorney, Attorneys, Professional Corporation,
LLB, Q.C.
NOTE: bare "QC" removed — conflicts with Quebec.
```

### Company Keywords (includes former department keywords)
```
Properties, Realty, Capital, REIT, Investments, Developments, Enterprises,
Partners, Healthcare, Residences, Management, Development, Investment Trust,
Pension, Board, Corporation, Solutions, Homes, Construction,
Senior Living, Health Care, Living, Retirement, Real Estate, Advisors,
Services, Consulting, Financial, Hotel, Motel, Housing, Acquisition,
Church, Group, Companies, Station, Outlet, Office, Postal,
Associates, Company, Authority, Parking, Bank, Rentals, Products, Plastics,
Insurance, Assurance, Automotive, Transport, Catering, Winery, Brewery,
Dispensary, Bookstore, Builders, Inn, Hoist, Mirror, Glass, Pipe, Tool,
Printers, Fitness, Sodding, Landscaping, Plumbing, Welding, Paving,
Aluminium, Aluminum, Rehab, Daycare, Dental, Commercial, Accounting,
Accountants, Systems, System, Wealth, Regency, Farms, Motor, Auto,
Retail, Wholesale, School, Lawyers, Lawyer, International, National,
Provincial, Chartered, Certified, Hospitality, Conference, Equity, Mortgages,
Nissan, Honda, Hyundai, Kia, Ford, Benz, Sobeys, Loblaws, Walmart, Costco,
Shoppers, Receiver, Appointed, Infrastructure, Lodges, Lodge, Estates, Estate,
Hospital, Printing, Club, Golf, Topsoil, Storage, Wire, Packers, Express,
Volkswagen, Volkswagon, Audi,
Department, Dept, Division, Legal Services, Legal Department,
Corporate Real Estate, Corporate Services, Real Estate Department,
Real Estate Branch, Mail Code, REPDO, Special Accounts, Head Office,
RT Office, Marketing Section, Development Section, Ministry of,
Special Loans, University Operations, Rental Office, Project Lending,
NCA Property Transactions, Air & Marine Programs, Mail Stop,
Facilities and Real Estate, Sales and Acquisitions, Executive Offices, Offices
```

### Building Keywords
```
Tower, Centre, Center, Place, Plaza, Building, Bldg, Hall, House, Campus,
Complex, Mall, Podium, Edifice, Industrial Park, Nursing Home,
Corporate Office, Ctr, Blk
```

### Building Context Keywords (only match without digit + street suffix)
```
Court, Square
```

### Street Suffixes (English + French)
```
English: St, Ave, Rd, Dr, Blvd, Cres, Way, Ct, Pl, Lane, Line, Pkwy, Hwy,
Circle, Gate, Trail, Walk, Grove, Terr, Terrace, Crt, Court, Close, Path,
Run, Rise, Glen, Park, Square, Green, Quay, Landing, Manor, Route, Road,
Highway, Concession, Conc, Sideroad, Queensway, Donway, Esplanade

French: rue, boulevard, bld, chemin, ch, promenade, autoroute, montée,
montee, côte, cote
```

### Not-a-Name Words (common words that are never first names)
```
Junction, Canada, Old, Blue, Red, Green, Black, White, Golden, Silver,
Royal, Star, Sun, Moon, Cedar, West, East, North, South, Central, Upper,
Lower, Bay, Lake, River, Creek, Hill, Valley, Ridge, Mountain, New, Grand,
Premier, Diamond, Crown, Imperial, Pro, Express, Direct, Master, Elite,
Pen, Budget, Extended, Stay, Coming, Generation, Vice, President,
Treasurer, Secretary, Director
```

### NOT_A_PERSON_WORDS (words that NEVER appear in a person's name)
```
Inc., Inc, Corp., Corp, Ltd., Ltd, Limited, LLC, LLP, Co., LP, Holdings,
Properties, Realty, Department, Dept, Deptartment, Division, Services,
Management, REIT, Trust, Board, Pension, ULC
```

### Common First Names
~300 names covering English male, English female, and international names common in Ontario CRE. See `dictionaries.py` for the full list.

---

## How to Run

```bash
# Full extraction + assembly from source HTML (~4 minutes)
python3 run_pipeline.py

# Full classification from assembled JSON (~25 seconds, 16 cores)
python3 run_classifier.py

# Run all 106 fixtures
python3 test_harness.py

# Cross-check classified output against all dictionaries
python3 crosscheck.py

# Visual review in browser
python3 review.py RT101601 RT57431

# Review with limit
python3 review.py --limit 50
```

---

## How to Improve — Structured Process

When you find a classification issue (through review, crosscheck, or the app):

### Step 1: Diagnose

Identify which layer is responsible:
- Is a definitive pattern being missed? → Layer 1 (regex/pattern issue)
- Is an address being caught by a keyword? → Layer 2/3 ordering issue
- Is a keyword missing from a dictionary? → Layer 3 (add to dictionaries.py)
- Is a default classification wrong? → Layer 4 (contextual logic)
- Are two adjacent lines not being joined? → Second pass (joining rules)

### Step 2: Trace

Run the line through `_classify_single_line` to see exactly which rule catches it:
```python
python3 -c "
from classifier.contacts import _classify_single_line
lt, data = _classify_single_line('the problematic text')
print(f'{lt}: {data}')
"
```

### Step 3: Plan the Fix

Determine which file and which section needs changing:

| Issue type | Fix location |
|-----------|--------------|
| Missing keyword | `dictionaries.py` — add to the appropriate list |
| Missing contact prefix | `dictionaries.py` — CONTACT_PREFIXES_WITH_COLON or _NO_COLON |
| Missing first name | `dictionaries.py` — COMMON_FIRST_NAMES |
| Wrong layer catching it | `contacts.py` — reorder within the layer or add a guard |
| Joining issue | `contacts.py` — `_join_lines` function |
| Header/site/consideration/broker issue | respective classifier file |

### Step 4: Implement

1. Make the change in the appropriate file
2. Clear Python cache: `find . -name '__pycache__' -exec rm -rf {} +`
3. Test the specific line: `python3 -c "from classifier.contacts import ..."`
4. Run fixtures: `python3 test_harness.py`

### Step 5: Validate at Scale

1. Re-classify the full dataset: `python3 run_classifier.py`
2. Run cross-check: `python3 crosscheck.py`
3. Compare cross-check numbers to previous run — nothing should get worse

### Step 6: Update Fixtures

If the change improves classification for approved fixtures, update them:
```python
python3 -c "
import json, os
from classifier.classify import classify_record
# Re-classify and save
"
```

### Step 7: Document

If the change adds a new dictionary word: it's self-documenting in `dictionaries.py`.
If the change alters layer logic: update this document's Layer tables.

### Rules for Changes

1. **Never change dictionaries.py without running test_harness.py after**
2. **Never change contacts.py layer ordering without running crosscheck.py after**
3. **Never update fixtures without understanding WHY the output changed**
4. **Dictionary additions are safe.** Adding a keyword to COMPANY_KEYWORDS cannot break existing classifications — it can only catch things that previously fell through.
5. **Layer reordering is risky.** Moving a check earlier means it catches things before later checks can see them. Always verify with crosscheck.
6. **Guard additions are moderate risk.** A new guard can block correct classifications. Test with specific examples AND crosscheck.

---

## File Reference

| File | Purpose | When to edit |
|------|---------|-------------|
| `classifier/dictionaries.py` | ALL keyword/pattern lists | Adding keywords, prefixes, names |
| `classifier/contacts.py` | 4-layer classification + joining + assembly | Changing classification logic |
| `classifier/header.py` | Date, price, city/region, address entries | Header parsing changes |
| `classifier/parties.py` | Party name extraction + phone + continuation joining | Party line logic |
| `classifier/site.py` | PIN, acreage, legal description, location | Site parsing |
| `classifier/consideration.py` | Cash, debt, chattels, charges | Consideration parsing |
| `classifier/broker.py` | Brokerage, agents, phone | Broker parsing |
| `classifier/description.py` | Join lines into string | Trivial, rarely changes |
| `classifier/classify.py` | Orchestrator — calls all section classifiers | Only if adding/removing sections |
| `parsers/detail.py` | Structural HTML parser | Only if Realtrack HTML format changes |
| `parsers/normalize.py` | HTML entity decoding, whitespace normalization | Rarely changes |
| `parsers/export.py` | Export JSON reader | Trivial, rarely changes |
| `parsers/results.py` | Results HTML row parser | Rarely changes |
| `assembler.py` | Joins three sources by position | Only if join logic needs updating |
| `crosscheck.py` | Dictionary cross-check tool | When fields change |
| `review.py` | Browser review report generator | When output format changes |
| `test_harness.py` | Fixture validation | When adding new test types |
| `run_pipeline.py` | Extraction + assembly runner | Rarely changes |
| `run_classifier.py` | Parallel classification runner | Rarely changes |
| `config.json` | Source data path | When moving data |

---

## Known Limitations

1. **~60 other_lines across 126K records** — edge cases that escape all 4 layers. Mostly malformed postal codes with special characters, extremely rare contact prefix typos, and international address formats.

2. **~252 no-digit address lines** — mostly legitimate (General Delivery, "One..." word-numbers, real street-name-only). ~50 genuinely ambiguous (Queen's Park, Fast Lane).

3. **Law firms without keywords** — firms named "LastName & LastName" without LLP/Barristers are detected by the & pattern in Layer 4.4. Firms with just a bare name (no & or keywords) default to contact_name unless followed by a "Barristers & Solicitors" line (joining pass catches these).

4. **Person names with uncommon first names** — if the first name isn't in COMMON_FIRST_NAMES, the name won't be detected by Layer 4.5. In c/o context, it defaults to company. In regular contact context, it defaults to contact_name.

5. **"Co" corporate suffix vs "CO" state abbreviation** — resolved by checking city/province BEFORE corporate suffix (Layer 3.1 before 3.2) and only checking the city part for corporate suffix, not the province part.
