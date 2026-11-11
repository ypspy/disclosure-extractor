"""희소 필드 판정과 과표집."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.sampler import find_sparse_fields, oversample
from gold_fixtures import run_sample


def _icfr_rows(conn):
    return conn.execute("""
        SELECT rcept_no, dcm_no, json_extract(meta, '$.oversample_for')
        FROM gold_samples
        WHERE role = 'oversample'
        """).fetchall()


def test_sparse_detected_and_oversampled(tmp_path) -> None:
    conn, run_id = run_sample(tmp_path, "x")
    sparse = find_sparse_fields(conn, run_id, threshold=60)
    assert ("icfr", "opinion") in sparse
    added = oversample(conn, run_id, ("icfr", "opinion"), target=60)
    rows = _icfr_rows(conn)
    assert added > 0
    assert added == len(rows)
    assert all(row[2] == "icfr:opinion" for row in rows)


def test_oversample_only_docs_with_claim(tmp_path) -> None:
    conn, run_id = run_sample(tmp_path, "x")
    oversample(conn, run_id, ("icfr", "opinion"), target=60)
    pairs = conn.execute(
        "SELECT rcept_no, dcm_no FROM gold_samples WHERE role = 'oversample'"
    ).fetchall()
    assert pairs
    for rcept_no, dcm_no in pairs:
        status = conn.execute(
            """
            SELECT icfr_status FROM cat.audit_report_facts
            WHERE rcept_no = ? AND dcm_no = ?
            """,
            (rcept_no, dcm_no),
        ).fetchone()[0]
        assert status == "ok"


def test_oversample_skips_non_audit_documents(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.db"
    cat = sqlite3.connect(catalog)
    cat.executescript(
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
        INSERT INTO disclosures VALUES
            ('R1', 'C1', '감사보고서', 'F001', '', '20200315', '2019.12'),
            ('R2', 'C1', '사업보고서', 'A001', '', '20200316', '2019.12');
        INSERT INTO entries VALUES
            ('a', 'R1', 'D1', '감사보고서', '내부회계관리제도', 'dart3.xsd'),
            ('b', 'R2', 'D2', '사업보고서', '내부회계관리제도', 'dart3.xsd');
        """
    )
    cat.commit()
    cat.close()
    conn = open_gold(tmp_path / "gold.db", catalog)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'gold-2026-10', '2026-11-10T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
            sample_hash, mode, role, queue_order, status, exclude_reason, meta,
            started_at, finished_at, active_seconds
        ) VALUES (
            'run', 'KEEP', 'KEEP', 'P6', NULL, 's', 1, 'hash', 'prefill', 'main',
            1, 'todo', NULL, '{}', NULL, NULL, NULL
        )
        """
    )
    conn.commit()
    added = oversample(conn, "run", ("icfr", "opinion"), target=5)
    rows = conn.execute(
        """
        SELECT rcept_no, dcm_no, meta
        FROM gold_samples
        WHERE role = 'oversample'
        """
    ).fetchall()
    assert added == 1
    assert [(row[0], row[1]) for row in rows] == [("R1", "D1")]
    assert json.loads(rows[0][2])["scope"] == "separate"


def _subsidiary_catalog(tmp_path: Path) -> Path:
    """문서명과 보고서 머릿글의 연결 여부가 서로 다른 두 감사보고서."""
    catalog = tmp_path / "catalog.db"
    cat = sqlite3.connect(catalog)
    cat.executescript(
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
        INSERT INTO disclosures VALUES
            ('CONS', 'C1', '감사보고서', 'F001', '', '20200315', '2019.12'),
            ('SEP', 'C1', '연결감사보고서', 'F002', '', '20200315', '2019.12');
        INSERT INTO entries VALUES
            ('c', 'CONS', 'DC', '연결감사보고서', '종속기업', 'dart3.xsd'),
            ('s', 'SEP', 'DS', '감사보고서', '종속기업', 'dart3.xsd');
        """
    )
    cat.commit()
    cat.close()
    return catalog


def _open_with_run(tmp_path: Path, catalog: Path) -> sqlite3.Connection:
    conn = open_gold(tmp_path / "gold.db", catalog)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'gold-2026-10', '2026-11-10T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    conn.commit()
    return conn


def _insert_main(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> None:
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
            sample_hash, mode, role, queue_order, status, exclude_reason, meta,
            started_at, finished_at, active_seconds
        ) VALUES (
            'run', ?, ?, 'P6', NULL, 's', 1, 'hash', 'prefill', 'main',
            1, 'todo', NULL, '{}', NULL, NULL, NULL
        )
        """,
        (rcept_no, dcm_no),
    )
    conn.commit()


def test_subsidiary_claim_follows_consolidated_document_name(tmp_path: Path) -> None:
    catalog = _subsidiary_catalog(tmp_path)
    conn = _open_with_run(tmp_path, catalog)
    _insert_main(conn, "CONS", "DC")
    sparse = find_sparse_fields(conn, "run", threshold=1)
    assert ("subsidiary", "value") not in sparse


def test_subsidiary_ignores_report_header_when_document_is_separate(tmp_path: Path) -> None:
    catalog = _subsidiary_catalog(tmp_path)
    conn = _open_with_run(tmp_path, catalog)
    _insert_main(conn, "SEP", "DS")
    sparse = find_sparse_fields(conn, "run", threshold=1)
    assert ("subsidiary", "value") in sparse


def test_subsidiary_oversample_uses_document_name(tmp_path: Path) -> None:
    catalog = _subsidiary_catalog(tmp_path)
    conn = _open_with_run(tmp_path, catalog)
    _insert_main(conn, "KEEP", "KEEP")
    added = oversample(conn, "run", ("subsidiary", "value"), target=5)
    rows = conn.execute(
        """
        SELECT rcept_no, dcm_no FROM gold_samples WHERE role = 'oversample'
        """
    ).fetchall()
    assert added == 1
    assert [(row[0], row[1]) for row in rows] == [("CONS", "DC")]
