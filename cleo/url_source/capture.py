"""
URL source — capture orchestrator (url-source-spec.md §5-§6).

One URL in -> {group, properties[]} out. If the URL is a portfolio/index page,
discover the individual property pages and extract each; if it is a single
property page, extract it directly. The group profile (contract extension,
keyed by GRP_) is attached once and every property links to it.
"""
from __future__ import annotations

from .extract import extract_from_url, MODEL
from .discover import discover_from_url


def _dedupe_urls(items):
    seen, out = set(), []
    for it in items:
        u = (it.get("url") or "").strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def capture_portfolio(url: str, max_properties: int | None = None, model: str = MODEL) -> dict:
    """Discover + extract a whole portfolio from one URL.

    max_properties caps how many property pages are visited (for cheap proofs);
    None processes every discovered property. Any capped/failed pages are
    reported honestly in `discovery` rather than silently dropped.
    """
    disc = discover_from_url(url, model=model)
    group = disc.get("group") or {}

    # Single property page: extract directly, reconcile shape.
    if not disc.get("is_list_page"):
        one = extract_from_url(url, model=model)
        props = one.get("properties", [])
        for p in props:
            p["_source_url"] = url
        # Prefer the richer group from the property extraction if discovery was thin.
        group = group or one.get("group") or {}
        return {
            "group": group,
            "properties": props,
            "discovery": {"is_list_page": False, "total_found": len(props),
                          "processed": len(props), "skipped": 0,
                          "about_url": disc.get("about_url"),
                          "site_structure_notes": disc.get("site_structure_notes")},
        }

    all_urls = _dedupe_urls(disc.get("property_urls", []))
    total = len(all_urls)
    urls = all_urls[:max_properties] if max_properties else all_urls

    properties, errors = [], 0
    for u in urls:
        try:
            r = extract_from_url(u, model=model)
            for p in r.get("properties", []):
                p["_source_url"] = u
                # Attach the portfolio group to each property when the property
                # page did not name its own owner.
                own = p.setdefault("ownership", {}) or {}
                if not own.get("relationship"):
                    own["relationship"] = "owns"
                    own["reasoning"] = (own.get("reasoning") or
                                        f"listed on {group.get('canonical_name') or 'portfolio'} index page")
                p["ownership"] = own
                properties.append(p)
        except Exception as exc:  # noqa: BLE001 — one bad page must not sink the run
            errors += 1
            properties.append({"_source_url": u, "_error": str(exc)})

    return {
        "group": group,
        "properties": properties,
        "discovery": {
            "is_list_page": True,
            "total_found": total,
            "processed": len(urls),
            "skipped": max(0, total - len(urls)),
            "errors": errors,
            "about_url": disc.get("about_url"),
            "site_structure_notes": disc.get("site_structure_notes"),
        },
    }
