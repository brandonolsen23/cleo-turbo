"""
Assembler — joins detail + export + results records by position within
a page folder. Cross-checks overlapping fields to verify the join.
Outputs one combined record per RT ID.
"""

import re


def normalize_for_compare(text):
    """Normalize a string for cross-check comparison.

    Strips punctuation, collapses whitespace, uppercases.
    Used to compare addresses/prices across sources where formatting differs.
    """
    text = text.upper()
    text = re.sub(r'[,$.\s]+', ' ', text)
    text = text.strip()
    return text


def check_address_match(detail_addr_lines, export_address, results_addr_lines):
    """Check if the address matches across the three sources.

    Returns True if the first address line from the detail matches
    the export address (which may be a comma-joined version).
    """
    if not detail_addr_lines or not export_address:
        return True  # Can't compare if missing

    detail_first = normalize_for_compare(detail_addr_lines[0])
    export_norm = normalize_for_compare(export_address)

    # Export address may contain all lines comma-joined
    # Check if the first detail address line appears in the export address
    return detail_first in export_norm or export_norm.startswith(detail_first)


def check_price_match(detail_price, export_consid):
    """Check if the price matches between detail and export.

    Detail price: "$2,550,000" → 2550000
    Export consid: "2550000"
    """
    if not detail_price or not export_consid:
        return True

    # Extract digits only
    detail_digits = re.sub(r'[^\d]', '', detail_price)
    export_digits = re.sub(r'[^\d]', '', export_consid)

    return detail_digits == export_digits


def check_date_match(detail_date, export_date):
    """Check if the date matches between detail and export.

    Detail date: "17 Jul 2014" → components
    Export date: "07/17/2014" → components
    """
    if not detail_date or not export_date:
        return True

    # Parse detail date: "DD Mon YYYY"
    months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
    }
    detail_match = re.match(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', detail_date)
    if not detail_match:
        return True  # Can't parse, skip check

    d_day = detail_match.group(1).zfill(2)
    d_month = months.get(detail_match.group(2), '00')
    d_year = detail_match.group(3)

    # Parse export date: "MM/DD/YYYY"
    export_match = re.match(r'(\d{2})/(\d{2})/(\d{4})', export_date)
    if not export_match:
        return True

    e_month = export_match.group(1)
    e_day = export_match.group(2)
    e_year = export_match.group(3)

    return d_day == e_day and d_month == e_month and d_year == e_year


def find_matching_export(detail_record, export_records):
    """When position-based join fails, find the correct export row by address.

    Compares the first address line from the detail against all export addresses.
    Returns the matching export record, or None if no match found.
    """
    detail_addr_lines = detail_record['header']['address_lines']
    if not detail_addr_lines:
        return None

    detail_first = normalize_for_compare(detail_addr_lines[0])

    # Best match: address + price + date all agree
    for export_record in export_records:
        export_addr = normalize_for_compare(export_record.get('address', ''))
        if detail_first in export_addr or export_addr.startswith(detail_first):
            if check_price_match(detail_record['header']['price_text'],
                                 export_record.get('consid', '')) and \
               check_date_match(detail_record['header']['date_text'],
                                export_record.get('date', '')):
                return export_record

    # Fallback: address + price (no date check)
    for export_record in export_records:
        export_addr = normalize_for_compare(export_record.get('address', ''))
        if detail_first in export_addr or export_addr.startswith(detail_first):
            if check_price_match(detail_record['header']['price_text'],
                                 export_record.get('consid', '')):
                return export_record

    return None


def assemble_record(detail_record, export_record, results_record):
    """Combine the three source records into one assembled record.

    Args:
        detail_record: output from parsers.detail.parse_detail()
        export_record: output from parsers.export.parse_export_at_position()
        results_record: output from parsers.results.parse_results_at_position()

    Returns:
        dict with combined data and join verification results
    """
    rt_id = detail_record['meta']['rt_id']
    position = detail_record['meta']['position']

    # Cross-check the join
    checks = {
        'address_match': True,
        'price_match': True,
        'date_match': True,
    }

    if export_record:
        checks['address_match'] = check_address_match(
            detail_record['header']['address_lines'],
            export_record.get('address', ''),
            results_record['address_lines'] if results_record else []
        )
        checks['price_match'] = check_price_match(
            detail_record['header']['price_text'],
            export_record.get('consid', '')
        )
        checks['date_match'] = check_date_match(
            detail_record['header']['date_text'],
            export_record.get('date', '')
        )

    join_verified = all(checks.values())

    return {
        'rt_id': rt_id,
        'source_folder': detail_record['meta']['source_folder'],
        'position': position,
        'join_verified': join_verified,
        'join_checks': checks,
        'detail': detail_record,
        'export': export_record,
        'results': results_record,
    }
