"""
Single source of truth for all address normalization dictionaries.

Every suffix map, direction map, province map, saint name, and compound road
prefix lives here. All address_normalizer modules import from this file.

Reference: schema/address_normalization_plan.md
"""

# ---------------------------------------------------------------------------
# STREET SUFFIX — abbreviation → long form (case-insensitive lookup)
# ---------------------------------------------------------------------------

SUFFIX_MAP = {
    # English
    'st': 'Street',
    'ave': 'Avenue',
    'rd': 'Road',
    'dr': 'Drive',
    'blvd': 'Boulevard',
    'cres': 'Crescent',
    'way': 'Way',
    'ct': 'Court',
    'pl': 'Place',
    'lane': 'Lane',
    'line': 'Line',
    'pkwy': 'Parkway',
    'hwy': 'Highway',
    'circle': 'Circle',
    'cir': 'Circle',
    'gate': 'Gate',
    'trail': 'Trail',
    'walk': 'Walk',
    'grove': 'Grove',
    'terr': 'Terrace',
    'terrace': 'Terrace',
    'crt': 'Court',
    'court': 'Court',
    'close': 'Close',
    'path': 'Path',
    'run': 'Run',
    'rise': 'Rise',
    'glen': 'Glen',
    'park': 'Park',
    'square': 'Square',
    'green': 'Green',
    'quay': 'Quay',
    'landing': 'Landing',
    'manor': 'Manor',
    'route': 'Route',
    'road': 'Road',
    'highway': 'Highway',
    'concession': 'Concession',
    'conc': 'Concession',
    'sideroad': 'Sideroad',
    'queensway': 'Queensway',
    'donway': 'Donway',
    'esplanade': 'Esplanade',
    'street': 'Street',
    'avenue': 'Avenue',
    'drive': 'Drive',
    'boulevard': 'Boulevard',
    'crescent': 'Crescent',
    'place': 'Place',

    # French
    'rue': 'Rue',
    'bld': 'Boulevard',
    'chemin': 'Chemin',
    'ch': 'Chemin',
    'promenade': 'Promenade',
    'autoroute': 'Autoroute',
    'montée': 'Montée',
    'montee': 'Montée',
    'côte': 'Côte',
    'cote': 'Côte',
}

# Set of all long-form suffixes (for matching already-expanded suffixes)
SUFFIX_LONG_FORMS = set(SUFFIX_MAP.values())

# ---------------------------------------------------------------------------
# DIRECTION — abbreviation → long form
# ---------------------------------------------------------------------------

DIRECTION_MAP = {
    'n': 'North',
    's': 'South',
    'e': 'East',
    'w': 'West',
    'ne': 'Northeast',
    'nw': 'Northwest',
    'se': 'Southeast',
    'sw': 'Southwest',
    'north': 'North',
    'south': 'South',
    'east': 'East',
    'west': 'West',
    'northeast': 'Northeast',
    'northwest': 'Northwest',
    'southeast': 'Southeast',
    'southwest': 'Southwest',
}

# ---------------------------------------------------------------------------
# PROVINCE — abbreviation/typo → long form
# ---------------------------------------------------------------------------

PROVINCE_MAP = {
    # Canadian — abbreviations
    'on': 'Ontario',
    'ont': 'Ontario',
    'ontario': 'Ontario',
    'qc': 'Quebec',
    'quebec': 'Quebec',
    'québec': 'Quebec',
    'ab': 'Alberta',
    'alberta': 'Alberta',
    'bc': 'British Columbia',
    'british columbia': 'British Columbia',
    'mb': 'Manitoba',
    'manitoba': 'Manitoba',
    'sk': 'Saskatchewan',
    'saskatchewan': 'Saskatchewan',
    'ns': 'Nova Scotia',
    'nova scotia': 'Nova Scotia',
    'nb': 'New Brunswick',
    'new brunswick': 'New Brunswick',
    'nl': 'Newfoundland',
    'newfoundland': 'Newfoundland',
    'pe': 'Prince Edward Island',
    'pei': 'Prince Edward Island',
    'prince edward island': 'Prince Edward Island',
    'yt': 'Yukon',
    'yukon': 'Yukon',
    'nt': 'Northwest Territories',
    'nwt': 'Northwest Territories',
    'northwest territories': 'Northwest Territories',
    'nu': 'Nunavut',
    'nunavut': 'Nunavut',

    # Canadian typo variants found in data
    'ontario': 'Ontario',
    'ontArio': 'Ontario',
    'ontarioi': 'Ontario',
    'ontrio': 'Ontario',
    'onario': 'Ontario',
    'ontarig': 'Ontario',

    # US — abbreviations
    'al': 'Alabama', 'ak': 'Alaska', 'az': 'Arizona', 'ar': 'Arkansas',
    'ca': 'California', 'co': 'Colorado', 'ct': 'Connecticut',
    'de': 'Delaware', 'fl': 'Florida', 'ga': 'Georgia',
    'hi': 'Hawaii', 'id': 'Idaho', 'il': 'Illinois',
    'in': 'Indiana', 'ia': 'Iowa', 'ks': 'Kansas',
    'ky': 'Kentucky', 'la': 'Louisiana', 'me': 'Maine',
    'md': 'Maryland', 'ma': 'Massachusetts', 'mi': 'Michigan',
    'mn': 'Minnesota', 'ms': 'Mississippi', 'mo': 'Missouri',
    'mt': 'Montana', 'ne': 'Nebraska', 'nv': 'Nevada',
    'nh': 'New Hampshire', 'nj': 'New Jersey', 'nm': 'New Mexico',
    'ny': 'New York', 'nc': 'North Carolina', 'nd': 'North Dakota',
    'oh': 'Ohio', 'ok': 'Oklahoma', 'or': 'Oregon',
    'pa': 'Pennsylvania', 'ri': 'Rhode Island', 'sc': 'South Carolina',
    'sd': 'South Dakota', 'tn': 'Tennessee', 'tx': 'Texas',
    'ut': 'Utah', 'vt': 'Vermont', 'va': 'Virginia',
    'wa': 'Washington', 'wv': 'West Virginia', 'wi': 'Wisconsin',
    'wy': 'Wyoming', 'dc': 'District of Columbia',

    # US full names (already correct but normalize case)
    'alabama': 'Alabama', 'alaska': 'Alaska', 'arizona': 'Arizona',
    'arkansas': 'Arkansas', 'california': 'California', 'colorado': 'Colorado',
    'connecticut': 'Connecticut', 'delaware': 'Delaware', 'florida': 'Florida',
    'georgia': 'Georgia', 'hawaii': 'Hawaii', 'idaho': 'Idaho',
    'illinois': 'Illinois', 'indiana': 'Indiana', 'iowa': 'Iowa',
    'kansas': 'Kansas', 'kentucky': 'Kentucky', 'louisiana': 'Louisiana',
    'maine': 'Maine', 'maryland': 'Maryland', 'massachusetts': 'Massachusetts',
    'michigan': 'Michigan', 'minnesota': 'Minnesota', 'mississippi': 'Mississippi',
    'missouri': 'Missouri', 'montana': 'Montana', 'nebraska': 'Nebraska',
    'nevada': 'Nevada', 'new hampshire': 'New Hampshire', 'new jersey': 'New Jersey',
    'new mexico': 'New Mexico', 'new york': 'New York',
    'north carolina': 'North Carolina', 'north dakota': 'North Dakota',
    'ohio': 'Ohio', 'oklahoma': 'Oklahoma', 'oregon': 'Oregon',
    'pennsylvania': 'Pennsylvania', 'rhode island': 'Rhode Island',
    'south carolina': 'South Carolina', 'south dakota': 'South Dakota',
    'tennessee': 'Tennessee', 'texas': 'Texas', 'utah': 'Utah',
    'vermont': 'Vermont', 'virginia': 'Virginia', 'washington': 'Washington',
    'west virginia': 'West Virginia', 'wisconsin': 'Wisconsin',
    'wyoming': 'Wyoming', 'district of columbia': 'District of Columbia',

    # US typo variants
    'illimois': 'Illinois',
    'virgina': 'Virginia',
}

# Canadian provinces (long form) — used to determine country
CANADIAN_PROVINCES_LONG = {
    'Ontario', 'Quebec', 'Alberta', 'British Columbia', 'Manitoba',
    'Saskatchewan', 'Nova Scotia', 'New Brunswick', 'Newfoundland',
    'Prince Edward Island', 'Yukon', 'Northwest Territories', 'Nunavut',
}

# US states (long form) — used to determine country
US_STATES_LONG = {
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
}

# ---------------------------------------------------------------------------
# COUNTRY — abbreviation → long form
# ---------------------------------------------------------------------------

COUNTRY_MAP = {
    'usa': 'United States',
    'united states': 'United States',
    'uk': 'United Kingdom',
    'united kingdom': 'United Kingdom',
}

# ---------------------------------------------------------------------------
# SAINT NAMES — protect "St" from becoming "Street"
# ---------------------------------------------------------------------------

SAINT_NAMES = {
    'thomas', 'catharines', 'johns', "john's", 'laurent', 'jacobs',
    'marys', 'george', 'clair', 'albert', 'boniface', 'paul',
    'andrews', 'peter', 'patrick', 'bernard', 'helens', 'davids',
    'charles', 'jerome', 'hubert', 'hyacinthe', 'jean', 'eustache',
    'lazare', 'bruno', 'constant', 'leonard', 'augustin',
}

# ---------------------------------------------------------------------------
# COMPOUND ROAD PREFIXES — suffix word is part of the name, not a suffix
# ---------------------------------------------------------------------------

COMPOUND_ROAD_PREFIXES = {
    'county', 'country', 'regional', 'old', 'fire', 'concession',
    'twp',    # Township Road
}

# ---------------------------------------------------------------------------
# UNIT/SUITE KEYWORDS
# ---------------------------------------------------------------------------

UNIT_KEYWORDS = {
    'suite', 'ste', 'unit', 'units', 'apt', 'apartment',
    'floor', 'flr', 'level', 'bureau', 'mezzanine', 'penthouse',
    'basement', 'entrance', 'stn',
}

# Ordinal floor patterns: "2nd Floor", "3rd Floor", etc.
ORDINAL_FLOOR_WORDS = {
    'first', 'second', 'third', 'fourth', 'fifth', 'sixth',
    'seventh', 'eighth', 'ninth', 'tenth', 'ground', 'lower',
    'upper', 'main', 'top', 'rear',
}

# ---------------------------------------------------------------------------
# WORD-NUMBERS — "One" → "1", for street numbers written as words
# ---------------------------------------------------------------------------

WORD_NUMBER_MAP = {
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
    'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
}

# ---------------------------------------------------------------------------
# ORDINAL PAIRS — word ↔ digit, for generating alternate search keys
# Both directions so we can swap either way.
# ---------------------------------------------------------------------------

ORDINAL_WORD_TO_DIGIT = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th',
    'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th',
    'ninth': '9th', 'tenth': '10th',
}

ORDINAL_DIGIT_TO_WORD = {v: k for k, v in ORDINAL_WORD_TO_DIGIT.items()}

# ---------------------------------------------------------------------------
# TOKENS THAT STAY UPPERCASE in Title Case
# ---------------------------------------------------------------------------

UPPERCASE_TOKENS = {'PO', 'RR', 'NE', 'NW', 'SE', 'SW'}

# ---------------------------------------------------------------------------
# JUNK MARKERS — words after an embedded suffix that signal garbage to strip
# ---------------------------------------------------------------------------

JUNK_MARKERS = {
    'store', 'mall', 'plaza', 'shopping', 'centre', 'center',
    'industrial', 'business', 'commercial', 'office', 'park',
    'no', 'sq',
}

# ---------------------------------------------------------------------------
# FRENCH PREFIX SUFFIXES — suffixes that appear BEFORE the street name
# ---------------------------------------------------------------------------

FRENCH_PREFIX_SUFFIXES = {'rue', 'chemin', 'ch', 'boulevard', 'bld',
                          'promenade', 'autoroute', 'montée', 'montee',
                          'côte', 'cote'}
