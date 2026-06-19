"""
Verification layer for parcel resolution (Stage 1).

Pure functions — canonical address-field matching + confidence tiering.
No I/O, no network, so this is fully unit-testable. Nothing here changes which
parcel a transaction resolves to; it only labels the result.

Tiers:
  verified  — parcel-locator match + field-match + point inside the polygon
  probable  — rooftop PointAddress inside the polygon (no full parcel/field match)
  review    — interpolated/centroid/uncontained/mismatch/disagrees -> needs eyes
"""

import re

from cleo.address.normalize import expand_suffix, expand_direction

VERIFIED = 'verified'
PROBABLE = 'probable'
REVIEW = 'review'

_CITY_PREFIXES = (
    'city of ', 'town of ', 'township of ', 'municipality of ',
    'corporation of the city of ', 'corporation of the ',
)


def _norm_city(city) -> str:
    if not city:
        return ''
    c = re.sub(r'\s+', ' ', str(city).lower().replace('.', ' ')).strip()
    for pre in _CITY_PREFIXES:
        if c.startswith(pre):
            c = c[len(pre):].strip()
            break
    return c


def _norm_street(name) -> str:
    """Canonicalize a street for matching: lowercase, strip punctuation, and
    expand a trailing direction then a trailing suffix (St->Street, E->East).
    Only trailing tokens are expanded, so a leading 'St'/saint (e.g. 'St Clair
    Ave') is left intact."""
    if not name:
        return ''
    s = re.sub(r'\s+', ' ', str(name).lower().replace('.', ' ')).strip()
    toks = [t for t in s.split(' ') if t]
    if not toks:
        return ''
    if len(toks) >= 2:
        d = expand_direction(toks[-1])
        if d:                       # trailing direction -> suffix is before it
            toks[-1] = d.lower()
            if len(toks) >= 3:
                suf = expand_suffix(toks[-2])
                if suf:
                    toks[-2] = suf.lower()
            return ' '.join(toks)
        suf = expand_suffix(toks[-1])  # no direction -> last token is suffix
        if suf:
            toks[-1] = suf.lower()
    return ' '.join(toks)


def field_match(rt_house, rt_street, rt_city, geo_house, geo_street, geo_city) -> bool:
    """True when RT address components equal the geocoder's parsed components
    after canonicalization. House must match exactly; street canonical-equal;
    city must agree only when both sides supply one."""
    if not (rt_house and geo_house):
        return False
    if str(rt_house).strip() != str(geo_house).strip():
        return False
    if _norm_street(rt_street) != _norm_street(geo_street):
        return False
    if rt_city and geo_city and _norm_city(rt_city) != _norm_city(geo_city):
        return False
    return True


def loc_bucket(loc_name) -> str:
    """Classify the geocoder Loc_name into parcel / roads / street / other."""
    u = (loc_name or '').upper()
    if u.startswith('PARCEL'):
        return 'parcel'
    if 'ROAD' in u:
        return 'roads'
    if u.startswith('STREET'):
        return 'street'
    return 'other'


def assign_tier(*, loc_name, addr_type, containment, fmatch,
                agrees_with_placement=True) -> str:
    """Assign a confidence tier from the captured signals.

    containment: 'contained' | 'nearest_centroid' | 'features0' | 'none'
    agrees_with_placement: False when a fresh parcel-level geocode lands on a
        different parcel than the record's current placement (Stage-1 flag).
    """
    contained = (containment == 'contained')
    if loc_bucket(loc_name) == 'parcel' and fmatch and contained and agrees_with_placement:
        return VERIFIED
    if addr_type == 'PointAddress' and contained and agrees_with_placement:
        return PROBABLE
    return REVIEW
