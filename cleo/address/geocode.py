"""
Shared geocode-string assembler for Cleo Turbo.

Canonical home for build_geocode_string — the single function every source
(RT, GW, URL, and future lanes) uses to turn address parts into the string
sent to the Ontario geocoder. Promoted here 2026-07-17 (field-contract Wave 1,
issue #5) so no lane hand-rolls its own geocoder query and identical addresses
always produce identical queries. Province / postal / country normalization
helpers live here alongside it, copied verbatim from the RT lane.

Usage:
    from cleo.address import build_geocode_string
    build_geocode_string("90 Signet Drive", "North York", "ON", "M9L 1T5")
    # -> "90 Signet Drive, North York, Ontario M9L 1T5, Canada"
"""
import re

from .normalize import to_title_case


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

COUNTRY_MAP = {
    'usa': 'United States',
    'united states': 'United States',
    'uk': 'United Kingdom',
    'united kingdom': 'United Kingdom',
}

CANADIAN_PROVINCES_LONG = {
    'Ontario', 'Quebec', 'Alberta', 'British Columbia', 'Manitoba',
    'Saskatchewan', 'Nova Scotia', 'New Brunswick', 'Newfoundland',
    'Prince Edward Island', 'Yukon', 'Northwest Territories', 'Nunavut',
}

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


def expand_province(text):
    """Expand a province/state abbreviation or typo to long form.

    Accepts full text (may be multi-word like "British Columbia").
    Returns long form if recognized, otherwise returns the input Title-Cased.
    """
    lookup = text.strip().lower()
    if lookup in PROVINCE_MAP:
        return PROVINCE_MAP[lookup]
    return to_title_case(text.strip())


def expand_country(text):
    """Expand a country abbreviation to long form."""
    lookup = text.strip().lower()
    if lookup in COUNTRY_MAP:
        return COUNTRY_MAP[lookup]
    return to_title_case(text.strip())


def normalize_postal(postal):
    """Normalize Canadian postal code format: A1A 1A1 (uppercase, with space)."""
    if not postal:
        return ''
    clean = postal.strip().upper().replace(' ', '')
    if len(clean) == 6 and re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', clean):
        return clean[:3] + ' ' + clean[3:]
    # Return as-is for US ZIPs and other formats
    return postal.strip().upper()


def build_geocode_string(display, city='', province='', postal='', country=''):
    """Assemble a geocode-ready string from address parts.

    Format: "{display}, {city}, {province} {postal}, {country}"
    The display passed in should be street-level only (no suite).
    """
    if not display:
        return None

    # Normalize province
    if province:
        province = expand_province(province)

    # Normalize postal code
    if postal:
        postal = normalize_postal(postal)

    # Determine country from province if not explicitly set
    if not country:
        if province in CANADIAN_PROVINCES_LONG:
            country = 'Canada'
        elif province in US_STATES_LONG:
            country = 'United States'
    elif country:
        country = expand_country(country)

    parts = [display]
    if city:
        parts.append(city)

    # Province and postal together
    prov_postal = ''
    if province and postal:
        prov_postal = f'{province} {postal}'
    elif province:
        prov_postal = province
    elif postal:
        prov_postal = postal
    if prov_postal:
        parts.append(prov_postal)

    if country:
        parts.append(country)

    return ', '.join(parts)
