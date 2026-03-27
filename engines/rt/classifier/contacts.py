"""
Contact lines classifier — 4-layer classification system.

Layer 1: Definitive patterns (regex, exact match — 100% certain)
Layer 2: Structural address patterns (digits, suffixes)
Layer 3: Keyword dictionaries (with precedence rules)
Layer 4: Contextual / default (weakest signals)

Then a second pass for line joining, and a third pass for assembly.

Reference: schema/engine_reference.md
"""

import re
from classifier.dictionaries import (
    CONTACT_PREFIX_REGEX,
    PHONE_REGEX,
    POSTAL_CODE_REGEX, US_ZIP_REGEX, MALFORMED_POSTAL_REGEX, UK_POSTAL_REGEX,
    ALL_PROVINCES_STATES,
    COUNTRIES, COUNTRY_REGEX,
    LAW_FIRM_KEYWORDS, LAW_FIRM_PC_REGEX,
    CORPORATE_SUFFIX_ANYWHERE_REGEX,
    COMPANY_KEYWORDS, TRUST_REFERENCE_REGEX, COMMON_FIRST_NAMES,
    STREET_SUFFIX_REGEX,
    BUILDING_KEYWORDS, BUILDING_CONTEXT_KEYWORDS,
    FLOOR_MODIFIER_REGEX, STATION_MODIFIER_REGEX,
    RURAL_ROUTE_REGEX, PO_BOX_REGEX, PO_BOX_ANYWHERE_REGEX,
    NOT_A_PERSON_REGEX,
)


# ======================================================================
# NOT-A-NAME WORDS — common English words that are never first names
# ======================================================================

_NOT_A_NAME_WORDS = {
    'Junction', 'Canada', 'Old', 'Blue', 'Red', 'Green', 'Black', 'White',
    'Golden', 'Silver', 'Royal', 'Star', 'Sun', 'Moon', 'Cedar',
    'West', 'East', 'North', 'South', 'Central', 'Upper', 'Lower',
    'Bay', 'Lake', 'River', 'Creek', 'Hill', 'Valley', 'Ridge', 'Mountain',
    'New', 'Grand', 'Premier', 'Diamond', 'Crown', 'Imperial',
    'Pro', 'Express', 'Direct', 'Master', 'Elite',
    'Pen', 'Budget', 'Extended', 'Stay', 'Coming', 'Generation',
    'Vice', 'President', 'Treasurer', 'Secretary', 'Director',
}


# ======================================================================
# HELPERS
# ======================================================================

def _has_building_keyword(text):
    """Check if text contains any building keyword."""
    lower = text.lower()
    for kw in BUILDING_KEYWORDS:
        if kw.lower() in lower:
            return True
    for kw in BUILDING_CONTEXT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
            return True
    return False


def _has_company_keyword(text):
    """Check if text contains any company keyword."""
    return any(kw in text for kw in COMPANY_KEYWORDS)


# ======================================================================
# TITLE NORMALIZATION MAP
# ======================================================================

_TITLE_MAP = {
    'attn': 'attn', 'att': 'attn', 'attan': 'attn', 'atttn': 'attn',
    'atth': 'attn', 'atnn': 'attn', 'attm': 'attn', 'annt': 'attn',
    'arttn': 'attn', 'attb': 'attn', 'atn': 'attn', 'sttn': 'attn',
    'pres': 'pres', 'press': 'pres', 'presd': 'pres', 'presl': 'pres',
    'pre': 'pres', 'pred': 'pres', 'prs': 'pres', 'pres.': 'pres',
    'pares': 'pres', 'presx': 'pres', 'presw': 'pres', 'prees': 'pres',
    'ptres': 'pres', 'prres': 'pres', 'prews': 'pres', 'peres': 'pres',
    'ptes': 'pres', 'presa': 'pres',
    'vp': 'vp', 'svp': 'svp',
    'aso': 'aso', 'asp': 'aso', 'aaso': 'aso', 'so': 'aso', 'rso': 'aso',
    'dir': 'dir',
    'co-pres': 'co-pres',
    'mayor': 'mayor', 'warden': 'warden', 'reeve': 'reeve',
    'treas': 'treas', 'tres': 'treas', 'sec': 'sec',
    'cfo': 'cfo', 'ceo': 'ceo', 'coo': 'coo', 'gm': 'gm',
    'chair': 'chair', 'chairman': 'chair',
    'trustee': 'trustee', 'executor': 'executor', 'executrix': 'executor',
    'bishop': 'bishop', 'pastor': 'pastor', 'chief': 'chief',
    'counsel': 'counsel', 'mgr': 'mgr', 'clerk': 'clerk',
    'principal': 'principal', 'cp': 'cp',
    'aka': 'aka',
    'mr': 'mr', 'mr.': 'mr',
    'mrs': 'mrs', 'mrs.': 'mrs',
    'ms': 'ms', 'ms.': 'ms',
    'dr': 'dr', 'dr.': 'dr',
    'attention': 'attn',
}


# ======================================================================
# MAIN CLASSIFIER — 4 LAYERS
# ======================================================================

def _classify_single_line(line):
    """Classify a single contact line using the 4-layer system."""
    stripped = line.strip()
    if not stripped:
        return ('empty', {})

    lower = stripped.lower()
    words = stripped.split()

    # ==================================================================
    # LAYER 1 — DEFINITIVE PATTERNS (100% certain)
    # ==================================================================

    # 1.1 Postal code (Canadian)
    if POSTAL_CODE_REGEX.match(stripped):
        return ('postal', {'postal': stripped})

    # 1.2 US ZIP
    if US_ZIP_REGEX.match(stripped):
        return ('postal', {'postal': stripped})

    # UK postal code
    if UK_POSTAL_REGEX.match(stripped):
        return ('postal', {'postal': stripped})

    # Malformed Canadian postal — alternating letter/digit with typos
    cleaned = re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', stripped)
    cleaned_nospace = cleaned.replace(' ', '').replace('-', '')
    if len(cleaned_nospace) == 6 and re.match(r'^[A-Za-z]\d[A-Za-z]\d[A-Za-z]\d$', cleaned_nospace):
        return ('postal', {'postal': cleaned, 'malformed': True})

    # Broader malformed — short string, mix of letters and digits, looks postal-ish
    if 5 <= len(cleaned_nospace) <= 8 and MALFORMED_POSTAL_REGEX.match(cleaned):
        has_letters = bool(re.search(r'[A-Za-z]', cleaned_nospace))
        has_digits = bool(re.search(r'\d', cleaned_nospace))
        if has_letters and has_digits and not re.search(r'[A-Za-z]{3,}', cleaned_nospace):
            return ('postal', {'postal': cleaned, 'malformed': True})

    # Standalone province
    if stripped in ALL_PROVINCES_STATES:
        return ('city_province', {'city': '', 'province': stripped})

    # 1.3 Phone number (only if line is primarily just the phone)
    phone_match = PHONE_REGEX.search(stripped)
    if phone_match:
        non_phone = PHONE_REGEX.sub('', stripped).strip()
        if len(non_phone) < 5:
            return ('phone', {'phone': phone_match.group(0)})

    # 1.4 Country
    if COUNTRY_REGEX.match(stripped):
        zip_match = re.search(r'(\d{5}(-\d{4})?)', stripped)
        zip_code = zip_match.group(1) if zip_match else ''
        return ('country', {'country': 'USA', 'zip': zip_code})
    if stripped == 'USA' or stripped in COUNTRIES:
        return ('country', {'country': stripped})

    # European country-prefixed addresses (CH-8004, D-80333, NL-2950)
    if re.match(r'^(CH|D|NL|F|A)\s*-\s*\d', stripped):
        return ('address_line', {'line': stripped})

    # 1.5 Contact prefix
    prefix_match = CONTACT_PREFIX_REGEX.match(stripped)
    if prefix_match:
        prefix = prefix_match.group(0).strip().rstrip(':').strip()
        name = stripped[prefix_match.end():].lstrip(':').strip()

        # FIX 1: Check NOT_A_PERSON directly on name text FIRST,
        # regardless of what the sub-classifier returns.
        if NOT_A_PERSON_REGEX.search(name):
            if any(kw in name for kw in LAW_FIRM_KEYWORDS) or LAW_FIRM_PC_REGEX.search(name):
                return ('law_firm', {'name': name})
            return ('company_name', {'name': name})

        # Then run sub-classifier for other strong types
        sub_type, sub_data = _classify_single_line(name)
        strong_non_person = {'law_firm'}
        if sub_type in strong_non_person:
            return (sub_type, sub_data)
        if sub_type == 'company_name' and CORPORATE_SUFFIX_ANYWHERE_REGEX.search(name):
            return (sub_type, sub_data)

        title = _TITLE_MAP.get(prefix.lower().rstrip(':').strip(), prefix.lower())
        return ('contact_name', {'name': name, 'title': title})

    # 1.6 c/o prefix (expanded variants: c/o, c/oName, c//o, c/i)
    # Must have / separator — can't just be "Co" as in "Concord"
    co_match = re.match(r'^c\s*/+\s*o?\s*(.*)', stripped, re.IGNORECASE)
    if not co_match:
        co_match = re.match(r'^c/i\s+(.*)', stripped, re.IGNORECASE)
    if co_match:
        rest = co_match.group(1).strip()
        sub_type, sub_data = _classify_single_line(rest)

        address_types = {'address_line', 'address_modifier', 'postal', 'city_province'}
        if sub_type in address_types:
            co_type = 'address'
        elif sub_type == 'law_firm':
            co_type = 'law_firm'
        elif sub_type in ('company_name', 'building_name'):
            co_type = 'company'
        elif sub_type == 'contact_name':
            first_word = rest.split()[0].rstrip('.,') if rest.split() else ''
            if first_word in COMMON_FIRST_NAMES and len(rest.split()) <= 4:
                co_type = 'person'
            elif rest.startswith(('Mr ', 'Mrs ', 'Ms ', 'Dr ', 'Mr. ', 'Mrs. ', 'Ms. ', 'Dr. ')):
                co_type = 'person'
            else:
                co_type = 'company'
        else:
            co_type = 'company'

        return ('care_of', {'type': co_type, 'text': rest})

    # 1.7 Trust reference → company
    if TRUST_REFERENCE_REGEX.match(stripped):
        return ('company_name', {'name': stripped})

    # 1.8 PO Box / RR / General Delivery (definitive address patterns)
    if PO_BOX_REGEX.match(stripped):
        return ('address_line', {'line': stripped})
    if PO_BOX_ANYWHERE_REGEX.search(stripped):
        return ('address_line', {'line': stripped})
    if RURAL_ROUTE_REGEX.match(stripped):
        return ('address_line', {'line': stripped})
    if stripped == 'General Delivery':
        return ('address_line', {'line': stripped})
    if re.search(r',\s*RR\s*#?\d', stripped):
        return ('address_line', {'line': stripped})

    # ==================================================================
    # LAYER 2 — STRUCTURAL ADDRESS PATTERNS
    # ==================================================================

    # 2.1 Digit + street suffix → ADDRESS (definitive)
    if re.match(r'^\d', stripped) and STREET_SUFFIX_REGEX.search(stripped):
        return ('address_line', {'line': stripped})

    # 2.2 Digit start, no suffix → ADDRESS (strong default)
    if re.match(r'^\d', stripped):
        return ('address_line', {'line': stripped})

    # 2.3 Word-number + street suffix → ADDRESS
    if re.match(r'^(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\s+', stripped) \
       and STREET_SUFFIX_REGEX.search(stripped):
        return ('address_line', {'line': stripped})

    # 2.4 Suite/Unit/Floor/Station modifiers
    if FLOOR_MODIFIER_REGEX.match(stripped):
        return ('address_modifier', {'modifier': stripped})
    if STATION_MODIFIER_REGEX.match(stripped):
        return ('address_modifier', {'modifier': stripped})

    # ==================================================================
    # LAYER 3 — KEYWORD DICTIONARIES
    # New order: city/province FIRST, then corporate suffix
    # ==================================================================

    # 3.1 City + Province (comma + known province) — MOVED UP
    # Structurally definitive: comma + known province is stronger
    # than a coincidental corporate suffix match like "CO"
    if ',' in stripped:
        after_last_comma = stripped.split(',')[-1].strip()
        after_clean = re.sub(r'\s+[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$', '', after_last_comma).strip()
        after_clean = re.sub(r'\s+\d{5}(-\d{4})?$', '', after_clean).strip()
        # Strip periods AND collapse spaces: "B. C." → "BC"
        after_noperiod = after_clean.replace('.', '').replace(' ', '').strip()

        # Skip Q.C. legal designation — not a province
        if '.C.' in after_last_comma or after_last_comma.strip() == 'Q.C.':
            province_match = None
        else:
            province_match = after_clean if after_clean in ALL_PROVINCES_STATES else (
                after_noperiod if after_noperiod in ALL_PROVINCES_STATES else None)

        if province_match:
            city = ','.join(stripped.split(',')[:-1]).strip()
            # Guard: only check CITY part for corporate suffix, not the whole line.
            # "Denver, CO" — city "Denver" has no corp suffix → pass.
            # "Acme Co., Ontario" — city "Acme Co." has corp suffix → blocked.
            # Don't check province part — two-letter provinces (CO, IN, LA) collide.
            if not CORPORATE_SUFFIX_ANYWHERE_REGEX.search(city):
                postal = ''
                postal_match_re = re.search(r'\s([A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)$', after_last_comma)
                if postal_match_re:
                    postal = postal_match_re.group(1)
                zip_match = re.search(r'\s(\d{5}(-\d{4})?)$', after_last_comma)
                if zip_match:
                    postal = zip_match.group(1)
                return ('city_province', {'city': city, 'province': province_match, 'postal': postal})

    # No-comma province variant — needs stronger guards
    if len(words) > 1:
        last_word_raw = words[-1]
        last_word = last_word_raw.replace('.', '').replace(' ', '')
        # Skip Q.C. legal designation
        if '.C.' in last_word_raw or last_word_raw == 'Q.C.':
            last_word = ''  # force no match
        if last_word in ALL_PROVINCES_STATES:
            rest_text = ' '.join(words[:-1])
            first_word = words[0].rstrip('.,')
            # Guard: if first word is a common first name + short line → person + designation, not city
            # "Larry Himmelfarb CA" → Larry is a name, CA is Chartered Accountant
            is_person_with_designation = (first_word in COMMON_FIRST_NAMES and len(words) <= 3)
            if not is_person_with_designation and \
               not CORPORATE_SUFFIX_ANYWHERE_REGEX.search(stripped) and \
               not _has_company_keyword(rest_text) and \
               not _has_building_keyword(rest_text):
                return ('city_province', {'city': rest_text, 'province': last_word})

    # 3.2 Corporate suffix → COMPANY (legally definitive)
    if CORPORATE_SUFFIX_ANYWHERE_REGEX.search(stripped):
        # But if it also has law firm keywords, law firm wins
        if any(kw in stripped for kw in LAW_FIRM_KEYWORDS) or LAW_FIRM_PC_REGEX.search(stripped):
            return ('law_firm', {'name': stripped})
        return ('company_name', {'name': stripped})

    # 3.3 Law firm keywords → LAW FIRM
    if any(kw in stripped for kw in LAW_FIRM_KEYWORDS) or LAW_FIRM_PC_REGEX.search(stripped):
        return ('law_firm', {'name': stripped})

    # 3.4 Building keywords → BUILDING NAME (before company keywords)
    if _has_building_keyword(stripped):
        return ('building_name', {'name': stripped})

    # 3.5 Company keywords → COMPANY
    if _has_company_keyword(stripped):
        return ('company_name', {'name': stripped})

    # "Trust" at end
    if stripped.rstrip('. ').endswith('Trust'):
        return ('company_name', {'name': stripped})

    # "City of X" / "Town of X"
    if lower.startswith('city of ') or lower.startswith('town of '):
        return ('company_name', {'name': stripped})

    # ==================================================================
    # LAYER 4 — CONTEXTUAL / DEFAULT (weakest signals)
    # Reordered: & pattern and name checks run BEFORE street-name-only
    # so street suffixes don't steal law firms and companies.
    # ==================================================================

    # 4.1 International address (digit at end, short line)
    if re.search(r'\b\d+$', stripped) and len(words) <= 3:
        return ('address_line', {'line': stripped})

    # 4.2 All-caps acronym → COMPANY
    if re.match(r'^[A-Z]{2,6}$', stripped):
        return ('company_name', {'name': stripped})

    # 4.3 "Mr &" or "Mr & Mrs" pattern → PERSON
    if re.match(r'^(Mr|Mrs|Ms|Dr)\s*&\s*(Mr|Mrs|Ms|Dr)?\s', stripped):
        return ('contact_name', {'name': stripped, 'title': 'mr'})

    # 4.4 & / "and" pattern — law firm vs couple (MOVED UP before street-name-only)
    if '&' in stripped or ' and ' in lower or (', ' in stripped and not stripped.endswith(',')):
        parts = re.split(r'\s*[&,]\s*|\s+and\s+', stripped)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) >= 2:
            last_part_words = parts[-1].split()
            if len(last_part_words) > 1:
                if last_part_words[0] in COMMON_FIRST_NAMES:
                    return ('contact_name', {'name': stripped, 'title': ''})
            return ('law_firm', {'name': stripped})

    # 4.5 First name match → CONTACT NAME
    if re.match(r"^[A-Za-z\s\-'\.]+$", stripped) and len(words) <= 3:
        first_word = words[0].rstrip('.,')
        if first_word in COMMON_FIRST_NAMES:
            return ('contact_name', {'name': stripped, 'title': ''})

    # 4.6 Not-a-name words → COMPANY
    for word in words:
        clean_word = word.strip('.,;:&()/')
        if clean_word in _NOT_A_NAME_WORDS:
            return ('company_name', {'name': stripped})

    # 4.7 "The" + proper noun → BUILDING
    if stripped.startswith('The ') or stripped.startswith('THE '):
        return ('building_name', {'name': stripped})

    # 4.8 Street-name-only — LAST RESORT (moved down from 4.1)
    # Only catches lines that didn't match any pattern above.
    if STREET_SUFFIX_REGEX.search(stripped) and len(words) <= 4:
        if not _has_building_keyword(stripped):
            if not CORPORATE_SUFFIX_ANYWHERE_REGEX.search(stripped):
                return ('address_line', {'line': stripped})

    # 4.9 Clean text default → CONTACT NAME
    if re.match(r"^[A-Za-z\s\-'\.&,]+$", stripped) and len(words) <= 5:
        return ('contact_name', {'name': stripped, 'title': ''})

    # Nothing matched
    return ('other', {'text': stripped})


# ======================================================================
# SECOND PASS — LINE JOINING
# ======================================================================

def _join_lines(classified_lines):
    """Join adjacent lines that belong together."""
    i = 0
    while i < len(classified_lines) - 1:
        line, line_type, data = classified_lines[i]
        next_line, next_type, next_data = classified_lines[i + 1]

        is_untitled_contact = (line_type == 'contact_name' and not data.get('title', ''))
        is_joinable = line_type in ('other', 'company_name', 'law_firm') or is_untitled_contact

        if is_joinable and next_type == 'law_firm':
            firm_name = data.get('text', data.get('name', line))
            descriptor = next_data.get('name', next_line)
            joined_name = f'{firm_name}, {descriptor}'
            classified_lines[i] = (joined_name, 'law_firm', {'name': joined_name})
            classified_lines.pop(i + 1)
        elif line_type == 'care_of' and next_type == 'law_firm':
            co_text = data.get('text', '')
            descriptor = next_data.get('name', next_line)
            joined_text = f'{co_text}, {descriptor}'
            classified_lines[i] = (line, 'care_of', {'type': 'law_firm', 'text': joined_text})
            classified_lines.pop(i + 1)
        else:
            i += 1

    return classified_lines


# ======================================================================
# THIRD PASS — ASSEMBLY
# ======================================================================

def classify_contacts(contact_lines):
    """Classify all contact lines and assemble into structured output."""
    result = {
        'contacts': [],
        'care_of': None,
        'law_firms': [],
        'companies': [],
        'address': {
            'lines': [],
            'modifiers': [],
            'building_names': [],
            'city': '',
            'province': '',
            'postal': '',
            'country': '',
        },
        'phone': '',
        'other_lines': [],
    }

    if not contact_lines:
        return result

    # Pass 1: classify all lines
    classified_lines = []
    for line in contact_lines:
        line_type, data = _classify_single_line(line)
        classified_lines.append((line, line_type, data))

    # Pass 2: join adjacent lines
    classified_lines = _join_lines(classified_lines)

    # Pass 3: assemble into output
    for line, line_type, data in classified_lines:

        if line_type == 'postal':
            result['address']['postal'] = data.get('postal', '')

        elif line_type == 'phone':
            result['phone'] = data.get('phone', '')

        elif line_type == 'country':
            result['address']['country'] = data.get('country', '')
            if data.get('zip'):
                result['address']['postal'] = data['zip']

        elif line_type == 'contact_name':
            result['contacts'].append(data)

        elif line_type == 'care_of':
            if data.get('type') == 'address':
                result['address']['lines'].append(data.get('text', ''))
            else:
                result['care_of'] = data

        elif line_type == 'city_province':
            result['address']['city'] = data.get('city', '')
            result['address']['province'] = data.get('province', '')
            if data.get('postal'):
                result['address']['postal'] = data['postal']

        elif line_type == 'law_firm':
            result['law_firms'].append(data.get('name', ''))

        elif line_type == 'company_name':
            result['companies'].append(data.get('name', ''))

        elif line_type == 'address_line':
            result['address']['lines'].append(data.get('line', ''))

        elif line_type == 'address_modifier':
            result['address']['modifiers'].append(data.get('modifier', ''))

        elif line_type == 'building_name':
            result['address']['building_names'].append(data.get('name', ''))

        elif line_type == 'other':
            result['other_lines'].append(data.get('text', ''))

    return result
