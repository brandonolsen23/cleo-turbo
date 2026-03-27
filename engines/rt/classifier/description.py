"""
Description classifier — joins lines into a single string.

Reference: schema/engine_reference.md — DESCRIPTION SECTION
"""


def classify_description(description_lines, more_info_url=''):
    """Classify description — just join lines.

    Args:
        description_lines: list of strings from structural extraction
        more_info_url: URL path to more info PDF if present

    Returns:
        dict with description text and more_info_url
    """
    return {
        'description': '\n'.join(description_lines) if description_lines else '',
        'more_info_url': more_info_url,
    }
