"""
Auto-tracer — given an issue on a clean record, walk backward through
pipeline stages to find which stage introduced the problem.
"""

import os
import json
import glob

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

STAGE_DIRS = {
    "clean":        os.path.join(PROJECT_ROOT, "clean-data", "rt"),
    "addresses":    os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "addresses"),
    "classified":   os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "classified"),
    "assembled":    os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "assembled"),
}

# Reverse lineage: clean field → [(stage, field_at_that_stage), ...]
# When a clean field path matches a key here, we check those stages in order.
REVERSE_LINEAGE = {
    "seller.address.lines": [
        ("addresses", "seller.address.original_lines"),
        ("classified", "seller.address.lines"),
        ("assembled", "detail.transferor.contact_lines"),
    ],
    "seller.address": [
        ("addresses", "seller.address"),
        ("classified", "seller.address"),
        ("assembled", "detail.transferor.contact_lines"),
    ],
    "seller.parties": [
        ("classified", "seller.parties"),
        ("assembled", "detail.transferor.party_lines"),
    ],
    "seller.contacts": [
        ("classified", "seller.contacts"),
        ("assembled", "detail.transferor.contact_lines"),
    ],
    "seller.phone": [
        ("classified", "seller.phone"),
        ("assembled", "detail.transferor.contact_lines"),
    ],
    "buyer.address.lines": [
        ("addresses", "buyer.address.original_lines"),
        ("classified", "buyer.address.lines"),
        ("assembled", "detail.transferee.contact_lines"),
    ],
    "buyer.address": [
        ("addresses", "buyer.address"),
        ("classified", "buyer.address"),
        ("assembled", "detail.transferee.contact_lines"),
    ],
    "buyer.parties": [
        ("classified", "buyer.parties"),
        ("assembled", "detail.transferee.party_lines"),
    ],
    "buyer.contacts": [
        ("classified", "buyer.contacts"),
        ("assembled", "detail.transferee.contact_lines"),
    ],
    "buyer.phone": [
        ("classified", "buyer.phone"),
        ("assembled", "detail.transferee.contact_lines"),
    ],
    "transaction.sale_date": [
        ("classified", "header.sale_date"),
        ("assembled", "detail.header.date_text"),
    ],
    "transaction.sale_price": [
        ("classified", "header.sale_price"),
        ("assembled", "detail.header.price_text"),
    ],
    "transaction.city": [
        ("classified", "header.city"),
        ("assembled", "detail.header.city_region"),
    ],
}

# Code locations for each stage's logic
CODE_LOCATIONS = {
    "assembled": "engines/rt/run_pipeline.py",
    "classified": "engines/rt/classifier/contacts.py",
    "addresses": "engines/rt/address_normalizer/run.py",
    "extracted": "engines/rt/run_pipeline.py",
}


def _get_nested(obj, path):
    """Get nested value by dot path, handling array indices."""
    import re as _re
    for key in path.split("."):
        if obj is None:
            return None
        m = _re.match(r'^(.+)\[(\d+)\]$', key)
        if m:
            obj = obj.get(m.group(1)) if isinstance(obj, dict) else None
            if isinstance(obj, list) and int(m.group(2)) < len(obj):
                obj = obj[int(m.group(2))]
            else:
                return None
        elif isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _value_exists_in(data, value):
    """Recursively check if a value exists anywhere in a nested dict/list."""
    if data == value:
        return True
    if isinstance(data, dict):
        return any(_value_exists_in(v, value) for v in data.values())
    if isinstance(data, list):
        return any(_value_exists_in(item, value) for item in data)
    return False


def _load_stage_record(rt_id, stage):
    """Load a record at a given stage."""
    stage_dir = STAGE_DIRS.get(stage)
    if not stage_dir:
        return None

    if stage == "clean":
        path = os.path.join(stage_dir, f"{rt_id}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None

    # For other stages, glob for the RT ID
    pattern = os.path.join(stage_dir, f"{rt_id}__*.json")
    matches = glob.glob(pattern)
    if matches:
        with open(matches[0]) as f:
            return json.load(f)
    return None


def trace_issue(rt_id, issue):
    """
    Trace an issue backward through pipeline stages to find where it was introduced.

    Returns a dict with:
      - introduced_at: stage name
      - origin_field: field path at that stage
      - source_field: where the value was before it got misplaced
      - explanation: human-readable
      - code_location: file to fix
    """
    field_path = issue.field_path
    actual_value = issue.actual_value

    # Strip array indices for lineage lookup
    # e.g., "seller.address.lines[0]" → "seller.address.lines"
    import re
    base_path = re.sub(r'\[\d+\]', '', field_path)

    # Find the best matching lineage chain
    lineage = None
    for key in sorted(REVERSE_LINEAGE.keys(), key=len, reverse=True):
        if base_path.startswith(key):
            lineage = REVERSE_LINEAGE[key]
            break

    if not lineage:
        # No lineage mapping — can't auto-trace
        return {
            "introduced_at": "unknown",
            "origin_field": field_path,
            "source_field": None,
            "explanation": f"No lineage mapping for {base_path} — manual trace needed",
            "code_location": None,
        }

    # Walk backward through stages
    prev_stage = "clean"
    prev_field = field_path

    for stage, stage_field in lineage:
        record = _load_stage_record(rt_id, stage)
        if record is None:
            continue

        # Check if the bad value exists at the expected field path
        stage_value = _get_nested(record, stage_field)

        if stage_value is not None and _value_exists_in(stage_value, actual_value):
            # Value exists here too — keep going back
            prev_stage = stage
            prev_field = stage_field
        else:
            # Value does NOT exist at this stage's expected field
            # But does it exist somewhere else in this stage's record?
            if _value_exists_in(record, actual_value):
                # Value exists at this stage but in a DIFFERENT field
                # The previous stage (which mapped it to the wrong field) is the culprit
                return {
                    "introduced_at": prev_stage,
                    "origin_field": prev_field,
                    "source_field": stage_field,
                    "explanation": (
                        f"Value '{actual_value[:50]}' was at '{stage_field}' in {stage} stage. "
                        f"The {prev_stage} stage moved it to '{prev_field}' instead of the correct field."
                    ),
                    "code_location": CODE_LOCATIONS.get(prev_stage),
                }
            else:
                # Value doesn't exist at this stage at all — introduced at prev_stage
                return {
                    "introduced_at": prev_stage,
                    "origin_field": prev_field,
                    "source_field": None,
                    "explanation": (
                        f"Value '{actual_value[:50]}' first appears at '{prev_field}' in {prev_stage} stage. "
                        f"Not present in {stage} stage."
                    ),
                    "code_location": CODE_LOCATIONS.get(prev_stage),
                }

    # Walked all the way back — the issue originates at the earliest stage we checked
    return {
        "introduced_at": prev_stage,
        "origin_field": prev_field,
        "source_field": None,
        "explanation": f"Value present from earliest traced stage ({prev_stage})",
        "code_location": CODE_LOCATIONS.get(prev_stage),
    }
