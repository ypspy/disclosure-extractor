"""모집단은 카탈로그의 문서 위치만 본다."""

from __future__ import annotations

import sqlite3

from dart_parser.gold.db import open_gold
from dart_parser.gold.sampler import load_population


def test_population_ignores_v19_facts(tmp_path) -> None:
    catalog = tmp_path / "catalog.db"
    conn = sqlite3.connect(catalog)
    conn.executescript(
        """
        CREATE TABLE disclosures (
            rcept_no TEXT PRIMARY KEY,
            corp_code TEXT,
            report_nm TEXT,
            report_type TEXT,
            correction_type TEXT,
            rcept_dt TEXT,
            year_end TEXT
        );
        CREATE TABLE corps (
            corp_code TEXT PRIMARY KEY,
            corp_cls TEXT
        );
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            section_name TEXT,
            dtd TEXT
        );
        INSERT INTO corps VALUES ('C1', 'Y');
        INSERT INTO disclosures VALUES (
            '20200315000001', 'C1', '감사보고서', 'F001', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e1', '20200315000001', '77', '표지', 'dart3.xsd'
        );
        INSERT INTO disclosures VALUES (
            '20200315000002', 'C1', '연결감사보고서', 'F003', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e2', '20200315000002', '88', '표지', 'dart3.xsd'
        );
        INSERT INTO disclosures VALUES (
            '20200315000003', 'C1', '감사의감사보고서', 'F001', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e3', '20200315000003', '99', '표지', 'dart3.xsd'
        );
        """
    )
    conn.commit()
    conn.close()
    gold = open_gold(tmp_path / "gold.db", catalog)
    rows = load_population(gold)
    keys = {(row.rcept_no, row.dcm_no) for row in rows}
    assert keys == {("20200315000001", "77")}
    assert rows[0].scope == "separate"
