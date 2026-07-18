"""
M1 seed capture — The Strongman Group (Ownership Intelligence pilot,
docs/ownership-intelligence-pipeline.md M1).

Builds the capture payload from the 2026-07-07 deep-dive facts (all
previously verified; nothing fabricated), saves it to
data/capture_payloads/strongman_m1.json, and POSTs it through the one
validated door at http://localhost:8099/api/portfolio/capture.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/strongman_m1_capture.py            # dry_run
    PYTHONPATH=. .venv/bin/python scripts/strongman_m1_capture.py --commit   # commit
"""
import json
import os
import sys
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

SCRAPE = ("/Users/brandonolsen/Library/CloudStorage/OneDrive-CanadianCommercial/"
          "00_Prospecting/Portfolio Capture/raw-scrapes/portfolio_strongman.json")
OUT = os.path.join(REPO, "data", "capture_payloads", "strongman_m1.json")

SITE = "https://www.thestrongmangroup.com/"
ABOUT = SITE + "about-us/"
TEAM = SITE + "our-team/"
PROPS = SITE + "properties/"

# The two properties captured as real links (excluded from the GW worklist)
LINKED_ADDRESSES = {"1094 Bloor Street West", "1900 King Street East"}

NARRATIVE = """## The Strongman Group

Fourth-generation family business. The roots are a 1908 paint business that
became Color Your World (corporate name: Tonecraft), with stores across
Canada. The family sold the paint company in 1984 — and kept the real
estate. [web: thestrongmangroup.com/about-us]

The group in its current form dates to 2009, assembled by Gerry (Gerald)
Strongman and his son Marc. Marc Strongman is CEO — in real estate since
1987, a former analyst at Tonecraft, later with VanEd Holdings.
[web: thestrongmangroup.com/our-team; addyinvest.ca 2020-03-23]

## Scale

$200M+ AUM, roughly 700,000 sf: 50+ properties, 130+ tenants, across
Western Canada and Ontario. [web: thestrongmangroup.com]

## Realtrack behavior

Net sellers of small-market Ontario retail: Orillia (2011), Owen Sound
(2011), Kingston (2018). Buys are rare — 664 Richmond St, London (2009).
[rt]

## Working the portfolio

Ontario titles sit in SPVs mailing to 1885 Marine Dr, North Vancouver —
the reverse-address key. 1900 King St E, Hamilton sits on title as KING
ROSE G P INC mailing to that HQ; the remaining site-claimed properties are
queued as GW pulls, each expected to name its holding SPV. [web + rt]
"""

HQ = "1885 Marine Dr, North Vancouver BC V7P 1V5"


def build_payload():
    facts = [
        # HQ + phone — web-claimed AND RT-corroborated (two provenance rows)
        {"field": "hq_address", "value": HQ,
         "value_json": json.dumps({"street": "1885 Marine Dr", "city": "North Vancouver",
                                   "province": "BC", "postal": "V7P 1V5"}),
         "source": "web", "source_url": SITE, "confidence": 0.95},
        {"field": "hq_address", "value": HQ, "source": "rt", "confidence": 0.95},
        {"field": "phone", "value": "6049909648",
         "value_json": json.dumps({"raw": "604-990-9648"}),
         "source": "web", "source_url": SITE, "confidence": 0.95},
        {"field": "phone", "value": "6049909648",
         "value_json": json.dumps({"raw": "604-990-9648"}),
         "source": "rt", "confidence": 0.95},
        # Principals
        {"field": "principal", "value": "Gerald Strongman",
         "value_json": json.dumps({"role": "co-founder", "note": '"Gerry"'}),
         "source": "web", "source_url": TEAM, "confidence": 0.9},
        {"field": "principal", "value": "Gerald Strongman",
         "value_json": json.dumps({"role": "co-founder",
                                   "note": "RT party sides observed 1999-2011"}),
         "source": "rt", "confidence": 0.9,
         "effective_from": "1999", "effective_to": "2011"},
        {"field": "principal", "value": "Marc Strongman",
         "value_json": json.dumps({"role": "CEO",
                                   "note": "in RE since 1987; ex-Tonecraft analyst; ex-VanEd Holdings"}),
         "source": "web", "source_url": TEAM, "confidence": 0.95,
         "effective_from": "2009"},
        {"field": "principal", "value": "William Strongman",
         "value_json": json.dumps({"note": "RT phone match to 604-990-9648"}),
         "source": "rt", "confidence": 0.85},
        {"field": "principal", "value": "Reid Strongman",
         "value_json": json.dumps({"note": "RT party record"}),
         "source": "rt", "confidence": 0.8},
        # Profile facts
        {"field": "website", "value": "thestrongmangroup.com",
         "source": "web", "source_url": SITE, "confidence": 0.98},
        {"field": "founded", "value": "2009",
         "value_json": json.dumps({"note": "group formed 2009 by Gerry + Marc Strongman; "
                                           "family real-estate roots to 1908"}),
         "source": "web", "source_url": ABOUT, "confidence": 0.9},
        {"field": "aum_estimate", "value": "$200M+ AUM",
         "value_json": json.dumps({"amount": 200000000, "currency": "CAD",
                                   "basis": "web-claimed; ~700k sf, 50+ properties, 130+ tenants"}),
         "source": "web", "source_url": SITE, "confidence": 0.85},
        {"field": "sector_focus",
         "value": "Retail shopping centres + free-standing commercial; Western Canada + Ontario",
         "value_json": json.dumps({"asset_classes": ["retail"],
                                   "regions": ["Western Canada", "Ontario"]}),
         "source": "web", "source_url": SITE, "confidence": 0.9},
        {"field": "behavior",
         "value": "Net sellers of small-market Ontario retail (Orillia 2011, Owen Sound 2011, "
                  "Kingston 2018); rare buys (664 Richmond St London 2009)",
         "source": "rt", "confidence": 0.9},
        {"field": "origin_story",
         "value": "1908 paint roots -> Color Your World (Tonecraft); sold 1984, "
                  "family kept the real estate",
         "source": "web", "source_url": ABOUT, "confidence": 0.9},
    ]

    # GW worklist: the 20 site-claimed properties WITHOUT a captured link
    with open(SCRAPE) as f:
        scraped = json.load(f)
    worklist = [r for r in scraped if r["address"] not in LINKED_ADDRESSES]
    assert len(worklist) == 20, f"expected 20 worklist rows, got {len(worklist)}"
    for r in worklist:
        facts.append({
            "field": "gw_worklist_item",
            "value": f'{r["address"]}, {r["city"]}',
            "value_json": json.dumps({
                "address": r["address"], "city": r["city"], "arn": None,
                "why": "title pull expected to name holding SPV",
                "expected_yield": 1, "status": "open",
                "resolved_by_ingest": None}),
            "source": "web", "source_url": PROPS, "confidence": 0.9,
        })

    return {
        "group": {
            "display_name": "The Strongman Group",
            "business_lines": ["owner"],
            "hq_address": HQ,
            "domain": "thestrongmangroup.com",
            "website": "https://www.thestrongmangroup.com",
            "summary": "4th-generation North Vancouver family group; $200M+ / ~700k sf of "
                       "retail and free-standing commercial across Western Canada and "
                       "Ontario, held in SPVs mailing to 1885 Marine Dr.",
            "narrative_md": NARRATIVE,
            "source_url": SITE,
        },
        "aliases": [{"alias": "Strongman Group", "source_url": SITE, "confidence": 0.95}],
        "match_keys": [
            {"type": "address", "value_raw": HQ, "source_url": SITE, "confidence": 0.95},
            {"type": "phone", "value_raw": "604-990-9648", "source_url": SITE, "confidence": 0.95},
            {"type": "spv_name", "value_raw": "Blenheim Investments Ltd", "confidence": 0.9},
            {"type": "spv_name", "value_raw": "DRSSL Ltd", "confidence": 0.9},
            {"type": "spv_name", "value_raw": "Northcote Properties Ltd", "confidence": 0.9},
            {"type": "spv_name", "value_raw": "King Rose G P Inc", "confidence": 0.9},
            {"type": "spv_name", "value_raw": "Strongman Properties Inc", "confidence": 0.9},
        ],
        "contacts": [],
        "facts": facts,
        "properties": [
            {"arn": "19040311000990000000", "display_address": "1094 Bloor St W",
             "city": "Toronto", "relationship": "owns", "source": "web_capture",
             "source_url": PROPS, "confidence": 0.92, "registry_confirmed": False},
            # GW title = KING ROSE G P INC mailing to 1885 Marine Dr; web_asserted
            # at 0.85 -> lands status='pending' by design; reconciler surfaces it.
            {"arn": "25180403410642000000", "display_address": "1900 King St E",
             "city": "Hamilton", "relationship": "owns", "source": "web_capture",
             "source_url": PROPS, "confidence": 0.85, "registry_confirmed": False},
        ],
        # Existing legacy GRPs of the named SPVs — PROPOSE only (apply_merges
        # is never sent, so nothing merges).
        "merge_candidates": ["GRP_22794", "GRP_24356", "GRP_29519", "GRP_43808"],
        "captured_by": "cowork:brandon",
    }


def main():
    commit = "--commit" in sys.argv
    payload = build_payload()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"payload saved: {OUT} "
          f"({len(payload['facts'])} facts, {len(payload['properties'])} links)")

    from cleo.web.auth import create_token
    token = create_token(1, "brandon", "admin")
    dry = "false" if commit else "true"
    url = f"http://localhost:8099/api/portfolio/capture?dry_run={dry}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode()
            print(f"HTTP {resp.status} ({'COMMIT' if commit else 'DRY RUN'})")
            print(json.dumps(json.loads(body), indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
