"""모집단은 카탈로그의 문서 위치만 본다."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
            document_name TEXT,
            section_name TEXT,
            dtd TEXT
        );
        INSERT INTO corps VALUES ('C1', 'Y');
        INSERT INTO disclosures VALUES (
            '20200315000001', 'C1', '감사보고서', 'F001', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e1', '20200315000001', '77', '감사보고서', '표지', 'dart3.xsd'
        );
        INSERT INTO disclosures VALUES (
            '20200315000002', 'C1', '연결감사보고서', 'F003', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e2', '20200315000002', '88', '연결감사보고서', '표지', 'dart3.xsd'
        );
        INSERT INTO disclosures VALUES (
            '20200315000003', 'C1', '감사의감사보고서', 'F001', '', '20200315', '2019.12'
        );
        INSERT INTO entries VALUES (
            'e3', '20200315000003', '99', '감사의감사보고서', '표지', 'dart3.xsd'
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


def _catalog(tmp_path: Path) -> Path:
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
            document_name TEXT,
            section_name TEXT,
            dtd TEXT
        );
        INSERT INTO corps VALUES ('C1', 'Y');
        """
    )
    conn.commit()
    conn.close()
    return catalog


def _filing(
    conn: sqlite3.Connection,
    rcept_no: str,
    report_type: str,
    correction: str,
    docs: list[tuple[str, str]],
) -> None:
    conn.execute(
        """
        INSERT INTO disclosures VALUES (?, 'C1', ?, ?, ?, '20200315', '2019.12')
        """,
        (rcept_no, docs[0][1], report_type, correction),
    )
    for index, (dcm_no, document_name) in enumerate(docs):
        conn.execute(
            """
            INSERT INTO entries VALUES (?, ?, ?, ?, '표지', 'dart3.xsd')
            """,
            (f"{rcept_no}-{index}", rcept_no, dcm_no, document_name),
        )


def test_population_keeps_only_audit_report_leaves(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    conn = sqlite3.connect(catalog)
    _filing(
        conn,
        "A",
        "A001",
        "",
        [
            ("1", "사업보고서"),
            ("2", "정관"),
            ("3", "감사보고서"),
            ("4", "연결감사보고서"),
            ("5", "감사의감사보고서"),
        ],
    )
    _filing(conn, "B", "A001", "기재정정", [("6", "사업보고서")])
    _filing(conn, "C0", "A001", "", [("7", "감사보고서")])
    _filing(conn, "C1", "A001", "기재정정", [("8", "[정정] 연결감사보고서")])
    _filing(
        conn,
        "D",
        "F001",
        "",
        [("9", "기업개황자료"), ("10", "감사보고서")],
    )
    _filing(
        conn,
        "E",
        "A001",
        "",
        [("11", "감사보고서"), ("11", "연결감사보고서")],
    )
    conn.commit()
    conn.close()
    gold = open_gold(tmp_path / "gold.db", catalog)
    rows = {(row.rcept_no, row.dcm_no): row for row in load_population(gold)}
    assert set(rows) == {("A", "3"), ("A", "4"), ("C0", "7"), ("C1", "8"), ("D", "10"), ("E", "11")}
    assert rows[("A", "3")].scope == "separate"
    assert rows[("A", "3")].form == "attached"
    assert rows[("A", "4")].scope == "consolidated"
    assert rows[("C0", "7")].scope == "separate"
    assert rows[("C1", "8")].scope == "consolidated"
    assert rows[("D", "10")].scope == "separate"
    assert rows[("D", "10")].form == "standalone"
    assert rows[("E", "11")].scope == "consolidated"
