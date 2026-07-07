"""
Shared address dictionaries for all Cleo Turbo pipelines.

This is the single source of truth for suffix maps, direction maps, ordinal
conversions, saint names, and all other address normalization lookups.

The RT address_normalizer re-exports from here for backward compatibility.
"""

# ---------------------------------------------------------------------------
# STREET SUFFIX -- abbreviation -> long form (case-insensitive lookup)
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
    # Additional abbreviations found in GW/OSM data
    'ln': 'Lane',
    'tr': 'Trail',
    'trl': 'Trail',
    'cr': 'Crescent',

    # French
    'rue': 'Rue',
    'bld': 'Boulevard',
    'chemin': 'Chemin',
    'ch': 'Chemin',
    'promenade': 'Promenade',
    'autoroute': 'Autoroute',
    'montee': 'Montee',
    'cote': 'Cote',
}

# Set of all long-form suffixes (for matching already-expanded suffixes)
SUFFIX_LONG_FORMS = set(SUFFIX_MAP.values())

# ---------------------------------------------------------------------------
# DIRECTION -- abbreviation -> long form
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
# ORDINAL MAPS -- extended to cover Ontario street names through 20th
#
# Policy:
#   1st-10th  -> word form (First through Tenth)
#   11th-20th -> numeric form (11th through 20th)
# ---------------------------------------------------------------------------

# Word -> digit (for converting word ordinals to numeric when > 10)
ORDINAL_WORD_TO_DIGIT = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th',
    'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th',
    'ninth': '9th', 'tenth': '10th',
    # 11+ (used to convert "Eleventh" -> "11th" etc.)
    'eleventh': '11th', 'twelfth': '12th', 'thirteenth': '13th',
    'fourteenth': '14th', 'fifteenth': '15th', 'sixteenth': '16th',
    'seventeenth': '17th', 'eighteenth': '18th', 'nineteenth': '19th',
    'twentieth': '20th',
}

# Digit -> word (reverse)
ORDINAL_DIGIT_TO_WORD = {v: k for k, v in ORDINAL_WORD_TO_DIGIT.items()}

# The ordinals that should display as WORDS (1st-10th)
ORDINAL_WORD_RANGE = {
    '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th',
}

# Corresponding word forms for the word range
ORDINAL_WORD_FORMS = {
    'first', 'second', 'third', 'fourth', 'fifth',
    'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
}

# ---------------------------------------------------------------------------
# SAINT NAMES -- protect "St" from becoming "Street"
# ---------------------------------------------------------------------------

SAINT_NAMES = {
    'thomas', 'catharines', 'johns', "john's", 'laurent', 'jacobs',
    'marys', 'george', 'clair', 'albert', 'boniface', 'paul',
    'andrews', 'peter', 'patrick', 'bernard', 'helens', 'davids',
    'charles', 'jerome', 'hubert', 'hyacinthe', 'jean', 'eustache',
    'lazare', 'bruno', 'constant', 'leonard', 'augustin',
}

# ---------------------------------------------------------------------------
# TOKENS THAT STAY UPPERCASE in Title Case
# ---------------------------------------------------------------------------

UPPERCASE_TOKENS = {'PO', 'RR', 'NE', 'NW', 'SE', 'SW'}

# ---------------------------------------------------------------------------
# COMPOUND ROAD PREFIXES -- suffix word is part of the name, not a suffix
# ---------------------------------------------------------------------------

COMPOUND_ROAD_PREFIXES = {
    'county', 'country', 'regional', 'old', 'fire', 'concession',
    'twp',    # Township Road
}

# ---------------------------------------------------------------------------
# FRENCH PREFIX SUFFIXES -- suffixes that appear BEFORE the street name
# ---------------------------------------------------------------------------

FRENCH_PREFIX_SUFFIXES = {'rue', 'chemin', 'ch', 'boulevard', 'bld',
                          'promenade', 'autoroute', 'montee',
                          'cote'}

# ---------------------------------------------------------------------------
# UNIT/SUITE KEYWORDS (used by the canonical decomposer in decompose.py)
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
# WORD-NUMBERS -- "One" -> "1", for street numbers written as words
# ---------------------------------------------------------------------------

WORD_NUMBER_MAP = {
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
    'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
}

# ---------------------------------------------------------------------------
# JUNK MARKERS -- words after an embedded suffix that signal garbage to strip
# ---------------------------------------------------------------------------

JUNK_MARKERS = {
    'store', 'mall', 'plaza', 'shopping', 'centre', 'center',
    'industrial', 'business', 'commercial', 'office', 'park',
    'no', 'sq',
}
