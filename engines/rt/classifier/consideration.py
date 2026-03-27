"""
Consideration classifier — parses cash, debt, chattels, other, and chargee blocks.

Reference: schema/engine_reference.md — CONSIDERATION SECTION
"""

import re


def _parse_dollar(text):
    """Parse a dollar amount string → integer. Returns None if unparseable."""
    if not text:
        return None
    digits = re.sub(r'[^\d]', '', text)
    if digits:
        return int(digits)
    return None


def classify_consideration(consideration_lines):
    """Classify consideration lines into structured fields.

    Args:
        consideration_lines: list of strings from structural extraction

    Returns:
        dict with cash, debt, chattels, other, charges array
    """
    result = {
        'cash': None,
        'debt': None,
        'chattels': None,
        'other': None,
        'charges': [],
    }

    if not consideration_lines:
        return result

    # First pass: extract cash/debt from the first line
    first_line = consideration_lines[0] if consideration_lines else ''

    cash_match = re.search(r'cash:\s*\$?([\d,]+)', first_line)
    if cash_match:
        result['cash'] = _parse_dollar(cash_match.group(1))

    debt_match = re.search(r'debt:\s*\$?([\d,]+)', first_line)
    if debt_match:
        result['debt'] = _parse_dollar(debt_match.group(1))

    # Check for chattels and other on subsequent lines
    for line in consideration_lines[1:]:
        line = line.strip()
        chattels_match = re.match(r'chattels:\s*\$?([\d,]+)', line)
        if chattels_match:
            result['chattels'] = _parse_dollar(chattels_match.group(1))
            continue

        other_match = re.match(r'other:\s*\$?([\d,]+)', line)
        if other_match:
            result['other'] = _parse_dollar(other_match.group(1))
            continue

    # Second pass: extract chargee blocks
    # Chargee blocks are separated by empty lines
    # Each block starts with "chargee:" or "Named Individual(s)"
    current_charge = None

    for line in consideration_lines:
        line = line.strip()

        # Empty line = end of current charge block
        if not line:
            if current_charge:
                result['charges'].append(current_charge)
                current_charge = None
            continue

        # Skip the cash/debt/chattels/other lines
        if re.match(r'^(cash:|chattels:|other:)', line):
            continue

        # Start of a new chargee block
        chargee_match = re.match(r'^chargee:\s*(.*)', line)
        if chargee_match:
            if current_charge:
                result['charges'].append(current_charge)
            current_charge = {
                'chargee': chargee_match.group(1).strip(),
                'principal': None,
                'rate': '',
                'registered': '',
                'due': '',
            }
            continue

        # "Named Individual(s)" as chargee (no "chargee:" prefix)
        if line == 'Named Individual(s)' and current_charge is None:
            current_charge = {
                'chargee': 'Named Individual(s)',
                'principal': None,
                'rate': '',
                'registered': '',
                'due': '',
            }
            continue

        # Lines within a chargee block
        if current_charge:
            # Additional chargee name line (multi-name chargees)
            if not line.startswith('principal:') and not line.startswith('registered:'):
                # Could be a second chargee name line
                if not current_charge.get('principal'):
                    current_charge['chargee'] += '\n' + line
                    continue

            # Principal + rate
            principal_match = re.search(r'principal:\s*\$?([\d,]+)', line)
            if principal_match:
                current_charge['principal'] = _parse_dollar(principal_match.group(1))

            rate_match = re.search(r'rate:\s*(.*?)(?:\s*$)', line)
            if rate_match:
                current_charge['rate'] = rate_match.group(1).strip()

            # Registered + due
            reg_match = re.search(r'registered:\s*(\d{2}/\d{2}/\d{4})', line)
            if reg_match:
                current_charge['registered'] = reg_match.group(1)

            due_match = re.search(r'due:\s*(.*?)(?:\s*$)', line)
            if due_match:
                current_charge['due'] = due_match.group(1).strip()

    # Don't forget the last charge block
    if current_charge:
        result['charges'].append(current_charge)

    return result
