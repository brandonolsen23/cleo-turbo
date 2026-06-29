"""External-signal helpers for distinctiveness classification.

- is_english_common_token / common_language_zipf: wordfreq Zipf (EN + FR)
- load_place_names + is_place_name: Canadian places gazetteer + DB table
- load_industry_stopwords: seed JSON + persistent DB table
- seed_places_table: populate places from canadian_places.json on first run
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Set

import wordfreq

_RESOURCES = Path(__file__).parent / "resources"

# Default threshold: tokens with Zipf >= 3.0 are considered common enough in
# English that they cannot be distinctive brand identifiers on their own.
# 3.0 → word appears ~1/million in general English, e.g. 'ridge', 'poultry'.
DEFAULT_ZIPF_THRESHOLD = 3.0


def common_language_zipf(token: str) -> float:
    """Return the maximum Zipf score across English and French wordfreq.

    Canadian RT data contains French-Canadian corporate names (e.g.
    'ferme', 'groupe', 'conseil'). Checking only English misses them.
    """
    en_zipf = wordfreq.zipf_frequency(token, "en")
    fr_zipf = wordfreq.zipf_frequency(token, "fr")
    return max(en_zipf, fr_zipf)


def is_english_common_token(token: str, *, zipf_threshold: float = DEFAULT_ZIPF_THRESHOLD) -> bool:
    """True if the token is common in English OR French at the given threshold.

    Kept the name for backward compat, though it's now bilingual.
    """
    return common_language_zipf(token) >= zipf_threshold


def load_place_names(conn=None) -> Set[str]:
    """Lowercased set of place-name tokens.

    Union of the bundled canadian_places.json and, if `conn` is given,
    any entries in the `places` DB table (seed + user-curated).
    """
    path = _RESOURCES / "canadian_places.json"
    data = json.loads(path.read_text())
    tokens: Set[str] = set()
    for key, value in data.items():
        if key == "comment":
            continue
        if isinstance(value, list):
            tokens.update(v.lower() for v in value)
    if conn is not None:
        for row in conn.execute("SELECT token FROM places"):
            tokens.add(row[0])
    return tokens


def seed_places_table(conn) -> int:
    """Populate `places` from canadian_places.json if empty.

    Only inserts source='seed' rows; user entries are untouched.
    Returns the number of rows inserted.
    """
    existing = {r[0] for r in conn.execute("SELECT token FROM places WHERE source = 'seed'")}
    path = _RESOURCES / "canadian_places.json"
    data = json.loads(path.read_text())
    inserted = 0
    for key, value in data.items():
        if key == "comment":
            continue
        if not isinstance(value, list):
            continue
        for token in value:
            t = token.lower()
            if t in existing:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO places (token, added_by, source) "
                "VALUES (?, 'system', 'seed')",
                (t,),
            )
            inserted += 1
    conn.commit()
    return inserted


def is_place_name(token: str, place_names: Optional[Set[str]] = None) -> bool:
    if place_names is None:
        place_names = load_place_names()
    return token in place_names


def load_industry_stopwords(conn) -> Set[str]:
    """Union of seed tokens and user-curated tokens in industry_stopwords."""
    path = _RESOURCES / "industry_stopwords_seed.json"
    data = json.loads(path.read_text())
    tokens = {t.lower() for t in data.get("tokens", [])}

    for row in conn.execute("SELECT token FROM industry_stopwords"):
        tokens.add(row[0])

    return tokens


def load_defining_brands(conn, level: str = "1gram") -> Set[str]:
    """User-asserted defining brand tokens that override the Zipf/English filter.

    A token in this set is treated as distinctive regardless of its
    common-language Zipf score. Designed for CRE brands that are also real
    English words (starlight, summit, crown, cadillac, phoenix, sterling, ...).
    """
    try:
        cur = conn.execute(
            "SELECT ngram FROM defining_brands WHERE level = ?",
            (level,),
        )
        return {row[0].lower() for row in cur}
    except Exception:
        # Table may not exist on a fresh DB; return empty set rather than crash.
        return set()


def seed_industry_stopwords_table(conn) -> int:
    """Populate industry_stopwords from the seed JSON if the table is empty.

    Only inserts entries whose source is 'seed' — does not touch 'user' entries.
    Returns the number of seed rows inserted.
    """
    existing = {r[0] for r in conn.execute("SELECT token FROM industry_stopwords WHERE source = 'seed'")}
    path = _RESOURCES / "industry_stopwords_seed.json"
    data = json.loads(path.read_text())
    inserted = 0
    for token in data.get("tokens", []):
        t = token.lower()
        if t in existing:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO industry_stopwords (token, added_by, source) "
            "VALUES (?, 'system', 'seed')",
            (t,),
        )
        inserted += 1
    conn.commit()
    return inserted
