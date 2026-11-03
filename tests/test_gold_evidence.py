"""근거는 v19 엔트리 컬럼이 아니라 섹션 창이다."""

from __future__ import annotations

import sqlite3

from dart_parser.gold.db import open_gold
from dart_parser.gold.evidence import annotate_cells, evidence_for, find_cells, section_windows


def test_section_windows_follow_the_field_map() -> None:
    assert section_windows("company_name") == ("cover",)
    assert section_windows("opinion") == ("opinion_letter",)
    assert section_windows("hours") == ("exhibit4_hours",)
    assert section_windows("accounts") == ("bs", "is_")
    assert section_windows("icfr") == ("icfr_opinion",)
    assert section_windows("notes_toc") == ("notes_toc",)
    assert section_windows("subsidiary") == ("subsidiaries",)


def test_annotate_and_find() -> None:
    html = "<table><tr><td>재고자산</td><td>1,234</td><td>999</td></tr></table>"
    marked = annotate_cells(html)
    assert 'data-t="0" data-r="0" data-c="1"' in marked
    assert find_cells(marked, "1,234", "재고자산") == [(0, 0, 1)]


def test_evidence_matches_catalog_section(tmp_path) -> None:
    catalog = tmp_path / "catalog.db"
    conn = sqlite3.connect(catalog)
    conn.execute(
        """
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            section_name TEXT,
            viewer_url TEXT,
            ele_id TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO entries (entry_id, rcept_no, dcm_no, section_name, viewer_url, ele_id)
        VALUES ('bs1', '20240315000001', '9', '재무상태표', 'https://example.test/viewer', '4')
        """
    )
    conn.commit()
    conn.close()
    gold = open_gold(tmp_path / "gold.db", catalog)
    found = evidence_for(gold, {"rcept_no": "20240315000001", "dcm_no": "9"}, "accounts")
    assert [item.entry_id for item in found] == ["bs1"]
    assert found[0].section_name == "재무상태표"
