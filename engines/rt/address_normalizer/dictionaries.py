"""
Address normalization dictionaries for the RT pipeline.

Shared dictionaries (SUFFIX_MAP, DIRECTION_MAP, ordinals, saint names, etc.)
are re-exported from cleo.address.dictionaries. RT-specific dictionaries
(PROVINCE_MAP, COUNTRY_MAP, UNIT_KEYWORDS, etc.) remain here.

Reference: schema/address_normalization_plan.md
"""

# ---------------------------------------------------------------------------
# Re-export shared dictionaries (canonical source: cleo/address/dictionaries.py)
# ---------------------------------------------------------------------------

from cleo.address.dictionaries import (  # noqa: F401
    SUFFIX_MAP,
    SUFFIX_LONG_FORMS,
    DIRECTION_MAP,
    SAINT_NAMES,
    UPPERCASE_TOKENS,
    COMPOUND_ROAD_PREFIXES,
    FRENCH_PREFIX_SUFFIXES,
    ORDINAL_WORD_TO_DIGIT,
    ORDINAL_DIGIT_TO_WORD,
    # Moved to the shared module with the decomposer promotion (2026-07-07):
    UNIT_KEYWORDS,
    ORDINAL_FLOOR_WORDS,
    WORD_NUMBER_MAP,
    JUNK_MARKERS,
)

# ---------------------------------------------------------------------------
# PROVINCE -- abbreviation/typo -> long form (RT-specific, used for contacts)
# ---------------------------------------------------------------------------

PROVINCE_MAP = {
    # Canadian -- abbreviations
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
    'ontArio': 'Ontario',
    'ontarioi': 'Ontario',
    'ontrio': 'Ontario',
    'onario': 'Ontario',
    'ontarig': 'Ontario',

    # US -- abbreviations
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

# Canadian provinces (long form) -- used to determine country
CANADIAN_PROVINCES_LONG = {
    'Ontario', 'Quebec', 'Alberta', 'British Columbia', 'Manitoba',
    'Saskatchewan', 'Nova Scotia', 'New Brunswick', 'Newfoundland',
    'Prince Edward Island', 'Yukon', 'Northwest Territories', 'Nunavut',
}

# US states (long form) -- used to determine country
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
# COUNTRY -- abbreviation -> long form
# ---------------------------------------------------------------------------

COUNTRY_MAP = {
    'usa': 'United States',
    'united states': 'United States',
    'uk': 'United Kingdom',
    'united kingdom': 'United Kingdom',
}
