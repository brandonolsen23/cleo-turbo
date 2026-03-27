"""
Review report generator — reads address normalizer output and displays it
in a browser-friendly HTML report for inspection.

Shows original addresses on the left and decomposed/normalized results on
the right, exactly like review.py but for the address normalization stage.

Usage:
    python3 review_decompose.py                     # show all records
    python3 review_decompose.py RT101601 RT57431    # show specific RT IDs
    python3 review_decompose.py --limit 50          # show first 50
    python3 review_decompose.py --ranges            # only range addresses
    python3 review_decompose.py --suites            # only addresses with suites
    python3 review_decompose.py --po-box            # only PO Box / RR
    python3 review_decompose.py --no-geocode        # only non-geocodable
"""

import json
import os
import sys
import html as html_module
import argparse


def render_value(value, depth=0):
    """Render a JSON value as formatted HTML."""
    if isinstance(value, list):
        if not value:
            return '<span class="empty">[ ]</span>'
        items = []
        for i, item in enumerate(value):
            if isinstance(item, (dict, list)):
                rendered = render_value(item, depth + 1)
            elif item == '':
                rendered = '<span class="empty-line">(empty)</span>'
            else:
                rendered = html_module.escape(str(item))
            items.append(f'<div class="array-item"><span class="index">[{i}]</span> {rendered}</div>')
        return '\n'.join(items)
    elif isinstance(value, dict):
        parts = []
        for k, v in value.items():
            parts.append(f'<div class="nested-field"><span class="field-name">{k}:</span> {render_value(v, depth + 1)}</div>')
        return '\n'.join(parts)
    elif value is None:
        return '<span class="empty">null</span>'
    elif value == '':
        return '<span class="empty">""</span>'
    elif isinstance(value, bool):
        color = '#27ae60' if value else '#e74c3c'
        return f'<span style="color:{color}; font-weight:bold">{str(value).lower()}</span>'
    else:
        return html_module.escape(str(value))


def render_original_address(classified_data):
    """Render the left panel — original raw addresses from classified data."""
    parts = []
    header = classified_data.get('header', {})

    parts.append('<div class="orig-section"><span class="orig-label">PROPERTY</span>')
    parts.append(f'<div class="orig-city">{html_module.escape(header.get("city", ""))} — {html_module.escape(header.get("region", ""))}</div>')
    for entry in header.get('address_entries', []):
        for line in entry.get('lines', []):
            parts.append(f'<div class="orig-line">{html_module.escape(line)}</div>')
        parts.append(f'<div class="orig-meta">type: {entry.get("type", "")} | geocodable: {entry.get("geocodable", "")}</div>')
    parts.append('</div>')

    for role in ['seller', 'buyer']:
        data = classified_data.get(role, {})
        addr = data.get('address', {})
        lines = addr.get('lines', [])
        city = addr.get('city', '')
        province = addr.get('province', '')
        postal = addr.get('postal', '')
        country = addr.get('country', '')
        modifiers = addr.get('modifiers', [])
        building_names = addr.get('building_names', [])

        parts.append(f'<div class="orig-section"><span class="orig-label">{role.upper()}</span>')
        if not lines and not city:
            parts.append('<div class="orig-empty">(no address)</div>')
        else:
            for line in lines:
                parts.append(f'<div class="orig-line">{html_module.escape(line)}</div>')
            if modifiers:
                for mod in modifiers:
                    parts.append(f'<div class="orig-modifier">{html_module.escape(mod)}</div>')
            if building_names:
                for bn in building_names:
                    parts.append(f'<div class="orig-building">{html_module.escape(bn)}</div>')
            loc_parts = [p for p in [city, province, postal] if p]
            if loc_parts:
                parts.append(f'<div class="orig-location">{html_module.escape(", ".join(loc_parts))}</div>')
            if country:
                parts.append(f'<div class="orig-country">{html_module.escape(country)}</div>')
        parts.append('</div>')

    # PIN / ARN
    site = classified_data.get('site', {})
    export = classified_data.get('export', {})
    pin = site.get('pin', '') or export.get('pin', '')
    arn = classified_data.get('arn', '') or export.get('rollno', '')
    if pin or arn:
        parts.append('<div class="orig-section"><span class="orig-label">IDENTIFIERS</span>')
        if pin:
            parts.append(f'<div class="orig-line">PIN: {html_module.escape(pin)}</div>')
        if arn:
            parts.append(f'<div class="orig-line">ARN: {html_module.escape(arn)}</div>')
        parts.append(f'<div class="orig-line">Export postal: {html_module.escape(export.get("postcode", ""))}</div>')
        parts.append('</div>')

    return '\n'.join(parts)


def render_address_block(addr, label, css_class):
    """Render a single normalized address section."""
    if isinstance(addr, dict) and 'addresses' in addr:
        # Property — multiple addresses possible
        parts = []
        for i, a in enumerate(addr['addresses']):
            tag = f'{label}' if len(addr['addresses']) == 1 else f'{label} [{i}]'
            parts.append(render_single_address(a, tag, css_class))
        # City/region/postal
        city = addr.get('city', '')
        region = addr.get('region', '')
        postal = addr.get('postal_from_export', '')
        if city or region or postal:
            meta = ' | '.join(p for p in [city, region, postal] if p)
            parts.append(f'<div class="addr-meta">{html_module.escape(meta)}</div>')
        return '\n'.join(parts)
    elif isinstance(addr, dict) and 'address' in addr:
        # Seller/buyer wrapper
        return render_contact_address(addr['address'], label, css_class)
    return ''


def render_single_address(a, label, css_class):
    """Render one normalized address entry."""
    parts = []
    parts.append(f'<div class="addr-block {css_class}">')
    parts.append(f'<div class="addr-label">{label}</div>')

    original = a.get('original', '')
    display = a.get('display', '')
    geocode = a.get('geocode_string', None)
    addr_type = a.get('type', '')
    geocodable = a.get('geocodable', False)
    keys = a.get('search_keys', [])
    variations = a.get('variations', [])
    comp = a.get('components', {})

    # Original → Display (the transformation)
    if original:
        changed = original != display
        arrow_class = 'changed' if changed else 'unchanged'
        parts.append(f'<div class="addr-transform {arrow_class}">')
        parts.append(f'<span class="addr-original">{html_module.escape(original)}</span>')
        parts.append(f'<span class="addr-arrow">&rarr;</span>')
        parts.append(f'<span class="addr-display">{html_module.escape(display)}</span>')
        parts.append('</div>')

    # Components
    comp_parts = []
    for field in ['street_number', 'street_name', 'street_suffix', 'street_direction', 'suite_type', 'suite_number']:
        val = comp.get(field, '')
        if val:
            comp_parts.append(f'<span class="comp-tag"><span class="comp-name">{field}:</span> {html_module.escape(val)}</span>')
    if comp_parts:
        parts.append(f'<div class="addr-components">{" ".join(comp_parts)}</div>')

    # Type + geocodable
    geo_icon = '&#10003;' if geocodable else '&#10007;'
    geo_class = 'geo-yes' if geocodable else 'geo-no'
    parts.append(f'<div class="addr-type"><span class="type-tag">{html_module.escape(addr_type)}</span> <span class="{geo_class}">{geo_icon} geocodable</span></div>')

    # Search keys
    if keys:
        keys_html = ' | '.join(f'<span class="search-key">{html_module.escape(k)}</span>' for k in keys)
        parts.append(f'<div class="addr-keys">keys: {keys_html}</div>')

    # Variations (for range/list addresses) — each with its own geocode
    if variations:
        var_parts = []
        for v in variations:
            vgeo = v.get('geocode_string', '')
            if vgeo:
                var_parts.append(f'<div class="variation-row"><span class="variation">{html_module.escape(v["display"])}</span> <span class="var-geocode">&rarr; {html_module.escape(vgeo)}</span></div>')
            else:
                var_parts.append(f'<div class="variation-row"><span class="variation">{html_module.escape(v["display"])}</span></div>')
        parts.append(f'<div class="addr-variations"><div class="var-label">variations (each geocoded):</div>{"".join(var_parts)}</div>')

    # Geocode string (main — for single addresses)
    elif geocode:
        parts.append(f'<div class="addr-geocode">geocode: <span class="geocode-str">{html_module.escape(geocode)}</span></div>')

    parts.append('</div>')
    return '\n'.join(parts)


def render_contact_address(addr, label, css_class):
    """Render a seller/buyer address block."""
    parts = []
    parts.append(f'<div class="addr-block {css_class}">')
    parts.append(f'<div class="addr-label">{label}</div>')

    display = addr.get('display', '')
    if not display:
        parts.append('<div class="addr-empty">(no address)</div>')
        parts.append('</div>')
        return '\n'.join(parts)

    original_lines = addr.get('original_lines', [])
    original = ' | '.join(original_lines) if original_lines else ''
    geocode = addr.get('geocode_string', None)
    keys = addr.get('search_keys', [])
    comp = addr.get('components', {})
    city = addr.get('city', '')
    province = addr.get('province', '')
    postal = addr.get('postal', '')
    country = addr.get('country', '')

    # Original → Display
    if original:
        changed = ' | '.join(original_lines) != display
        arrow_class = 'changed' if changed else 'unchanged'
        parts.append(f'<div class="addr-transform {arrow_class}">')
        parts.append(f'<span class="addr-original">{html_module.escape(original)}</span>')
        parts.append(f'<span class="addr-arrow">&rarr;</span>')
        parts.append(f'<span class="addr-display">{html_module.escape(display)}</span>')
        parts.append('</div>')

    # Components
    comp_parts = []
    for field in ['street_number', 'street_name', 'street_suffix', 'street_direction', 'suite_type', 'suite_number']:
        val = comp.get(field, '')
        if val:
            comp_parts.append(f'<span class="comp-tag"><span class="comp-name">{field}:</span> {html_module.escape(val)}</span>')
    if comp_parts:
        parts.append(f'<div class="addr-components">{" ".join(comp_parts)}</div>')

    # Location
    loc_parts = [p for p in [city, province, postal] if p]
    if loc_parts:
        parts.append(f'<div class="addr-location">{html_module.escape(", ".join(loc_parts))}</div>')
    if country:
        parts.append(f'<div class="addr-country">{html_module.escape(country)}</div>')

    # Search keys
    if keys:
        keys_html = ' | '.join(f'<span class="search-key">{html_module.escape(k)}</span>' for k in keys)
        parts.append(f'<div class="addr-keys">keys: {keys_html}</div>')

    # Geocode string
    if geocode:
        parts.append(f'<div class="addr-geocode">geocode: <span class="geocode-str">{html_module.escape(geocode)}</span></div>')

    parts.append('</div>')
    return '\n'.join(parts)


def render_pin_arn(address_data):
    """Render PIN/ARN section."""
    pin = address_data.get('pin', {})
    arn = address_data.get('arn', {})

    parts = []
    if pin.get('original') or arn.get('original'):
        parts.append('<div class="addr-block pin-block">')
        parts.append('<div class="addr-label">PIN / ARN</div>')

        if pin.get('original'):
            changed = pin['original'] != pin.get('api_format', '')
            arrow_class = 'changed' if changed else 'unchanged'
            multi = ' <span class="multi-badge">MULTIPLE</span>' if pin.get('multiple') else ''
            api = pin.get('api_format', '')
            if isinstance(api, list):
                api = ', '.join(api)
            parts.append(f'<div class="addr-transform {arrow_class}">PIN: <span class="addr-original">{html_module.escape(pin["original"])}</span> <span class="addr-arrow">&rarr;</span> <span class="addr-display">{html_module.escape(api)}</span>{multi}</div>')

        if arn.get('original'):
            parts.append(f'<div class="addr-transform changed">ARN: <span class="addr-original">{html_module.escape(arn["original"])}</span> <span class="addr-arrow">&rarr;</span> <span class="addr-display">{html_module.escape(arn.get("api_format", ""))}</span></div>')

        parts.append('</div>')

    return '\n'.join(parts)


def has_filter_match(address_data, filter_type):
    """Check if this record matches the given filter."""
    if filter_type == 'ranges':
        for a in address_data.get('property', {}).get('addresses', []):
            if a.get('variations'):
                return True
        return False
    elif filter_type == 'suites':
        for a in address_data.get('property', {}).get('addresses', []):
            if a.get('components', {}).get('suite_number'):
                return True
        for role in ['seller', 'buyer']:
            addr = address_data.get(role, {}).get('address', {})
            if addr.get('components', {}).get('suite_number'):
                return True
        return False
    elif filter_type == 'po_box':
        for a in address_data.get('property', {}).get('addresses', []):
            if a.get('type') in ('po_box', 'rural_route'):
                return True
        for role in ['seller', 'buyer']:
            addr = address_data.get(role, {}).get('address', {})
            comp = addr.get('components', {})
            if comp.get('suite_type') in ('PO Box', 'RR'):
                return True
        return False
    elif filter_type == 'no_geocode':
        for a in address_data.get('property', {}).get('addresses', []):
            if not a.get('geocodable'):
                return True
        return False
    return True


def generate_record_html(classified_data, address_data):
    """Generate HTML for one record."""
    rt_id = address_data['rt_id']

    # Left panel: original raw data
    left_html = render_original_address(classified_data)

    # Right panel: normalized addresses
    right_parts = []
    right_parts.append(render_address_block(address_data.get('property', {}), 'PROPERTY', 'prop-block'))
    right_parts.append(render_address_block(address_data.get('seller', {}), 'SELLER', 'seller-block'))
    right_parts.append(render_address_block(address_data.get('buyer', {}), 'BUYER', 'buyer-block'))
    right_parts.append(render_pin_arn(address_data))
    right_html = '\n'.join(right_parts)

    # Badges
    badges = []
    for a in address_data.get('property', {}).get('addresses', []):
        if a.get('variations'):
            badges.append('<span class="badge badge-range">RANGE</span>')
        if not a.get('geocodable'):
            badges.append('<span class="badge badge-nogeo">NO GEO</span>')
    for role in ['seller', 'buyer']:
        addr = address_data.get(role, {}).get('address', {})
        if addr.get('components', {}).get('suite_number'):
            badges.append(f'<span class="badge badge-suite">{role[0].upper()} SUITE</span>')
    badge_html = ' '.join(badges)

    source_folder = classified_data.get('source_folder', '')

    return f'''
    <div class="record-card" id="card-{rt_id}">
        <div class="record-header" onclick="toggleRecord('{rt_id}')">
            <h2>{rt_id}</h2>
            {badge_html}
            <span class="source-path">{html_module.escape(source_folder)}</span>
            <span class="toggle-icon">&#9660;</span>
        </div>
        <div class="record-body" id="body-{rt_id}" style="display:none">
            <div class="columns">
                <div class="col source-col">
                    <h3>Original (Classified)</h3>
                    <div class="source-content">{left_html}</div>
                </div>
                <div class="col parsed-col">
                    <h3>Normalized (Addresses)</h3>
                    <div class="parsed-content">{right_html}</div>
                </div>
            </div>
            <div class="record-actions">
                <button class="flag-btn-record" onclick="toggleFlag(this, '{rt_id}')" title="Flag for review">&#9873; Flag</button>
                <button class="approve-btn" onclick="approveRecord('{rt_id}')">Approve</button>
            </div>
        </div>
    </div>'''


def generate_report(file_triples, output_path, filter_type=None):
    """Generate the complete HTML review report."""
    records_html = ''
    total = 0
    filtered = 0
    errors = 0

    for classified_path, address_path in file_triples:
        try:
            with open(classified_path) as f:
                classified = json.load(f)
            with open(address_path) as f:
                address = json.load(f)
            total += 1

            if filter_type and not has_filter_match(address, filter_type):
                continue
            filtered += 1

            records_html += generate_record_html(classified, address)
        except Exception as e:
            errors += 1
            name = os.path.basename(classified_path)
            records_html += f'<div class="record-card error"><div class="record-header"><h2>ERROR: {html_module.escape(name)}</h2><span class="error-msg">{html_module.escape(str(e))}</span></div></div>'

    filter_label = ''
    if filter_type:
        filter_label = f' — filtered: {filter_type} ({filtered}/{total})'

    report_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Cleo Engine — Address Decomposition Review</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; padding: 20px; }}

    .toolbar {{ background: #1a1a2e; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
    .toolbar h1 {{ font-size: 18px; font-weight: 600; }}
    .toolbar .count {{ font-size: 14px; opacity: 0.8; }}
    .toolbar-actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .toolbar button {{ background: #e94560; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }}
    .toolbar button:hover {{ background: #c73a54; }}
    .toolbar .search-box {{ padding: 8px 12px; border: none; border-radius: 4px; font-size: 13px; width: 250px; }}

    .record-card {{ background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
    .record-card.approved {{ border-left: 4px solid #27ae60; }}
    .record-card.flagged {{ border-left: 4px solid #e74c3c; }}
    .record-header {{ padding: 12px 20px; cursor: pointer; display: flex; align-items: center; gap: 12px; background: #fafafa; border-bottom: 1px solid #eee; }}
    .record-header:hover {{ background: #f0f0f0; }}
    .record-header h2 {{ font-size: 16px; font-weight: 600; color: #1a1a2e; min-width: 90px; }}
    .source-path {{ font-size: 11px; color: #888; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .toggle-icon {{ font-size: 12px; color: #888; }}

    .badge {{ font-size: 10px; padding: 2px 7px; border-radius: 3px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }}
    .badge-range {{ background: #d4edda; color: #155724; }}
    .badge-nogeo {{ background: #f8d7da; color: #721c24; }}
    .badge-suite {{ background: #cce5ff; color: #004085; }}

    .record-body {{ padding: 0; }}
    .columns {{ display: flex; gap: 0; min-height: 300px; max-height: 80vh; }}
    .col {{ flex: 1; padding: 15px; overflow-y: auto; }}
    .source-col {{ border-right: 2px solid #e0e0e0; background: #fefefe; }}
    .source-col h3, .parsed-col h3 {{ font-size: 12px; text-transform: uppercase; color: #888; margin-bottom: 12px; letter-spacing: 1px; position: sticky; top: 0; background: inherit; padding: 5px 0; z-index: 1; }}
    .parsed-col {{ background: #f8f9fa; }}

    /* Left panel — original addresses */
    .orig-section {{ margin-bottom: 16px; padding: 10px; border-radius: 6px; background: #f8f9fa; }}
    .orig-label {{ display: inline-block; font-size: 11px; font-weight: 700; color: #555; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; padding: 2px 8px; border-radius: 3px; background: #e9ecef; }}
    .orig-line {{ font-family: monospace; font-size: 13px; line-height: 1.7; color: #1a1a2e; padding: 1px 0; }}
    .orig-city {{ font-size: 12px; color: #666; margin-bottom: 4px; }}
    .orig-location {{ font-size: 12px; color: #444; margin-top: 4px; }}
    .orig-country {{ font-size: 12px; color: #888; }}
    .orig-modifier {{ font-size: 12px; color: #6c757d; font-style: italic; }}
    .orig-building {{ font-size: 12px; color: #856404; }}
    .orig-meta {{ font-size: 10px; color: #aaa; margin-top: 2px; }}
    .orig-empty {{ font-size: 12px; color: #bbb; font-style: italic; }}

    /* Right panel — normalized addresses */
    .addr-block {{ margin-bottom: 16px; padding: 10px; border-radius: 6px; border: 1px solid #dee2e6; }}
    .prop-block {{ background: #fff; border-color: #b8daff; }}
    .seller-block {{ background: #f0f7ff; border-color: #cce0ff; }}
    .buyer-block {{ background: #f0fff4; border-color: #c6f6d5; }}
    .pin-block {{ background: #fff3cd; border-color: #ffeeba; }}
    .addr-label {{ font-size: 11px; font-weight: 700; color: #555; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px; }}
    .addr-empty {{ font-size: 12px; color: #bbb; font-style: italic; }}

    .addr-transform {{ font-family: monospace; font-size: 13px; line-height: 1.8; padding: 4px 8px; border-radius: 4px; margin-bottom: 6px; }}
    .addr-transform.changed {{ background: #d4edda; }}
    .addr-transform.unchanged {{ background: #f8f9fa; }}
    .addr-original {{ color: #888; text-decoration: line-through; }}
    .addr-arrow {{ color: #27ae60; font-weight: bold; margin: 0 6px; }}
    .addr-display {{ color: #155724; font-weight: 600; }}
    .addr-transform.unchanged .addr-original {{ text-decoration: none; color: #333; }}
    .addr-transform.unchanged .addr-arrow {{ display: none; }}
    .addr-transform.unchanged .addr-display {{ display: none; }}

    .addr-components {{ margin: 6px 0; display: flex; flex-wrap: wrap; gap: 4px; }}
    .comp-tag {{ font-size: 11px; padding: 2px 6px; border-radius: 3px; background: #e2e3e5; color: #383d41; font-family: monospace; }}
    .comp-name {{ color: #666; font-weight: 600; }}

    .addr-type {{ font-size: 11px; color: #666; margin: 4px 0; }}
    .type-tag {{ padding: 1px 6px; border-radius: 3px; background: #e9ecef; font-weight: 600; }}
    .geo-yes {{ color: #27ae60; }}
    .geo-no {{ color: #e74c3c; }}

    .addr-keys {{ font-size: 11px; color: #6c757d; margin: 4px 0; }}
    .search-key {{ font-family: monospace; background: #f8f9fa; padding: 1px 4px; border-radius: 2px; }}

    .addr-variations {{ font-size: 11px; color: #856404; margin: 6px 0; padding: 6px 8px; background: #fffbe6; border-radius: 4px; border: 1px solid #ffeeba; }}
    .var-label {{ font-weight: 600; margin-bottom: 4px; }}
    .variation-row {{ padding: 2px 0; }}
    .variation {{ font-family: monospace; background: #fff3cd; padding: 1px 4px; border-radius: 2px; font-weight: 600; }}
    .var-geocode {{ font-family: monospace; color: #004085; font-size: 10px; }}

    .addr-geocode {{ font-size: 11px; color: #004085; margin: 4px 0; }}
    .geocode-str {{ font-family: monospace; background: #cce5ff; padding: 1px 4px; border-radius: 2px; }}

    .addr-location {{ font-size: 12px; color: #444; margin: 4px 0; }}
    .addr-country {{ font-size: 12px; color: #888; }}
    .addr-meta {{ font-size: 11px; color: #888; margin-top: 4px; }}

    .multi-badge {{ font-size: 10px; padding: 1px 6px; border-radius: 3px; background: #f8d7da; color: #721c24; font-weight: 700; }}

    .record-actions {{ padding: 10px 15px; border-top: 1px solid #eee; text-align: right; display: flex; justify-content: flex-end; gap: 10px; }}
    .approve-btn {{ background: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
    .approve-btn:hover {{ background: #219a52; }}
    .approve-btn.done {{ background: #888; cursor: default; }}
    .flag-btn-record {{ background: none; border: 1px solid #e74c3c; color: #e74c3c; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
    .flag-btn-record:hover {{ background: #fdf2f2; }}
    .flag-btn-record.active {{ background: #e74c3c; color: white; }}

    .error {{ border-left: 4px solid #e74c3c; }}
    .error-msg {{ color: #e74c3c; font-size: 12px; }}
</style>
</head>
<body>
<div class="toolbar">
    <div>
        <h1>Cleo Engine — Address Decomposition Review</h1>
        <span class="count">{filtered} records{filter_label}</span>
    </div>
    <div class="toolbar-actions">
        <input type="text" class="search-box" placeholder="Search RT ID or address..." oninput="filterRecords(this.value)">
        <button onclick="expandAll()">Expand All</button>
        <button onclick="collapseAll()">Collapse All</button>
        <button onclick="exportFeedback()">Export Feedback</button>
    </div>
</div>

{records_html}

<script>
const feedback = {{}};
const approved = new Set();

function toggleRecord(rtId) {{
    const body = document.getElementById('body-' + rtId);
    body.style.display = body.style.display === 'none' ? 'block' : 'none';
}}
function expandAll() {{
    document.querySelectorAll('.record-body').forEach(el => el.style.display = 'block');
}}
function collapseAll() {{
    document.querySelectorAll('.record-body').forEach(el => el.style.display = 'none');
}}
function toggleFlag(btn, rtId) {{
    const isActive = btn.classList.toggle('active');
    const card = document.getElementById('card-' + rtId);
    card.classList.toggle('flagged', isActive);
    if (isActive) {{
        feedback[rtId] = feedback[rtId] || 'flagged';
    }} else {{
        delete feedback[rtId];
    }}
}}
function approveRecord(rtId) {{
    approved.add(rtId);
    const card = document.getElementById('card-' + rtId);
    card.classList.add('approved');
    const btn = card.querySelector('.approve-btn');
    btn.textContent = 'Approved';
    btn.classList.add('done');
}}
function filterRecords(query) {{
    const q = query.toLowerCase();
    document.querySelectorAll('.record-card').forEach(card => {{
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(q) ? '' : 'none';
    }});
}}
function exportFeedback() {{
    const data = {{ feedback, approved: Array.from(approved), exported_at: new Date().toISOString() }};
    const blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cleo-decompose-feedback.json';
    a.click();
}}
</script>
</body>
</html>'''

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_html)

    print(f'Report saved to: {output_path}')
    print(f'Records: {filtered}' + (f' (of {total} total)' if filter_type else ''))
    if errors:
        print(f'Errors: {errors}')


def main():
    parser = argparse.ArgumentParser(description='Generate address decomposition review report')
    parser.add_argument('rt_ids', nargs='*', help='Specific RT IDs (e.g., RT101601)')
    parser.add_argument('--limit', type=int, help='Limit to first N records')
    parser.add_argument('--ranges', action='store_true', help='Only range addresses')
    parser.add_argument('--suites', action='store_true', help='Only addresses with suites')
    parser.add_argument('--po-box', action='store_true', help='Only PO Box / RR')
    parser.add_argument('--no-geocode', action='store_true', help='Only non-geocodable')
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path) as f:
        config = json.load(f)

    classified_dir = os.path.join(config['pipeline_output'], 'classified')
    address_dir = os.path.join(config['pipeline_output'], 'addresses')

    if not os.path.isdir(address_dir):
        print(f'No address data found at {address_dir}')
        print('Run the address normalizer first: python -m address_normalizer.run')
        sys.exit(1)

    # Determine filter
    filter_type = None
    if args.ranges:
        filter_type = 'ranges'
    elif args.suites:
        filter_type = 'suites'
    elif args.po_box:
        filter_type = 'po_box'
    elif args.no_geocode:
        filter_type = 'no_geocode'

    if args.rt_ids:
        address_files = os.listdir(address_dir)
        pairs = []
        for rt_id in args.rt_ids:
            matches = [f for f in address_files if f.startswith(rt_id + '__')]
            for m in matches:
                cp = os.path.join(classified_dir, m)
                ap = os.path.join(address_dir, m)
                if os.path.isfile(cp) and os.path.isfile(ap):
                    pairs.append((cp, ap))
            if not matches:
                print(f'WARNING: {rt_id} not found')
    else:
        address_files = sorted([f for f in os.listdir(address_dir) if f.endswith('.json')])
        if args.limit:
            address_files = address_files[:args.limit]
        pairs = []
        for af in address_files:
            cp = os.path.join(classified_dir, af)
            ap = os.path.join(address_dir, af)
            if os.path.isfile(cp):
                pairs.append((cp, ap))

    if not pairs:
        print('No records found.')
        sys.exit(1)

    output = os.path.join(os.path.dirname(__file__), 'reports', 'review-decompose.html')
    generate_report(pairs, output, filter_type=filter_type)


if __name__ == '__main__':
    main()
