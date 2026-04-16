"""
Shared address formatting module for Cleo Turbo.

All address display formatting goes through this module, regardless of source
(RT, GW, or OSM). Individual pipelines handle source-specific parsing and
decomposition, then call format_display() to produce a canonical display string.

Usage:
    from cleo.address import format_display, normalize_street_name

    # From structured components (RT decomposer, or GW/OSM after parsing):
    display = format_display({
        'street_number': '732-746',
        'street_name': 'Tenth',
        'street_suffix': 'Street',
        'street_direction': '',
        'suite_type': '',
        'suite_number': '',
    })
    # → "732-746 Tenth Street"

    # Normalize a raw street string (for GW/OSM that don't decompose):
    from cleo.address.decompose import decompose_simple
    components = decompose_simple("732-746 10TH ST E")
    display = format_display(components)
    # → "732-746 Tenth Street East"
"""

from .formatter import format_display
from .normalize import normalize_street_name
