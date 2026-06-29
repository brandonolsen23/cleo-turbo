"""
Milestone 1 acceptance tests for Portfolio Capture.

Runs ONLY against a copy of cleo.db passed on the command line. Proves:
  T1  a captured 'owns' link FILLS a dark property's owner group.
  T3  a captured link does NOT overwrite a Realtrack-derived owner; it is
      flagged status='conflict' and logged to data_issues.
  T2  CRM data survives drop_derived_tables(), and the override pass
      RE-DERIVES the owner after a rebuild wipes the derived row.
      (Runs LAST because it is destructive to the derived tables.)

Usage: python test_portfolio_capture_m1.py /tmp/cleo_test.db
"""
import sqlite3, sys

sys.path.insert(0, "/sessions/friendly-exciting-albattani/mnt/cleo-turbo")
from cleo.database.schema import create_all_tables, drop_derived_tables
from cleo.compiler.owner_overrides import apply_owner_overrides

DARK_ARN = "25180403410642000000"   # PRO_76572, 1900 King St E Metro
ROSART = "GRP_50676"

db = sys.argv[1]
assert "cleo_test" in db or "/tmp/" in db, "refusing to run on a non-copy path"
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

# ---- seed sanity ----
print("\n=== seed verification ===")
p = c.execute("SELECT id, arn, current_owner_group_id, current_owner_name, transaction_count "
              "FROM properties WHERE arn=?", (DARK_ARN,)).fetchone()
check("dark Metro PRO_76572 present", p is not None and p["id"] == "PRO_76572",
      f'id={p["id"] if p else None}')
check("dark Metro has no RT transactions (tx_count=0)", p and (p["transaction_count"] or 0) == 0,
      f'tx_count={p["transaction_count"] if p else None}')
g = c.execute("SELECT id, display_name FROM groups WHERE id=?", (ROSART,)).fetchone()
check("Rosart group GRP_50676 present", g is not None, g["display_name"] if g else "missing")
gname = g["display_name"] if g else "Rosart Properties Inc"

# ---- T1: fill a dark property ----
print("\n=== T1: captured link fills a dark owner ===")
c.execute("INSERT INTO manual_owner_links (arn, group_id, relationship, source) "
          "VALUES (?,?, 'owns','test')", (DARK_ARN, ROSART))
c.commit()
stats = apply_owner_overrides(c, verbose=False)
p = c.execute("SELECT current_owner_group_id, current_owner_name FROM properties WHERE arn=?",
              (DARK_ARN,)).fetchone()
link = c.execute("SELECT status, property_id FROM manual_owner_links WHERE arn=?", (DARK_ARN,)).fetchone()
check("override filled owner group = GRP_50676", p["current_owner_group_id"] == ROSART,
      f'now={p["current_owner_group_id"]}')
check("link active + property_id cached", link["status"] == "active" and link["property_id"] == "PRO_76572",
      f'status={link["status"]} pid={link["property_id"]}')
check("stats.filled == 1", stats["filled"] == 1, str(stats))

# ---- T3: conflict with an RT-derived owner (runs on real data, before the destructive T2) ----
print("\n=== T3: does NOT overwrite a Realtrack-derived owner ===")
rt = c.execute("SELECT id, arn, current_owner_group_id, current_owner_name "
               "FROM properties WHERE transaction_count > 0 AND current_owner_group_id IS NOT NULL "
               "AND arn IS NOT NULL AND arn != '' LIMIT 1").fetchone()
other = None
if rt:
    other = c.execute("SELECT id FROM groups WHERE id != ? LIMIT 1",
                      (rt["current_owner_group_id"],)).fetchone()
check("found an RT-owned property + a different group", rt is not None and other is not None,
      f'prop={rt["id"] if rt else None} rt_owner={rt["current_owner_group_id"] if rt else None}')
if rt and other:
    c.execute("INSERT INTO manual_owner_links (arn, group_id, relationship, source) VALUES (?,?, 'owns','test')",
              (rt["arn"], other["id"]))
    c.commit()
    stats3 = apply_owner_overrides(c, scope_arns=[rt["arn"]], verbose=False)
    after = c.execute("SELECT current_owner_group_id FROM properties WHERE id=?", (rt["id"],)).fetchone()
    link3 = c.execute("SELECT status, conflict_note FROM manual_owner_links WHERE arn=? AND group_id=?",
                      (rt["arn"], other["id"])).fetchone()
    issue = c.execute("SELECT COUNT(*) FROM data_issues WHERE rule='manual_owner_conflict' "
                      "AND source_id=? AND status='open'", (rt["id"],)).fetchone()[0]
    check("RT owner NOT overwritten", after["current_owner_group_id"] == rt["current_owner_group_id"],
          f'still={after["current_owner_group_id"]}')
    check("link flagged status=conflict", link3["status"] == "conflict", f'status={link3["status"]}')
    check("data_issues conflict logged", issue == 1, f'issues={issue}')
    check("stats.conflicts == 1", stats3["conflicts"] == 1, str(stats3))

# ---- T2 (destructive, LAST): survive rebuild + re-derive ----
print("\n=== T2: survives drop_derived_tables + re-derives after rebuild ===")
drop_derived_tables(c)
link_after_drop = c.execute("SELECT COUNT(*) FROM manual_owner_links WHERE arn=?", (DARK_ARN,)).fetchone()[0]
check("manual_owner_links survives drop_derived_tables", link_after_drop == 1, f"rows={link_after_drop}")
# recreate derived tables (as a real compile does) and simulate the rebuilt DARK property + group
create_all_tables(c)
c.execute("INSERT INTO groups (id, display_name, normalized_name) VALUES (?,?,?)",
          (ROSART, gname, "rosart_test_norm"))
c.execute("INSERT INTO properties (id, arn, display_address, transaction_count, current_owner_name) "
          "VALUES ('PRO_76572', ?, '', 0, 'KING ROSE G.P. INC')", (DARK_ARN,))
c.commit()
pre = c.execute("SELECT current_owner_group_id FROM properties WHERE arn=?", (DARK_ARN,)).fetchone()
apply_owner_overrides(c, verbose=False)
post = c.execute("SELECT current_owner_group_id, current_owner_name FROM properties WHERE arn=?",
                 (DARK_ARN,)).fetchone()
check("owner dark immediately after rebuild", pre["current_owner_group_id"] in (None, ""),
      f'pre={pre["current_owner_group_id"]}')
check("override RE-DERIVED owner after rebuild", post["current_owner_group_id"] == ROSART,
      f'post={post["current_owner_group_id"]}')
check("GW registry owner name preserved", post["current_owner_name"] == "KING ROSE G.P. INC",
      f'name={post["current_owner_name"]}')

print(f"\n=== RESULT: {len(passed)} passed, {len(failed)} failed ===")
if failed:
    print("FAILED:", failed)
sys.exit(1 if failed else 0)
