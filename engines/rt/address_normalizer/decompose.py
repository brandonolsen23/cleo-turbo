"""
Address decomposition — breaks a single address line into structured components.

This is the hardest module. It follows an 11-step pipeline defined in
schema/address_normalization_plan.md. Order matters — each step removes
noise before the next runs.

Reference: schema/address_normalization_plan.md § Address Decomposition
"""

import re
from .dictionaries import (
    SUFFIX_MAP, SUFFIX_LONG_FORMS, DIRECTION_MAP,
    COMPOUND_ROAD_PREFIXES, UNIT_KEYWORDS, ORDINAL_FLOOR_WORDS,
    WORD_NUMBER_MAP, JUNK_MARKERS, FRENCH_PREFIX_SUFFIXES,
)
from .normalize import (
    to_title_case, expand_suffix, expand_direction,
    protect_saints, restore_saints, collapse_possessives,
    normalize_highway_hash, strip_preamble,
)


def _empty_result():
    return {
        'street_number': '',
        'street_name': '',
        'street_suffix': '',
        'street_direction': '',
        'suite_type': '',
        'suite_number': '',
        'special_type': '',   # PO Box, RR, General Delivery, legal description
        'display': '',        # Reassembled normalized display string
    }


def decompose(line):
    """Decompose a single address line into structured components.

    Input:  Raw address string (e.g., "247 SUMMERLEA RD")
    Output: Dict with street_number, street_name, street_suffix,
            street_direction, suite_type, suite_number, special_type, display.
    """
    if not line or not line.strip():
        return _empty_result()

    text = line.strip()

    # === Step 1: Strip descriptive preamble ===
    text = strip_preamble(text)

    # === Step 2: Normalize highway hash ===
    text = normalize_highway_hash(text)

    # === Step 3: Protect saint names ===
    text, _saints = protect_saints(text)

    # === Step 4: Collapse possessives ===
    text = collapse_possessives(text)

    # === Step 5: Check PO Box / RR / General Delivery ===
    special = _check_special_type(text)
    if special:
        special['display'] = _build_display(special)
        return special

    # === Step 6: Extract unit/suite ===
    text, suite_type, suite_number = _extract_unit(text)

    # === Step 7: Extract street number ===
    text, street_number = _extract_street_number(text)

    # === Step 8-10: Extract direction, suffix, and street name ===
    # Work on the remaining words
    words = text.split()
    words = [w for w in words if w]  # Remove empty strings

    # === Step 8: Extract direction (last word) ===
    street_direction = ''
    if words:
        last = words[-1].rstrip('.,')
        # Handle hyphenated directions: N-W → NW
        dir_expanded = expand_direction(last)
        if not dir_expanded and '-' in last:
            collapsed = last.replace('-', '')
            dir_expanded = expand_direction(collapsed)
        if dir_expanded:
            # Guard: "The West Mall" — if preceding word is "The", it's a name
            if len(words) >= 2 and words[-2].lower() == 'the':
                pass  # Don't extract direction
            else:
                street_direction = dir_expanded
                words = words[:-1]

    # === Step 9: Extract suffix (last word after direction removed) ===
    street_suffix = ''
    if words:
        last = words[-1].rstrip('.,')
        suffix_expanded = expand_suffix(last)
        if suffix_expanded:
            # Compound road guard: check if preceding word is a compound prefix
            if len(words) >= 2 and words[-2].lower() in COMPOUND_ROAD_PREFIXES:
                pass  # Don't extract — it's "County Road 93" etc.
            else:
                street_suffix = suffix_expanded
                words = words[:-1]
        elif re.match(r'^\d+$', last) and len(words) >= 2:
            # Route number pattern: "Perth Rd 147" — suffix is second-to-last
            second_last = words[-2].rstrip('.,')
            route_suffix = expand_suffix(second_last)
            if route_suffix:
                # Expand the suffix in place but keep it all as the name (route name)
                words[-2] = route_suffix
                # Don't set street_suffix — the whole thing is the name
        if not street_suffix and not re.match(r'^\d+$', last):
            # Check for French prefix suffix (at the beginning)
            street_suffix = _check_french_prefix_suffix(words)
            if street_suffix:
                words = words[1:]  # Remove the French suffix from the front

    # If no suffix found at end, try embedded suffix scan
    if not street_suffix and len(words) >= 2:
        street_suffix, words, embedded_dir = _scan_embedded_suffix(words)
        if embedded_dir:
            street_direction = embedded_dir

    # === Step 10: Remaining words = street name ===
    street_name = ' '.join(words).strip(' ,')

    # Restore saint names in the street name
    street_name = restore_saints(street_name)

    # Apply title case to street name
    street_name = to_title_case(street_name)

    # Convert word-numbers in street number
    if street_number.lower() in WORD_NUMBER_MAP:
        street_number = WORD_NUMBER_MAP[street_number.lower()]

    result = {
        'street_number': street_number,
        'street_name': street_name,
        'street_suffix': street_suffix,
        'street_direction': street_direction,
        'suite_type': suite_type,
        'suite_number': suite_number,
        'special_type': '',
        'display': '',
    }
    result['display'] = _build_display(result)
    return result


# ---------------------------------------------------------------------------
# Step 5: Special types
# ---------------------------------------------------------------------------

def _check_special_type(text):
    """Check if the address is a PO Box, RR, or General Delivery."""
    upper = text.upper().strip()

    # PO Box
    m = re.match(r'^P\.?\s*O\.?\s*BOX\s+(\S+)', upper)
    if m:
        return {
            'street_number': '', 'street_name': '', 'street_suffix': '',
            'street_direction': '', 'suite_type': 'PO Box',
            'suite_number': m.group(1), 'special_type': 'po_box',
        }

    # RR (Rural Route)
    m = re.match(r'^R\.?\s*R\.?\s*#?\s*(\d+)', upper)
    if m:
        return {
            'street_number': '', 'street_name': '', 'street_suffix': '',
            'street_direction': '', 'suite_type': 'RR',
            'suite_number': m.group(1), 'special_type': 'rural_route',
        }

    # General Delivery
    if re.match(r'^GENERAL\s+DELIVERY', upper):
        return {
            'street_number': '', 'street_name': '', 'street_suffix': '',
            'street_direction': '', 'suite_type': 'General Delivery',
            'suite_number': '', 'special_type': 'general_delivery',
        }

    # Legal description: CONC, LOT, LOTS, PART LOT, PT LOT, PLAN
    if re.match(r'^(CONC|LOTS?|PART\s+LOTS?|PT\s+LOTS?|PLAN)\b', upper):
        return {
            'street_number': '', 'street_name': to_title_case(text.strip()),
            'street_suffix': '', 'street_direction': '',
            'suite_type': '', 'suite_number': '',
            'special_type': 'legal_description',
        }

    # Lot continuation: bare number lists like "21, 43 & 44" or "14, 15, 22, 23, 27"
    # These are continuation lines from multi-line lot descriptions that got split
    # by the address parser. They contain ONLY digits separated by commas/ampersands/dashes.
    if re.match(r'^\d+(?:\s*[-,&]\s*\d+)+\s*$', text.strip()):
        return {
            'street_number': '', 'street_name': to_title_case(text.strip()),
            'street_suffix': '', 'street_direction': '',
            'suite_type': '', 'suite_number': '',
            'special_type': 'lot_continuation',
        }

    return None


# ---------------------------------------------------------------------------
# Step 6: Unit/suite extraction
# ---------------------------------------------------------------------------

def _extract_unit(text):
    """Extract unit/suite from the address text. Returns (remaining_text, suite_type, suite_number)."""
    stripped = text.strip()

    # 6a. Leading hash: "#5 861 York Mills Road" or "#5-861 York Mills Road"
    m = re.match(r'^#\s*(\w+)\s*[-,]?\s*(.+)', stripped)
    if m:
        return m.group(2).strip(), '#', m.group(1)

    # 6b. Leading keyword: "Unit A4B 40 Kingston Road"
    # But also handle: "Suite C9 1270 Fischer Hallman Road" (unit overflow)
    for kw in ['suite', 'ste', 'unit', 'apt', 'apartment']:
        pattern = rf'^{kw}\.?\s+(\S+)\s*[,-]?\s*(.+)'
        m = re.match(pattern, stripped, re.IGNORECASE)
        if m:
            unit_val = m.group(1).rstrip(',')
            remainder = m.group(2).strip()
            # Check unit value overflow: does the remainder start with a number?
            # If unit_val itself looks like it contains a street number, split it
            return remainder, kw.capitalize() if kw != 'ste' else 'Suite', unit_val

    # 6c. Trailing keyword: "123 Main St, Suite 200" or "123 Main St Suite 200"
    for kw in ['suite', 'ste', 'unit', 'units', 'apt', 'apartment', 'floor', 'flr',
               'level', 'bureau', 'stn']:
        pattern = rf'^(.+?)\s*[,]\s*{kw}\.?\s+(.+?)$'
        m = re.match(pattern, stripped, re.IGNORECASE)
        if m:
            suite_label = kw.capitalize() if kw != 'ste' else 'Suite'
            if kw == 'flr':
                suite_label = 'Floor'
            return m.group(1).strip(), suite_label, m.group(2).strip().rstrip(',')

    # Also try without comma for trailing keyword
    for kw in ['suite', 'ste', 'unit', 'apt']:
        pattern = rf'^(.+?(?:Street|Avenue|Road|Drive|Boulevard|Crescent|Way|Court|Place|Lane|Line|Parkway|Highway|Circle|Gate|Trail|Walk|Grove|Terrace|Close|Path|Run|Rise|Glen|Park|Square|Green|Quay|Landing|Manor|Route|Concession|Sideroad|Queensway|Donway|Esplanade|Rue|Chemin|Promenade|Autoroute|St|Ave|Rd|Dr|Blvd|Cres|Ct|Pl|Hwy|Cir|Terr|Crt)\.?)\s+{kw}\.?\s+(.+?)$'
        m = re.match(pattern, stripped, re.IGNORECASE)
        if m:
            suite_label = kw.capitalize() if kw != 'ste' else 'Suite'
            return m.group(1).strip(), suite_label, m.group(2).strip().rstrip(',')

    # 6d. Dash-joined unit: "B7-77 Billy Bishop Way" or "14-3650 Langstaff Rd"
    m = re.match(r'^([A-Za-z0-9]+)-(\d+)\s+(.+)', stripped)
    if m:
        left = m.group(1)
        right = m.group(2)
        has_letter = re.search(r'[A-Za-z]', left)
        left_digits = re.sub(r'\D', '', left)
        # Letter on left = always a unit
        # Pure digits: left has fewer digits than right = unit (14-3650)
        # Pure digits: same/more digits = range (69-71) → skip, let street number handle it
        if has_letter:
            return right + ' ' + m.group(3), 'Unit', left
        elif len(left_digits) < len(right):
            return right + ' ' + m.group(3), 'Unit', left

    # 6e. Range check: "69-71" — pure digits both sides = NOT a unit, it's a range
    # (handled in street number extraction, not here)

    # 6f. Trailing ordinal floor: "2441 Yonge St, 2nd Floor"
    m = re.match(r'^(.+?)\s*,\s*(\d+(?:st|nd|rd|th)\s+(?:Floor|Flr))\s*$', stripped, re.IGNORECASE)
    if m:
        return m.group(1).strip(), 'Floor', m.group(2).strip()

    # Trailing ordinal word floor: "2441 Yonge St, Second Floor"
    ordinal_words = '|'.join(ORDINAL_FLOOR_WORDS)
    m = re.match(rf'^(.+?)\s*,\s*((?:{ordinal_words})\s+(?:Floor|Level))\s*$', stripped, re.IGNORECASE)
    if m:
        return m.group(1).strip(), 'Floor', to_title_case(m.group(2).strip())

    # 6g. Trailing hash: "45 King St, #301"
    m = re.match(r'^(.+?)\s*,\s*#\s*(\S+)\s*$', stripped)
    if m:
        return m.group(1).strip(), '#', m.group(2)

    # 6h. Trailing RR: "465448 Curries Rd, RR 4"
    m = re.match(r'^(.+?)\s*,\s*R\.?\s*R\.?\s*#?\s*(\d+)\s*$', stripped, re.IGNORECASE)
    if m:
        return m.group(1).strip(), 'RR', m.group(2)

    return text, '', ''


# ---------------------------------------------------------------------------
# Step 7: Street number extraction
# ---------------------------------------------------------------------------

def _extract_street_number(text):
    """Extract street number from start of text. Returns (remaining, number)."""
    text = text.strip()
    if not text:
        return text, ''

    # Word-number at start: "One Mount Pleasant Rd"
    first_word = text.split()[0].lower()
    if first_word in WORD_NUMBER_MAP:
        rest = text[len(text.split()[0]):].strip()
        return rest, WORD_NUMBER_MAP[first_word]

    # Half symbol replacement
    text = text.replace('½', '1/2')

    # Range: "69 - 71" or "69-71" (pure digits both sides)
    m = re.match(r'^(\d+)\s*-\s*(\d+)\s+(.+)', text)
    if m:
        left = m.group(1)
        right = m.group(2)
        # Pure digits both sides = range
        return m.group(3), f'{left}-{right}'

    # Number-dash-ordinal: "67-45th" → number=67, rest=45th ...
    m = re.match(r'^(\d+)-(\d+(?:st|nd|rd|th))\s+(.+)', text, re.IGNORECASE)
    if m:
        return m.group(2) + ' ' + m.group(3), m.group(1)

    # Fraction: "399 1/2 King St" — number with fraction
    m = re.match(r'^(\d+)\s+(1/2)\s+(.+)', text)
    if m:
        return m.group(3), f'{m.group(1)} {m.group(2)}'

    # Plus suffix: "1255A+B"
    m = re.match(r'^(\d+[A-Za-z]?\+[A-Za-z]+)\s+(.+)', text)
    if m:
        return m.group(2), m.group(1)

    # Letter suffix: "620A Main St" or "54B"
    m = re.match(r'^(\d+[A-Za-z])\s+(.+)', text)
    if m:
        # Make sure the letter isn't the start of the next word
        # "620A" is valid, but we need the next char to be a space
        return m.group(2), m.group(1)

    # Comma/ampersand list: "4, 14, 34 & 44 Main St" → "4,14,34,44"
    m = re.match(r'^(\d+(?:\s*[,&]\s*\d+)+)\s+(.+)', text)
    if m:
        raw = m.group(1)
        # Normalize to comma-separated digits: "4,14,34,44"
        numbers = re.findall(r'\d+', raw)
        return m.group(2), ','.join(numbers)

    # Slash list: "245/251 Main St" → "245/251"
    m = re.match(r'^(\d+(?:/\d+)+)\s+(.+)', text)
    if m:
        return m.group(2), m.group(1)

    # Simple number: "247"
    m = re.match(r'^(\d+)\s+(.+)', text)
    if m:
        return m.group(2), m.group(1)

    # No street number (e.g., "HAZELDEAN RD")
    return text, ''


# ---------------------------------------------------------------------------
# Step 9 helper: French prefix suffix
# ---------------------------------------------------------------------------

def _check_french_prefix_suffix(words):
    """Check if the first word is a French prefix suffix (rue, chemin, etc.)."""
    if words and words[0].lower() in FRENCH_PREFIX_SUFFIXES:
        return expand_suffix(words[0]) or ''
    return ''


# ---------------------------------------------------------------------------
# Embedded suffix scan
# ---------------------------------------------------------------------------

def _scan_embedded_suffix(words):
    """Scan left-to-right for an embedded suffix followed by junk.

    'KENT STREET WEST LINDSAY SQ MALL' → suffix=Street, dir=West, name=Kent
    """
    for i, word in enumerate(words):
        bare = word.lower().rstrip('.,')
        suffix_expanded = expand_suffix(bare)
        if suffix_expanded and i > 0:
            remaining_after = words[i + 1:]
            # Check if what follows is junk or a direction + junk
            direction = ''
            if remaining_after:
                dir_check = expand_direction(remaining_after[0])
                if dir_check:
                    direction = dir_check
                    remaining_after = remaining_after[1:]

            # Check if remaining words are junk
            if remaining_after and all(w.lower().rstrip('.,') in JUNK_MARKERS for w in remaining_after):
                return suffix_expanded, words[:i], direction
            # Also match if remaining starts with a known junk marker
            if remaining_after and remaining_after[0].lower().rstrip('.,') in JUNK_MARKERS:
                return suffix_expanded, words[:i], direction

    return '', words, ''


# ---------------------------------------------------------------------------
# Display string assembly
# ---------------------------------------------------------------------------

def _build_display(result):
    """Build a normalized display string from decomposed components."""
    if result.get('special_type') == 'po_box':
        return f"PO Box {result['suite_number']}"
    if result.get('special_type') == 'rural_route':
        return f"RR {result['suite_number']}"
    if result.get('special_type') == 'general_delivery':
        return 'General Delivery'
    if result.get('special_type') == 'legal_description':
        return result.get('street_name', '')

    parts = []
    if result['street_number']:
        parts.append(result['street_number'])
    if result['street_name']:
        parts.append(result['street_name'])
    if result['street_suffix']:
        parts.append(result['street_suffix'])
    if result['street_direction']:
        parts.append(result['street_direction'])

    display = ' '.join(parts)

    if result['suite_type'] and result['suite_number']:
        if result['suite_type'] == '#':
            display += f", #{result['suite_number']}"
        else:
            display += f", {result['suite_type']} {result['suite_number']}"

    return display
