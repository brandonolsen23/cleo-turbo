"""
Milestone 2 + 4 acceptance tests for the Portfolio Capture endpoint.

Runs ONLY against a copy of cleo.db passed on the command line. Proves:
  A  normalize_arn ARN atom (engine-delegated) is canonical.
  B  a low-specificity spv_name match key is rejected with 422.
  C  dry_run=true returns the diff and leaves ZERO rows behind.
  D  commit fills a dark property's owner; off-book ARN creates a
     manual_properties stub and surfaces in warnings.
  E  an identical re-POST is idempotent (no duplicate links/keys/aliases).
  F  the M4 sweep attaches two seeded dark parcels sharing a normalized
     SPV owner name, and leaves an ambiguous shared-address owner in
     sweep.ambiguous (never attached).

Usage: .venv/bin/python scripts/test_portfolio_capture_m2.py /tmp/cleo_m2_test.db
"""
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
from cleo.atoms.normalize import normalize_arn, compose_address_key

# Minimal app: no lifespan, so nothing ever touches the real data/cleo.db.
app = FastAPI()
app.include_router(portfolio_router, prefix="/api/portfolio")


def _override_db():
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_current_user] = lambda: {
    "username": "m2test", "display_name": "M2 Test", "role": "admin"}
client = TestClient(app)

c = sqlite3.connect(db_path)
c.row_factory = sqlite3.Row

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          f"{(' — ' + detail) if detail else ''}")


# ---- A: ARN atom ----
print("\n=== A: normalize_arn (engine-delegated) ===")
check("normalize_arn('25 18 060 613 08750') == 20-digit api",
      normalize_arn("25 18 060 613 08750") == "25180606130875000000",
      str(normalize_arn("25 18 060 613 08750")))
pro = c.execute("SELECT id FROM properties WHERE arn = ?",
                ("25180606130875000000",)).fetchone()
check("...and resolves to PRO_77861", pro is not None and pro["id"] == "PRO_77861",
      pro["id"] if pro else "not in properties")
check("registry-prefixed input rejected", normalize_arn("HR-120738") is None)

# ---- pick a live dark property to fill ----
dark = c.execute(
    "SELECT arn, id FROM properties "
    "WHERE (transaction_count IS NULL OR transaction_count = 0) "
    "AND (current_owner_group_id IS NULL OR current_owner_group_id = '') "
    "AND arn IS NOT NULL AND arn != '' LIMIT 1").fetchone()
assert dark, "no dark property found in the copy"
DARK_ARN, DARK_PID = dark["arn"], dark["id"]
OFFBOOK_ARN = "19990000000000000099"  # valid format, not in properties

PAYLOAD = {
    "group": {
        "display_name": "M2 Test Holdings Alpha",
        "business_lines": ["owner"],
        "hq_address": "100 Test St Suite 5 Toronto",
        "domain": "m2testalpha.example",
        "website": "https://m2testalpha.example",
        "summary": "M2 acceptance test group",
    },
    "aliases": [{"alias": "M2TA Holdings", "confidence": 0.95}],
    "match_keys": [
        {"type": "address", "value_raw": "100 Test St Suite 5 Toronto",
         "confidence": 0.95},
        {"type": "spv_name", "value_raw": "M2TA Sub Two Holdings Inc",
         "confidence": 0.95},
        {"type": "domain", "value_raw": "m2testalpha.example"},
    ],
    "contacts": [],
    "properties": [
        {"arn": DARK_ARN, "relationship": "owns", "source": "geowarehouse",
         "confidence": 0.98, "registry_confirmed": True},
        {"arn": OFFBOOK_ARN, "display_address": "1 Offbook Rd",
         "city": "Toronto", "relationship": "owns", "source": "geowarehouse",
         "confidence": 0.98, "registry_confirmed": True},
    ],
    "merge_candidates": [],
    "captured_by": "test:m2",
}


def snapshot():
    q = lambda sql: c.execute(sql).fetchone()[0]
    return {
        "groups": q("SELECT COUNT(*) FROM groups"),
        "links": q("SELECT COUNT(*) FROM manual_owner_links"),
        "keys": q("SELECT COUNT(*) FROM group_match_keys"),
        "aliases": q("SELECT COUNT(*) FROM group_aliases"),
        "profiles": q("SELECT COUNT(*) FROM group_profile"),
        "manual_props": q("SELECT COUNT(*) FROM manual_properties"),
        "contacts": q("SELECT COUNT(*) FROM contacts"),
    }


# ---- B: low-specificity match key -> 422 ----
print("\n=== B: specificity guard rejects 'Forum' with 422 ===")
bad = {**PAYLOAD, "match_keys": PAYLOAD["match_keys"] + [
    {"type": "spv_name", "value_raw": "Forum"}]}
pre = snapshot()
r = client.post("/api/portfolio/capture?dry_run=true", json=bad)
check("low-specificity spv_name returns 422", r.status_code == 422,
      f"status={r.status_code} body={r.text[:120]}")
after = snapshot()
check("422 request left zero rows", after == pre,
      f"before={pre} after={after}")

# ---- C: dry_run leaves zero rows ----
print("\n=== C: dry_run=true returns diff, writes nothing ===")
before = snapshot()
r = client.post("/api/portfolio/capture?dry_run=true", json=PAYLOAD)
check("dry_run returns 200", r.status_code == 200, r.text[:200])
diff = r.json() if r.status_code == 200 else {}
check("dry_run diff: created new group", diff.get("created") is True, str(diff.get("created")))
check("dry_run diff: dark fill counted", diff.get("overrides", {}).get("filled") == 1,
      str(diff.get("overrides")))
check("dry_run diff: off-book ARN pending_no_property == 1",
      diff.get("overrides", {}).get("pending_no_property") == 1, str(diff.get("overrides")))
check("dry_run diff: off-book ARN in warnings",
      any(OFFBOOK_ARN in w for w in diff.get("warnings", [])), str(diff.get("warnings")))
after = snapshot()
check("dry_run left ZERO rows in every capture table", before == after,
      f"before={before} after={after}")
p = c.execute("SELECT current_owner_group_id FROM properties WHERE arn=?",
              (DARK_ARN,)).fetchone()
check("dry_run did not fill the property", not p["current_owner_group_id"],
      str(p["current_owner_group_id"]))

# ---- D: commit fills the dark property ----
print("\n=== D: commit (dry_run=false) fills dark owner ===")
r = client.post("/api/portfolio/capture?dry_run=false", json=PAYLOAD)
check("commit returns 200", r.status_code == 200, r.text[:200])
diff = r.json()
GID = diff["group_id"]
p = c.execute("SELECT current_owner_group_id FROM properties WHERE arn=?",
              (DARK_ARN,)).fetchone()
check("dark property owner filled with new group",
      p["current_owner_group_id"] == GID,
      f"owner={p['current_owner_group_id']} expected={GID}")
link = c.execute(
    "SELECT status, property_id, approved_at FROM manual_owner_links "
    "WHERE arn=? AND group_id=?", (DARK_ARN, GID)).fetchone()
check("link active + property cached + approval stamped",
      link is not None and link["status"] == "active"
      and link["property_id"] == DARK_PID and link["approved_at"],
      str(dict(link)) if link else "missing")
mp = c.execute("SELECT COUNT(*) FROM manual_properties WHERE arn=?",
               (OFFBOOK_ARN,)).fetchone()[0]
check("off-book ARN created a manual_properties stub", mp == 1, f"rows={mp}")
sw0 = c.execute(
    "SELECT sweepable FROM group_match_keys WHERE group_id=? AND key_type='domain'",
    (GID,)).fetchone()
check("domain key stored identity-only (sweepable=0)",
      sw0 is not None and sw0["sweepable"] == 0, str(dict(sw0)) if sw0 else "missing")

# ---- E: idempotent re-POST ----
print("\n=== E: identical re-POST changes nothing ===")
before = snapshot()
r = client.post("/api/portfolio/capture?dry_run=false", json=PAYLOAD)
check("re-POST returns 200", r.status_code == 200, r.text[:200])
diff2 = r.json()
after = snapshot()
check("re-POST added zero rows anywhere", before == after,
      f"before={before} after={after}")
check("re-POST resolves to the same group, created=false",
      diff2["group_id"] == GID and diff2["created"] is False,
      f"gid={diff2['group_id']} created={diff2['created']}")
check("re-POST counters all zero",
      diff2["match_keys_added"] == 0 and diff2["aliases_added"] == 0
      and diff2["sweep"]["attached"] == 0,
      f"keys={diff2['match_keys_added']} aliases={diff2['aliases_added']} "
      f"sweep={diff2['sweep']['attached']}")
# Note: owner_overrides counts a dark-property re-derive as 'filled' (its
# 'confirmed' branch is for RT-owned properties). The DB result is what
# must be idempotent: same owner, no new rows.
p2 = c.execute("SELECT current_owner_group_id FROM properties WHERE arn=?",
               (DARK_ARN,)).fetchone()
check("re-POST re-derives the SAME owner (idempotent result)",
      p2["current_owner_group_id"] == GID
      and diff2["overrides"]["filled"] + diff2["overrides"]["confirmed"] == 1
      and diff2["overrides"]["conflicts"] == 0,
      f"owner={p2['current_owner_group_id']} overrides={diff2['overrides']}")
nlinks = c.execute(
    "SELECT COUNT(*) FROM manual_owner_links WHERE arn=? AND group_id=?",
    (DARK_ARN, GID)).fetchone()[0]
check("no duplicate link rows", nlinks == 1, f"rows={nlinks}")

# ---- F: M4 sweep — attach shared-SPV parcels, surface ambiguity ----
print("\n=== F: match-key sweep (M4) ===")
SPV_A, SPV_B = "99990000000000000001", "99990000000000000002"
AMB_A, AMB_B = "99990000000000000003", "99990000000000000004"
c.execute("INSERT INTO properties (id, arn, display_address, city, "
          "transaction_count, current_owner_name) VALUES "
          "('PRO_M2SWA', ?, '11 Sweep St', 'toronto', 0, 'M2 Sweepco Holdings Inc')",
          (SPV_A,))
c.execute("INSERT INTO properties (id, arn, display_address, city, "
          "transaction_count, current_owner_name) VALUES "
          "('PRO_M2SWB', ?, '22 Sweep St', 'toronto', 0, 'M2 SWEEPCO HOLDINGS INC.')",
          (SPV_B,))
c.execute("INSERT INTO properties (id, arn, display_address, city, "
          "transaction_count, current_owner_name) VALUES "
          "('PRO_M2AMA', ?, '33 Amb St', 'toronto', 0, 'Ambig Alpha Inc')", (AMB_A,))
c.execute("INSERT INTO properties (id, arn, display_address, city, "
          "transaction_count, current_owner_name) VALUES "
          "('PRO_M2AMB', ?, '44 Amb St', 'toronto', 0, 'Ambig Beta Inc')", (AMB_B,))
c.execute("INSERT INTO gw_assessments (id, gw_id, arn, owner_name, owner_mailing) "
          "VALUES ('GW_M2AMA', 'GW_M2AMA', ?, 'Ambig Alpha Inc', "
          "'55 Ambigtest St, Testville, ON')", (AMB_A,))
c.execute("INSERT INTO gw_assessments (id, gw_id, arn, owner_name, owner_mailing) "
          "VALUES ('GW_M2AMB', 'GW_M2AMB', ?, 'Ambig Beta Inc', "
          "'55 Ambigtest St, Testville, ON')", (AMB_B,))
c.commit()

sweep_payload = {
    "group": {"display_name": "M2 Sweep Parent Group"},
    "aliases": [],
    "match_keys": [
        {"type": "spv_name", "value_raw": "M2 Sweepco Holdings Inc",
         "confidence": 0.95},
        {"type": "address", "value_raw": "55 Ambigtest St Testville",
         "confidence": 0.95},
    ],
    "contacts": [],
    "properties": [],
    "merge_candidates": [],
    "captured_by": "test:m2",
}
r = client.post("/api/portfolio/capture?dry_run=false", json=sweep_payload)
check("sweep POST returns 200", r.status_code == 200, r.text[:200])
sd = r.json()
SGID = sd["group_id"]
sweep = sd["sweep"]
check("sweep attached exactly the two shared-SPV parcels",
      sweep["attached"] == 2 and set(sweep["matched_arns"]) == {SPV_A, SPV_B},
      str(sweep))
check("ambiguous shared-address owners surfaced, not attached",
      set(sweep["ambiguous"]) == {AMB_A, AMB_B}, str(sweep["ambiguous"]))
for arn, pid in ((SPV_A, "PRO_M2SWA"), (SPV_B, "PRO_M2SWB")):
    p = c.execute("SELECT current_owner_group_id, current_owner_name "
                  "FROM properties WHERE arn=?", (arn,)).fetchone()
    check(f"swept parcel {pid} owner filled + registry name preserved",
          p["current_owner_group_id"] == SGID
          and "sweepco" in (p["current_owner_name"] or "").lower(),
          f"gid={p['current_owner_group_id']} name={p['current_owner_name']}")
amb_links = c.execute(
    "SELECT COUNT(*) FROM manual_owner_links WHERE arn IN (?, ?)",
    (AMB_A, AMB_B)).fetchone()[0]
check("no links written for ambiguous parcels", amb_links == 0, f"rows={amb_links}")
sw_links = c.execute(
    "SELECT COUNT(*) FROM manual_owner_links WHERE group_id=? "
    "AND source='match_key_sweep'", (SGID,)).fetchone()[0]
check("sweep links carry source=match_key_sweep", sw_links == 2, f"rows={sw_links}")

print(f"\n=== RESULT: {len(passed)} passed, {len(failed)} failed ===")
if failed:
    print("FAILED:", failed)
sys.exit(1 if failed else 0)
