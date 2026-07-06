"""
Group ID minting for Portfolio Capture (M2).

Mirrors the AGRP_ pattern used by discovery_v2, but for the canonical
GRP_ namespace used by the groups table. The reconciler mints GRP_ ids
for compiler-derived groups; this helper mints the NEXT id for groups
created by the capture endpoint so the two never collide (both key off
the max numeric suffix present in the table).
"""


def _next_group_id(conn) -> str:
    """Return the next unused GRP_##### id.

    Selects the max numeric suffix from groups.id LIKE 'GRP_%' and returns
    f'GRP_{n+1:05d}'. The underscore is escaped so LIKE does not treat it
    as a single-char wildcard (would otherwise match AGRP-style ids too).
    """
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) FROM groups "
        "WHERE id LIKE 'GRP\\_%' ESCAPE '\\'"
    ).fetchone()
    n = row[0] if row and row[0] is not None else 0
    # The compiler also mints GRP_ ids from the app_meta 'next_grp_id'
    # counter. Take whichever is higher, and bump the counter past the id
    # we hand out so the two allocators never collide.
    meta = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'next_grp_id'"
    ).fetchone()
    if meta and meta[0] is not None:
        try:
            n = max(n, int(meta[0]) - 1)
        except (TypeError, ValueError):
            pass
    nxt = n + 1
    conn.execute(
        "UPDATE app_meta SET value = ?, updated_at = datetime('now') "
        "WHERE key = 'next_grp_id'",
        (str(nxt + 1),),
    )
    return f"GRP_{nxt:05d}"
