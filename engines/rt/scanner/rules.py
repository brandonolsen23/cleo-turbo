"""
Data quality validation rules.

Each rule detects a GENUINE data quality issue — not just missing data that
doesn't exist in the source. A rule should only flag something if it's
actually wrong, not just absent.

Key principle: if the source HTML doesn't have a phone number, that's not
an error. An error is when data EXISTS but is in the WRONG field.
"""

import re
from dataclasses import dataclass
from typing import List

# ── Patterns ──

# Ontario numbered companies look like "1234567 Ontario Inc" — NOT phone numbers
NUMBERED_COMPANY_RE = re.compile(r'^\d{5,10}\s+(Ontario|Canada|Alberta|BC)\s+(Inc|Ltd|Corp|Limited)', re.IGNORECASE)

# Actual phone: must have separators (parentheses, dashes, dots, spaces between groups)
# This avoids matching "1234567 Ontario Inc" which has no separators
PHONE_RE = re.compile(r'(?:\(\d{3}\)\s*|\d{3}[-.\s])\d{3}[-.\s]\d{4}')

# Corporate suffixes — but NOT words that appear in street names
CORP_ONLY_SUFFIXES = [
    "INC", "LTD", "CORP", "LIMITED", "HOLDINGS", "INVESTMENTS",
    "ENTERPRISES", "LLC", "LP", "LLP",
]

# Words that can be both a company keyword AND a street name — don't flag these alone
AMBIGUOUS_WORDS = {"COMPANY", "CAPITAL", "TRUST", "MANAGEMENT", "PROPERTIES", "REALTY", "DEVELOPMENT"}

STREET_SUFFIXES = [
    "STREET", "AVENUE", "ROAD", "DRIVE", "BOULEVARD", "CRESCENT",
    "COURT", "PLACE", "LANE", "CIRCLE", "TRAIL", "HIGHWAY",
    "WAY", "TERRACE", "PARKWAY", "CONCESSION", "DR", "ST",
    "AVE", "RD", "BLVD", "CRES", "CRT", "PL", "LN", "HWY",
]


@dataclass
class Issue:
    rule: str
    severity: str
    field_path: str
    actual_value: str
    message: str


def _get_nested(obj, path):
    for key in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _has_street_suffix(text):
    """Check if text contains a street suffix, suggesting it's an address."""
    words = text.upper().split()
    return any(w in STREET_SUFFIXES for w in words)


def _is_numbered_company(text):
    """Check if text is an Ontario numbered company like '1234567 Ontario Inc'."""
    return bool(NUMBERED_COMPANY_RE.match(text.strip()))


def _check_side(record, side):
    """Run all per-side checks. Only flags genuine misclassifications."""
    issues = []
    s = _get_nested(record, side) or {}

    # ── company_in_address ──
    # Flag: a line in address that has a corporate suffix BUT no street suffix
    # (if it has a street suffix, it's likely "123 Capital Dr" which is valid)
    addr = s.get("address", {}) or {}
    addr_lines = addr.get("lines") or addr.get("original_lines") or []
    if isinstance(addr_lines, list):
        for i, line in enumerate(addr_lines):
            if isinstance(line, str) and len(line.strip()) > 3:
                upper = line.upper()
                words = upper.split()
                has_corp = any(suf in words for suf in CORP_ONLY_SUFFIXES)
                has_street = _has_street_suffix(line)
                has_digit_prefix = bool(re.match(r'^\d+\s', line.strip()))

                # Only flag if it has a corporate suffix AND doesn't look like an address
                if has_corp and not has_street and not has_digit_prefix:
                    issues.append(Issue(
                        rule="company_in_address",
                        severity="error",
                        field_path=f"{side}.address.lines[{i}]",
                        actual_value=line,
                        message=f"Company name in address field (no street indicators)",
                    ))

    # ── phone_in_name ──
    # Flag: an actual phone number (with separators) embedded in a name field
    # Skip Ontario numbered companies ("1234567 Ontario Inc")
    parties = s.get("parties") or []
    for i, p in enumerate(parties):
        name = p.get("name", "") if isinstance(p, dict) else str(p)
        if PHONE_RE.search(name) and not _is_numbered_company(name):
            # Verify the phone is embedded (name has other text besides the phone)
            without_phone = PHONE_RE.sub("", name).strip()
            if len(without_phone) > 3:  # There's actual name text alongside the phone
                issues.append(Issue(
                    rule="phone_in_name",
                    severity="error",
                    field_path=f"{side}.parties[{i}].name",
                    actual_value=name,
                    message="Phone number embedded in party name — should be extracted to phone field",
                ))

    contacts = s.get("contacts") or []
    for i, c in enumerate(contacts):
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        if PHONE_RE.search(name) and not _is_numbered_company(name):
            without_phone = PHONE_RE.sub("", name).strip()
            if len(without_phone) > 3:
                issues.append(Issue(
                    rule="phone_in_name",
                    severity="error",
                    field_path=f"{side}.contacts[{i}].name",
                    actual_value=name,
                    message="Phone number embedded in contact name — should be extracted to phone field",
                ))

    # ── street_as_contact ──
    # Flag: contact name that IS a street address (has digit prefix + street suffix)
    for i, c in enumerate(contacts):
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        if re.match(r'^\d+\s', name.strip()) and _has_street_suffix(name):
            issues.append(Issue(
                rule="street_as_contact",
                severity="error",
                field_path=f"{side}.contacts[{i}].name",
                actual_value=name,
                message="Street address classified as contact name",
            ))

    # ── address_in_party ──
    # Flag: party name that starts with a number and has a street suffix
    # (like "27 Bridge Street Inc" — valid company name, just informational)
    for i, p in enumerate(parties):
        name = p.get("name", "") if isinstance(p, dict) else str(p)
        if re.match(r'^\d+\s', name.strip()) and _has_street_suffix(name):
            # Only flag if it does NOT have a corporate suffix (pure address in party field)
            words = name.upper().split()
            has_corp = any(suf in words for suf in CORP_ONLY_SUFFIXES)
            if not has_corp:
                issues.append(Issue(
                    rule="address_in_party",
                    severity="warning",
                    field_path=f"{side}.parties[{i}].name",
                    actual_value=name,
                    message="Street address in party name field (no corporate suffix)",
                ))

    return issues


def check_record(record: dict) -> List[Issue]:
    """Run all validation rules against a clean record."""
    issues = []

    issues.extend(_check_side(record, "seller"))
    issues.extend(_check_side(record, "buyer"))

    # ── null_required — truly critical fields ──
    txn = _get_nested(record, "transaction") or {}
    if not txn.get("sale_price") and not txn.get("sale_date"):
        issues.append(Issue(
            rule="null_required",
            severity="error",
            field_path="transaction",
            actual_value="no price or date",
            message="Transaction has neither sale price nor sale date",
        ))

    # ── format_mismatch — only if data exists but is malformed ──
    sale_date = txn.get("sale_date")
    if sale_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', str(sale_date)):
        issues.append(Issue(
            rule="format_mismatch",
            severity="warning",
            field_path="transaction.sale_date",
            actual_value=str(sale_date),
            message=f"Sale date '{sale_date}' not in ISO format",
        ))

    return issues


# Rule metadata for the API
RULES = {
    "company_in_address": {
        "description": "Company name (with corporate suffix, no street indicators) found in address field",
        "severity": "error",
    },
    "phone_in_name": {
        "description": "Actual phone number (with separators) embedded alongside name text in party/contact name",
        "severity": "error",
    },
    "street_as_contact": {
        "description": "Street address (digit prefix + street suffix) classified as a contact name",
        "severity": "error",
    },
    "address_in_party": {
        "description": "Street address in party name field with no corporate suffix",
        "severity": "warning",
    },
    "null_required": {
        "description": "Transaction missing both sale price and sale date",
        "severity": "error",
    },
    "format_mismatch": {
        "description": "Field value exists but format is incorrect",
        "severity": "warning",
    },
}
