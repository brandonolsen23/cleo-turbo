# Address Normalization & Expansion Plan

**Status:** PLAN — not yet implemented
**Input:** `pipeline/classified/` (read-only)
**Output:** `pipeline/addresses/` (new stage)
**Benchmark:** All changes must preserve RT ID linkage. No data lost.

---

## Overview

This is a NEW pipeline stage, completely independent from structural extraction and classification. It reads classified JSON, normalizes all addresses, decomposes them into components, expands range addresses, normalizes PIN/ARN for API queries, and produces geocode-ready output.

```
pipeline/classified/   (input — read only, never modified)
    ↓
Address Normalization & Expansion
    ↓
pipeline/addresses/    (output — one JSON per RT)
```

---

## Design Principles

1. **Read-only from classification.** Never modify classified output.
2. **All three address sources treated equally.** Header (property), seller (mailing), buyer (mailing) — all get the same normalization, decomposition, and geocode preparation.
3. **Long form everywhere.** Street → Street (not St). Avenue → Avenue (not Ave). Ontario → Ontario (not ON). West → West (not W).
4. **Title Case for storage.** "247 Summerlea Road" not "247 SUMMERLEA RD".
5. **Every address decomposes into components.** Street number, name, suffix, direction, suite — structured for search, display, and geocoding.
6. **Range addresses expand to searchable variations.** 69-71 Selby Road → three search entries.
7. **PIN/ARN normalized for provincial API.** ARN: 20-digit zero-padded. PIN: 9-digit no dash.

---

## File Structure

```
address_normalizer/
  __init__.py
  normalize.py         ← case, suffix, direction, province normalization
  decompose.py         ← break address into components (THE HARD ONE)
  expand.py            ← range address expansion, search key generation
  pin_arn.py           ← PIN/ARN normalization for API
  dictionaries.py      ← suffix maps, direction maps, province maps
  run.py               ← orchestrator — reads classified, writes addresses
```

---

## Normalization Rules

### Case: Title Case

| Input | Output |
|-------|--------|
| `247 SUMMERLEA RD` | `247 Summerlea Road` |
| `14 Big Moe Cres` | `14 Big Moe Crescent` |
| `PO Box 265` | `PO Box 265` (PO stays uppercase) |
| `RR 2` | `RR 2` (RR stays uppercase) |

Exceptions that stay uppercase: PO, RR, NE, NW, SE, SW (only when kept as abbreviations for internal use).

### Street Suffix: Long Form

```
St → Street          Ave → Avenue         Rd → Road
Dr → Drive           Blvd → Boulevard     Cres → Crescent
Way → Way            Ct → Court           Pl → Place
Lane → Lane          Line → Line          Pkwy → Parkway
Hwy → Highway        Cir/Circle → Circle  Gate → Gate
Trail → Trail        Walk → Walk          Grove → Grove
Terr → Terrace       Crt → Court          Close → Close
Path → Path          Run → Run            Rise → Rise
Glen → Glen          Park → Park          Square → Square
Green → Green        Quay → Quay          Landing → Landing
Manor → Manor        Route → Route        Road → Road
Concession → Concession   Conc → Concession
Sideroad → Sideroad       Queensway → Queensway
Donway → Donway           Esplanade → Esplanade
```

French:
```
rue → Rue            boulevard/bld → Boulevard
chemin/ch → Chemin   promenade → Promenade
autoroute → Autoroute   montée/montee → Montée
côte/cote → Côte
```

### Direction: Long Form

```
N → North      S → South      E → East       W → West
NE → Northeast NW → Northwest SE → Southeast SW → Southwest
```

### Province: Long Form

```
ON/Ont → Ontario                    QC → Quebec
AB → Alberta                        BC → British Columbia
MB → Manitoba                       SK → Saskatchewan
NS → Nova Scotia                    NB → New Brunswick
NL → Newfoundland                   PE → Prince Edward Island
YT → Yukon                          NT → Northwest Territories
NU → Nunavut

US states: CA → California, CO → Colorado, NY → New York, etc.
```

Typo variants normalized: OntArio → Ontario, Illimois → Illinois, etc.

### Country: Long Form

```
USA → United States
UK → United Kingdom
```

---

## Address Decomposition

Every address line gets broken into structured components.

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| `street_number` | Civic number or range | "247" or "69-71" |
| `street_name` | Street name | "Summerlea" |
| `street_suffix` | Long form suffix | "Road" |
| `street_direction` | Long form direction | "West" |
| `suite_type` | Suite/Unit/Apt designation | "Suite" |
| `suite_number` | Suite/unit number | "4200" |

### Decomposition Logic

This is the hardest part. The logic must handle:

**Standard format:** `66 Wellington St W, Ste 4200`
```
street_number: 66
street_name: Wellington
street_suffix: Street
street_direction: West
suite_type: Suite
suite_number: 4200
```

**Range format:** `69 - 71 Selby Rd`
```
street_number: 69-71
street_name: Selby
street_suffix: Road
street_direction: (empty)
suite_type: (empty)
suite_number: (empty)
```

**No suite:** `247 Summerlea Rd`
```
street_number: 247
street_name: Summerlea
street_suffix: Road
street_direction: (empty)
suite_type: (empty)
suite_number: (empty)
```

**Unit in address:** `5155 Spectrum Way, Unit 31`
```
street_number: 5155
street_name: Spectrum
street_suffix: Way
street_direction: (empty)
suite_type: Unit
suite_number: 31
```

**Multiple words in street name:** `123 Commerce Valley Drive East`
```
street_number: 123
street_name: Commerce Valley
street_suffix: Drive
street_direction: East
```

**PO Box:** `PO Box 265`
```
street_number: (empty)
street_name: (empty)
street_suffix: (empty)
street_direction: (empty)
suite_type: PO Box
suite_number: 265
```

**Rural Route:** `RR 2`
```
street_number: (empty)
street_name: (empty)
street_suffix: (empty)
street_direction: (empty)
suite_type: RR
suite_number: 2
```

### Decomposition Steps

Order is critical. Each step removes noise before the next step runs.

```
1. Strip descriptive preamble ("LOCATED AT 6301 Silver Dart Dr" → "6301 Silver Dart Dr")
2. Normalize highway hash numbers ("Highway #7" → "Highway 7") — must happen before unit extraction sees the #
3. Protect saint names ("St Thomas" → mark as saint, not "Street Thomas")
4. Collapse possessives ("Queen's" → "Queens") — prevents "'s" from becoming "South"
5. Check for PO Box / RR / General Delivery — special types, not decomposable as street
6. Extract unit/suite (multiple patterns, tried in order):
   a. Leading hash: "#5 861 York Mills Road" → unit=5
   b. Leading keyword: "Unit A4B 40 Kingston Road" → unit=A4B
   c. Leading keyword with comma: "Suite 2430, PO Box 519, 161 Bay St" → unit=2430
   d. Dash-joined unit: "B7-77 Billy Bishop Way" → unit=B7 (letter on left = unit)
   e. Trailing keyword: "123 Main St, Suite 200" → unit=200
   f. Trailing ordinal floor: "2441 Yonge St, 2nd Floor" → unit=2nd Floor
   g. Trailing hash: "45 King St, #301" → unit=301
7. Extract street number — digits at start, with handling for:
   a. Simple: "247"
   b. Letter suffix: "620A", "54B"
   c. Fractions: "399 1/2", "84 1/2"
   d. Half symbol: "½" → "1/2"
   e. Plus suffix: "1255A+B"
   f. Range (pure digits both sides): "69 - 71" → range, not unit
   g. Comma/ampersand lists: "165, 170, 180" (multi-address)
   h. Slash lists: "245/251"
8. Extract direction — N/S/E/W/NE/NW/SE/SW at end, after suffix
9. Extract suffix — match known suffix, with guards:
   a. Compound road check: "County Road 93" → "Road" stays part of name
   b. Embedded suffix scan: if no suffix at end, scan left-to-right for embedded suffix with junk after it
10. Remaining words — street name
11. Restore saint names: "SAINT THOMAS" → display as "St. Thomas" or "Saint Thomas"
```

### Dash Ambiguity Rule

The dash between two parts of an address is ambiguous. The rule:

| Pattern | Left side | Interpretation | Example |
|---------|-----------|---------------|---------|
| `NN-NN` | Pure digits both sides | **Range address** | `69-71 Selby Rd` |
| `LN-NN` | Letter+digit on left | **Unit-number** | `B7-77 Billy Bishop Way` |
| `L-NN` | Single letter on left | **Unit-number** | `E-2015 Parkedale Ave` |
| `NL-NN` | Digit+letter on left | **Unit-number** | `2A-5005 South Service Rd` |
| `N-ordinal` | Number-dash-ordinal | **Number + ordinal street** | `67-45th Street` |

### Saint Name Protection

Before expanding suffixes, protect known saint names so "St" doesn't become "Street":

```
St. Thomas, St Thomas, St. Catharines, St Catharines,
St. John's, St Johns, St. Laurent, St Laurent,
St. Jacobs, St. Marys, St. George, St. Clair,
St. Albert, St. Boniface, St. Paul, St. Andrews,
St. Peter, St. Patrick, St. Bernard, St. Helens
```

Rule: if "St" or "St." is followed by a word from the saint names list → protect it (it means "Saint", not "Street").

### Possessive Handling

Before suffix/direction expansion, collapse possessives:

```
Queen's → Queens    (prevents "'s" → "South")
O'Neill → O'Neill   (keep — not a possessive)
John's → Johns      (prevents "'s" → "South")
```

Rule: replace `'s` and `'s` (smart quote) at end of a word with `s`. Only the `'s` suffix, not all apostrophes.

### Compound Road Names

When these words precede a suffix word, the suffix is part of the road name — do NOT split:

```
County Road, Country Road, Regional Road, Old Highway,
Fire Route, Concession Road
```

"County Road 93" → street_name="County Road 93", suffix="" (not name="County", suffix="Road")

### Highway Hash Normalization

Strip `#` from highway route numbers before unit extraction:

```
Highway #7     → Highway 7
Hwy, #50 North → Highway 50 North
Hwy #20        → Highway 20
```

Must run before unit extraction — otherwise `#7` looks like a unit number.

### Embedded Suffix Detection

When no suffix is found at the end of the line, scan left-to-right for an embedded suffix followed by recognizable trailing junk:

```
KENT STREET WEST LINDSAY SQ MALL → suffix=Street, direction=West, name=Kent
DIXIE ROAD STORE NO 12           → suffix=Road, name=Dixie
```

Only split if what follows the suffix is: a known city name, a province code, or a junk marker (Store, Mall, Plaza, etc.).

### Descriptive Preamble Stripping

Some addresses have descriptive text before the actual address:

```
TAXI STAND FOR DRIVERS LOCATED AT 6301 SILVER DART DRIVE → 6301 Silver Dart Drive
LOCATED AT 123 MAIN STREET                                → 123 Main Street
```

Rule: if the line contains "LOCATED AT" followed by a street number, strip everything before it.

### Unit Value Overflow

Sometimes the captured unit value contains the street address:

```
Suite C9 1270 Fischer Hallman Road → unit=C9, street=1270 Fischer Hallman Road
```

After extracting a unit, check if the unit value contains a street number + street name. If so, split: keep the short part as unit, put the rest back as the street.

### Edge Cases Summary

| Input | Challenge | Handling |
|-------|-----------|----------|
| `401 The West Mall` | "West" is direction AND part of name | Known street list or: "The" before direction = name |
| `14-3650 Langstaff Rd` | Dash-joined unit | Left side shorter + digit = unit |
| `B7-77 Billy Bishop Way` | Dash-joined unit | Letter on left = unit |
| `69-71 Selby Rd` | Range | Pure digits both sides = range |
| `One Mount Pleasant Rd` | Word-number | "One" → "1" for components |
| `6721 Fourth Line` | "Fourth" is name, "Line" is suffix | Street name = "Fourth", suffix = "Line" |
| `CONC 4, PT LOT 5` | Legal description | Flag as non-decomposable |
| `HAZELDEAN RD` | No street number | street_number empty, decompose name/suffix |
| `General Delivery` | Not an address | Special type, no decomposition |
| `St. Thomas St` | "St" = Saint AND Street | Saint list protects first "St", second expands |
| `Queen's Park` | Possessive | Collapse to "Queens Park" before expansion |
| `County Road 93` | Compound road name | "Road" stays in name, not extracted as suffix |
| `Highway #7` | Hash in highway | Strip # before processing |
| `620A Main St` | Letter suffix on number | street_number = "620A" |
| `399 1/2 King St` | Fraction in number | street_number = "399 1/2" |
| `#5 861 York Mills Rd` | Leading hash unit | unit=5, address=861 York Mills Rd |
| `Suite C9 1270 Fischer Rd` | Unit value contains address | Split: unit=C9, address=1270 Fischer Rd |
| `Kent St W Lindsay Sq Mall` | Embedded suffix with junk | suffix=Street, name=Kent, junk stripped |
| `LOCATED AT 6301 Silver Dr` | Descriptive preamble | Strip "LOCATED AT" prefix |
| `67-45th Street` | Number-dash-ordinal | number=67, name=45th, suffix=Street |

---

## Range Address Expansion

"69 - 71 Selby Road" produces:

```json
{
  "canonical": "69-71 Selby Road",
  "variations": [
    {"display": "69-71 Selby Road", "search_key": "69-71 selby road"},
    {"display": "69 Selby Road", "search_key": "69 selby road"},
    {"display": "71 Selby Road", "search_key": "71 selby road"}
  ]
}
```

Only endpoints expanded (69 and 71), not every number in between.

All variations link to the same RT ID. Search for any → find the RT.

---

## PIN/ARN Normalization

### ARN → Provincial API Format

**Rule:** Strip all spaces, right-pad with zeros to exactly 20 digits.

| Source | Original | API Format (20 digits) |
|--------|----------|----------------------|
| Realtrack | `21 10 100 025 27110` | `21101000252711000000` |
| Realtrack | `19 04 062 100 00600` | `19040621000060000000` |
| Realtrack | `34 24 000 005 04200` | `34240000050420000000` |

API endpoint: `https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services/AIA/Assessment_Parcel_Map/MapServer/0/query`
Query parameter: `where=ASSESSMENT_ROLL_NUMBER='NNNNNNNNNNNNNNNNNNNN'`

### PIN → API Format

**Rule:** Strip dash, keep as 9 digits.

| Source | Original | API Format (9 digits) |
|--------|----------|----------------------|
| Realtrack | `14024-0032` | `140240032` |
| Realtrack | `08074-0030` | `080740030` |

Query parameter: `where=PIN='NNNNNNNNN'`

**Note:** PIN queries had high failure rates in previous runs. ARN queries and spatial (coordinate) queries were more reliable. PIN format is still normalized for completeness and for matching against GeoWarehouse data.

### Output

```json
{
  "pin": {
    "original": "14024-0032",
    "display": "14024-0032",
    "api_format": "140240032",
    "multiple": false
  },
  "arn": {
    "original": "21 10 100 025 27110",
    "display": "21 10 100 025 27110",
    "api_format": "21101000252711000000"
  }
}
```

---

## Search Key Generation

Every address produces a `search_key` — a lowercase, normalized string for matching.

| Display | Search Key |
|---------|-----------|
| `247 Summerlea Road` | `247 summerlea road` |
| `66 Wellington Street West, Suite 4200` | `66 wellington street west` |
| `PO Box 265` | `po box 265` |

Search keys DROP suite/unit information (you don't search by suite number). They keep street number, name, suffix, direction.

Additional search key without suffix (for partial matching):
| Display | Partial Key |
|---------|------------|
| `247 Summerlea Road` | `247 summerlea` |

This lets "247 summerlea" match even if the user doesn't type "road".

---

## Geocode String Assembly

Each address produces a `geocode_string` — a complete address formatted for a geocoding API.

**Format:** `{street_number} {street_name} {suffix} {direction}, {city}, {province} {postal}, Canada`

| Components | Geocode String |
|-----------|----------------|
| 247 Summerlea Road, Brampton, Ontario, L6T 4E1 | `247 Summerlea Road, Brampton, Ontario L6T 4E1, Canada` |
| 66 Wellington Street West, Toronto, Ontario, M5K 1N6 | `66 Wellington Street West, Toronto, Ontario M5K 1N6, Canada` |
| 6600 LBJ Freeway, Dallas, Texas, 75240 | `6600 LBJ Freeway, Dallas, Texas 75240, United States` |

Postal code included when available (from export data or contact section). Country appended based on province — Ontario/Quebec/etc. → "Canada", Texas/California/etc. → "United States".

Non-geocodable addresses (legal descriptions, street-name-only) get `geocode_string: null`.

---

## Complete Output Schema

One JSON file per RT in `pipeline/addresses/`:

```json
{
  "rt_id": "RT101601",

  "property": {
    "addresses": [
      {
        "original": "247 SUMMERLEA RD",
        "display": "247 Summerlea Road",
        "components": {
          "street_number": "247",
          "street_name": "Summerlea",
          "street_suffix": "Road",
          "street_direction": "",
          "suite_type": "",
          "suite_number": ""
        },
        "search_keys": ["247 summerlea road", "247 summerlea"],
        "variations": [],
        "geocode_string": "247 Summerlea Road, Brampton, Ontario L6T 4E1, Canada",
        "geocodable": true,
        "type": "street_address"
      }
    ],
    "city": "Brampton",
    "region": "Peel Region",
    "postal_from_export": "L6T 4E1"
  },

  "seller": {
    "address": {
      "original_lines": ["14 Big Moe Cres"],
      "display": "14 Big Moe Crescent",
      "components": {
        "street_number": "14",
        "street_name": "Big Moe",
        "street_suffix": "Crescent",
        "street_direction": "",
        "suite_type": "",
        "suite_number": ""
      },
      "search_keys": ["14 big moe crescent", "14 big moe"],
      "geocode_string": "14 Big Moe Crescent, Brampton, Ontario L6P 1J7, Canada",
      "modifiers": [],
      "building_names": [],
      "city": "Brampton",
      "province": "Ontario",
      "postal": "L6P 1J7",
      "country": ""
    }
  },

  "buyer": {
    "address": {
      "original_lines": ["147 Whitwell Dr"],
      "display": "147 Whitwell Drive",
      "components": {
        "street_number": "147",
        "street_name": "Whitwell",
        "street_suffix": "Drive",
        "street_direction": "",
        "suite_type": "",
        "suite_number": ""
      },
      "search_keys": ["147 whitwell drive", "147 whitwell"],
      "geocode_string": "147 Whitwell Drive, Brampton, Ontario L6P 1L2, Canada",
      "modifiers": [],
      "building_names": [],
      "city": "Brampton",
      "province": "Ontario",
      "postal": "L6P 1L2",
      "country": ""
    }
  },

  "pin": {
    "original": "14024-0032",
    "display": "14024-0032",
    "api_format": "140240032",
    "multiple": false
  },

  "arn": {
    "original": "21 10 100 025 27110",
    "display": "21 10 100 025 27110",
    "api_format": "21101000252711000000"
  }
}
```

### Range Address Example

```json
{
  "original": "69 - 71 SELBY RD",
  "display": "69-71 Selby Road",
  "components": {
    "street_number": "69-71",
    "street_name": "Selby",
    "street_suffix": "Road",
    "street_direction": "",
    "suite_type": "",
    "suite_number": ""
  },
  "search_keys": ["69-71 selby road", "69 selby road", "71 selby road", "69-71 selby", "69 selby", "71 selby"],
  "variations": [
    {"number": "69-71", "display": "69-71 Selby Road"},
    {"number": "69", "display": "69 Selby Road"},
    {"number": "71", "display": "71 Selby Road"}
  ],
  "geocode_string": "69 Selby Road, ...",
  "geocodable": true,
  "type": "street_address"
}
```

---

## Implementation Order

### Phase 1: Foundation
1. `dictionaries.py` — suffix maps, direction maps, province maps
2. `normalize.py` — case, suffix, direction, province conversion
3. `pin_arn.py` — PIN/ARN formatting (simplest, most deterministic)

### Phase 2: Decomposition
4. `decompose.py` — break addresses into components
   - Start with standard format (number + name + suffix + direction)
   - Add suite extraction
   - Add range handling
   - Add PO Box / RR / General Delivery special cases
   - Add edge cases (word-numbers, multi-word names, etc.)

### Phase 3: Assembly
5. `expand.py` — range expansion, search key generation, geocode string assembly
6. `run.py` — orchestrator, reads classified output, writes address output

### Phase 4: Validation
7. Review samples across all address types
8. Cross-check: decomposition + reassembly = original address (round-trip test)
9. Spot-check geocode strings against a geocoder for accuracy

---

## How to Extend Later

### Adding geocoding
A future independent process reads `pipeline/addresses/` and:
1. Takes each `geocode_string`
2. Sends to MapTiler / geocoding API
3. Gets back lat/lng + normalized city name
4. Writes to `pipeline/geocoded/` (another new stage)

### Adding parcel polygon lookup
Another independent process reads `pipeline/addresses/` and:
1. Takes `arn.api_format` (20-digit)
2. Queries provincial ArcGIS API
3. Gets back polygon geometry
4. Writes to `pipeline/parcels/`

### Adding city normalization
After geocoding returns coordinates:
1. Reverse-geocode lat/lng → current official city name
2. Point-in-polygon against census subdivision boundaries → population
3. Add `city_normalized` and `market_population` to address data

Each of these is a separate, independent process reading from the previous stage's output. The address normalization stage just prepares the data — it doesn't call any external APIs.

---

## Known Challenges

1. **Multi-word street names** — "Commerce Valley Drive" vs "Valley Drive" — which words are the name and which is the suffix? Positional logic: suffix is always the LAST matching word, unless preceded by a compound road prefix.
2. **Direction ambiguity** — "West Mall" — is "West" a direction or part of the name? Rule: if "The" precedes the direction, it's part of the name ("The West Mall"). Otherwise direction.
3. **French addresses** — "510 Rue Hodge" — "Rue" is a prefix (before the name), not a suffix. Need French-specific decomposition: number + French suffix + name (reversed from English).
4. **Legal descriptions as addresses** — "CONC 4, PT LOT 5" — not decomposable into street components. Flag and skip.
5. **Missing postal codes** — not all records have postal codes in the export data. Geocoding will be less precise for these.
6. **International addresses** — US, European formats differ from Canadian. Need separate handling or at minimum flag them.
7. **Saint name / Street abbreviation collision** — "St" means both "Saint" and "Street". Must protect saint names before suffix expansion using a saint names dictionary.
8. **Possessive / direction collision** — "Queen's" has `'s` that could match "South". Must collapse possessives before direction expansion.
9. **Dash ambiguity** — dashes between numbers mean range OR unit-number. Rule: letter on either side = unit; pure digits = range.
10. **Compound road names** — "County Road 93" — "Road" is part of the name, not a suffix to extract. Protect with compound prefix list.
11. **Unit value overflow** — extracted unit sometimes contains the street address. Need to detect and split back.
12. **Descriptive preambles** — "LOCATED AT 6301 Silver Dart Dr" — strip non-address text before the actual address.
13. **Highway hash numbers** — "#7" in "Highway #7" must be stripped before unit extraction mistakes it for a unit.
