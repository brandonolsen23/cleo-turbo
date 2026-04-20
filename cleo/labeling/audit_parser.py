"""Parser for docs/discovery-audit/{YYYY-MM-DD}/*.md audit files.

Reads the markdown table (one row per transaction_parties row) and
returns a structured list of distinct (source_id, side) parties that
can anchor a labeling session.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import re


@dataclass
class AuditFile:
    slug: str                    # e.g. "08-plazacorp"
    title: str                   # first H1 in the file
    date_folder: str             # e.g. "2026-04-19"
    path: Path
    parties: List[dict] = field(default_factory=list)


# Required column headers (lowercase)
_EXPECTED_COLS = {"group_id", "side", "party_name", "trade_name",
                  "care_of", "mailing", "phone", "source_id"}


def parse_audit_file(path: Path) -> AuditFile:
    """Parse a single audit markdown file.

    Returns an AuditFile with parties[] — one dict per table row.
    """
    text = path.read_text()
    slug = path.stem
    date_folder = path.parent.name

    # Title = first H1
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = m.group(1).strip() if m else slug

    # Find the table header row — line starting/ending with |, containing the expected columns
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if _EXPECTED_COLS.issubset(set(cells)):
            header_idx = i
            break

    parties: List[dict] = []
    if header_idx is None:
        return AuditFile(slug=slug, title=title, date_folder=date_folder,
                         path=path, parties=parties)

    header_cells = [c.strip().lower() for c in lines[header_idx].strip().strip("|").split("|")]

    # Data rows start after header + separator line
    for line in lines[header_idx + 2:]:
        if not line.lstrip().startswith("|"):
            break  # table ended
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(header_cells):
            continue
        row = dict(zip(header_cells, cells))
        if not row.get("source_id") or not row.get("side"):
            continue
        parties.append({
            "source_id": row["source_id"],
            "side": row["side"],
            "group_id": row.get("group_id", ""),
            "party_name": row.get("party_name", ""),
            "trade_name": row.get("trade_name", ""),
            "care_of": row.get("care_of", ""),
            "mailing": row.get("mailing", ""),
            "phone": row.get("phone", ""),
        })

    return AuditFile(slug=slug, title=title, date_folder=date_folder,
                     path=path, parties=parties)


def list_audits(docs_root: Path) -> List[AuditFile]:
    """List audits from the most recent date folder under docs_root.

    docs_root is typically `docs/discovery-audit/`.
    """
    if not docs_root.is_dir():
        return []

    # Find most recent date folder (YYYY-MM-DD format, lexical sort works)
    date_dirs = sorted(
        [p for p in docs_root.iterdir()
         if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", p.name)],
        reverse=True,
    )
    if not date_dirs:
        return []

    latest = date_dirs[0]
    results: List[AuditFile] = []
    for md in sorted(latest.glob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        results.append(parse_audit_file(md))
    return results


def load_audit_by_slug(docs_root: Path, slug: str) -> Optional[AuditFile]:
    """Load a single audit by slug from the most recent date folder."""
    for audit in list_audits(docs_root):
        if audit.slug == slug:
            return audit
    return None
