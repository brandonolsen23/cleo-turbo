"""
Broker classifier — parses brokerage name, agent names, and phone.

Reference: schema/engine_reference.md — BROKER SECTION
"""

import re
from classifier.dictionaries import PHONE_REGEX


def classify_broker(broker_lines):
    """Classify broker lines into structured entries.

    Args:
        broker_lines: list of strings from structural extraction

    Returns:
        dict with brokers array
    """
    result = {
        'brokers': [],
    }

    for line in broker_lines:
        line = line.strip()
        if not line:
            continue

        entry = {
            'brokerage': '',
            'agents': [],
            'phone': '',
        }

        # Extract phone from end of line
        phone_match = PHONE_REGEX.search(line)
        if phone_match:
            entry['phone'] = phone_match.group(0)
            # Remove phone from line for further parsing
            line = line[:phone_match.start()].strip().rstrip(',').strip()

        # Split brokerage from agents on first colon
        if ':' in line:
            parts = line.split(':', 1)
            entry['brokerage'] = parts[0].strip()
            agents_text = parts[1].strip()
        else:
            agents_text = line

        # Split agent names on ', ' and ' & ' and ' and '
        if agents_text:
            # First split on ' & ' and ' and '
            parts = re.split(r'\s+&\s+|\s+and\s+', agents_text)
            agents = []
            for part in parts:
                # Then split on ', ' but be careful with names like "D'Orsay"
                sub_parts = [p.strip() for p in part.split(', ') if p.strip()]
                agents.extend(sub_parts)
            entry['agents'] = [a for a in agents if a]

        result['brokers'].append(entry)

    return result
