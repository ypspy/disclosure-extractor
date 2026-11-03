"""gold.db 연결과 스키마 마이그레이션."""

from __future__ import annotations

import sqlite3

import pytest

from dart_parser.gold.db import migrate, open_gold
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


def test_busy_timeout_on_connection(tmp_path) -> None:
    conn = open_gold(tmp_path / "gold.db", None)
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
