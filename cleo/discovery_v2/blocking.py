"""Candidate pair blocking — generate pairs that share at least one
non-generic atom. Prevents O(N²) comparisons.
"""

from __future__ import annotations
from itertools import combinations
from typing import Dict, Generator, Tuple

from .config import CALIBRATION

PartySide = Tuple[str, str]  # (source_id, side)
CandidatePair = Tuple[str, str, str, str, str, str]
# (source_id_a, side_a, source_id_b, side_b, atom_type, atom_value)


def _canonical_pair(a: PartySide, b: PartySide) -> Tuple[PartySide, PartySide]:
    """Order-independent pair key so we emit each pair once."""
    return (a, b) if a < b else (b, a)


def generate_candidate_pairs(
    conn, idf_map: Dict[Tuple[str, str], float], *,
    min_idf: float = None, max_sides: int = None,
) -> Generator[CandidatePair, None, None]:
    """Yield candidate pairs sharing at least one non-generic atom.

    Atom types scanned:
      - brand_token (multi-valued; IDF-gated by min_idf)
      - phone (singleton)
      - address_triple (synthesized from street_number + street_name + street_suffix)
      - contact_fingerprint (singleton)

    Yields (source_id_a, side_a, source_id_b, side_b, atom_type, atom_value),
    ordered so (a_key) < (b_key).
    Deduplicated across atom types.

    Parameters
    ----------
    max_sides : int, optional
        Skip any atom value whose party-side count exceeds this cap.
        Atoms shared by hundreds of unrelated parties (e.g. "1 King Street")
        produce millions of pathological pairs without discriminating signal.
        Default uses CALIBRATION["blocking_max_sides_per_atom"]["max_sides"].
    """
    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]
    if max_sides is None:
        max_sides = CALIBRATION["blocking_max_sides_per_atom"]["max_sides"]

    excluded_tokens = CALIBRATION["excluded_brand_tokens"]
    seen_pairs: set = set()

    def _emit(a: PartySide, b: PartySide, atom_type: str, atom_value: str):
        """Inner generator — yields one tuple if unseen, nothing if already emitted."""
        if a == b:
            return
        a_sorted, b_sorted = _canonical_pair(a, b)
        key = (a_sorted, b_sorted, atom_type, atom_value)
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        yield (a_sorted[0], a_sorted[1], b_sorted[0], b_sorted[1], atom_type, atom_value)

    # 1. brand_token — gated by IDF threshold and exclusion list
    rows = conn.execute(
        "SELECT atom_value, source_id, side FROM party_atoms "
        "WHERE atom_type = 'brand_token' ORDER BY atom_value"
    ).fetchall()
    bucket: Dict[str, list] = {}
    for r in rows:
        val = r["atom_value"]
        if val in excluded_tokens:
            continue
        if min_idf > 0.0 and idf_map.get(("brand_token", val), 0.0) < min_idf:
            continue
        bucket.setdefault(val, []).append((r["source_id"], r["side"]))
    for val, sides in bucket.items():
        if len(sides) < 2:
            continue
        uniq = sorted(set(sides))
        if len(uniq) > max_sides:
            continue
        for a, b in combinations(uniq, 2):
            yield from _emit(a, b, "brand_token", val)

    # 2. phone — no IDF gate in Phase A (require_co_signal handled in scoring)
    for row in conn.execute(
        "SELECT phone, COUNT(*) AS c FROM party_fingerprints "
        "WHERE phone IS NOT NULL AND phone != '' "
        "GROUP BY phone HAVING c >= 2 AND c <= ?",
        (max_sides,),
    ):
        phone = row["phone"]
        sides = [
            (r["source_id"], r["side"]) for r in conn.execute(
                "SELECT source_id, side FROM party_fingerprints WHERE phone = ?",
                (phone,),
            )
        ]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "phone", phone)

    # 3. address_triple — full match only
    for row in conn.execute(
        """SELECT street_number, street_name, street_suffix,
                  GROUP_CONCAT(source_id || '|' || side, ';') AS sides_csv,
                  COUNT(*) AS c
           FROM party_fingerprints
           WHERE street_number IS NOT NULL AND street_number != ''
             AND street_name IS NOT NULL AND street_name != ''
             AND street_suffix IS NOT NULL AND street_suffix != ''
           GROUP BY street_number, street_name, street_suffix
           HAVING c >= 2 AND c <= ?""",
        (max_sides,),
    ):
        triple = f"{row['street_number']}|{row['street_name']}|{row['street_suffix']}"
        sides = [tuple(s.split("|")) for s in row["sides_csv"].split(";")]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "address_triple", triple)

    # 4. contact_fingerprint — exact
    for row in conn.execute(
        "SELECT contact_fingerprint, COUNT(*) AS c FROM party_fingerprints "
        "WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != '' "
        "GROUP BY contact_fingerprint HAVING c >= 2 AND c <= ?",
        (max_sides,),
    ):
        cf = row["contact_fingerprint"]
        sides = [
            (r["source_id"], r["side"]) for r in conn.execute(
                "SELECT source_id, side FROM party_fingerprints WHERE contact_fingerprint = ?",
                (cf,),
            )
        ]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "contact_fingerprint", cf)
