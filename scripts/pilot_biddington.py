"""
Biddington pilot — executable acceptance for M2-M5 (spec Section 13).

Runs ONLY against a copy of cleo.db. Posts the full Biddington payload
dry_run=true, then commits with apply_merges=true, then re-POSTs to prove
idempotency, and verifies every Section 13.5 acceptance criterion.

Usage: .venv/bin/python scripts/pilot_biddington.py /tmp/cleo_test.db
"""
import json
import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

db_path = sys.argv[1]
assert "cleo_test" in db_path or "/tmp/" in db_path, \
    "refusing to run on a non-copy path"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from cleo.web.deps import get_db, get_current_user
from cleo.web.routes.portfolio import router as portfolio_router

app = FastAPI()  # minimal app: no lifespan, nothing touches data/cleo.db
app.include_router(portfolio_router, prefix="/api/portfolio")


def _override_db():
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_current_user] = lambda: {
    "username": "brandon", "display_name": "Brandon Olsen", "role": "admin"}
client = TestClient(app)

c = sqlite3.connect(db_path)
c.row_factory = sqlite3.Row

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          f"{(' — ' + detail) if detail else ''}")


MERGE_CANDIDATES = ["GRP_107934", "GRP_64356", "GRP_114797",
                    "GRP_61921", "GRP_34862"]

GROUP_A = [  # (arn, address, city, expected PRO id)
    ("25180606130875000000", "969 Fennell Avenue East", "Hamilton", "PRO_77861"),
    ("19080315000260000000", "1008 Wilson Avenue", "North York", "PRO_76051"),
    ("19011030310020100000", "2355 Warden Avenue", "Scarborough", "PRO_79231"),
    ("24010100301945000000", "303 Upper Middle Road East", "Oakville", "PRO_84236"),
]

GROUP_B = [  # (arn, address, city)
    ("19190444600095000000", "1889 Albion Road", "Etobicoke"),
    ("19190253350060000000", "235 Dixon Road", "Etobicoke"),
    ("19140642600260000000", "2202 Weston Road", "Toronto"),
    ("19190383000250000000", "21 Fasken Drive", "Etobicoke"),
    ("19190383000280000000", "296 Carlingview Drive", "Etobicoke"),
    ("19190383000310000000", "276 Carlingview Drive", "Etobicoke"),
    ("19190383000320000000", "276 Carlingview Drive", "Etobicoke"),
    ("19080544400030100000", "219-245 Wilmington Avenue", "North York"),
]

PAYLOAD = {
    "group": {
        "display_name": "The Biddington Group",
        "business_lines": ["owner", "developer", "property_manager"],
        "hq_address": "1962 Yonge St Suite 200 Toronto",
        "domain": "biddington.com",
        "website": "https://www.biddington.com",
        "summary": "Family-held Toronto owner/developer; SPV-heavy portfolio "
                   "(Kilbarry, Quadrillium, Biddington Yonge Street entities).",
        "source_url": "https://www.biddington.com",
    },
    "aliases": [],
    "match_keys": [
        {"type": "address", "value_raw": "1962 Yonge St Suite 200 Toronto",
         "source_url": "https://www.biddington.com", "confidence": 0.95},
        {"type": "address", "value_raw": "1960 Yonge St", "confidence": 0.9},
        {"type": "spv_name", "value_raw": "Kilbarry Holding Corporation",
         "confidence": 0.95},
        {"type": "spv_name", "value_raw": "Kilbarry Holdings Corporation",
         "confidence": 0.95},
        {"type": "spv_name", "value_raw": "The Quadrillium Corporation",
         "confidence": 0.95},
        {"type": "spv_name", "value_raw": "Biddington Homes Wilmington Inc",
         "confidence": 0.95},
        {"type": "spv_name", "value_raw": "Biddington Property Management Corp",
         "confidence": 0.95},
        {"type": "domain", "value_raw": "biddington.com"},
    ],
    "contacts": [],
    "properties": (
        [{"arn": a, "display_address": addr, "city": city,
          "relationship": "owns", "source": "geowarehouse",
          "confidence": 0.98, "registry_confirmed": True}
         for a, addr, city, _pid in GROUP_A]
        + [{"arn": a, "display_address": addr, "city": city,
            "relationship": "owns", "source": "geowarehouse",
            "confidence": 0.98, "registry_confirmed": True}
           for a, addr, city in GROUP_B]
    ),
    "merge_candidates": MERGE_CANDIDATES,
    "captured_by": "cowork:brandon",
}

BASE_FIELDS = ("arn", "display_address", "city", "postal", "lat", "lng",
               "legal_description")


def base_snapshot():
    snap = {}
    for arn, _addr, _city, pid in GROUP_A:
        r = c.execute(
            "SELECT arn, display_address, city, postal, lat, lng, "
            "legal_description, LENGTH(COALESCE(parcel_geojson,'')) AS geo_len "
            "FROM properties WHERE id = ?", (pid,)).fetchone()
        snap[pid] = dict(r) if r else None
    return snap


def counts():
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    return {
        "groups": q("SELECT COUNT(*) FROM groups"),
        "links": q("SELECT COUNT(*) FROM manual_owner_links"),
        "keys": q("SELECT COUNT(*) FROM group_match_keys"),
        "profiles": q("SELECT COUNT(*) FROM group_profile"),
        "manual_props": q("SELECT COUNT(*) FROM manual_properties"),
        "merges": q("SELECT COUNT(*) FROM group_merges WHERE unmerged_at IS NULL"),
    }

# ── Step 1: dry_run=true ─────────────────────────────────────────────
print("\n=== Biddington pilot: dry_run=true ===")
base_before = base_snapshot()
counts_before = counts()
r = client.post("/api/portfolio/capture?dry_run=true", json=PAYLOAD)
check("dry_run returns 200", r.status_code == 200, r.text[:300])
dry = r.json()
print("\n--- DRY-RUN DIFF ---")
print(json.dumps(dry, indent=2))
check("dry_run: new parent group minted", dry["created"] is True)
check("dry_run: 4 Group A dark fills", dry["overrides"]["filled"] >= 4,
      str(dry["overrides"]))
check("dry_run: 8 Group B ARNs pending (no property row yet)",
      dry["overrides"]["pending_no_property"] == 8, str(dry["overrides"]))
check("dry_run: zero conflicts", dry["overrides"]["conflicts"] == 0,
      str(dry["overrides"]))
check("dry_run: all 5 merges proposed, none applied",
      set(dry["merges_proposed"]) == set(MERGE_CANDIDATES)
      and dry["merges_applied"] == 0,
      f"proposed={dry['merges_proposed']} applied={dry['merges_applied']}")
check("dry_run: every Group B ARN surfaced in warnings (not dropped)",
      all(any(a in w for w in dry["warnings"]) for a, _x, _y in GROUP_B),
      str(dry["warnings"])[:300])
check("dry_run left ZERO rows", counts() == counts_before,
      f"before={counts_before} after={counts()}")

# ── Step 2: commit with apply_merges=true ────────────────────────────
print("\n=== Biddington pilot: dry_run=false&apply_merges=true ===")
r = client.post("/api/portfolio/capture?dry_run=false&apply_merges=true",
                json=PAYLOAD)
check("commit returns 200", r.status_code == 200, r.text[:300])
commit = r.json()
PARENT = commit["group_id"]
print("\n--- COMMIT DIFF ---")
print(json.dumps(commit, indent=2))

# 13.5 — PRO_77861 owner becomes the Biddington parent
row = c.execute("SELECT current_owner_group_id FROM properties WHERE id='PRO_77861'").fetchone()
check("PRO_77861 (Fennell) owner = Biddington parent",
      row["current_owner_group_id"] == PARENT,
      f"owner={row['current_owner_group_id']} parent={PARENT}")

# All four Group A parcels filled
for arn, _addr, _city, pid in GROUP_A:
    row = c.execute("SELECT current_owner_group_id FROM properties WHERE id=?",
                    (pid,)).fetchone()
    check(f"{pid} owner = parent", row["current_owner_group_id"] == PARENT,
          str(row["current_owner_group_id"]))

# Group B: manual_properties rows + links
for arn, _addr, _city in GROUP_B:
    mp = c.execute("SELECT COUNT(*) FROM manual_properties WHERE arn=?",
                   (arn,)).fetchone()[0]
    lk = c.execute(
        "SELECT COUNT(*) FROM manual_owner_links WHERE arn=? AND group_id=? "
        "AND relationship='owns'", (arn, PARENT)).fetchone()[0]
    check(f"Group B {arn}: manual_properties + link", mp == 1 and lk == 1,
          f"manual={mp} links={lk}")

# All 12 ARNs attach as owns
n = c.execute(
    "SELECT COUNT(*) FROM manual_owner_links WHERE group_id=? AND "
    "relationship='owns' AND source='geowarehouse'", (PARENT,)).fetchone()[0]
check("all 12 captured ARNs attached as owns", n == 12, f"links={n}")

# Merges applied; pool groups merged; parent consolidated
check("5 merges applied on commit", commit["merges_applied"] == 5,
      str(commit["merges_applied"]))
for g in MERGE_CANDIDATES:
    row = c.execute("SELECT status FROM groups WHERE id=?", (g,)).fetchone()
    mrow = c.execute(
        "SELECT target_group_id FROM group_merges WHERE source_group_id=? "
        "AND unmerged_at IS NULL", (g,)).fetchone()
    check(f"{g} merged into parent",
          row["status"] == "merged" and mrow and mrow["target_group_id"] == PARENT,
          f"status={row['status']} target={mrow['target_group_id'] if mrow else None}")
# Consolidated property_count: execute_merge recomputes from live rows, so
# it must equal the actual owned-property count and include the 4 Group A
# fills plus anything the merged pool groups really owned. (Candidates'
# pre-merge property_count values can be stale derived numbers.)
pc = c.execute("SELECT property_count FROM groups WHERE id=?", (PARENT,)).fetchone()
actual = c.execute(
    "SELECT COUNT(*) FROM properties WHERE current_owner_group_id=?",
    (PARENT,)).fetchone()[0]
check("parent shows consolidated property_count (recomputed, >= 4 Group A)",
      pc["property_count"] == actual and actual >= 5,
      f"property_count={pc['property_count']} actual={actual}")

# Base property fields untouched
base_after = base_snapshot()
check("base property fields untouched (arn/address/city/postal/geo/latlng)",
      base_before == base_after,
      "" if base_before == base_after else f"{base_before} != {base_after}")

# ── Step 3: second identical POST changes nothing ────────────────────
print("\n=== Biddington pilot: idempotent re-POST ===")
counts_mid = counts()
owners_mid = {pid: c.execute(
    "SELECT current_owner_group_id FROM properties WHERE id=?", (pid,)
).fetchone()[0] for _a, _b, _c2, pid in GROUP_A}
r = client.post("/api/portfolio/capture?dry_run=false&apply_merges=true",
                json=PAYLOAD)
check("re-POST returns 200", r.status_code == 200, r.text[:300])
again = r.json()
check("re-POST resolves same parent, created=false",
      again["group_id"] == PARENT and again["created"] is False,
      f"gid={again['group_id']} created={again['created']}")
check("re-POST: no new rows in any capture table", counts() == counts_mid,
      f"before={counts_mid} after={counts()}")
check("re-POST: no additional merges", again["merges_applied"] == 0,
      str(again["merges_applied"]))
check("re-POST: zero new keys/aliases/links",
      again["match_keys_added"] == 0 and again["aliases_added"] == 0
      and again["sweep"]["attached"] == 0,
      f"keys={again['match_keys_added']} sweep={again['sweep']['attached']}")
owners_now = {pid: c.execute(
    "SELECT current_owner_group_id FROM properties WHERE id=?", (pid,)
).fetchone()[0] for _a, _b, _c2, pid in GROUP_A}
check("re-POST: owners unchanged", owners_now == owners_mid, str(owners_now))
check("base fields still untouched", base_snapshot() == base_before)

print(f"\n=== PILOT RESULT: {len(passed)} passed, {len(failed)} failed ===")
if failed:
    print("FAILED:", failed)
sys.exit(1 if failed else 0)
