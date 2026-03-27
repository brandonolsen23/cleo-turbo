"""
Shared normalization for all parsers.

Rules:
  - Decode HTML entities (&nbsp; → space, &amp; → &, &#39; → ', etc.)
  - Trim leading/trailing whitespace from each line
  - Strip \r characters (normalize to Unix line endings)
  - Preserve internal multi-space runs (they carry signal for classification)
  - Drop empty-string lines that are purely HTML formatting artifacts
    (but preserve intentional blank lines represented as empty strings in arrays)
"""

import html as html_module
import re


def decode_html(text):
    """Decode HTML entities to plain text.

    Handles both named entities (&amp; &nbsp; &lt; &gt; &quot;)
    and numeric entities (&#39; &#233; &#8217; &#160;).

    &nbsp; (and &#160;) become regular ASCII space (U+0020),
    not Unicode non-breaking space (U+00A0).
    """
    # First pass: convert &nbsp; and &#160; to regular space explicitly
    # (html.unescape would convert them to U+00A0 which we don't want)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&#160;', ' ')

    # Second pass: let Python's html module handle everything else
    text = html_module.unescape(text)

    # Belt and suspenders: if any U+00A0 snuck through, convert to regular space
    text = text.replace('\u00a0', ' ')

    return text


def strip_tags(text):
    """Remove all HTML tags from text, leaving just the content."""
    return re.sub(r'<[^>]+>', '', text)


def clean_line(text):
    """Apply full normalization to a single line of extracted text."""
    text = decode_html(text)
    text = strip_tags(text)
    text = text.replace('\r', '')
    text = text.strip()
    return text


def split_br(html_fragment):
    """Split an HTML fragment on <br /> tags and return cleaned lines.

    Returns a list of strings. Each string is the cleaned text between
    consecutive <br /> tags. Trailing empty lines are stripped.
    """
    # Split on <br /> variations
    parts = re.split(r'<br\s*/?\s*>', html_fragment)
    lines = [clean_line(p) for p in parts]

    # Strip trailing empty lines (but keep internal empty lines)
    while lines and lines[-1] == '':
        lines.pop()

    return lines


def split_p(html_fragment):
    """Split an HTML fragment on <p /> tags and return cleaned lines.

    Each <p /> separated block is further split by <br />.
    Returns a flat list of strings with empty strings marking paragraph breaks.
    """
    blocks = re.split(r'<p\s*/?\s*>', html_fragment)
    lines = []
    for i, block in enumerate(blocks):
        if i > 0 and lines:
            lines.append('')  # paragraph break marker
        block_lines = split_br(block)
        lines.extend(block_lines)

    # Strip trailing empty lines
    while lines and lines[-1] == '':
        lines.pop()

    return lines
