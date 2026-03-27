"""
Export parser — reads export.json from a page folder and returns
one record per array position.

This is nearly trivial. The export data is already structured JSON
from the scraper. We just pass it through with the position index added.
"""

import json


def parse_export_file(export_path):
    """Parse an export.json file and return a list of records, one per position.

    Args:
        export_path: absolute path to export.json

    Returns:
        list of dicts, each with 'position' added to the original export fields
    """
    with open(export_path, 'r', encoding='utf-8') as f:
        rows = json.load(f)

    records = []
    for i, row in enumerate(rows):
        record = {
            'position': i,
            'address': row.get('address', ''),
            'postcode': row.get('postcode', ''),
            'municipality': row.get('municipality', ''),
            'region': row.get('region', ''),
            'date': row.get('date', ''),
            'desc': row.get('desc', ''),
            'bldg': row.get('bldg', ''),
            'acreage': row.get('acreage', ''),
            'consid': row.get('consid', ''),
            'cash': row.get('cash', ''),
            'debt': row.get('debt', ''),
            'note': row.get('note', ''),
            'pin': row.get('pin', ''),
            'rollno': row.get('rollno', ''),
        }
        records.append(record)

    return records


def parse_export_at_position(export_path, position):
    """Parse export.json and return the record at a specific position.

    Args:
        export_path: absolute path to export.json
        position: 0-based array index

    Returns:
        dict with export fields + position, or None if position out of range
    """
    records = parse_export_file(export_path)
    if position < len(records):
        return records[position]
    return None
