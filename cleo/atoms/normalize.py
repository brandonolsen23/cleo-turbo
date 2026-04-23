"""Normalizer module — pure functions that canonicalize raw RT data values
into atom-level forms for portfolio discovery.

Every function takes a raw string (may be None or empty), returns the
canonical form, or None if the input had no content after stripping.

The goal is deterministic, reversible-by-convention canonicalization:
two inputs that should be treated as the same atom must normalize to
identical strings; two inputs that mean different things must not collide.
"""

from __future__ import annotations
import re
import unicodedata
from typing import List, Optional
from cleanco import basename as cleanco_basename


# ── Lookup tables (module-level, frozen) ──────────────────────────────

STOP_BRAND_TOKENS = frozenset({
    "the", "of", "and", "a", "an", "&", "co", "inc", "ltd", "llc", "corp",
    # keep minimal; cleanco already strips most legal suffixes before tokenization
})

_STREET_SUFFIX_MAP: dict[str, str] = {
    # street
    "st": "street", "str": "street", "street": "street",
    # avenue
    "ave": "avenue", "av": "avenue", "avenue": "avenue",
    # boulevard
    "blvd": "boulevard", "bl": "boulevard", "boul": "boulevard",
    "bld": "boulevard", "boulevard": "boulevard",
    # road
    "rd": "road", "road": "road",
    # drive
    "dr": "drive", "drive": "drive",
    # crescent
    "cres": "crescent", "crs": "crescent", "crescent": "crescent",
    # court
    "ct": "court", "crt": "court", "court": "court",
    # place
    "pl": "place", "place": "place",
    # parkway
    "pkwy": "parkway", "pky": "parkway", "parkway": "parkway",
    # lane
    "ln": "lane", "lane": "lane",
    # terrace
    "ter": "terrace", "terr": "terrace", "terrace": "terrace",
    # circle
    "cir": "circle", "circ": "circle", "circle": "circle",
    # trail
    "trl": "trail", "tr": "trail", "trail": "trail",
    # way
    "wy": "way", "way": "way",
    # square
    "sq": "square", "square": "square",
    # highway
    "hwy": "highway", "highway": "highway",
    # line
    "line": "line",
    # concession
    "conc": "concession", "concession": "concession",
    # sideroad
    "sdrd": "sideroad", "sr": "sideroad", "sideroad": "sideroad",
}

_DIRECTION_MAP: dict[str, str] = {
    "n": "north", "no": "north", "nor": "north", "north": "north",
    "n.": "north", "no.": "north",
    "s": "south", "so": "south", "sou": "south", "south": "south",
    "s.": "south", "so.": "south",
    "e": "east", "ea": "east", "east": "east", "e.": "east",
    "w": "west", "we": "west", "wst": "west", "west": "west",
    "w.": "west",
    "ne": "northeast", "ne.": "northeast", "northeast": "northeast",
    "nw": "northwest", "nw.": "northwest", "northwest": "northwest",
    "se": "southeast", "se.": "southeast", "southeast": "southeast",
    "sw": "southwest", "sw.": "southwest", "southwest": "southwest",
}

_SUITE_TYPE_MAP: dict[str, str] = {
    "suite": "suite", "ste": "suite", "s.": "suite", "#": "suite",
    "po box": "po_box", "pobox": "po_box", "po": "po_box",
    "p.o. box": "po_box", "p o box": "po_box", "p.o box": "po_box",
    "floor": "floor", "flr": "floor", "fl": "floor", "level": "floor",
    "unit": "unit", "apt": "unit", "apartment": "unit",
    "penthouse": "penthouse", "ph": "penthouse",
}

_PROVINCE_MAP: dict[str, str] = {
    "on": "ontario", "ont": "ontario", "ontario": "ontario",
    "qc": "quebec", "que": "quebec", "quebec": "quebec", "québec": "quebec",
    "bc": "british_columbia", "bc.": "british_columbia",
    "british columbia": "british_columbia",
    "ab": "alberta", "alta": "alberta", "alberta": "alberta",
    "mb": "manitoba", "man": "manitoba", "manitoba": "manitoba",
    "sk": "saskatchewan", "sask": "saskatchewan", "saskatchewan": "saskatchewan",
    "ns": "nova_scotia", "nova scotia": "nova_scotia",
    "nb": "new_brunswick", "new brunswick": "new_brunswick",
    "nl": "newfoundland", "nf": "newfoundland",
    "newfoundland": "newfoundland",
    "newfoundland and labrador": "newfoundland",
    "pe": "prince_edward_island", "pei": "prince_edward_island",
    "prince edward island": "prince_edward_island",
    "yt": "yukon", "yukon": "yukon",
    "nt": "northwest_territories", "nwt": "northwest_territories",
    "northwest territories": "northwest_territories",
    "nu": "nunavut", "nunavut": "nunavut",
}

_COUNTRY_MAP: dict[str, str] = {
    "ca": "canada", "can": "canada", "canada": "canada",
    "us": "united_states", "usa": "united_states",
    "united states": "united_states",
    "united states of america": "united_states",
}

# Honorifics to strip from first names (lowercase, no trailing dot)
_HONORIFICS = frozenset({"mr", "mrs", "ms", "dr", "prof", "sir", "hon"})

# Suffixes to strip from last names (lowercase, no trailing dot)
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "esq"})

# Regex: punctuation except & and hyphen → space
_PUNCT_TO_SPACE = re.compile(r"[^\w\s&-]+")

# Regex: collapse runs of whitespace
_WHITESPACE = re.compile(r"\s+")

# Leading abbreviation expansions for street names
_LEADING_ABBREV = re.compile(
    r"^(st|st\.|ft|ft\.|mt|mt\.)\s+(?=\S)",
    re.IGNORECASE,
)
_LEADING_ABBREV_MAP = {
    "st": "saint", "st.": "saint",
    "ft": "fort", "ft.": "fort",
    "mt": "mount", "mt.": "mount",
}

# Canadian postal code pattern
_POSTAL_CA = re.compile(r"^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$")
# US ZIP pattern
_POSTAL_US = re.compile(r"^\d{5}(-\d{4})?$")


# ── Internal helpers ──────────────────────────────────────────────────

def _strip_or_none(value: Optional[str]) -> Optional[str]:
    """Return stripped string, or None if empty/None."""
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def _remove_diacritics(s: str) -> str:
    """NFKD decompose then drop non-ASCII characters."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn"
    )


# ── Brand / party-name atoms ──────────────────────────────────────────

def normalize_brand(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a brand-identifying string (party_name, trade_name,
    care_of, single entry of companies_json, single entry of law_firms_json).

    Steps:
      1. Strip. Return None if empty.
      2. Strip legal suffixes via cleanco.basename().
      3. Lowercase.
      4. Collapse internal whitespace to single spaces.
      5. Keep `&` as `&` (do NOT rewrite to "and").
      6. Replace all punctuation runs (except `&`) with single space. Collapse.

    Keep `&` as `&` — "h&r" stays distinctive.
    Other punctuation: commas, periods, parens, slashes all become spaces.

    Examples:
      "KingSett Capital Inc." -> "kingsett capital"
      "H&R REIT" -> "h&r reit"
      "The  Regional  Group" -> "the regional group"
      "c/o Plazacorp Investments Ltd" -> "c o plazacorp investments"
      "  "  -> None
      None  -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    # Strip legal suffixes via cleanco
    s = cleanco_basename(s)

    # Lowercase
    s = s.lower()

    # Replace punctuation except & with spaces (covers / , . ( ) etc.)
    # Keep alphanumeric, whitespace, &, and hyphen-like chars
    s = re.sub(r"[^\w\s&]+", " ", s)

    # Collapse whitespace
    s = _WHITESPACE.sub(" ", s).strip()

    return s if s else None


def tokenize_brand(normalized: Optional[str]) -> List[str]:
    """Split an already-normalized brand string into distinctive tokens.

    Steps:
      1. Split on whitespace.
      2. Drop tokens of length <2.
      3. Drop stopword tokens (see STOP_BRAND_TOKENS).
      4. Deduplicate preserving first-occurrence order.

    Returns [] if `normalized` is None or yields no tokens.

    Examples:
      "kingsett capital" -> ["kingsett", "capital"]
      "the regional group" -> ["regional", "group"]
      "h&r reit" -> ["h&r", "reit"]
      "c o plazacorp investments" -> ["plazacorp", "investments"]
      None -> []
    """
    if normalized is None:
        return []

    seen: set[str] = set()
    result: List[str] = []
    for token in normalized.split():
        if len(token) < 2:
            continue
        if token in STOP_BRAND_TOKENS:
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


# ── Contact atom ──────────────────────────────────────────────────────

def normalize_contact_name(first: Optional[str], last: Optional[str]) -> Optional[str]:
    """Canonicalize a person's first+last name into a single fingerprint atom.

    Steps:
      1. If both inputs empty/None, return None.
      2. For each: lowercase, strip, drop leading honorifics (mr, mrs, ms, dr, prof, sir, hon).
      3. For last name: strip trailing suffixes (jr, sr, ii, iii, iv, esq).
      4. Collapse whitespace.
      5. Format as "first last" with a single space (first may be empty, last
         may be empty, but not both).

    Does NOT do fuzzy matching (Dan/Daniel are different atoms).

    Examples:
      ("Dan", "Hagler") -> "dan hagler"
      ("Mr. Peter", "Aghar") -> "peter aghar"
      ("Jonathan", "Gitlin Jr.") -> "jonathan gitlin"
      (None, "Smith") -> "smith"
      (" ", " ") -> None
    """
    def _clean_part(s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.strip().lower()
        # Remove trailing periods from each token, then collapse
        tokens = s.split()
        tokens = [t.rstrip(".") for t in tokens]
        return " ".join(tokens)

    def _strip_leading_honorifics(s: str) -> str:
        tokens = s.split()
        while tokens and tokens[0] in _HONORIFICS:
            tokens = tokens[1:]
        return " ".join(tokens)

    def _strip_trailing_suffixes(s: str) -> str:
        tokens = s.split()
        while tokens and tokens[-1] in _NAME_SUFFIXES:
            tokens = tokens[:-1]
        return " ".join(tokens)

    first_clean = _strip_leading_honorifics(_clean_part(first))
    last_clean = _strip_trailing_suffixes(_strip_leading_honorifics(_clean_part(last)))

    parts = [p for p in [first_clean, last_clean] if p]
    if not parts:
        return None
    return " ".join(parts)


# ── Phone atom ────────────────────────────────────────────────────────

def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a phone number to digits-only.

    Steps:
      1. Strip. Return None if empty.
      2. Remove all non-digit characters.
      3. Strip leading "1" if the total length is 11 (Canadian/US country code).
      4. Return None if fewer than 7 digits remain (invalid/noise).
      5. Return the digits string.

    Examples:
      "(416) 687-6700" -> "4166876700"
      "+1 416 687 6700" -> "4166876700"
      "1-416-687-6700" -> "4166876700"
      "416.687.6700" -> "4166876700"
      "ext 234" -> None
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    digits = re.sub(r"\D", "", s)

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) < 7:
        return None

    return digits


# ── Address atoms ─────────────────────────────────────────────────────

def normalize_street_number(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a street number.

    Steps:
      1. Strip. Return None if empty.
      2. Lowercase.
      3. Strip leading zeros if the whole string is numeric. Preserve
         alphabetic suffixes ("30a", "12b") unchanged apart from lowercasing.

    Examples:
      "030" -> "30"
      "30A" -> "30a"
      "0030-32" -> "30-32"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    s = s.lower()

    # If purely numeric, strip leading zeros
    if re.match(r"^\d+$", s):
        s = str(int(s))
    else:
        # Compound like "0030-32": strip leading zeros from leading numeric segment
        s = re.sub(r"^0+(\d)", r"\1", s)

    return s if s else None


def normalize_street_name(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a street name.

    Steps:
      1. Strip. Return None if empty.
      2. Lowercase.
      3. Strip apostrophes.
      4. Expand common leading abbreviations: "st"/"st." -> "saint" when
         followed by a space + another word; "ft"/"ft." -> "fort" same rule;
         "mt"/"mt." -> "mount" same rule.
      5. Collapse multiple whitespace to single space.

    Do NOT expand "st" when it's the whole name or trailing.

    Examples:
      "Wellington" -> "wellington"
      "St. John's" -> "saint johns"
      "St Clair" -> "saint clair"
      "Bay" -> "bay"
      "O'Connor" -> "oconnor"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    s = s.lower()

    # Strip apostrophes
    s = s.replace("'", "")

    # Expand leading abbreviations (only when followed by more words)
    def _expand_abbrev(m: re.Match) -> str:
        key = m.group(1).lower()
        return _LEADING_ABBREV_MAP.get(key, key) + " "

    s = _LEADING_ABBREV.sub(_expand_abbrev, s)

    # Collapse whitespace
    s = _WHITESPACE.sub(" ", s).strip()

    return s if s else None


def normalize_street_suffix(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a street suffix to full-word form.

    Uses a lookup table (case-insensitive match on lowercased stripped input
    after removing trailing period). Returns the canonical full-word form.
    If input isn't in the table, returns the lowercased stripped form.

    Examples:
      "St" -> "street"
      "Ave." -> "avenue"
      "Blvd" -> "boulevard"
      "Road" -> "road"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    key = s.lower().rstrip(".")
    return _STREET_SUFFIX_MAP.get(key, key)


def normalize_street_direction(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a compass direction to canonical full-word form.

    Matches case-insensitively. If input doesn't match, returns lowercased
    stripped form.

    Examples:
      "W" -> "west"
      "NE" -> "northeast"
      "North" -> "north"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    key = s.lower()
    return _DIRECTION_MAP.get(key, key)


def normalize_suite_type(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a suite-type indicator.

    Lookup (case-insensitive, after trimming and period removal):
      suite, po_box, floor, unit, penthouse

    If not matched, returns lowercased stripped form.

    Examples:
      "Suite" -> "suite"
      "Ste." -> "suite"
      "PO Box" -> "po_box"
      "P.O. Box" -> "po_box"
      "Floor" -> "floor"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    # Try with periods collapsed then stripped
    # Normalize: lowercase, collapse internal spaces, strip periods
    key = s.lower()
    # For multi-word variants like "P.O. Box", normalize periods to spaces first
    key_normalized = re.sub(r"\.", " ", key)
    key_normalized = _WHITESPACE.sub(" ", key_normalized).strip()

    # Try normalized form first
    if key_normalized in _SUITE_TYPE_MAP:
        return _SUITE_TYPE_MAP[key_normalized]

    # Try with periods stripped (for "s." -> "s")
    key_stripped = key.replace(".", "").strip()
    if key_stripped in _SUITE_TYPE_MAP:
        return _SUITE_TYPE_MAP[key_stripped]

    # Try original lowercased
    if key in _SUITE_TYPE_MAP:
        return _SUITE_TYPE_MAP[key]

    return key


def normalize_suite_number(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a suite number.

    Steps:
      1. Strip. Return None if empty.
      2. Lowercase.
      3. Strip leading zeros from purely numeric values.
      4. Preserve alphabetic mixed values ("PH2", "A12") after lowercasing.
      5. Strip surrounding punctuation (parens, commas).

    Examples:
      "4400" -> "4400"
      "0200" -> "200"
      "PH2" -> "ph2"
      "A-12" -> "a-12"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    # Strip surrounding punctuation (parens, commas, spaces)
    s = s.strip("(),. ")
    s = s.strip()
    if not s:
        return None

    s = s.lower()

    # Strip leading zeros from purely numeric values
    if re.match(r"^\d+$", s):
        s = str(int(s))

    return s if s else None


def normalize_city(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a city name.

    Steps:
      1. Strip. Return None if empty.
      2. Lowercase.
      3. Remove diacritics (NFKD decompose + ASCII filter).
      4. Collapse whitespace.
      5. Strip internal apostrophes.

    Examples:
      "Toronto" -> "toronto"
      "Québec" -> "quebec"
      "St. John's" -> "st johns"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    s = s.lower()
    s = _remove_diacritics(s)
    s = s.replace("'", "")
    # Remove non-alpha/space/hyphen punctuation (like periods)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = _WHITESPACE.sub(" ", s).strip()

    return s if s else None


def normalize_province(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a Canadian province or US state to canonical full name lowercase.

    Canadian provinces have canonical underscore-joined names (e.g. "british_columbia").
    US states fall through and are preserved as-is (lowercased).

    Examples:
      "Ontario" -> "ontario"
      "ON" -> "ontario"
      "Québec" -> "quebec"
      "CA" -> "ca"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    # Try exact lowercased match first
    key = s.lower()
    if key in _PROVINCE_MAP:
        return _PROVINCE_MAP[key]

    # Try diacritic-stripped form
    key_stripped = _remove_diacritics(key)
    if key_stripped in _PROVINCE_MAP:
        return _PROVINCE_MAP[key_stripped]

    # Fallthrough: return lowercased stripped input
    return key


def normalize_postal(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a Canadian postal code or US ZIP, or None if the value
    doesn't match either format.

    Canadian: UPPERCASE, strip internal spaces. "M5K 1H6" -> "M5K1H6".
    US ZIP: preserve hyphen for ZIP+4. Strip surrounding whitespace.
    Non-matching: return None (caller should preserve via postal_raw if needed).

    Examples:
      "m5k 1h6" -> "M5K1H6"
      "M4W 3E23" -> None  (invalid — 4 chars in second half)
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    upper = s.upper().strip()

    if _POSTAL_CA.match(upper):
        return upper.replace(" ", "")

    stripped = s.strip()
    if _POSTAL_US.match(stripped):
        return stripped

    return None


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """Canonicalize country codes to canonical form.

    Lookup:
      canada (ca, can, canada)
      united_states (us, usa, united states, united states of america)

    If not matched, returns lowercased stripped form.

    Examples:
      "Canada" -> "canada"
      "CA" -> "canada"
      "USA" -> "united_states"
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    key = s.lower()
    if key in _COUNTRY_MAP:
        return _COUNTRY_MAP[key]

    return key
