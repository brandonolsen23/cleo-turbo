"""External-signal helpers for distinctiveness classification.

- is_english_common_token: uses wordfreq Zipf frequency
- load_place_names + is_place_name: Canadian places gazetteer
- load_industry_stopwords: seed JSON + persistent DB table
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


def is_english_common_token(token: str, *, zipf_threshold: float = DEFAULT_ZIPF_THRESHOLD) -> bool:
    """True if the token is common enough in English to NOT be distinctive."""
    return wordfreq.zipf_frequency(token, "en") >= zipf_threshold


def load_place_names() -> Set[str]:
    """Return a lowercased set of Canadian place-name tokens."""
    path = _RESOURCES / "canadian_places.json"
    data = json.loads(path.read_text())
    tokens: Set[str] = set()
    for key, value in data.items():
        if key == "comment":
            continue
        if isinstance(value, list):
            tokens.update(v.lower() for v in value)
    return tokens


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
