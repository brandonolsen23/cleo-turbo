"""
Address decomposition — thin re-export of the canonical decomposer.

The full 11-step decomposer that used to live here was PROMOTED verbatim to
cleo/address/decompose.py (2026-07-07) so that the RT and GW lanes share a
single source of truth for address decomposition (data-doctrine rule: no
copy-paste of decomposer logic). RT output is byte-identical to the
pre-promotion implementation — RT is the reference lane.

Everything importable from this module before the promotion is still
importable here, including the private helpers used by tests and tooling.

Reference: schema/address_normalization_plan.md § Address Decomposition
"""

from cleo.address.decompose import (  # noqa: F401
    decompose,
    _empty_result,
    _check_special_type,
    _extract_unit,
    _extract_street_number,
    _check_french_prefix_suffix,
    _scan_embedded_suffix,
    _build_display,
)
