#!/usr/bin/env python3
"""
Cleo Turbo Test Runner — runs all test suites in sequence.

Run from project root: python3 .claude/skills/test/scripts/run_all.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

TESTS = [
    ("Compiler Output Tests", SCRIPT_DIR / "test_compiler_output.py"),
    ("Data-Flow Trace Tests", SCRIPT_DIR / "test_data_flow.py"),
    ("API Response Shape Tests", SCRIPT_DIR / "test_api_shapes.py"),
]

any_failed = False

print("=" * 60)
print("Cleo Turbo — Full Test Suite")
print("=" * 60)
print()

for name, script in TESTS:
    if not script.exists():
        print(f"⚠ Skipping {name}: {script.name} not found")
        print()
        continue

    print(f"▶ Running {name}...")
    print()

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        any_failed = True

    print()

print("=" * 60)
if any_failed:
    print("✗ Some test suites had failures — review output above")
    sys.exit(1)
else:
    print("✓ All test suites passed!")
    sys.exit(0)
