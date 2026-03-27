"""
Review report generator — reads classified JSON files from the
pipeline output and displays them in a browser-friendly HTML report
alongside the source HTML.

This file does NOT run the parser or classifier. It only reads what
the pipeline has already produced.

Usage:
    python3 review.py                          # show all classified records
    python3 review.py RT101601 RT57431         # show specific RT IDs
    python3 review.py --limit 20               # show first 20
"""

import json
import os
import sys
import re
import html as html_module
import argparse


def render_source_preview(detail_path):
    """Read the source HTML and render a simplified preview for display."""
    if not os.path.isfile(detail_path):
        return f'<p class="error">Source file not found: {html_module.escape(detail_path)}</p>'

    with open(detail_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    body_match = re.search(r'<body>(.*)</body>', html_content, re.DOTALL)
    body = body_match.group(1) if body_match else html_content
    body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL)
    body = re.sub(r'<div id="headerNav">.*?</div>', '', body, flags=re.DOTALL)
    body = re.sub(r'<div id="mygallery"[^>]*>.*?</div></div></div>', '', body, flags=re.DOTALL)
    body = re.sub(r'<a\s+[^>]*>', '<span class="link">', body)
    body = body.replace('</a>', '</span>')
    return body


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


def generate_record_html(classified_data, assembled_data):
    """Generate HTML for one classified record."""
    rt_id = classified_data['rt_id']

    # Source HTML preview
    detail_path = assembled_data['detail']['meta']['detail_path']
    source_preview = render_source_preview(detail_path)

    # Build right panel — all sections
    header = classified_data['header']
    sections = [
        ('address', header.get('address_entries', []), 'header-block'),
        ('sale info', {'date': header.get('sale_date'), 'price': header.get('sale_price'), 'city': header.get('city'), 'region': header.get('region'), 'note': header.get('transaction_note')}, 'header-block'),
        ('seller', classified_data['seller'], 'seller-block'),
        ('buyer', classified_data['buyer'], 'buyer-block'),
        ('description', classified_data['description'], 'desc-block'),
        ('site', classified_data['site'], 'site-block'),
        ('arn', classified_data['arn'], 'arn-block'),
        ('consideration', classified_data['consideration'], 'consid-block'),
        ('broker', classified_data['broker'], 'broker-block'),
        ('export', classified_data.get('export', {}), 'export-block'),
        ('results', classified_data.get('results', {}), 'results-block'),
    ]

    sections_html = ''
    for section_name, section_value, css_class in sections:
        sections_html += f'''
        <div class="section-block {css_class}" id="{rt_id}-{section_name}">
            <div class="section-header">
                <span class="section-name">{section_name}</span>
                <button class="flag-btn" onclick="toggleFlag(this, '{rt_id}', '{section_name}')" title="Flag">&#9873;</button>
            </div>
            <div class="section-content">{render_value(section_value)}</div>
            <div class="flag-note" style="display:none">
                <textarea placeholder="What's wrong?" oninput="updateNote('{rt_id}', '{section_name}', this.value)"></textarea>
            </div>
        </div>'''

    # Check for other_lines
    seller_other = classified_data.get('seller', {}).get('other_lines', [])
    buyer_other = classified_data.get('buyer', {}).get('other_lines', [])
    has_other = len(seller_other) + len(buyer_other) > 0
    other_badge = f'<span class="other-badge">{len(seller_other) + len(buyer_other)} unclassified</span>' if has_other else ''

    return f'''
    <div class="record-card" id="card-{rt_id}">
        <div class="record-header" onclick="toggleRecord('{rt_id}')">
            <h2>{rt_id}</h2>
            {other_badge}
            <span class="source-path">{html_module.escape(classified_data.get('source_folder', ''))}</span>
            <span class="toggle-icon">&#9660;</span>
        </div>
        <div class="record-body" id="body-{rt_id}" style="display:none">
            <div class="columns">
                <div class="col source-col">
                    <h3>Source HTML</h3>
                    <div class="source-content">{source_preview}</div>
                </div>
                <div class="col parsed-col">
                    <h3>Classified Output</h3>
                    <div class="parsed-content">{sections_html}</div>
                </div>
            </div>
            <div class="record-actions">
                <button class="approve-btn" onclick="approveRecord('{rt_id}')">Approve</button>
            </div>
        </div>
    </div>'''


def generate_report(file_pairs, output_path):
    """Generate the complete HTML review report."""
    records_html = ''
    errors = 0
    for classified_path, assembled_path in file_pairs:
        try:
            with open(classified_path) as f:
                classified = json.load(f)
            with open(assembled_path) as f:
                assembled = json.load(f)
            records_html += generate_record_html(classified, assembled)
        except Exception as e:
            errors += 1
            name = os.path.basename(classified_path)
            records_html += f'<div class="record-card error"><div class="record-header"><h2>ERROR: {html_module.escape(name)}</h2><span class="error-msg">{html_module.escape(str(e))}</span></div></div>'

    report_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Cleo Engine — Classified Data Review</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; padding: 20px; }}
    .toolbar {{ background: #1a1a2e; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
    .toolbar h1 {{ font-size: 18px; font-weight: 600; }}
    .toolbar-actions {{ display: flex; gap: 10px; }}
    .toolbar button {{ background: #e94560; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
    .toolbar .count {{ font-size: 14px; opacity: 0.8; }}

    .record-card {{ background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
    .record-card.approved {{ border-left: 4px solid #27ae60; }}
    .record-card.has-flags {{ border-left: 4px solid #e74c3c; }}
    .record-header {{ padding: 12px 20px; cursor: pointer; display: flex; align-items: center; gap: 15px; background: #fafafa; border-bottom: 1px solid #eee; }}
    .record-header:hover {{ background: #f0f0f0; }}
    .record-header h2 {{ font-size: 16px; font-weight: 600; color: #1a1a2e; }}
    .source-path {{ font-size: 11px; color: #888; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .toggle-icon {{ font-size: 12px; color: #888; }}
    .other-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 600; background: #f8d7da; color: #721c24; }}

    .record-body {{ padding: 0; }}
    .columns {{ display: flex; gap: 0; height: 80vh; }}
    .col {{ flex: 1; padding: 15px; overflow-y: auto; overflow-x: auto; }}
    .source-col {{ border-right: 2px solid #e0e0e0; background: #fefefe; font-size: 13px; }}
    .source-col h3, .parsed-col h3 {{ font-size: 13px; text-transform: uppercase; color: #888; margin-bottom: 10px; letter-spacing: 1px; position: sticky; top: 0; background: inherit; padding: 5px 0; z-index: 1; }}
    .parsed-col {{ background: #f8f9fa; }}
    .source-content {{ font-family: monospace; font-size: 12px; line-height: 1.6; word-wrap: break-word; }}
    .source-content strong {{ color: #1a1a2e; }}
    .source-content font[color="#848484"] {{ color: #848484; font-weight: bold; }}
    .source-content font[color="#CC0000"] {{ color: #CC0000; font-weight: bold; }}

    .section-block {{ margin-bottom: 8px; padding: 8px; border-radius: 4px; border: 1px solid transparent; }}
    .section-block:hover {{ border-color: #ddd; background: white; }}
    .section-block.flagged {{ border-color: #e74c3c; background: #fdf2f2; }}
    .section-block.seller-block {{ background: #f0f7ff; border-color: #cce0ff; }}
    .section-block.buyer-block {{ background: #f0fff4; border-color: #c6f6d5; }}
    .section-block.export-block {{ background: #e8f4f8; border-color: #bee5eb; }}
    .section-block.results-block {{ background: #fff3cd; border-color: #ffeeba; }}
    .section-block.consid-block {{ background: #fef9e7; border-color: #f9e79f; }}
    .section-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
    .section-name {{ font-weight: 600; font-size: 13px; color: #1a1a2e; }}
    .section-content {{ font-family: monospace; font-size: 12px; line-height: 1.5; padding-left: 12px; }}
    .flag-btn {{ background: none; border: none; cursor: pointer; font-size: 16px; opacity: 0.3; padding: 2px 6px; }}
    .flag-btn:hover {{ opacity: 0.7; }}
    .flag-btn.active {{ opacity: 1; color: #e74c3c; }}
    .flag-note textarea {{ width: 100%; height: 50px; margin-top: 5px; padding: 8px; border: 1px solid #e74c3c; border-radius: 4px; font-size: 12px; resize: vertical; }}

    .array-item {{ padding: 1px 0; }}
    .index {{ color: #888; font-size: 11px; }}
    .nested-field {{ padding: 2px 0 2px 12px; }}
    .field-name {{ color: #666; font-weight: 600; font-size: 11px; }}
    .empty {{ color: #bbb; font-style: italic; }}
    .empty-line {{ color: #ccc; font-style: italic; font-size: 11px; }}

    .record-actions {{ padding: 10px 15px; border-top: 1px solid #eee; text-align: right; }}
    .approve-btn {{ background: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
    .approve-btn:hover {{ background: #219a52; }}
    .approve-btn.approved {{ background: #888; cursor: default; }}
    .error {{ border-left: 4px solid #e74c3c; }}
    .error-msg {{ color: #e74c3c; font-size: 12px; }}
</style>
</head>
<body>
<div class="toolbar">
    <div>
        <h1>Cleo Engine — Classified Data Review</h1>
        <span class="count">{len(file_pairs)} records</span>
    </div>
    <div class="toolbar-actions">
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
function toggleFlag(btn, rtId, section) {{
    const block = btn.closest('.section-block');
    const noteDiv = block.querySelector('.flag-note');
    const isActive = btn.classList.toggle('active');
    block.classList.toggle('flagged', isActive);
    noteDiv.style.display = isActive ? 'block' : 'none';
    if (!isActive && feedback[rtId]) delete feedback[rtId][section];
    const card = document.getElementById('card-' + rtId);
    card.classList.toggle('has-flags', card.querySelectorAll('.flag-btn.active').length > 0);
}}
function updateNote(rtId, section, note) {{
    if (!feedback[rtId]) feedback[rtId] = {{}};
    feedback[rtId][section] = note;
}}
function approveRecord(rtId) {{
    approved.add(rtId);
    const card = document.getElementById('card-' + rtId);
    card.classList.add('approved');
    const btn = card.querySelector('.approve-btn');
    btn.textContent = 'Approved';
    btn.classList.add('approved');
}}
function exportFeedback() {{
    const data = {{ feedback, approved: Array.from(approved), exported_at: new Date().toISOString() }};
    const blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cleo-review-feedback.json';
    a.click();
}}
</script>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_html)

    print(f'Report saved to: {output_path}')
    print(f'Records: {len(file_pairs)}')


def find_files_by_rt_ids(rt_ids, classified_dir, assembled_dir):
    """Find classified + assembled file pairs by RT ID prefix matching."""
    pairs = []
    classified_files = os.listdir(classified_dir)
    assembled_files = os.listdir(assembled_dir)

    for rt_id in rt_ids:
        # Find matching classified file (filename starts with RT ID)
        c_match = [f for f in classified_files if f.startswith(rt_id + '__')]
        a_match = [f for f in assembled_files if f.startswith(rt_id + '__')]

        if c_match and a_match:
            pairs.append((
                os.path.join(classified_dir, c_match[0]),
                os.path.join(assembled_dir, a_match[0])
            ))
        else:
            print(f'WARNING: {rt_id} not found in classified output')

    return pairs


def main():
    parser = argparse.ArgumentParser(description='Generate review report from classified pipeline output')
    parser.add_argument('rt_ids', nargs='*', help='Specific RT IDs (e.g., RT101601)')
    parser.add_argument('--limit', type=int, help='Limit to first N records')
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path) as f:
        config = json.load(f)

    classified_dir = os.path.join(config['pipeline_output'], 'classified')
    assembled_dir = os.path.join(config['pipeline_output'], 'assembled')

    if not os.path.isdir(classified_dir):
        print(f'No classified data found at {classified_dir}')
        print('Run the classifier first.')
        sys.exit(1)

    if args.rt_ids:
        pairs = find_files_by_rt_ids(args.rt_ids, classified_dir, assembled_dir)
    else:
        classified_files = sorted([f for f in os.listdir(classified_dir) if f.endswith('.json')])
        if args.limit:
            classified_files = classified_files[:args.limit]
        pairs = []
        for cf in classified_files:
            cp = os.path.join(classified_dir, cf)
            ap = os.path.join(assembled_dir, cf)
            if os.path.isfile(ap):
                pairs.append((cp, ap))

    if not pairs:
        print('No records found.')
        sys.exit(1)

    output = os.path.join(os.path.dirname(__file__), 'reports', 'review.html')
    generate_report(pairs, output)


if __name__ == '__main__':
    main()
