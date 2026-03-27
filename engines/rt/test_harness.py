"""
Test harness — runs the detail parser AND classifier against approved fixtures
and reports pass/fail in plain English.

Tests both:
  - structural.approved.json (parser output)
  - classified.approved.json (classifier output)

Usage:
    python3 test_harness.py              # run all fixtures
    python3 test_harness.py RT101601     # run one fixture
"""

import json
import os
import sys

from parsers.detail import parse_detail
from classifier.classify import classify_record
from assembler import assemble_record


def compare_values(expected, actual, path=''):
    """Recursively compare two values and return a list of differences.

    Returns list of (field_path, expected_value, actual_value) tuples.
    """
    diffs = []

    if isinstance(expected, dict) and isinstance(actual, dict):
        all_keys = set(list(expected.keys()) + list(actual.keys()))
        for key in sorted(all_keys):
            if key.startswith('_'):
                continue  # Skip comment fields
            child_path = f'{path}.{key}' if path else key
            if key not in expected:
                diffs.append((child_path, '(missing)', actual[key]))
            elif key not in actual:
                diffs.append((child_path, expected[key], '(missing)'))
            else:
                diffs.extend(compare_values(expected[key], actual[key], child_path))

    elif isinstance(expected, list) and isinstance(actual, list):
        max_len = max(len(expected), len(actual))
        for i in range(max_len):
            child_path = f'{path}[{i}]'
            if i >= len(expected):
                diffs.append((child_path, '(missing)', actual[i]))
            elif i >= len(actual):
                diffs.append((child_path, expected[i], '(missing)'))
            elif expected[i] != actual[i]:
                diffs.append((child_path, expected[i], actual[i]))

    else:
        if expected != actual:
            diffs.append((path, expected, actual))

    return diffs


def run_fixture(fixture_dir):
    """Run the parser against one fixture and return results.

    Returns:
        dict with 'rt_id', 'passed', 'total_fields', 'diffs'
    """
    # Read approved output
    approved_path = os.path.join(fixture_dir, 'structural.approved.json')
    with open(approved_path) as f:
        expected = json.load(f)

    # Run parser on source HTML
    detail_path = os.path.join(fixture_dir, 'detail.html')
    actual = parse_detail(
        detail_path,
        source_folder=expected['meta']['source_folder'],
        position=expected['meta']['position']
    )

    # Override detail_path since fixture copy is in a different location
    actual['meta']['detail_path'] = expected['meta']['detail_path']

    # Compare
    diffs = compare_values(expected, actual)

    rt_id = expected['meta']['rt_id']
    return {
        'rt_id': rt_id,
        'passed': len(diffs) == 0,
        'diffs': diffs,
    }


def run_classified_fixture(fixture_dir):
    """Run the classifier against one fixture and return results."""
    approved_path = os.path.join(fixture_dir, 'classified.approved.json')
    with open(approved_path) as f:
        expected = json.load(f)

    # Run parser then classifier
    detail_path = os.path.join(fixture_dir, 'detail.html')
    structural = parse_detail(
        detail_path,
        source_folder=expected.get('source_folder', ''),
        position=expected.get('position', 0)
    )

    # Build a minimal assembled record for the classifier
    assembled = {
        'rt_id': expected.get('rt_id', ''),
        'source_folder': expected.get('source_folder', ''),
        'position': expected.get('position', 0),
        'join_verified': True,
        'detail': structural,
        'export': expected.get('export'),
        'results': expected.get('results'),
    }

    actual = classify_record(assembled)

    # Compare only seller and buyer (the classified parts)
    diffs = []
    for section in ['seller', 'buyer']:
        if section in expected and section in actual:
            section_diffs = compare_values(expected[section], actual[section], section)
            diffs.extend(section_diffs)

    rt_id = expected.get('rt_id', '')
    return {
        'rt_id': rt_id,
        'passed': len(diffs) == 0,
        'diffs': diffs,
    }


def main():
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')

    # Which fixtures to run
    if len(sys.argv) > 1:
        fixture_names = sys.argv[1:]
    else:
        fixture_names = sorted([
            d for d in os.listdir(fixtures_dir)
            if os.path.isdir(os.path.join(fixtures_dir, d)) and d.startswith('RT')
        ])

    if not fixture_names:
        print('No fixtures found.')
        return

    print(f'Running {len(fixture_names)} fixtures...')
    print()

    passed = 0
    failed = 0
    failures = []

    for name in fixture_names:
        fixture_dir = os.path.join(fixtures_dir, name)
        if not os.path.isdir(fixture_dir):
            print(f'  {name}: SKIP (not found)')
            continue

        # Run structural test (if structural fixture exists)
        structural_path = os.path.join(fixture_dir, 'structural.approved.json')
        if os.path.isfile(structural_path):
            result = run_fixture(fixture_dir)
        else:
            result = {'rt_id': name, 'passed': True, 'diffs': []}

        # Run classified test if fixture exists
        classified_path = os.path.join(fixture_dir, 'classified.approved.json')
        if os.path.isfile(classified_path):
            c_result = run_classified_fixture(fixture_dir)
            if not c_result['passed']:
                result['passed'] = False
                result['diffs'].extend(
                    [('CLASSIFIED: ' + d[0], d[1], d[2]) for d in c_result['diffs']]
                )

        if result['passed']:
            print(f'  {result["rt_id"]}: PASS')
            passed += 1
        else:
            print(f'  {result["rt_id"]}: FAIL ({len(result["diffs"])} differences)')
            for field, exp, act in result['diffs']:
                exp_str = json.dumps(exp) if not isinstance(exp, str) else exp
                act_str = json.dumps(act) if not isinstance(act, str) else act
                if len(exp_str) > 60:
                    exp_str = exp_str[:60] + '...'
                if len(act_str) > 60:
                    act_str = act_str[:60] + '...'
                print(f'    {field}:')
                print(f'      expected: {exp_str}')
                print(f'      got:      {act_str}')
            failed += 1
            failures.append(result)

    print()
    print(f'Results: {passed} passed, {failed} failed, {passed + failed} total')

    if failed == 0:
        print('All fixtures passed.')
    else:
        print(f'{failed} fixture(s) failed.')
        sys.exit(1)


if __name__ == '__main__':
    main()
