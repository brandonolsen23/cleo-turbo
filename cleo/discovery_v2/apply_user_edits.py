"""Stage Z: Apply user edits as the final say.

Runs LAST in the discovery_v2 pipeline, after all algorithmic stages
(seeding, expansion, standalone coverage, display + counts, legacy map).
Reads `auto_group_user_edits WHERE is_active = 1` in chronological order
and re-applies each edit so manual assertions survive every rebuild.

Edit types:
- detach: remove (source_id, side) from auto_group_id. Party-side falls back
  to its standalone auto_group (or another active attach edit if any).
- attach: remove existing membership for (source_id, side) across all groups,
  insert into target auto_group_id.
- rename: override `auto_groups.display_name` for auto_group_id.
- merge: move all members of source auto_group_id into target_auto_group_id;
  mark source as tier='merged'.
- split: not implemented in this iteration; we'll handle as needed.
- create: ensure the auto_group exists (idempotency safety — POST endpoint
  should have already created it).

User edits also set `auto_group_members.attached_by = 'user_edit'` on every
row they write so the UI can distinguish them.
"""
from __future__ import annotations
import sqlite3


def apply_user_edits(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Re-apply every active user edit, in chronological order."""
    counts = {
        'n_detach': 0,
        'n_attach': 0,
        'n_rename': 0,
        'n_merge': 0,
        'n_create': 0,
        'n_set_address': 0,
        'n_set_website': 0,
        'n_set_phone': 0,
    }

    edits = list(conn.execute(
        "SELECT id, edit_type, auto_group_id, source_id, side, "
        "       target_auto_group_id, new_display_name, new_canonical_stem, "
        "       new_primary_address, new_website, new_primary_phone "
        "FROM auto_group_user_edits "
        "WHERE is_active = 1 ORDER BY id ASC"
    ))

    for e in edits:
        edit_type = e['edit_type']
        agid = e['auto_group_id']

        if edit_type == 'create':
            # Ensure auto_group row exists
            existing = conn.execute(
                "SELECT 1 FROM auto_groups WHERE auto_group_id = ?", (agid,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO auto_groups "
                    "(auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members) "
                    "VALUES (?, ?, ?, 'standalone', 1.0, 0, 0)",
                    (agid, e['new_canonical_stem'] or agid, e['new_display_name'] or agid),
                )
            counts['n_create'] += 1

        elif edit_type == 'rename':
            if e['new_display_name']:
                conn.execute(
                    "UPDATE auto_groups SET display_name = ? WHERE auto_group_id = ?",
                    (e['new_display_name'], agid),
                )
            counts['n_rename'] += 1

        elif edit_type == 'detach':
            conn.execute(
                "DELETE FROM auto_group_members "
                "WHERE auto_group_id = ? AND source_id = ? AND side = ? AND member_type = 'party_side'",
                (agid, e['source_id'], e['side']),
            )
            counts['n_detach'] += 1
            # NOTE: The fallback to a standalone group happens naturally on the
            # next discovery_v2 run via standalone_coverage. If we want immediate
            # fallback here we'd need to look up the legacy group's standalone
            # auto_group. For now we let the next rebuild handle it.

        elif edit_type == 'attach':
            # Remove from any prior groups; insert into the target
            target = e['target_auto_group_id'] or agid
            conn.execute(
                "DELETE FROM auto_group_members "
                "WHERE source_id = ? AND side = ? AND member_type = 'party_side'",
                (e['source_id'], e['side']),
            )
            conn.execute(
                "INSERT OR IGNORE INTO auto_group_members "
                "(auto_group_id, member_type, source_id, side, corp_name, match_score, attached_by) "
                "VALUES (?, 'party_side', ?, ?, NULL, 1.0, 'user_edit')",
                (target, e['source_id'], e['side']),
            )
            counts['n_attach'] += 1

        elif edit_type == 'merge':
            target = e['target_auto_group_id']
            if not target:
                continue
            # Move every member of source → target (avoid UNIQUE collisions with OR IGNORE)
            conn.execute(
                "INSERT OR IGNORE INTO auto_group_members "
                "(auto_group_id, member_type, source_id, side, corp_name, match_score, attached_by) "
                "SELECT ?, member_type, source_id, side, corp_name, match_score, 'user_edit' "
                "FROM auto_group_members WHERE auto_group_id = ?",
                (target, agid),
            )
            conn.execute("DELETE FROM auto_group_members WHERE auto_group_id = ?", (agid,))
            # Mark source as merged so it doesn't show in the active group list
            conn.execute(
                "UPDATE auto_groups SET tier = 'merged' WHERE auto_group_id = ?",
                (agid,),
            )
            counts['n_merge'] += 1

        elif edit_type == 'set_address':
            if e['new_primary_address']:
                conn.execute(
                    "UPDATE auto_groups SET primary_address = ?, primary_address_source = 'manual' "
                    "WHERE auto_group_id = ?",
                    (e['new_primary_address'], agid),
                )
                # Confirmed addresses become identity anchors so future RT
                # transactions with this mailing address auto-attach.
                conn.execute(
                    "INSERT OR REPLACE INTO auto_group_anchors "
                    "(auto_group_id, anchor_type, anchor_value, score) VALUES (?, 'address_unit', ?, 5.0)",
                    (agid, e['new_primary_address']),
                )
            counts['n_set_address'] += 1

        elif edit_type == 'set_website':
            if e['new_website']:
                conn.execute(
                    "UPDATE auto_groups SET website = ? WHERE auto_group_id = ?",
                    (e['new_website'], agid),
                )
            counts['n_set_website'] += 1

        elif edit_type == 'set_phone':
            if e['new_primary_phone']:
                # Normalise to digits-only for anchor key (matches party_fingerprints.phone)
                digits = ''.join(c for c in e['new_primary_phone'] if c.isdigit())
                conn.execute(
                    "UPDATE auto_groups SET primary_phone = ? WHERE auto_group_id = ?",
                    (e['new_primary_phone'], agid),
                )
                if digits:
                    conn.execute(
                        "INSERT OR REPLACE INTO auto_group_anchors "
                        "(auto_group_id, anchor_type, anchor_value, score) VALUES (?, 'phone', ?, 5.0)",
                        (agid, digits),
                    )
            counts['n_set_phone'] += 1

    # Recompute n_members for any group that was touched
    conn.execute("""
        UPDATE auto_groups SET n_members = COALESCE((
            SELECT COUNT(*) FROM auto_group_members
            WHERE auto_group_id = auto_groups.auto_group_id
        ), 0)
    """)

    conn.commit()

    if verbose:
        total = sum(counts.values())
        if total == 0:
            print('  Stage Z (apply_user_edits): no active edits.', flush=True)
        else:
            summary = ', '.join(f'{k}={v}' for k, v in counts.items() if v)
            print(f'  Stage Z (apply_user_edits): applied {total} edit(s) — {summary}.', flush=True)

    return {f'n_user_edits_{k}': v for k, v in counts.items()}
