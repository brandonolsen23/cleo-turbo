"""
Detail page parser — reads one Realtrack detail HTML file and returns
a structural JSON record per schema/structural_complete_template.json.

Each section is parsed by its own function. The main parse_detail()
function orchestrates them all.
"""

import re
from parsers.normalize import decode_html, strip_tags, clean_line, split_br, split_p


# ---------------------------------------------------------------------------
# Section boundary helpers
# ---------------------------------------------------------------------------

# The grey section headers that divide the page
SECTION_LABELS = [
    'Transferor(s)',
    'Transferee(s)',
    'Description',
    'Site',
    'Assessment Roll Number',
    'Consideration',
    'Broker/Agent',
]


def _find_section(html, label):
    """Find the start position of a section by its grey-font label.

    Returns the index of the start of the section content (after the
    </font> tag and any <br /> that follows), or -1 if not found.
    """
    marker = f'<font color="#848484">{label}</font>'
    pos = html.find(marker)
    if pos == -1:
        return -1
    # Move past the marker
    return pos + len(marker)


def _section_content(html, label, next_labels=None):
    """Extract the raw HTML content of a section.

    Finds the section by label and returns everything from after the label
    to the start of the next section (or end of body). Returns empty string
    if section not found.
    """
    start = _find_section(html, label)
    if start == -1:
        return ''

    # Find the end: the next section header, or </body>
    end = len(html)
    search_after = start

    # Check all possible next sections
    if next_labels is None:
        next_labels = SECTION_LABELS

    for next_label in next_labels:
        marker = f'<font color="#848484">{next_label}</font>'
        pos = html.find(marker, search_after)
        if pos != -1 and pos < end:
            end = pos

    # Stop at navigation links (prev/next) — these always come after
    # the last section and before the footer
    nav_match = re.search(r'<a\s+href="\?page=details', html[search_after:])
    if nav_match:
        nav_pos = search_after + nav_match.start()
        if nav_pos < end:
            end = nav_pos

    # Also stop at the footer grey font tag (page position / RT ID)
    footer_match = re.search(
        r'<font color="#848484">\d+\s*/\s*\d+',
        html[search_after:]
    )
    if footer_match:
        footer_pos = search_after + footer_match.start()
        if footer_pos < end:
            end = footer_pos

    # Final fallback: </body>
    body_end = html.find('</body>', search_after)
    if body_end != -1 and body_end < end:
        end = body_end

    return html[start:end]


# ---------------------------------------------------------------------------
# Individual section parsers
# ---------------------------------------------------------------------------

def parse_footer(html):
    """Extract RT ID and page position from the footer.

    Footer pattern:
      <font color="#848484">N / M&nbsp;...&nbsp;RTXXXXX</font></body>
    """
    # Find the last grey font tag — that's always the footer
    pattern = r'<font color="#848484">(\d+ / \d+)[\s&nbsp;]+(RT\d+)</font>\s*</body>'
    # Need to handle &nbsp; entities in the spacing
    footer_match = re.search(
        r'<font color="#848484">(\d+\s*/\s*\d+)(?:&nbsp;|\s)+(RT\d+)</font>\s*</body>',
        html
    )
    if footer_match:
        page_position = clean_line(footer_match.group(1))
        rt_id = footer_match.group(2)
        return {
            'page_position': page_position,
            'rt_id': rt_id,
        }

    return {
        'page_position': '',
        'rt_id': '',
    }


def parse_header(html):
    """Extract address lines, city/region, date, price, and transaction note.

    HTML structure:
      <strong id="address">LINE1<br />LINE2<br />...</strong><br />
      City : Region<br />
      DD Mon YYYY&nbsp;&nbsp;$N,NNN,NNN&nbsp;&nbsp;<font color="#CC0000">Note</font>
    """
    result = {
        'address_lines': [],
        'city_region': '',
        'date_text': '',
        'price_text': '',
        'note': '',
    }

    # Extract address lines from <strong id="address">...</strong>
    addr_match = re.search(
        r'<strong id="address">(.*?)</strong>',
        html,
        re.DOTALL
    )
    if addr_match:
        addr_html = addr_match.group(1)
        result['address_lines'] = split_br(addr_html)

    # Get everything between </strong> and the Transferor section
    after_addr = ''
    strong_end = html.find('</strong>')
    if strong_end != -1:
        # Find the next section (Transferor or photos)
        tor_pos = html.find('<font color="#848484">Transferor(s)</font>', strong_end)
        photos_pos = html.find('<font color="#848484">street photos:', strong_end)
        aerial_pos = html.find('<font color="#848484">aerial photos:', strong_end)

        end_pos = tor_pos if tor_pos != -1 else len(html)
        if photos_pos != -1 and photos_pos < end_pos:
            end_pos = photos_pos
        if aerial_pos != -1 and aerial_pos < end_pos:
            end_pos = aerial_pos

        after_addr = html[strong_end + len('</strong>'):end_pos]

    # Parse the header text after the address
    # Clean it up — decode entities, strip tags
    header_text = decode_html(after_addr)
    header_text = header_text.replace('\r', '')

    # City : Region is on the first <br /> separated line after </strong>
    header_parts = re.split(r'<br\s*/?\s*>', after_addr)

    for part in header_parts:
        cleaned = clean_line(part)
        if not cleaned:
            continue

        # City : Region line — contains a colon with text on both sides
        if ':' in cleaned and not result['city_region'] and not cleaned.startswith('$'):
            result['city_region'] = cleaned
            continue

        # Date and price line — starts with DD Mon YYYY pattern
        date_match = re.match(r'(\d{1,2}\s+\w{3}\s+\d{4})', cleaned)
        if date_match and not result['date_text']:
            result['date_text'] = date_match.group(1)

            # Price follows the date, separated by spaces
            price_match = re.search(r'(\$[\d,]+)', cleaned)
            if price_match:
                result['price_text'] = price_match.group(1)
            continue

    # Transaction note from red font tag
    note_match = re.search(
        r'<font color="#CC0000">(.*?)</font>',
        after_addr
    )
    if note_match:
        result['note'] = clean_line(note_match.group(1))

    return result


def _parse_party_block(html, label):
    """Parse a Transferor(s) or Transferee(s) block.

    HTML structure:
      <font color="#848484">Label</font><br />
      Party Line 1<br />
      Party Line 2&nbsp; &nbsp; &nbsp;phone<br />
      <em>Trade Name</em>
      <p />
      Contact Line 1<br />
      Contact Line 2<br />
      City, Province<br />
      Postal Code
      <p />

    Named Individual(s) variant:
      <font color="#848484">Label</font><br />
      Named Individual(s)
      <p />
    """
    result = {
        'party_lines': [],
        'trade_name': '',
        'contact_lines': [],
    }

    section_start = _find_section(html, label)
    if section_start == -1:
        return result

    # Determine end of this block — next section header or next grey font
    # For Transferor, end is Transferee. For Transferee, end is Description/Site/etc.
    if label == 'Transferor(s)':
        next_section = _find_section(html, 'Transferee(s)')
        if next_section == -1:
            return result
        # Back up to find the font tag
        block_end = html.rfind('<font color="#848484">Transferee(s)', section_start, next_section + 50)
    else:
        # Transferee — end is the next section (Description, Site, or wherever)
        block_end = len(html)
        for next_label in ['Description', 'Site', 'Assessment Roll Number', 'Consideration']:
            pos = html.find(f'<font color="#848484">{next_label}</font>', section_start)
            if pos != -1 and pos < block_end:
                block_end = pos

    block_html = html[section_start:block_end]

    # Check for Named Individual(s) — simple case, no em tag, no contact block
    if 'Named Individual(s)' in block_html and '<em>' not in block_html:
        result['party_lines'] = ['Named Individual(s)']
        return result

    # Find the <em> tag — it separates party lines from contact lines
    em_match = re.search(r'<em>(.*?)</em>', block_html)

    if em_match:
        # Party lines: from start of content to <em> tag
        party_html = block_html[:em_match.start()]
        # Skip the leading <br />
        party_html = re.sub(r'^\s*<br\s*/?\s*>', '', party_html)
        result['party_lines'] = split_br(party_html)

        # Trade name from <em> content
        trade = clean_line(em_match.group(1))
        result['trade_name'] = trade

        # Contact lines: after </em><p/> to the next <p/>
        after_em = block_html[em_match.end():]
        # Split on <p /> — first segment is empty or whitespace (between em and first p),
        # second segment is the contact block
        p_blocks = re.split(r'<p\s*/?\s*>', after_em)
        if len(p_blocks) >= 2:
            contact_html = p_blocks[1]
            result['contact_lines'] = split_br(contact_html)
    else:
        # No <em> tag but not Named Individual(s) — unusual but handle it
        # Split on first <p /> to separate party lines from contact lines
        p_blocks = re.split(r'<p\s*/?\s*>', block_html)
        if p_blocks:
            party_html = p_blocks[0]
            party_html = re.sub(r'^\s*<br\s*/?\s*>', '', party_html)
            result['party_lines'] = split_br(party_html)
        if len(p_blocks) >= 2:
            result['contact_lines'] = split_br(p_blocks[1])

    # Clean up: remove empty trailing entries
    while result['party_lines'] and result['party_lines'][-1] == '':
        result['party_lines'].pop()
    while result['contact_lines'] and result['contact_lines'][-1] == '':
        result['contact_lines'].pop()

    return result


def parse_transferor(html):
    """Parse the Transferor(s) section."""
    return _parse_party_block(html, 'Transferor(s)')


def parse_transferee(html):
    """Parse the Transferee(s) section."""
    return _parse_party_block(html, 'Transferee(s)')


def parse_description(html):
    """Extract description lines from the Description section.

    Returns a list of strings. Empty list if no Description section.
    """
    content = _section_content(html, 'Description',
                                next_labels=['Site', 'Assessment Roll Number',
                                             'Consideration', 'Broker/Agent'])
    if not content:
        return []

    # Remove the leading <br /> after the section header
    content = re.sub(r'^\s*<br\s*/?\s*>', '', content)

    # Remove "more info:" link from description lines (captured separately)
    content = re.sub(r'more info:.*?</a>', '', content, flags=re.DOTALL)

    lines = split_p(content)

    # Strip trailing empty lines
    while lines and lines[-1] == '':
        lines.pop()

    return lines


def parse_more_info(html):
    """Extract the 'more info:' PDF URL if present.

    Can appear in the Description section or after the Transferee contact block.
    """
    match = re.search(
        r"window\.open\('(/assets/files/[^']+)'",
        html
    )
    if match:
        return match.group(1)
    return ''


def parse_site(html):
    """Extract site lines from the Site section.

    Contains legal descriptions, PIN, acreage, location, Except blocks.
    All captured as a flat line array.
    """
    content = _section_content(html, 'Site',
                                next_labels=['Assessment Roll Number',
                                             'Consideration', 'Broker/Agent'])
    if not content:
        return []

    # Remove leading <br />
    content = re.sub(r'^\s*<br\s*/?\s*>', '', content)

    lines = split_p(content)

    # Strip trailing empty lines
    while lines and lines[-1] == '':
        lines.pop()

    return lines


def parse_arn(html):
    """Extract assessment roll number text.

    Returns the raw ARN string or empty string if section not present.
    """
    content = _section_content(html, 'Assessment Roll Number',
                                next_labels=['Consideration', 'Broker/Agent'])
    if not content:
        return ''

    # Remove leading <br />
    content = re.sub(r'^\s*<br\s*/?\s*>', '', content)

    # ARN is typically a single line
    text = clean_line(content)

    # Remove any trailing <p /> artifacts
    text = re.sub(r'<p\s*/?\s*>', '', text).strip()
    text = strip_tags(text).strip()

    return text


def parse_consideration(html):
    """Extract consideration lines from the Consideration section.

    Contains cash/debt line, optional chattels/other, and chargee blocks.
    All captured as a flat line array.
    """
    content = _section_content(html, 'Consideration',
                                next_labels=['Broker/Agent'])
    if not content:
        return []

    # Remove leading <br />
    content = re.sub(r'^\s*<br\s*/?\s*>', '', content)

    # Remove prev/next navigation links that might be caught at the end
    content = re.sub(r'<a\s+href="\?page=details[^"]*">[^<]*</a>', '', content)

    lines = split_p(content)

    # Strip trailing empty lines
    while lines and lines[-1] == '':
        lines.pop()

    return lines


def parse_broker(html):
    """Extract broker lines from the Broker/Agent section.

    Returns list of broker entries. Empty list if section not present.
    """
    content = _section_content(html, 'Broker/Agent',
                                next_labels=[])  # Broker is always last section
    if not content:
        return []

    # Remove leading <br />
    content = re.sub(r'^\s*<br\s*/?\s*>', '', content)

    # Remove prev/next navigation links
    content = re.sub(r'<a\s+href="\?page=details[^"]*">[^<]*</a>', '', content)

    lines = split_p(content)

    # Strip trailing empty lines
    while lines and lines[-1] == '':
        lines.pop()

    return lines


def parse_photos(html):
    """Extract photo URLs from the three possible photo formats.

    1. Street photos: carousel gallery images from realtrack.cachefly.net
    2. Aerial photos: shadowbox links to /assets/files/.../airN.jpg
    3. Standalone photo: older single-image format
    """
    result = {
        'street_photo_urls': [],
        'aerial_photo_urls': [],
        'standalone_photo_url': '',
    }

    # Street photos from carousel
    result['street_photo_urls'] = re.findall(
        r'<img src="(http://realtrack\.cachefly\.net/photos/[^"]+)"',
        html
    )

    # Aerial photos from shadowbox
    result['aerial_photo_urls'] = re.findall(
        r'href="(/assets/files/[^"]+)"[^>]*rel="shadowbox\[aerials\]"',
        html
    )

    # Standalone photo (older format)
    standalone_match = re.search(
        r"<img src='(/assets/files/[^']+)'[^>]*alt=\"Photo\"",
        html
    )
    if standalone_match:
        result['standalone_photo_url'] = standalone_match.group(1)

    return result


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def parse_detail(html_path, source_folder=None, position=None):
    """Parse a detail HTML file and return the complete structural record.

    Args:
        html_path: absolute path to the detail HTML file
        source_folder: region/type/page path (e.g., 'Peel_Region/industrial/p032')
                       If None, derived from html_path.
        position: 0-based position within folder (from filename detail_NNN.html)
                  If None, derived from html_path.

    Returns:
        dict matching schema/structural_complete_template.json
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Derive position from filename if not provided
    if position is None:
        import os
        filename = os.path.basename(html_path)
        pos_match = re.match(r'detail_(\d+)\.html', filename)
        if pos_match:
            position = int(pos_match.group(1))

    # Derive source_folder from path if not provided
    if source_folder is None:
        import os
        # Path structure: .../pages/Region/type/pageNNN/detail_NNN.html
        parts = html_path.replace('\\', '/').split('/')
        try:
            pages_idx = parts.index('pages')
            source_folder = '/'.join(parts[pages_idx + 1: pages_idx + 4])
        except (ValueError, IndexError):
            source_folder = ''

    # Parse each section independently
    footer = parse_footer(html)
    header = parse_header(html)
    transferor = parse_transferor(html)
    transferee = parse_transferee(html)
    description = parse_description(html)
    more_info = parse_more_info(html)
    site = parse_site(html)
    arn = parse_arn(html)
    consideration = parse_consideration(html)
    broker = parse_broker(html)
    photos = parse_photos(html)

    return {
        'meta': {
            'rt_id': footer['rt_id'],
            'source_folder': source_folder,
            'position': position,
            'detail_path': html_path,
        },
        'header': header,
        'transferor': transferor,
        'transferee': transferee,
        'description_lines': description,
        'more_info_url': more_info,
        'site_lines': site,
        'arn_text': arn,
        'consideration_lines': consideration,
        'broker_lines': broker,
        'photos': photos,
        'footer': footer,
    }
