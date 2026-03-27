# Cleo Engine

Data extraction and classification engine for Ontario commercial real estate transaction data from Realtrack. Reads 126,000+ saved HTML files and produces clean, structured, classified JSON records.

## Pipeline

Three steps, each saves its output independently:

### Step 1: Structural Extraction (`run_pipeline.py`)
Three parsers read the source HTML/JSON files and extract raw text by HTML structure:
- `parsers/detail.py` — detail HTML pages (the main transaction data)
- `parsers/export.py` — export.json (already structured)
- `parsers/results.py` — results.html (seller/buyer names)

The assembler (`assembler.py`) joins the three by position within each page folder and cross-checks address/price/date to verify the join.

Output: `pipeline/extracted/` and `pipeline/assembled/`

### Step 2: Classification (`run_classifier.py`)
A 4-layer classification system (`classifier/contacts.py`) processes each assembled record:
- **Layer 1**: Definitive patterns (postal codes, phones, countries, contact prefixes, c/o, PO Box)
- **Layer 2**: Structural address patterns (digit + street suffix, word-numbers, modifiers)
- **Layer 3**: Keyword dictionaries (city/province, corporate suffix, law firm, building, company)
- **Layer 4**: Contextual defaults (& pattern for law firms, first name matching, clean text)

All keywords live in one file: `classifier/dictionaries.py`

Runs in parallel across all CPU cores. 126K records in ~25 seconds.

Output: `pipeline/classified/`

### Step 3: Load (future)
Load classified JSON into a database for the web app.

## Testing

106 manually reviewed and approved fixtures in `fixtures/`. Run the test harness:
```
python3 test_harness.py
```

Cross-check classified output against all dictionaries:
```
python3 crosscheck.py
```

Visual review in browser:
```
python3 review.py RT101601 RT57431
```

## Running

```
# Full extraction + assembly (from source HTML)
python3 run_pipeline.py

# Full classification (from assembled JSON)
python3 run_classifier.py

# Test fixtures
python3 test_harness.py
```

## Folder structure

```
cleo-engine/
  parsers/              — three source parsers + normalization
  classifier/           — 4-layer classification system + dictionaries
  fixtures/             — 106 approved test cases (detail.html + approved JSON)
  schema/               — structural schema definition + historical planning docs
  pipeline/             — output (not in git)
    extracted/          — step 1 output
    assembled/          — step 2 output
    classified/         — step 3 output
  reports/              — generated HTML review reports
  config.json           — source data path
  assembler.py          — joins three sources by position
  run_pipeline.py       — runs extraction + assembly
  run_classifier.py     — runs classification (parallel)
  test_harness.py       — validates fixtures
  crosscheck.py         — dictionary cross-check
  review.py             — generates browser review reports
```

## Source data

Source HTML files: `~/cleo-facts/cleo-data/rt/` (configured in `config.json`). The engine reads from there but never modifies those files.
