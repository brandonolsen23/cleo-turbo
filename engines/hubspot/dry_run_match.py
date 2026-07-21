"""
M0 dry run — read-only HubSpot ↔ Cleo match pass (spec §2a, build brief Session 1).

This does NOT touch the schema, does NOT write to Cleo, and does NOT write to
HubSpot. It fetches every HubSpot contact via the read-only search API, normalizes
the keys the SAME way Cleo does (reusing Cleo's own fingerprint + phone functions),
matches in memory against the Cleo `contacts` pool using the spec §2a tiers, and
reports the tier counts so Brandon can tune the thresholds before any schema work.

Run (against a COPY of the DB, per guardrail 5):
    cp data/cleo.db /tmp/cleo_test.db
    CLEO_DB_PATH=/tmp/cleo_test.db python -m engines.hubspot.dry_run_match

Requires HUBSPOT_PRIVATE_APP_TOKEN in .env (read-only scopes). If it is missing the
script stops — it never mocks HubSpot data.

Output: printed summary + outputs/hubspot_dry_run_YYYYMMDD.json (NOT committed —
contains real personal contact data; outputs/ is gitignored).
"""

import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

import httpx
from dotenv import load_dotenv

# Reuse Cleo's OWN normalization so the match keys are byte-identical to what the
# compiler stores. Do NOT reimplement these — matching correctness depends on it.
from cleo.compiler.reconciler import make_name_fingerprint
from cleo.atoms.normalize import normalize_phone
from cleo.database.connection import get_connection

# ── Tunable thresholds (this is what the GATE is for — tune after this run) ──────
PHONE_UNIQUE_MAX = 2   # normalized phone on ≤N Cleo contacts → treated as a direct-ish line
PHONE_ONLY_MAX = 3     # phone-only match on ≤N Cleo contacts → review suggestion; above → no suggestion (pure metadata)
TOP_OFFENDERS = 15     # how many switchboard numbers to list

HUBSPOT_BASE = "https://api.hubapi.com"
CONTACT_PROPERTIES = [
    "hs_object_id", "firstname", "lastname", "email",
    "phone", "mobilephone", "jobtitle", "company",
]

_EXT_MARKERS = ("ext", "x", "#", "poste", "extension")


def split_extension(raw):
    """Return the base phone string with any trailing extension removed.

    HubSpot numbers can carry extensions ("416-687-6700 ext 234", "…x12") that would
    otherwise get concatenated into the digit string and break matching. RT numbers
    (Cleo side) are clean, so this only matters for the HubSpot side, but we apply it
    to both for symmetry.
    """
    if not raw:
        return raw
    low = raw.lower()
    cut = len(raw)
    for marker in _EXT_MARKERS:
        idx = low.find(marker)
        # require the marker to sit after some digits so we don't chop a leading 'x'
        if idx > 0 and any(ch.isdigit() for ch in raw[:idx]):
            cut = min(cut, idx)
    return raw[:cut]


def norm_phone(raw):
    """Extension-split then run Cleo's canonical normalize_phone. Returns digits or None."""
    return normalize_phone(split_extension(raw)) if raw else None


def hs_fingerprint(first, last):
    """Cleo-compatible name fingerprint from HubSpot first/last name fields."""
    name = " ".join(p for p in [(first or "").strip(), (last or "").strip()] if p)
    return make_name_fingerprint(name)


# ── HubSpot fetch (read-only search API, paginated) ─────────────────────────────

def fetch_hubspot_contacts(token):
    """Page through every contact via POST /crm/v3/objects/contacts/search.

    Read-only: the search endpoint performs no writes despite the POST verb. Sorted
    by hs_object_id ascending for stable pagination. Retries on 429/5xx.
    """
    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results = []
    after = None
    total = None
    page = 0
    with httpx.Client(timeout=30.0) as client:
        while True:
            body = {
                "limit": 100,
                "properties": CONTACT_PROPERTIES,
                "sorts": [{"propertyName": "hs_object_id", "direction": "ASCENDING"}],
                "filterGroups": [],
            }
            if after:
                body["after"] = after

            for attempt in range(6):
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 200:
                    break
                if resp.status_code in (429, 502, 503, 504):
                    wait = 2 ** attempt
                    print(f"  [{resp.status_code}] backing off {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"HubSpot API error {resp.status_code}: {resp.text[:300]}"
                )
            else:
                raise RuntimeError("HubSpot API: exhausted retries")

            data = resp.json()
            if total is None:
                total = data.get("total")
            results.extend(data.get("results", []))
            page += 1
            print(f"  page {page}: fetched {len(results)}"
                  + (f"/{total}" if total else ""), file=sys.stderr)

            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break
            time.sleep(0.2)  # be gentle on the rate limit

    return results, total


# ── Cleo pool indexes ───────────────────────────────────────────────────────────

def load_cleo_indexes(conn):
    """Build in-memory match indexes over the Cleo contacts pool (read-only)."""
    fp_index = defaultdict(list)      # fingerprint -> [cleo_id]
    phone_index = defaultdict(set)    # normalized phone -> {cleo_id}
    email_index = defaultdict(list)   # lowercased email -> [cleo_id]
    names = {}                        # cleo_id -> display_name (for readable output)

    rows = conn.execute(
        "SELECT id, name_fingerprint, display_name, phone, mobile, email FROM contacts"
    ).fetchall()
    for r in rows:
        cid = r["id"]
        names[cid] = r["display_name"]
        fp = (r["name_fingerprint"] or "").strip()
        if fp:
            fp_index[fp].append(cid)
        for raw in (r["phone"], r["mobile"]):
            ph = norm_phone(raw)
            if ph:
                phone_index[ph].add(cid)
        em = (r["email"] or "").strip().lower()
        if em:
            email_index[em].append(cid)

    phone_count = {ph: len(ids) for ph, ids in phone_index.items()}
    return {
        "pool_size": len(rows),
        "fp_index": fp_index,
        "phone_index": phone_index,
        "phone_count": phone_count,
        "email_index": email_index,
        "names": names,
    }


# ── Matcher (spec §2a tiers) ─────────────────────────────────────────────────────

def classify(hs, idx, hs_fp_counts):
    """Return a classification dict for one prepared HubSpot contact.

    hs: {hs_id, name, fp, phones (set of normalized), email}
    """
    fp = hs["fp"]
    phones = hs["phones"]
    email = hs["email"]
    fp_index = idx["fp_index"]
    phone_index = idx["phone_index"]
    phone_count = idx["phone_count"]
    email_index = idx["email_index"]

    fp_cleo = set(fp_index.get(fp, [])) if fp else set()
    phone_cleo = {cid for ph in phones for cid in phone_index.get(ph, set())}
    email_cleo = email_index.get(email, []) if email else []
    corroborates_rt = bool(phone_cleo)  # any HS phone matches any RT phone

    def out(outcome, tier, reason, target, n=None):
        return {
            "hs_id": hs["hs_id"], "name": hs["name"], "fp": fp,
            "outcome": outcome, "tier": tier, "reason": reason,
            "cleo_target": target, "shared_count": n,
            "corroborates_rt": corroborates_rt,
        }

    # 0. Email exact — near-certain, low yield (only 9 Cleo contacts have email).
    if email_cleo:
        return out("auto_link", "email_exact", None, email_cleo[0])

    # Name-fingerprint present and matches at least one Cleo contact.
    if fp and fp_cleo:
        phone_agree_ids = phone_cleo & fp_cleo  # same person by BOTH name and phone
        if phone_agree_ids:
            # lowest shared-count among the agreeing numbers = strongest signal
            agree_ns = [phone_count[ph] for ph in phones
                        if any(cid in phone_index.get(ph, set()) for cid in fp_cleo)]
            n_best = min(agree_ns)
            if n_best <= PHONE_UNIQUE_MAX:
                # unique-ish phone disambiguates even a fingerprint collision
                return out("auto_link", "tier1", "fp+direct_phone",
                           sorted(phone_agree_ids)[0], n_best)
            # switchboard phone: only auto-link when the fingerprint is unique in the pool
            if len(fp_cleo) == 1:
                return out("auto_link", "tier1", "fp_unique+switchboard_phone",
                           next(iter(fp_cleo)), n_best)
            return out("review", "tier3", "fp_collision_switchboard_phone",
                       sorted(fp_cleo), n_best)

        # Fingerprint matches but no phone agreement on a name candidate.
        phone_conflict = bool(phones) and bool(phone_cleo - fp_cleo)
        if phone_conflict:
            # phone points at a DIFFERENT contact than the name → disagreement
            return out("review", "tier3", "key_disagreement", sorted(fp_cleo | phone_cleo))

        fp_unique_both = (len(fp_cleo) == 1) and (hs_fp_counts[fp] == 1)
        if fp_unique_both:
            return out("auto_link", "tier2", "fp_unique_both_sides", next(iter(fp_cleo)))
        return out("review", "tier3", "fp_collision", sorted(fp_cleo))

    # No name match — consider phone-only.
    if phone_cleo:
        phone_ns = [phone_count[ph] for ph in phones if phone_index.get(ph)]
        n_best = min(phone_ns)
        if n_best <= PHONE_ONLY_MAX:
            return out("review", "tier3", "phone_only_suggestion", sorted(phone_cleo), n_best)
        # switchboard phone-only: pure metadata, NO suggestion (avoids RioCan-line spam)
        return out("no_match", "tier4", "phone_only_switchboard", None, n_best)

    # 4. HubSpot-only — stays in the mirror, invisible to the pool.
    return out("no_match", "tier4", "hubspot_only", None)


# ── Report ───────────────────────────────────────────────────────────────────────

def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        print("ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set in .env — stopping (never mock).",
              file=sys.stderr)
        sys.exit(1)

    conn = get_connection()
    db_path = conn.execute("PRAGMA database_list").fetchone()["file"]
    print(f"Cleo DB: {db_path}", file=sys.stderr)
    print("Loading Cleo contact indexes...", file=sys.stderr)
    idx = load_cleo_indexes(conn)
    print(f"  Cleo pool: {idx['pool_size']:,} contacts, "
          f"{len(idx['fp_index']):,} distinct fingerprints, "
          f"{len(idx['phone_index']):,} distinct normalized phones", file=sys.stderr)

    print("Fetching HubSpot contacts (read-only search API)...", file=sys.stderr)
    raw, portal_total = fetch_hubspot_contacts(token)
    print(f"  Fetched {len(raw):,} HubSpot contacts (portal total: {portal_total})",
          file=sys.stderr)

    # Prepare + precompute HubSpot fingerprint frequencies (for "unique both sides").
    prepared = []
    hs_fp_counts = Counter()
    for rec in raw:
        p = rec.get("properties", {})
        fp = hs_fingerprint(p.get("firstname"), p.get("lastname"))
        phones = set()
        for f in ("phone", "mobilephone"):
            ph = norm_phone(p.get(f))
            if ph:
                phones.add(ph)
        email = (p.get("email") or "").strip().lower() or None
        name = " ".join(x for x in [p.get("firstname"), p.get("lastname")] if x) or "(no name)"
        prepared.append({
            "hs_id": rec.get("id"), "name": name, "fp": fp,
            "phones": phones, "email": email,
        })
        if fp:
            hs_fp_counts[fp] += 1

    # Classify.
    classifications = [classify(hs, idx, hs_fp_counts) for hs in prepared]

    # Tally.
    tier_counts = Counter(c["tier"] for c in classifications)
    outcome_counts = Counter(c["outcome"] for c in classifications)
    review_reasons = Counter(c["reason"] for c in classifications if c["outcome"] == "review")
    auto_tiers = Counter(c["tier"] for c in classifications if c["outcome"] == "auto_link")
    phone_only_suggestions = sum(1 for c in classifications if c["reason"] == "phone_only_suggestion")
    hubspot_only = sum(1 for c in classifications if c["reason"] == "hubspot_only")
    phone_only_switchboard = sum(1 for c in classifications if c["reason"] == "phone_only_switchboard")
    corroborated = sum(1 for c in classifications if c["corroborates_rt"])
    # distinct RT numbers validated by a HubSpot number:
    corroborated_numbers = set()
    hs_phone_set = set()
    for hs in prepared:
        hs_phone_set |= hs["phones"]
    for ph in hs_phone_set:
        if ph in idx["phone_index"]:
            corroborated_numbers.add(ph)

    top_offenders = sorted(idx["phone_count"].items(), key=lambda kv: -kv[1])[:TOP_OFFENDERS]

    total_auto = outcome_counts["auto_link"]
    total_review = outcome_counts["review"]

    # ── Printed summary ───────────────────────────────────────────────────────
    line = "=" * 66
    print("\n" + line)
    print("HubSpot → Cleo  M0 DRY RUN  (read-only, no schema changes)")
    print(line)
    print(f"HubSpot contacts fetched : {len(prepared):,}")
    print(f"Cleo contact pool        : {idx['pool_size']:,}  (unchanged — dry run links nothing)")
    print(f"Thresholds               : PHONE_UNIQUE_MAX={PHONE_UNIQUE_MAX}  PHONE_ONLY_MAX={PHONE_ONLY_MAX}")
    print(line)
    print("AUTO-LINK (would link automatically)")
    print(f"  Tier 1  fp + phone agrees        : {auto_tiers['tier1']:,}")
    print(f"  Tier 2  fp unique both sides     : {auto_tiers['tier2']:,}")
    print(f"  Email exact (bonus key)          : {auto_tiers['email_exact']:,}")
    print(f"  ── auto-link total               : {total_auto:,}")
    print(line)
    print(f"REVIEW QUEUE (needs a human)        : {total_review:,}")
    for reason, n in review_reasons.most_common():
        print(f"    {reason:<32}: {n:,}")
    print(line)
    print("PHONE-ONLY")
    print(f"  Suggestions (≤{PHONE_ONLY_MAX} shared)            : {phone_only_suggestions:,}   (surface on card)")
    print(f"  Switchboard, no suggestion       : {phone_only_switchboard:,}   (pure metadata, suppressed)")
    print(line)
    print("NO CLEO MATCH")
    print(f"  HubSpot-only (name+phone miss)   : {hubspot_only:,}")
    print(f"  ── total invisible-to-pool       : {outcome_counts['no_match']:,}")
    print(line)
    print("CORROBORATION (spec §2b — validates RT phones)")
    print(f"  HubSpot contacts w/ RT-matching # : {corroborated:,}")
    print(f"  Distinct RT numbers validated     : {len(corroborated_numbers):,}")
    print(line)
    print(f"TOP {TOP_OFFENDERS} SHARED-NUMBER OFFENDERS (Cleo pool — switchboards)")
    for ph, n in top_offenders:
        print(f"    {ph:<14}: {n:,} contacts")
    print(line)
    print("NOTE: fuzzy-near-name review candidates are NOT computed in this pass")
    print("      (exact fingerprint + phone only). Add if the gate wants them.")
    print(line + "\n")

    # ── JSON artifact ─────────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.abspath(os.path.join(out_dir, f"hubspot_dry_run_{stamp}.json"))
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cleo_db": db_path,
        "thresholds": {"PHONE_UNIQUE_MAX": PHONE_UNIQUE_MAX, "PHONE_ONLY_MAX": PHONE_ONLY_MAX},
        "hubspot_contacts_fetched": len(prepared),
        "hubspot_portal_total": portal_total,
        "cleo_pool_size": idx["pool_size"],
        "cleo_distinct_fingerprints": len(idx["fp_index"]),
        "cleo_distinct_phones": len(idx["phone_index"]),
        "summary": {
            "auto_link_total": total_auto,
            "auto_link_by_tier": dict(auto_tiers),
            "review_total": total_review,
            "review_by_reason": dict(review_reasons),
            "phone_only_suggestions": phone_only_suggestions,
            "phone_only_switchboard_suppressed": phone_only_switchboard,
            "hubspot_only": hubspot_only,
            "no_match_total": outcome_counts["no_match"],
            "corroborated_hs_contacts": corroborated,
            "corroborated_rt_numbers": len(corroborated_numbers),
        },
        "top_shared_number_offenders": [{"phone": ph, "count": n} for ph, n in top_offenders],
        "classifications": classifications,
    }
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
