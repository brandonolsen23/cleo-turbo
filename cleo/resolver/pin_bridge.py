"""
PIN→ARN Bridge — resolve PINs to ARNs using GeoWarehouse lookup data.

Zero API calls — purely local data lookup from clean-data/gw/.
"""

import json
import os
from typing import Optional

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
GW_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')


def build_gw_pin_to_arn() -> dict[str, str]:
    """Load GW clean records and build PIN → ARN lookup table.

    Returns:
        Dict mapping PIN strings to 20-digit ARN strings.
        Uses first valid ARN per PIN.
    """
    pin_to_arn: dict[str, str] = {}

    if not os.path.isdir(GW_DIR):
        return pin_to_arn

    for fname in os.listdir(GW_DIR):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        try:
            with open(os.path.join(GW_DIR, fname)) as f:
                gw = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        pin = gw.get('pin', '').strip()
        if not pin:
            continue

        for assessment in gw.get('assessments', []):
            arn = assessment.get('arn_api', '').strip()
            if arn and not all(c == '0' for c in arn):
                pin_to_arn[pin] = arn
                break  # Use first valid ARN

    return pin_to_arn


def lookup_pin(pin: str, pin_to_arn: dict[str, str]) -> Optional[str]:
    """Look up a PIN in the GW bridge table.

    Args:
        pin: 9-digit PIN string.
        pin_to_arn: Pre-built lookup table from build_gw_pin_to_arn().

    Returns:
        20-digit ARN string, or None if no match.
    """
    if not pin or not pin.strip():
        return None
    return pin_to_arn.get(pin.strip())
