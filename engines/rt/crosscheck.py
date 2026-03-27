"""
Cross-check report — tallies how many times each dictionary's keywords
show up in each classified field. Surfaces misclassifications at scale.

Usage:
    python3 crosscheck.py                # check all classified records
    python3 crosscheck.py --limit 1000   # check first 1000
"""

import json
import os
import re
import argparse
from collections import defaultdict

from classifier.dictionaries import (
    CORPORATE_SUFFIX_ANYWHERE_REGEX,
    COMPANY_KEYWORDS,
    LAW_FIRM_KEYWORDS, LAW_FIRM_PC_REGEX,
    BUILDING_KEYWORDS, BUILDING_CONTEXT_KEYWORDS,
    STREET_SUFFIX_REGEX,
    PHONE_REGEX,
    POSTAL_CODE_REGEX,
    CONTACT_PREFIX_REGEX,
    NOT_A_PERSON_REGEX,
    ALL_PROVINCES_STATES,
    PO_BOX_REGEX, RURAL_ROUTE_REGEX,
)


def check_line(text):
    """Check a text string against ALL dictionaries. Returns set of matching dictionary names."""
    if not text or not text.strip():
        return set()

    hits = set()

    if CORPORATE_SUFFIX_ANYWHERE_REGEX.search(text):
        hits.add('corporate_suffix')
    if any(kw in text for kw in COMPANY_KEYWORDS):
        hits.add('company_keyword')
    if any(kw in text for kw in LAW_FIRM_KEYWORDS) or LAW_FIRM_PC_REGEX.search(text):
        hits.add('law_firm_keyword')
    if any(kw.lower() in text.lower() for kw in BUILDING_KEYWORDS):
        hits.add('building_keyword')
    if any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in BUILDING_CONTEXT_KEYWORDS):
        hits.add('building_context')
    if STREET_SUFFIX_REGEX.search(text):
        hits.add('street_suffix')
    if PHONE_REGEX.search(text):
        hits.add('phone_pattern')
    if POSTAL_CODE_REGEX.match(text.strip()):
        hits.add('postal_pattern')
    if CONTACT_PREFIX_REGEX.match(text):
        hits.add('contact_prefix')
    # Department keywords (now part of COMPANY_KEYWORDS, but still useful to detect separately for cross-check)
    _dept_kws = ['Department', 'Dept', 'Division', 'Ministry', 'Mail Code', 'REPDO']
    if any(kw.lower() in text.lower() for kw in _dept_kws):
        hits.add('department_keyword')
    if re.match(r'^\d', text):
        hits.add('starts_with_digit')
    if not re.search(r'\d', text):
        hits.add('no_digit')
    if ',' in text:
        after = text.split(',')[-1].strip().replace('.', '')
        if after in ALL_PROVINCES_STATES:
            hits.add('province_after_comma')
    if PO_BOX_REGEX.match(text) or RURAL_ROUTE_REGEX.match(text):
        hits.add('po_box_or_rr')

    return hits


def extract_field_texts(classified, role):
    """Extract all text values from a seller/buyer classified block, by field."""
    data = classified[role]
    fields = {}

    # Contact names
    fields['contacts'] = [c.get('name', '') for c in data.get('contacts', [])]

    # Companies
    fields['companies'] = data.get('companies', [])

    # Law firms
    fields['law_firms'] = data.get('law_firms', [])

    # Departments

    # Address lines
    fields['address_lines'] = data.get('address', {}).get('lines', [])

    # Address modifiers
    fields['address_modifiers'] = data.get('address', {}).get('modifiers', [])

    # Building names
    fields['building_names'] = data.get('address', {}).get('building_names', [])

    # Care of
    co = data.get('care_of')
    if co:
        fields['care_of'] = [co.get('text', '')]
    else:
        fields['care_of'] = []

    # Trust references

    # Party names
    fields['parties'] = [p.get('name', '') for p in data.get('parties', [])]

    # Other
    fields['other_lines'] = data.get('other_lines', [])

    return fields


def main():
    parser = argparse.ArgumentParser(description='Cross-check classified fields against all dictionaries')
    parser.add_argument('--limit', type=int, help='Limit to first N records')
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path) as f:
        config = json.load(f)

    classified_dir = os.path.join(config['pipeline_output'], 'classified')

    files = sorted([f for f in os.listdir(classified_dir) if f.endswith('.json')])
    if args.limit:
        files = files[:args.limit]

    if not files:
        print('No classified files found.')
        return

    # Tally: field_name → dictionary_name → count
    tally = defaultdict(lambda: defaultdict(int))
    # Samples: field_name → dictionary_name → list of (rt_id, text)
    samples = defaultdict(lambda: defaultdict(list))

    total = 0
    for f in files:
        with open(os.path.join(classified_dir, f)) as fp:
            classified = json.load(fp)

        total += 1
        rt_id = classified.get('rt_id', f)

        for role in ['seller', 'buyer']:
            fields = extract_field_texts(classified, role)

            for field_name, texts in fields.items():
                for text in texts:
                    if not text:
                        continue
                    hits = check_line(text)
                    for dict_name in hits:
                        tally[field_name][dict_name] += 1
                        if len(samples[field_name][dict_name]) < 3:
                            samples[field_name][dict_name].append((rt_id, text))

    # Print report — focus on UNEXPECTED cross-matches
    print(f'Cross-check report — {total} classified records')
    print(f'{"=" * 70}')
    print()

    # Define what's EXPECTED vs UNEXPECTED for each field
    expected = {
        'contacts': {'no_digit'},  # names normally have no digits
        'companies': {'corporate_suffix', 'company_keyword', 'no_digit', 'building_keyword', 'building_context'},
        'law_firms': {'law_firm_keyword', 'corporate_suffix', 'no_digit'},
        'address_lines': {'starts_with_digit', 'street_suffix', 'po_box_or_rr'},
        'address_modifiers': {'starts_with_digit', 'no_digit'},
        'building_names': {'building_keyword', 'building_context', 'no_digit'},
        'care_of': {'no_digit', 'corporate_suffix', 'company_keyword'},
        'parties': set(),  # parties can be anything
        'other_lines': set(),
    }

    for field_name in sorted(tally.keys()):
        dict_hits = tally[field_name]
        expected_dicts = expected.get(field_name, set())

        unexpected = {k: v for k, v in dict_hits.items() if k not in expected_dicts}

        if unexpected:
            print(f'  {field_name}:')
            for dict_name, count in sorted(unexpected.items(), key=lambda x: -x[1]):
                sample_list = samples[field_name][dict_name]
                sample_strs = [f'{rt}: "{t}"' for rt, t in sample_list[:3]]
                print(f'    {dict_name}: {count}')
                for s in sample_strs:
                    print(f'      {s}')
            print()

    # Summary of clean fields
    print(f'{"=" * 70}')
    print('Fields with NO unexpected dictionary matches:')
    for field_name in sorted(expected.keys()):
        dict_hits = tally.get(field_name, {})
        expected_dicts = expected.get(field_name, set())
        unexpected = {k: v for k, v in dict_hits.items() if k not in expected_dicts}
        if not unexpected:
            print(f'  {field_name}: CLEAN')


if __name__ == '__main__':
    main()
