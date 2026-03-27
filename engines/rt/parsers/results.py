"""
Results parser — reads results.html from a page folder and returns
one record per table row.

Each row contains: address, city/region, date, transaction note,
property description, seller names, buyer names, and price.
"""

import re
from parsers.normalize import decode_html, clean_line


def parse_results_file(results_path):
    """Parse a results.html file and return a list of records, one per row.

    Args:
        results_path: absolute path to results.html

    Returns:
        list of dicts, each with position and extracted fields
    """
    with open(results_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Each transaction is a table row with three <td class="content"> cells:
    #   Cell 1: address, city:region, date, note
    #   Cell 2: description, seller names, "to", buyer names
    #   Cell 3: price
    rows = re.findall(
        r'<tr><td class="content">(.*?)</td></tr>',
        html,
        re.DOTALL
    )

    records = []
    for i, row_html in enumerate(rows):
        # Split into the three cells
        cells = re.split(r'</td><td class="content">', row_html)
        if len(cells) < 3:
            continue

        cell1, cell2, cell3 = cells[0], cells[1], cells[2]

        record = {
            'position': i,
            'address_lines': [],
            'city_region': '',
            'date_text': '',
            'note': '',
            'description': '',
            'seller_lines': [],
            'buyer_lines': [],
            'price_text': '',
        }

        # --- Cell 1: address, city:region, date, note ---
        # Address from propAddr link — can contain <br /> for multi-line
        addr_match = re.search(r'class="propAddr"[^>]*>(.*?)</a>', cell1, re.DOTALL)
        if addr_match:
            addr_html = addr_match.group(1)
            record['address_lines'] = [
                clean_line(part) for part in re.split(r'<br\s*/?\s*>', addr_html)
                if clean_line(part)
            ]

        # After the address: city:region, date, note — separated by <br />
        after_addr = cell1[cell1.find('</a>'):] if '</a>' in cell1 else ''
        parts = re.split(r'<br\s*/?\s*>', after_addr)
        for part in parts:
            cleaned = clean_line(part)
            if not cleaned:
                continue
            if ':' in cleaned and not record['city_region']:
                record['city_region'] = cleaned
            elif re.match(r'\d{1,2}\s+\w{3}\s+\d{4}', cleaned) and not record['date_text']:
                record['date_text'] = cleaned

        # Note from red font
        note_match = re.search(r'<font color="#CC0000">(.*?)</font>', cell1)
        if note_match:
            record['note'] = clean_line(note_match.group(1))

        # --- Cell 2: description, seller names, "to", buyer names ---
        # Description from propDesc
        desc_match = re.search(r'<p class="propDesc">(.*?)</p>', cell2)
        if desc_match:
            record['description'] = clean_line(desc_match.group(1))

        # Seller and buyer names split by the "to" divider
        # Remove the description tag first
        names_html = re.sub(r'<p class="propDesc">.*?</p>', '', cell2)
        # Split on the "to" divider: <font color="#cccccc">to </font>
        to_split = re.split(r'<font color="#cccccc">to\s*</font>', names_html)

        if len(to_split) >= 1:
            # Seller names — before "to"
            seller_parts = re.split(r'<br\s*/?\s*>', to_split[0])
            record['seller_lines'] = [
                clean_line(p) for p in seller_parts if clean_line(p)
            ]

        if len(to_split) >= 2:
            # Buyer names — after "to"
            buyer_parts = re.split(r'<br\s*/?\s*>', to_split[1])
            record['buyer_lines'] = [
                clean_line(p) for p in buyer_parts if clean_line(p)
            ]

        # --- Cell 3: price ---
        record['price_text'] = clean_line(cell3)

        records.append(record)

    return records


def parse_results_at_position(results_path, position):
    """Parse results.html and return the record at a specific position.

    Args:
        results_path: absolute path to results.html
        position: 0-based row index

    Returns:
        dict with results fields + position, or None if position out of range
    """
    records = parse_results_file(results_path)
    if position < len(records):
        return records[position]
    return None
