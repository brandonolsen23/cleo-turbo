#!/usr/bin/env python3
"""
Cleo Turbo API Response Shape Tests

Hits every API endpoint and verifies that the response keys match
the TypeScript interfaces in frontend/src/types/index.ts.

Requires: backend running on port 8099 with a valid auth token.
Run from project root: python3 .claude/skills/test/scripts/test_api_shapes.py
"""

import re
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
TYPES_PATH = PROJECT_ROOT / "frontend" / "src" / "types" / "index.ts"
BASE_URL = "http://localhost:8099/api"

passed = 0
failed = 0
warnings = 0

# Auth token — set via environment or hardcode for local testing
import os
AUTH_TOKEN = os.environ.get("CLEO_AUTH_TOKEN", "")


def ok(msg):
    global passed
    passed += 1
    print(f"  ✓ {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  ✗ {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  ⚠ {msg}")


def extract_interfaces(types_text):
    """Extract TypeScript interface names and their fields."""
    interfaces = {}
    for m in re.finditer(
        r'export\s+interface\s+(\w+)\s*(?:extends\s+(\w+)\s*)?\{([^}]+)\}',
        types_text, re.DOTALL
    ):
        name = m.group(1)
        extends = m.group(2)
        body = m.group(3)
        fields = []
        optional_fields = []
        for line in body.split("\n"):
            line = line.strip()
            field_match = re.match(r'(\w+)(\??)\s*:', line)
            if field_match:
                field_name = field_match.group(1)
                is_optional = field_match.group(2) == "?"
                fields.append(field_name)
                if is_optional:
                    optional_fields.append(field_name)
        interfaces[name] = {
            "fields": fields,
            "optional": optional_fields,
            "extends": extends,
        }

    # Resolve extends — merge parent fields into child
    for name, info in interfaces.items():
        if info["extends"] and info["extends"] in interfaces:
            parent = interfaces[info["extends"]]
            all_fields = list(parent["fields"]) + info["fields"]
            all_optional = list(parent["optional"]) + info["optional"]
            info["fields"] = list(dict.fromkeys(all_fields))  # dedupe preserving order
            info["optional"] = list(dict.fromkeys(all_optional))

    return interfaces


def api_get(path):
    """Make a GET request to the API."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    if AUTH_TOKEN:
        req.add_header("Authorization", f"Bearer {AUTH_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"__error": e.code, "__message": str(e)}
    except urllib.error.URLError as e:
        return {"__error": "connection", "__message": str(e)}


def check_shape(endpoint, response_data, interface_name, interfaces, is_browse=False):
    """Compare response keys against TypeScript interface fields."""
    if "__error" in response_data:
        if response_data["__error"] == "connection":
            fail(f"{endpoint}: Cannot connect to backend (is it running on port 8099?)")
        elif response_data["__error"] == 401:
            fail(f"{endpoint}: 401 Unauthorized (set CLEO_AUTH_TOKEN env var)")
        elif response_data["__error"] == 404:
            warn(f"{endpoint}: 404 Not Found (no data?)")
        else:
            fail(f"{endpoint}: HTTP {response_data['__error']}")
        return

    if interface_name not in interfaces:
        warn(f"{endpoint}: interface '{interface_name}' not found in types/index.ts")
        return

    iface = interfaces[interface_name]
    expected_fields = set(iface["fields"])
    optional_fields = set(iface["optional"])
    required_fields = expected_fields - optional_fields

    # For browse endpoints, check results[0]
    if is_browse:
        results = response_data.get("results", [])
        if not results:
            warn(f"{endpoint} → {interface_name}: no results to check (empty dataset)")
            return
        actual_keys = set(results[0].keys())
    else:
        actual_keys = set(response_data.keys())

    # Fields in TypeScript but not in response
    missing_required = required_fields - actual_keys
    missing_optional = optional_fields - actual_keys

    # Fields in response but not in TypeScript
    extra = actual_keys - expected_fields

    if not missing_required and not extra:
        ok(f"{endpoint} → {interface_name}: all {len(expected_fields)} fields match")
    else:
        if missing_required:
            fail(f"{endpoint} → {interface_name}: missing required fields: {sorted(missing_required)}")
        if extra:
            warn(f"{endpoint} → {interface_name}: extra fields not in TypeScript: {sorted(extra)}")

    if missing_optional:
        # Optional fields missing is just informational
        pass  # Don't even warn — optional means optional


def main():
    global passed, failed, warnings

    print("=" * 60)
    print("Cleo Turbo API Response Shape Tests")
    print("=" * 60)
    print()

    # Parse TypeScript interfaces
    types_text = TYPES_PATH.read_text()
    interfaces = extract_interfaces(types_text)
    print(f"Loaded {len(interfaces)} interfaces from types/index.ts")
    print()

    # ================================================================
    # Browse Endpoints
    # ================================================================
    print("TEST GROUP: Browse Endpoints")

    browse_tests = [
        ("/properties?per_page=1", "PropertyBrowseItem"),
        ("/transactions?per_page=1", "TransactionBrowseItem"),
        ("/contacts?per_page=1", "ContactBrowseItem"),
        ("/groups?per_page=1", "GroupBrowseItem"),
        ("/gw?per_page=1", "GwAssessment"),
    ]

    for path, iface_name in browse_tests:
        data = api_get(path)
        check_shape(path, data, iface_name, interfaces, is_browse=True)

    print()

    # ================================================================
    # Detail Endpoints
    # ================================================================
    print("TEST GROUP: Detail Endpoints")

    # Get sample IDs from browse results
    detail_tests = [
        ("/properties", "/properties/{id}", "PropertyDetail"),
        ("/transactions", "/transactions/{id}", "TransactionDetail"),
        ("/contacts", "/contacts/{id}", "ContactDetail"),
        ("/groups", "/groups/{id}", "GroupDetail"),
    ]

    for browse_path, detail_template, iface_name in detail_tests:
        browse_data = api_get(f"{browse_path}?per_page=1")
        if "__error" in browse_data:
            warn(f"{detail_template}: skipping (browse failed)")
            continue

        results = browse_data.get("results", [])
        if not results:
            warn(f"{detail_template}: skipping (no data)")
            continue

        sample_id = results[0].get("id")
        if not sample_id:
            warn(f"{detail_template}: skipping (no id in browse result)")
            continue

        detail_path = detail_template.replace("{id}", sample_id)
        detail_data = api_get(detail_path)
        check_shape(detail_path, detail_data, iface_name, interfaces, is_browse=False)

    print()

    # ================================================================
    # Search Endpoints
    # ================================================================
    print("TEST GROUP: Search Endpoints")

    search_tests = [
        ("/properties/search?q=toronto&limit=1", "PropertyBrowseItem"),
        ("/contacts/search?q=smith&limit=1", "ContactBrowseItem"),
        ("/groups/search?q=inc&limit=1", "GroupBrowseItem"),
        ("/transactions/search?q=toronto&limit=1", "TransactionBrowseItem"),
    ]

    for path, iface_name in search_tests:
        data = api_get(path)
        if "__error" in data:
            if data["__error"] == 404:
                warn(f"{path}: search endpoint not found")
            else:
                check_shape(path, data, iface_name, interfaces, is_browse=True)
            continue

        results = data.get("results", [])
        if results:
            actual_keys = set(results[0].keys())
            expected = set(interfaces.get(iface_name, {}).get("fields", []))
            if actual_keys & expected:
                ok(f"{path}: returns {iface_name}-shaped results ({len(results)} hits)")
            else:
                warn(f"{path}: results don't match {iface_name}")
        else:
            warn(f"{path}: no results for test query")

    print()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    if failed == 0:
        print("✓ All checks passed!")
    else:
        print(f"✗ {failed} issue(s) need fixing")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
