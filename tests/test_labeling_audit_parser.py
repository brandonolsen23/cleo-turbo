"""Tests for audit markdown parser."""

import pytest
from pathlib import Path
from cleo.labeling.audit_parser import parse_audit_file, list_audits, AuditFile


def _write_fixture(tmp_path, content):
    d = tmp_path / "2026-04-19"
    d.mkdir()
    f = d / "08-plazacorp.md"
    f.write_text(content)
    return tmp_path


def test_parse_audit_extracts_parties_from_table(tmp_path):
    content = """# Plazacorp Investments Ltd

Some prose.

| group_id | side | party_name | trade_name | care_of | mailing | phone | source_id |
|---|---|---|---|---|---|---|---|
| GRP_01099 | buyer | Widmer Residences Corp | Plazacorp Investments Ltd |  | 10 Wanless | 416-481-2222 | RT101184 |
|  | buyer |  | Plazacorp Investments Ltd |  | 10 Wanless | 416-481-2222 | RT101911 |
| GRP_01867 | seller | 503-507 Bloor Street West Ltd | Plazacorp |  | 10 Wanless | 416-481-2222 | RT64069 |
"""
    docs_root = _write_fixture(tmp_path, content)

    result = parse_audit_file(docs_root / "2026-04-19" / "08-plazacorp.md")

    assert result.slug == "08-plazacorp"
    assert result.title == "Plazacorp Investments Ltd"
    assert len(result.parties) == 3
    assert result.parties[0] == {
        "source_id": "RT101184", "side": "buyer",
        "group_id": "GRP_01099", "party_name": "Widmer Residences Corp",
        "trade_name": "Plazacorp Investments Ltd", "care_of": "",
        "mailing": "10 Wanless", "phone": "416-481-2222",
    }
    # Blank group_id preserved as empty string, not dropped
    assert result.parties[1]["group_id"] == ""
    assert result.parties[1]["source_id"] == "RT101911"


def test_list_audits_returns_most_recent_date_folder(tmp_path):
    old = tmp_path / "2026-03-01"
    new = tmp_path / "2026-04-19"
    old.mkdir()
    new.mkdir()
    (new / "01-kingsett-capital.md").write_text("# KingSett Capital\n\n| source_id |\n|---|\n| RT1 |\n")
    (new / "README.md").write_text("# README")
    (old / "01-something.md").write_text("# Something\n\n| source_id |\n|---|\n| RT2 |\n")

    audits = list_audits(tmp_path)

    assert len(audits) == 1
    assert audits[0].slug == "01-kingsett-capital"
    assert audits[0].date_folder == "2026-04-19"
