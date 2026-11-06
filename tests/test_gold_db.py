"""gold.db 연결과 스키마 마이그레이션."""

from __future__ import annotations

import sqlite3

import pytest

from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.schema import MIGRATIONS
from gold_fixtures import make_catalog


def test_migrate_creates_tables(tmp_path) -> None:
    conn = open_gold(tmp_path / "gold.db", None)
    assert migrate(conn) >= 1
    names = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "gold_runs",
        "gold_samples",
        "gold_labels",
        "gold_label_history",
        "gold_scores",
        "extractor_snapshots",
    } <= names


def test_migrate_idempotent(tmp_path) -> None:
    conn = open_gold(tmp_path / "gold.db", None)
    version = migrate(conn)
    assert migrate(conn) == version


def test_catalog_attached_read_only(tmp_path) -> None:
    catalog = make_catalog(tmp_path)
    conn = open_gold(tmp_path / "gold.db", catalog)
    assert conn.execute("SELECT count(*) FROM cat.disclosures").fetchone()[0] > 0
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM cat.disclosures")


def test_pin_table_is_a_new_migration(tmp_path) -> None:
    assert "gold_run_extractors" not in MIGRATIONS[0]
    assert "gold_run_extractors" not in MIGRATIONS[1]
    assert "CREATE TABLE gold_run_extractors" in MIGRATIONS[2]
    conn = open_gold(tmp_path / "gold.db", None)
    assert migrate(conn) >= 3
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-06T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_run_extractors (run_id, extractor_version, extractor_commit)
        VALUES ('run', '0.1.0', 'abc123')
        """
    )
    conn.commit()
    row = conn.execute(
        "SELECT extractor_version, extractor_commit FROM gold_run_extractors"
    ).fetchone()
    assert (row[0], row[1]) == ("0.1.0", "abc123")


def test_busy_timeout_on_connection(tmp_path) -> None:
    conn = open_gold(tmp_path / "gold.db", None)
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
