"""
Address-normalization conformance test: RT lane vs GW lane.

Both lanes must clean the same raw street string to the same canonical
components, because the owner's corporate-address match keys depend on it.

Entry points compared (tightest apples-to-apples available):

  RT lane:  address_normalizer.decompose.decompose(raw)
            (engines/rt/address_normalizer -- since the 2026-07-07
             unification this is a thin re-export of the canonical
             decomposer in cleo/address/decompose.py.)

  GW lane:  cleo.address.decompose.decompose_simple(raw)
            + cleo.address.formatter.format_display(components)
            (engines/gw/normalize.py parse_mpac_address now calls the
             canonical decompose() directly; decompose_simple is kept as a
             compatibility alias of the same function. We feed the
             already-stripped street portion, so both lanes see the
             identical raw input.)

UNIFICATION (2026-07-07): both lanes import the ONE canonical decomposer
promoted from the RT pipeline into cleo/address/decompose.py. Agreement went
from 30/48 fixtures (62.5%) to 48/48 (100%); the 18 KNOWN_DIVERGENCES were
all resolved and removed. This test remains as a tripwire: any future edit
that forks the lanes' behavior again will fail here.

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
    # EMPTY since the 2026-07-07 unification: both lanes call the same
    # canonical decomposer (cleo/address/decompose.py), so a divergence is
    # structurally impossible unless someone forks the code paths again.
    # All 18 pre-unification entries were verified resolved and removed.
}

# NOTE (shared quality bugs, NOT divergences -- both lanes agree, so these
# fixtures PASS). Since unification the lanes are identically imperfect on:
#   1. Comma-less unit after a direction ("150 BLOOR ST W SUITE M101",
#      "22 ST CLAIR AVE E SUITE 500", "2800 HIGHWAY 7 W UNIT 301",
#      "4191 LINE 32 SUITE R"): suffix + direction + suite fold into
#      street_name unparsed. The comma-less trailing-unit regex requires a
#      recognized suffix word immediately before the unit keyword.
#   2. Compound-road guard over-reach ("121 CONCESSION ST E"): 'concession'
#      is in COMPOUND_ROAD_PREFIXES, so "St" is left unexpanded in
#      street_name -> "121 Concession St East". The old GW-only decomposer
#      handled this better, but RT is the byte-identical reference lane, so
#      both lanes now share RT's behavior (see tests/test_address_formatter
#      .py::TestDecomposeSimple::test_with_direction).
# Conformant, but the match key is built from a bad parse in both lanes.
# Flagged here so they aren't mistaken for good parses.


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
    "121 CONCESSION ST E",             # [hc] compound-prefix guard (shared imperfection #2)
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
