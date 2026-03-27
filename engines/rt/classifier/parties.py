"""
Party lines classifier — extracts party names and phone number.

Includes continuation logic: if a party line ends with a preposition,
article, conjunction, or comma, the next line is a continuation of the
same party name, not a new party.

Reference: schema/engine_reference.md — PARTY LINES CLASSIFICATION
"""

import re
from classifier.dictionaries import PHONE_REGEX

# Words that signal the line continues onto the next line
CONTINUATION_ENDINGS = re.compile(
    r'\b(of|by|the|a|an|in|for|to|at|on|with|and|or|&|as|represented)$|,\s*$',
    re.IGNORECASE
)

# Phrases that are never standalone entity names — if a line starts with one,
# it's a continuation of the previous line
CONTINUATION_STARTS = re.compile(
    r'^(Limited Partnership|General Partnership|in trust|'
    r'as represented by|as trustee|on behalf of|'
    r'and [A-Z])',
    re.IGNORECASE
)


def _rejoin_continuation_lines(party_lines):
    """Rejoin party lines that are continuations of each other.

    If a line ends with a preposition, article, conjunction, or comma,
    the next line is part of the same party name.

    "Her Majesty the Queen in right of" +
    "Ontario as represented by the" +
    "Minister of Economic Development," +
    "Employment and Infrastructure     416-327-3937"
    → one joined line
    """
    if not party_lines:
        return party_lines

    joined = []
    current = party_lines[0].strip()

    for i in range(1, len(party_lines)):
        next_line = party_lines[i].strip()
        if not next_line:
            continue

        # Check if current line ends with a continuation word/comma
        # OR if the next line starts with a continuation phrase
        if CONTINUATION_ENDINGS.search(current) or CONTINUATION_STARTS.match(next_line):
            current = current.rstrip(',').strip() + ', ' if current.endswith(',') else current + ' '
            current += next_line
        else:
            joined.append(current)
            current = next_line

    joined.append(current)
    return joined


def classify_parties(party_lines, trade_name=''):
    """Classify party lines into party names + phone.

    Args:
        party_lines: list of strings from structural extraction
        trade_name: trade name / DBA from <em> tag

    Returns:
        dict with parties array, phone, trade_name
    """
    result = {
        'parties': [],
        'phone': '',
        'trade_name': trade_name,
    }

    if not party_lines:
        return result

    # First: rejoin continuation lines
    lines = _rejoin_continuation_lines(party_lines)

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        is_last = (i == len(lines) - 1)

        if is_last:
            # Check for phone number separated by multi-space gap (3+ spaces)
            # Pattern: "Company Name     905-789-9500"
            gap_match = re.search(r'\s{3,}', line)
            if gap_match:
                before = line[:gap_match.start()].strip()
                after = line[gap_match.end():].strip()

                phone_match = PHONE_REGEX.search(after)
                if phone_match:
                    # Split: name + phone
                    if before:
                        result['parties'].append({'name': before})
                    result['phone'] = phone_match.group(0)
                    continue

            # Also check if the whole line is just a phone (rare but possible)
            phone_match = PHONE_REGEX.match(line)
            if phone_match and phone_match.end() >= len(line.strip()) - 5:
                result['phone'] = phone_match.group(0)
                continue

        # Regular party name
        result['parties'].append({'name': line})

    return result
