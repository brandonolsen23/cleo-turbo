"""
Inventory manager — tracks which RT IDs we already have so we only
download what's missing.

Scans both raw-data/rt/ and clean-data/rt/ to build a complete set
of known RT IDs.
"""

import json
import os
import re


def load_existing_rt_ids(project_root):
    """Build a set of all RT IDs we already have (from any source).

    Checks:
      1. clean-data/rt/*.json  (compiled records — filename is RT ID)
      2. raw-data/rt/pages/**/detail_*.html  (raw detail pages — parse footer for RT ID)

    Returns a set of strings like {'RT100002', 'RT100003', ...}.
    """
    known = set()

    # 1. Clean data — fastest, one file per RT ID
    clean_dir = os.path.join(project_root, 'clean-data', 'rt')
    if os.path.isdir(clean_dir):
        for fname in os.listdir(clean_dir):
            if fname.endswith('.json') and fname.startswith('RT'):
                known.add(fname[:-5])  # strip .json

    # 2. Raw data detail pages — parse RT ID from footer
    #    This catches records that were scraped but failed pipeline processing
    raw_dir = os.path.join(project_root, 'raw-data', 'rt', 'pages')
    if os.path.isdir(raw_dir):
        for region_dir in os.listdir(raw_dir):
            region_path = os.path.join(raw_dir, region_dir)
            if not os.path.isdir(region_path):
                continue
            for prop_type in os.listdir(region_path):
                prop_path = os.path.join(region_path, prop_type)
                if not os.path.isdir(prop_path):
                    continue
                for page_dir in os.listdir(prop_path):
                    page_path = os.path.join(prop_path, page_dir)
                    if not os.path.isdir(page_path):
                        continue
                    # Check _page.json for saved RT IDs if available
                    page_meta = os.path.join(page_path, '_page.json')
                    if os.path.isfile(page_meta):
                        try:
                            with open(page_meta) as f:
                                meta = json.load(f)
                            # Some _page.json files have rt_ids list
                            if 'rt_ids' in meta:
                                known.update(meta['rt_ids'])
                                continue
                        except (json.JSONDecodeError, OSError):
                            pass

                    # Fallback: check export.json for RT IDs
                    export_path = os.path.join(page_path, 'export.json')
                    if os.path.isfile(export_path):
                        try:
                            with open(export_path) as f:
                                export = json.load(f)
                            # Export rows sometimes have rt_id field
                            if isinstance(export, list):
                                for row in export:
                                    if isinstance(row, dict) and 'rt_id' in row:
                                        known.add(row['rt_id'])
                        except (json.JSONDecodeError, OSError):
                            pass

    return known


def load_existing_rt_ids_fast(project_root):
    """Fast version — only checks clean-data/rt/ filenames.

    Use this when you just need a quick check and don't care about
    raw-data records that haven't been compiled yet.
    """
    known = set()
    clean_dir = os.path.join(project_root, 'clean-data', 'rt')
    if os.path.isdir(clean_dir):
        for fname in os.listdir(clean_dir):
            if fname.endswith('.json') and fname.startswith('RT'):
                known.add(fname[:-5])
    return known
