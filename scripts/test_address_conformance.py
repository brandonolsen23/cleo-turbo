"""
Address-normalization conformance test: RT lane vs GW lane.

Both lanes must clean the same raw street string to the same canonical
components, because the owner's corporate-address match keys depend on it.

Entry points compared (tightest apples-to-apples available):

  RT lane:  address_normalizer.decompose.decompose(raw)
            (engines/rt/address_normalizer -- the full 11-step decomposer.
             This is what run.py calls per address line; its 'display' field
             is built via the shared cleo.address.formatter.format_display.)

  GW lane:  cleo.address.decompose.decompose_simple(raw)
            + cleo.address.formatter.format_display(components)
            (This is exactly what engines/gw/normalize.py parse_mpac_address
             does after it strips postal code / province / municipality from
             the MPAC string. We feed the already-stripped street portion,
             so both lanes see the identical raw input.)

Both return the same component keys, so we compare:
  street_number, street_name, street_suffix, street_direction,
  suite_type, suite_number, special_type, and the formatted display string.

PASS criteria: every fixture either agrees on all compared fields, OR is
explicitly listed in KNOWN_DIVERGENCES with a reason. Every entry in
KNOWN_DIVERGENCES is a documented bug to review, not an excuse. A stale
KNOWN_DIVERGENCES entry (fixture now agrees) is also a FAIL, so the list
cannot rot.

Read-only, pure-function: imports + fixtures only. No DB, no network,
no pipeline. Fixtures marked [db] were sampled once from data/cleo.db
(transactions.display_address and gw_assessments.owner_mailing with
city/province/postal stripped) and are hardcoded here for determinism.

Usage: PYTHONPATH=. .venv/bin/python scripts/test_address_conformance.py
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))

from address_normalizer.decompose import decompose as rt_decompose  # noqa: E402
from cleo.address.decompose import decompose_simple                 # noqa: E402
from cleo.address.formatter import format_display                   # noqa: E402


# ---------------------------------------------------------------------------
# Known divergences: raw fixture -> one-line reason.
# Each of these is a REAL disagreement between the two lanes, found by this
# test. They are documented bugs to review, not accepted behaviour.
# ---------------------------------------------------------------------------
KNOWN_DIVERGENCES = {
    "123 MAIN ST UNIT 5":
        "GW only strips trailing units after a comma; 'Unit 5' folds into street_name and suffix goes unexpanded",
    "#5 861 YORK MILLS ROAD":
        "GW has no leading-hash unit rule; '#5 861' stays in street_name and the street number is lost",
    "2441 YONGE ST, 2ND FLOOR":
        "GW leaves '2nd Floor' in street_name; RT extracts it but sets suite_number to the full '2ND FLOOR' text (dupe word, raw case)",
    "14-3650 LANGSTAFF RD":
        "RT splits unit-dash-number into Unit 14 / 3650; GW keeps '14-3650' as a range street_number",
    "B7-77 BILLY BISHOP WAY":
        "RT extracts Unit B7 / 77; GW has no letter-unit-dash rule, so 'B7-77' blocks street number extraction entirely",
    "399 1/2 KING ST":
        "RT keeps the fraction in street_number ('399 1/2'); GW pushes '1/2' into street_name (displays match, components don't)",
    "ONE MOUNT PLEASANT RD":
        "RT converts word street numbers (One -> 1); GW leaves 'One' in street_name with no street_number",
    "1255A+B DUNDAS ST E":
        "RT keeps plus-joined number '1255A+B' as street_number; GW leaves it in street_name and title-cases it to '1255a+b'",
    "4, 14 & 34 MAIN ST":
        "RT normalizes comma/ampersand number lists to '4,14,34'; GW leaves the whole list in street_name",
    "245/251 MAIN ST":
        "RT keeps slash number list as street_number; GW leaves it in street_name (displays match, components don't)",
    "CONC 12, PT LOT 6":
        "RT tags rural legals special_type='legal_description'; GW has no legal-description detection",
    "PO BOX 130":
        "RT tags special_type='po_box' with suite fields; GW treats 'PO Box 130' as a street_name",
    "RR 4":
        "RT tags special_type='rural_route' with suite fields; GW treats 'RR 4' as a street_name",
    "375 HAGEY BLVD UNIT 316":
        "GW comma-less trailing unit: 'Unit 316' folds into street_name, 'Blvd' never expanded (RT catches it via suffix-word pattern)",
    "3235 ELECTRICITY DR SUITE B":
        "GW comma-less trailing suite: 'Suite B' folds into street_name, 'Dr' never expanded",
    "25 AMY CROFT DR UNIT 23B":
        "GW comma-less trailing unit: 'Unit 23B' folds into street_name and gets title-cased to '23b'",
    "7077 KEELE ST UNIT 102":
        "GW comma-less trailing unit: 'Unit 102' folds into street_name, 'St' never expanded",
    "Conc 19, Pt Lots 10 & 20":
        "RT tags rural legals special_type='legal_description'; GW has no legal-description detection",
}

# NOTE (shared quality bug, NOT a divergence -- both lanes agree, so these
# fixtures PASS): when a comma-less unit follows a direction ("150 BLOOR ST W
# SUITE M101", "22 ST CLAIR AVE E SUITE 500", "2800 HIGHWAY 7 W UNIT 301",
# "4191 LINE 32 SUITE R"), BOTH lanes fold suffix + direction + suite into
# street_name unparsed. Conformant, but the match key is built from a bad
# parse in both lanes. Flagged here so it isn't mistaken for a good parse.


COMPARED_FIELDS = [
    'street_number', 'street_name', 'street_suffix', 'street_direction',
    'suite_type', 'suite_number', 'special_type',
]


# ---------------------------------------------------------------------------
# Fixtures. [hc] = hand-crafted edge case, [db] = sampled from data/cleo.db.
# ---------------------------------------------------------------------------
FIXTURES = [
    # -- hand-crafted edge cases --
    "1962 YONGE ST., SUITE 200",       # [hc] trailing suite after comma
    "123 MAIN ST UNIT 5",              # [hc] trailing unit, NO comma
    "UNIT 5 100 MAIN ST",              # [hc] leading unit keyword
    "#5 861 YORK MILLS ROAD",          # [hc] leading hash unit
    "45 KING ST, #301",                # [hc] trailing hash unit
    "2441 YONGE ST, 2ND FLOOR",        # [hc] ordinal floor
    "247 SUMMERLEA RD",                # [hc] simple abbreviation
    "732-746 10TH ST E",               # [hc] hyphenated range + ordinal + dir
    "14-3650 LANGSTAFF RD",            # [hc] unit-dash-number (unit prefix)
    "B7-77 BILLY BISHOP WAY",          # [hc] letter unit dash number
    "399 1/2 KING ST",                 # [hc] fraction street number
    "ONE MOUNT PLEASANT RD",           # [hc] word street number
    "620A MAIN ST",                    # [hc] letter-suffixed number
    "1255A+B DUNDAS ST E",             # [hc] plus-joined number
    "4, 14 & 34 MAIN ST",              # [hc] comma/ampersand number list
    "245/251 MAIN ST",                 # [hc] slash number list
    "HAZELDEAN RD",                    # [hc] no street number
    "25 THE WEST MALL",                # [hc] 'The West Mall' direction guard
    "CONC 12, PT LOT 6",               # [hc] rural legal description
    "PO BOX 130",                      # [hc] PO box
    "RR 4",                            # [hc] rural route
    "290 RUE PRINCIPALE",              # [hc] French prefix street type
    "10 ST. CLAIR AVE W",              # [hc] saint with period + direction
    # -- sampled from gw_assessments.owner_mailing (city/prov/postal stripped) --
    "26 WELLINGTON ST W",              # [db]
    "150 BLOOR ST W SUITE M101",       # [db] suite, no comma
    "100 SHEPPARD AVE E SUITE 502",    # [db] suite, no comma
    "22 ST CLAIR AVE E SUITE 500",     # [db] saint + dir + suite, no comma
    "375 HAGEY BLVD UNIT 316",         # [db] unit, no comma
    "2800 HIGHWAY 7 W UNIT 301",       # [db] numbered highway + dir + unit
    "684 WHARNCLIFFE RD S",            # [db]
    "4191 LINE 32 SUITE R",            # [db] numbered line + letter suite
    "41644 JOHN WISE LINE",            # [db]
    "632 PRINCIPALE RUE",              # [db] French suffix, trailing
    "3235 ELECTRICITY DR SUITE B",     # [db] letter suite, no comma
    "25 AMY CROFT DR UNIT 23B",        # [db] alphanumeric unit, no comma
    "7077 KEELE ST UNIT 102",          # [db] unit, no comma
    "186 CHATHAM ST N",                # [db]
    # -- sampled from transactions.display_address --
    "69-71 Selby Road",                # [db] hyphenated range
    "30-32 Kent Street West",          # [db] range + direction
    "84-88 1/2 Colborne Street",       # [db] range + fraction
    "3001 County Road 134",            # [db] compound road + route number
    "8312 Concession 8",               # [db] concession + number
    "9408 Seventeenth Sideroad",       # [db] ordinal word + sideroad
    "Conc 19, Pt Lots 10 & 20",        # [db] rural legal description
    "15-17 The Queensway South",       # [db] range + 'The' street name
    "1102 Ashforth Dr #4",             # [db] trailing hash, no comma
    "3914 Line 9",                     # [db] numbered line
    "6721 Fourth Line",                # [db] ordinal word street name
]


def run_rt(raw):
    out = rt_decompose(raw)
    return {f: out.get(f, '') for f in COMPARED_FIELDS} | {'display': out.get('display', '')}


def run_gw(raw):
    comps = decompose_simple(raw)
    return {f: comps.get(f, '') for f in COMPARED_FIELDS} | {'display': format_display(comps)}


def diff_fields(rt, gw):
    return [f for f in COMPARED_FIELDS + ['display'] if rt[f] != gw[f]]


def fmt(out):
    parts = [f"{f}={out[f]!r}" for f in COMPARED_FIELDS if out[f]]
    return f"display={out['display']!r} ({', '.join(parts) if parts else 'no components'})"


def main():
    passed, failed = [], []

    def check(name, cond, detail=''):
        (passed if cond else failed).append(name)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

    agree = 0
    divergent = []

    print("=== RT vs GW address conformance ===")
    for raw in FIXTURES:
        rt = run_rt(raw)
        gw = run_gw(raw)
        diffs = diff_fields(rt, gw)
        known = raw in KNOWN_DIVERGENCES

        if not diffs:
            agree += 1
            check(f"agree: {raw!r}", not known,
                  "STALE KNOWN_DIVERGENCES entry — lanes now agree, remove it" if known else '')
        else:
            divergent.append(raw)
            detail = f"fields={diffs} | rt: {fmt(rt)} | gw: {fmt(gw)}"
            if known:
                check(f"known divergence: {raw!r}", True,
                      KNOWN_DIVERGENCES[raw])
                print(f"         {detail}")
            else:
                check(f"UNDOCUMENTED divergence: {raw!r}", False, detail)

    print()
    print(f"Fixtures: {len(FIXTURES)}  |  agree: {agree}  |  "
          f"divergent: {len(divergent)} ({len(KNOWN_DIVERGENCES)} documented)")
    print(f"=== RESULT: {len(passed)} passed, {len(failed)} failed ===")
    if failed:
        print("FAILED:", failed)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
