"""
GeoWarehouse HTML Parser -- extracts property data from saved GW detail pages.

Uses stable Angular HTML id attributes for extraction. Improvements over V3:
  - Captures ALL ARNs on multi-parcel properties (find_all, not find)
  - Adds has_mpac_data and is_active quality flags
  - Deduplicates by PIN (keeps newest timestamp per PIN)

Input:  engines/gw/pipeline/html/*.html
Output: engines/gw/pipeline/parsed/{GW_ID}.json

Usage:
    python engines/gw/parse.py
    python engines/gw/parse.py --dry-run
    python engines/gw/parse.py --limit 10
"""

import json
import os
import re
import sys
import argparse

from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

HTML_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'html')
PARSED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parsed')


# ================================================================
# HTML extraction helpers
# ================================================================

def _get_text(soup, element_id):
    """Find element by id, return stripped text or empty string."""
    el = soup.find(id=element_id)
    if el is None:
        return ""
    return el.get_text(strip=True)


def _get_text_within(parent, element_id):
    """Find element by id within a parent element."""
    el = parent.find(id=element_id)
    if el is None:
        return ""
    return el.get_text(strip=True)


# ================================================================
# Section parsers
# ================================================================

def _parse_summary(soup):
    """Extract fields from the summary section (sum-* IDs)."""
    return {
        "address": _get_text(soup, "sum-h1-address"),
        "owner_names": _get_text(soup, "sum-owner-names"),
        "last_sale_price": _get_text(soup, "sum-lastsale-value"),
        "last_sale_date": _get_text(soup, "sum-lastsale-date"),
        "lot_size_area": _get_text(soup, "sum-lotsize-area"),
        "lot_size_perimeter": _get_text(soup, "sum-lotsize-perimeter"),
        "party_to": _get_text(soup, "sum-partyto-value"),
        "legal_description": _get_text(soup, "sum-legal-desc"),
    }


def _parse_registry(soup):
    """Extract fields from the registry section (reg-* IDs)."""
    return {
        "gw_address": _get_text(soup, "reg-gw-address"),
        "land_registry_office": _get_text(soup, "reg-lro"),
        "owner_names": _get_text(soup, "reg-on"),
        "ownership_type": _get_text(soup, "reg-ot"),
        "land_registry_status": _get_text(soup, "reg-lrs"),
        "property_type": _get_text(soup, "reg-pt"),
        "registration_type": _get_text(soup, "reg-rt"),
        "pin": _get_text(soup, "reg-pin"),
    }


def _parse_assessment(soup, arn_el):
    """Extract a single assessment record from an ARN element and its suffix."""
    arn_text = arn_el.get_text(strip=True)
    arn = arn_text.removeprefix("ARN :").strip() or arn_text

    suffix = arn_el["id"].removeprefix("ss-an-arn-")

    return {
        "arn": arn,
        "frontage": _get_text(soup, f"ss-site-frontage-{suffix}"),
        "zoning": _get_text(soup, f"ss-site-sa-{suffix}"),
        "depth": _get_text(soup, f"ss-site-depth-{suffix}"),
        "property_description": _get_text(soup, f"ss-struct-pd-{suffix}"),
        "property_code": _get_text(soup, f"ss-struct-pc-{suffix}"),
        "assessed_value": _get_text(soup, f"ss-ad-cav-{suffix}"),
        "valuation_date": _get_text(soup, f"ss-ad-vd-{suffix}"),
        "legal_description": _get_text(soup, f"ss-msed-ld-{suffix}"),
        "site_area": _get_text(soup, f"ss-msed-sa-{suffix}"),
        "property_address": _get_text(soup, f"ss-msap-pa-{suffix}"),
        "municipality": _get_text(soup, f"ss-msap-muni-{suffix}"),
        "owner_names_mpac": _get_text(soup, f"ss-msap-on-{suffix}"),
        "owner_mailing_address": _get_text(soup, f"ss-msap-oma-{suffix}"),
    }


def _parse_all_assessments(soup):
    """Extract ALL assessment records (multi-parcel support)."""
    arn_elements = soup.find_all(id=re.compile(r"^ss-an-arn-"))
    if not arn_elements:
        return []
    return [_parse_assessment(soup, el) for el in arn_elements]


def _parse_sales_history(soup):
    """Extract the sales history table rows."""
    rows = []

    for el in soup.find_all(id=re.compile(r"^vs-tbl-row-")):
        row_id = el.get("id", "")
        if row_id == "vs-tbl-row-hdr":
            continue

        date_suffix = row_id.removeprefix("vs-tbl-row-")

        sale_date = _get_text_within(el, f"vs-tbl-data-sd-{date_suffix}")
        sale_amount = _get_text_within(el, f"vs-tbl-data-sa-{date_suffix}")
        txn_type = _get_text_within(el, f"vs-tbl-data-type-{date_suffix}")
        party_to = _get_text_within(el, f"vs-tbl-data-pt-{date_suffix}")

        notes = _get_text_within(el, f"vs-tbl-data-notes-{date_suffix}")
        if not notes:
            notes = _get_text_within(el, f"vs-tbl-data-notes-empty-{date_suffix}")

        if not sale_date:
            sale_date = date_suffix

        rows.append({
            "sale_date": sale_date,
            "sale_amount": sale_amount,
            "type": txn_type,
            "party_to": party_to,
            "notes": notes,
        })

    return rows


# ================================================================
# Main parser
# ================================================================

def parse_gw_html(html, filename):
    """Parse a GeoWarehouse HTML file into structured data.

    Returns None for non-detail pages.
    """
    soup = BeautifulSoup(html, "lxml")

    if not soup.find(id="pr-expansion-panel-registry"):
        return None

    registry = _parse_registry(soup)
    assessments = _parse_all_assessments(soup)

    record = {
        "source_file": filename,
        "is_detail_page": True,
        "has_mpac_data": len(assessments) > 0,
        "is_active": registry.get("land_registry_status", "").lower() != "not active",
        "pin": registry.get("pin", ""),
        "summary": _parse_summary(soup),
        "registry": registry,
        "assessments": assessments,
        "sales_history": _parse_sales_history(soup),
    }

    return record


def _extract_timestamp(filename):
    """Extract timestamp from filename for dedup ordering.

    geowarehouse-2025-12-10T03-00-27-699Z.html → '2025-12-10T03-00-27-699Z'
    """
    return filename.removeprefix("geowarehouse-").removesuffix(".html")


# ================================================================
# Pipeline runner
# ================================================================

def run(limit=None, dry_run=False):
    """Parse all ingested HTML files into structured JSON."""

    if not os.path.isdir(HTML_DIR):
        print(f'ERROR: HTML directory not found: {HTML_DIR}')
        print(f'Run the ingester first.')
        sys.exit(1)

    html_files = sorted(f for f in os.listdir(HTML_DIR) if f.endswith('.html'))
    if not html_files:
        print(f'ERROR: No HTML files in {HTML_DIR}')
        sys.exit(1)

    print('Cleo Engine -- Parse GeoWarehouse HTML')
    print(f'HTML files:  {len(html_files):,}')
    print()

    # Parse all files, tracking per-PIN dedup
    pin_best = {}  # pin -> (timestamp, record, filename)
    no_pin_records = []  # records without PIN
    stats = {
        'detail_pages': 0,
        'non_detail': 0,
        'parse_errors': 0,
        'multi_arn': 0,
        'no_mpac': 0,
        'inactive': 0,
    }

    files_to_parse = html_files[:limit] if limit else html_files

    for i, fname in enumerate(files_to_parse):
        try:
            with open(os.path.join(HTML_DIR, fname), encoding='utf-8') as f:
                html = f.read()

            result = parse_gw_html(html, fname)

            if result is None:
                stats['non_detail'] += 1
                continue

            stats['detail_pages'] += 1

            if not result['has_mpac_data']:
                stats['no_mpac'] += 1
            if not result['is_active']:
                stats['inactive'] += 1
            if len(result.get('assessments', [])) > 1:
                stats['multi_arn'] += 1

            pin = result.get('pin', '').strip()
            ts = _extract_timestamp(fname)

            if pin:
                if pin not in pin_best or ts > pin_best[pin][0]:
                    pin_best[pin] = (ts, result, fname)
            else:
                no_pin_records.append(result)

        except Exception as e:
            stats['parse_errors'] += 1
            print(f'  ERROR parsing {fname}: {e}')

        if (i + 1) % 200 == 0:
            print(f'  [{i+1:,}/{len(files_to_parse):,}] parsed...')

    # Combine: PIN-deduped records + no-PIN records
    unique_records = [rec for _, rec, _ in sorted(pin_best.values(), key=lambda x: x[1].get('pin', ''))]
    unique_records.extend(no_pin_records)

    print(f'\nParsing complete:')
    print(f'  Detail pages:  {stats["detail_pages"]:,}')
    print(f'  Non-detail:    {stats["non_detail"]:,}')
    print(f'  Parse errors:  {stats["parse_errors"]:,}')
    print(f'  Multi-ARN:     {stats["multi_arn"]:,}')
    print(f'  No MPAC data:  {stats["no_mpac"]:,}')
    print(f'  Inactive:      {stats["inactive"]:,}')
    print(f'  After PIN dedup: {len(unique_records):,} unique records')
    print()

    if dry_run:
        return

    # Assign GW IDs and write
    os.makedirs(PARSED_DIR, exist_ok=True)

    for i, record in enumerate(unique_records, start=1):
        gw_id = f'GW{i:05d}'
        record['gw_id'] = gw_id

        out_path = os.path.join(PARSED_DIR, f'{gw_id}.json')
        with open(out_path, 'w') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

    # Write meta
    meta = {
        'total_parsed': len(unique_records),
        'detail_pages_found': stats['detail_pages'],
        'non_detail_skipped': stats['non_detail'],
        'pin_duplicates_removed': stats['detail_pages'] - len(unique_records) + len(no_pin_records),
    }
    with open(os.path.join(PARSED_DIR, '_meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'Wrote {len(unique_records):,} records to {PARSED_DIR}')


def main():
    parser = argparse.ArgumentParser(description='Parse GeoWarehouse HTML into structured JSON')
    parser.add_argument('--limit', type=int, help='Parse only the first N HTML files')
    parser.add_argument('--dry-run', action='store_true', help='Parse and report without writing files')
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
