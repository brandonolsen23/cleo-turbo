"""Dry-run report for the proposed contact honorific-stripping merge.

Read-only. Computes what migration 021 would do without writing anything.

Output:
    docs/superpowers/run-notes/2026-05-06-honorific-merge-dryrun.md
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = "data/cleo.db"
REPORT_PATH = "docs/superpowers/run-notes/2026-05-06-honorific-merge-dryrun.md"

LEADING_HONORIFICS = {
    # Excludes "HON" — appears as a Chinese given name (e.g., "Hon Lam"), so
    # only strip the explicit "HON." / "HONOURABLE" forms which are unambiguous.
    "DR", "DR.", "MR", "MR.", "MRS", "MRS.",
    "MS", "MS.", "MISS",
    "PROF", "PROF.", "PROFESSOR",
    "HON.", "HONOURABLE",
    "SIR", "MADAM", "MADAME", "DAME",
    "REV", "REV.", "REVEREND", "FATHER", "FR", "FR.",
    "LORD", "LADY", "MX", "MX.",
}


def make_name_fingerprint_new(name: str) -> str:
    if not name:
        return ""
    tokens = name.upper().split()
    while tokens and tokens[0] in LEADING_HONORIFICS:
        tokens = tokens[1:]
    return " ".join(tokens)


def con_id_num(con_id: str) -> int:
    return int(con_id.split("_")[1])


def crm_counts(conn: sqlite3.Connection, con_id: str) -> dict:
    q = lambda s, *p: conn.execute(s, p).fetchone()[0]
    return {
        "txn_parties": q("SELECT COUNT(*) FROM transaction_parties WHERE contact_id=?", con_id),
        "notes":       q("SELECT COUNT(*) FROM contact_notes WHERE contact_id=?", con_id),
        "activities":  q(
            "SELECT COUNT(*) FROM activities WHERE contact_id=? OR (entity_type='contact' AND entity_id=?)",
            con_id, con_id,
        ),
        "stars":       q("SELECT COUNT(*) FROM user_stars WHERE entity_type='contact' AND entity_id=?", con_id),
        "list_memb":   q("SELECT COUNT(*) FROM list_members WHERE member_type='contact' AND member_id=?", con_id),
        "group_links": q("SELECT COUNT(*) FROM group_contacts WHERE contact_id=?", con_id),
        "buy_mand":    q("SELECT COUNT(*) FROM buy_mandates WHERE contact_id=?", con_id),
        "overrides":   q("SELECT COUNT(*) FROM contact_field_overrides WHERE contact_id=?", con_id),
        "work_hist":   q("SELECT COUNT(*) FROM contact_work_history WHERE contact_id=?", con_id),
    }


def shared_groups(conn: sqlite3.Connection, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        WITH per AS (
          SELECT contact_id AS cid, group_id FROM group_contacts WHERE contact_id IN ({placeholders})
          UNION
          SELECT c.id AS cid, c.current_group_id AS group_id
          FROM contacts c
          WHERE c.id IN ({placeholders}) AND c.current_group_id IS NOT NULL
        )
        SELECT group_id, COUNT(DISTINCT cid) AS n FROM per WHERE group_id IS NOT NULL GROUP BY group_id HAVING n > 1
        """,
        (*ids, *ids),
    ).fetchall()
    return {r[0] for r in rows}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    contacts = conn.execute(
        """
        SELECT id, display_name, first_name, last_name, name_fingerprint,
               phone, transaction_count, current_group_id,
               first_seen_date, last_seen_date
        FROM contacts
        """
    ).fetchall()

    by_new_fp: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for c in contacts:
        new_fp = make_name_fingerprint_new(c["display_name"])
        if not new_fp:
            continue
        by_new_fp[new_fp].append(c)

    collisions = {fp: rows for fp, rows in by_new_fp.items() if len(rows) >= 2}

    merges: list[dict] = []
    for new_fp, rows in collisions.items():
        canonical = [r for r in rows if r["name_fingerprint"] == new_fp]
        if canonical:
            winner = min(canonical, key=lambda r: con_id_num(r["id"]))
            tiebreaker = "canonical-already-clean"
        else:
            winner = min(rows, key=lambda r: con_id_num(r["id"]))
            tiebreaker = "lowest-CON_ID (no canonical)"
        losers = [r for r in rows if r["id"] != winner["id"]]
        all_ids = [winner["id"]] + [l["id"] for l in losers]
        sg = shared_groups(conn, all_ids)
        winner_phone = (winner["phone"] or "").strip()
        any_phone_match = any((l["phone"] or "").strip() == winner_phone and winner_phone for l in losers)
        merges.append({
            "new_fp": new_fp,
            "tiebreaker": tiebreaker,
            "winner": dict(winner),
            "winner_counts": crm_counts(conn, winner["id"]),
            "losers": [{"row": dict(l), "counts": crm_counts(conn, l["id"])} for l in losers],
            "shared_groups": sorted(sg),
            "any_phone_match": any_phone_match,
        })

    singletons_renamed: list[dict] = []
    for new_fp, rows in by_new_fp.items():
        if len(rows) == 1:
            r = rows[0]
            if r["name_fingerprint"] != new_fp:
                singletons_renamed.append({
                    "new_fp": new_fp,
                    "old_fp": r["name_fingerprint"],
                    "id": r["id"],
                    "display_name": r["display_name"],
                })

    out: list[str] = []
    out.append("# Honorific Merge — Dry Run Report")
    out.append("")
    out.append(f"- DB: `{DB_PATH}`")
    out.append(f"- Generated: 2026-05-06")
    out.append(f"- Total contacts: {len(contacts):,}")
    out.append(f"- New-fingerprint groups with >=2 contacts: **{len(merges)}**")
    out.append(f"- Total losers (will redirect + delete): **{sum(len(m['losers']) for m in merges)}**")
    out.append(f"- Singletons whose fingerprint just changes (no merge): **{len(singletons_renamed)}**")
    out.append("")

    no_phone_no_group = [m for m in merges if not m["any_phone_match"] and not m["shared_groups"]]
    out.append(f"### Suspicious cases (no shared phone AND no shared group): **{len(no_phone_no_group)}**")
    out.append("These should be reviewed extra carefully — there's no signal that they're the same person beyond the name.")
    out.append("")

    out.append("## Proposed merges")
    out.append("")
    out.append("| New fingerprint | Winner (CON_ID · name · txns) | Losers (CON_ID · name · txns) | Shared phone? | Shared group? | Tiebreaker |")
    out.append("|---|---|---|---|---|---|")
    for m in merges:
        w = m["winner"]
        wsum = f"{w['id']} · {w['display_name']} · txns:{w['transaction_count']}"
        lsums = "<br>".join(
            f"{lo['row']['id']} · {lo['row']['display_name']} · txns:{lo['row']['transaction_count']}"
            for lo in m["losers"]
        )
        phone = "yes" if m["any_phone_match"] else "no"
        groups = "yes" if m["shared_groups"] else "no"
        out.append(f"| `{m['new_fp']}` | {wsum} | {lsums} | {phone} | {groups} | {m['tiebreaker']} |")
    out.append("")

    out.append("## Per-merge CRM data counts")
    out.append("")
    out.append("Counts for tables that would be redirected (so you can see if the survivor inherits everything correctly).")
    out.append("Format: `txn_parties / notes / activities / stars / list_memb / group_links / buy_mand / overrides / work_hist`")
    out.append("")
    for m in merges:
        w = m["winner"]
        wc = m["winner_counts"]
        out.append(f"### `{m['new_fp']}`")
        out.append("")
        out.append(f"- **Winner** {w['id']} ({w['display_name']}): "
                   f"{wc['txn_parties']} / {wc['notes']} / {wc['activities']} / {wc['stars']} / "
                   f"{wc['list_memb']} / {wc['group_links']} / {wc['buy_mand']} / "
                   f"{wc['overrides']} / {wc['work_hist']}")
        for lo in m["losers"]:
            r = lo["row"]
            c = lo["counts"]
            out.append(f"- Loser   {r['id']} ({r['display_name']}): "
                       f"{c['txn_parties']} / {c['notes']} / {c['activities']} / {c['stars']} / "
                       f"{c['list_memb']} / {c['group_links']} / {c['buy_mand']} / "
                       f"{c['overrides']} / {c['work_hist']}")
        if m["shared_groups"]:
            out.append(f"- Shared groups: {', '.join(m['shared_groups'][:5])}"
                       + ("…" if len(m["shared_groups"]) > 5 else ""))
        out.append("")

    out.append("## Singletons (fingerprint cleaned in-place, no merge)")
    out.append("")
    out.append(f"{len(singletons_renamed)} contacts. Just an `id_mappings.anchor_key` rename + `contacts.first_name/last_name/name_fingerprint` rewrite. CON_ID preserved.")
    out.append("")
    if singletons_renamed:
        out.append("Sample (first 25):")
        out.append("")
        out.append("| CON_ID | display_name | old fingerprint | new fingerprint |")
        out.append("|---|---|---|---|")
        for s in singletons_renamed[:25]:
            out.append(f"| {s['id']} | {s['display_name']} | `{s['old_fp']}` | `{s['new_fp']}` |")
        out.append("")

    Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(REPORT_PATH).write_text("\n".join(out))

    print(f"Wrote {REPORT_PATH}")
    print(f"Merges: {len(merges)} (losers: {sum(len(m['losers']) for m in merges)})")
    print(f"Singleton renames: {len(singletons_renamed)}")
    print(f"Suspicious (no phone + no group): {len(no_phone_no_group)}")


if __name__ == "__main__":
    main()
