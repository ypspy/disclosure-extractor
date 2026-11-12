"""gold.db 연결과 스키마 마이그레이션."""

from __future__ import annotations

import sqlite3

import pytest

from dart_parser.gold.db import migrate, open_catalog_readonly, open_gold
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
        "gold_captures",
        "gold_capture_units",
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


def test_open_catalog_readonly_rejects_writes(tmp_path) -> None:
    catalog = make_catalog(tmp_path)
    conn = open_catalog_readonly(catalog)
    try:
        assert conn.execute("SELECT count(*) FROM disclosures").fetchone()[0] > 0
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        for statement in (
            "INSERT INTO disclosures (rcept_no) VALUES ('new-row')",
            "UPDATE corps SET corp_name = '바꿈'",
            "DELETE FROM disclosures",
            "CREATE TABLE should_fail (id INTEGER)",
        ):
            with pytest.raises(sqlite3.OperationalError, match="readonly|query_only"):
                conn.execute(statement)
    finally:
        conn.close()


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


_EARLIER_TABLES = (
    "gold_runs",
    "gold_samples",
    "gold_labels",
    "gold_label_history",
    "gold_scores",
    "extractor_snapshots",
    "gold_rereview",
    "gold_run_extractors",
    "gold_captures",
    "gold_capture_units",
    "gold_capture_history",
)

_RECAPTURE_TABLES = (
    "gold_recaptures",
    "gold_recapture_units",
    "gold_recapture_history",
    "gold_recapture_status",
    "gold_adjudications",
    "gold_adjudication_history",
)


def test_recapture_migration_appends_tables_without_changing_earlier_ones(tmp_path) -> None:
    assert len(MIGRATIONS) == 6
    for earlier in MIGRATIONS[:5]:
        assert "gold_recapture" not in earlier
        assert "gold_adjudication" not in earlier
    conn = open_gold(tmp_path / "gold.db", None)
    for ddl in MIGRATIONS[:5]:
        conn.executescript(ddl)
    before = {
        name: conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()[0]
        for name in _EARLIER_TABLES
    }
    conn.executescript(MIGRATIONS[5])
    for name, sql in before.items():
        after = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()[0]
        assert after == sql
    names = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert set(_RECAPTURE_TABLES) <= names
    fresh = open_gold(tmp_path / "migrated.db", None)
    assert migrate(fresh) == 6
    status_cols = [row[1] for row in fresh.execute("PRAGMA table_info(gold_recapture_status)")]
    assert status_cols == ["run_id", "rcept_no", "dcm_no", "status", "started_at", "finished_at"]
    adjudication_cols = [row[1] for row in fresh.execute("PRAGMA table_info(gold_adjudications)")]
    assert adjudication_cols == [
        "rcept_no",
        "dcm_no",
        "bundle",
        "subject",
        "chosen_pass",
        "note",
        "decided_at",
    ]
    history_cols = [row[1] for row in fresh.execute("PRAGMA table_info(gold_adjudication_history)")]
    assert history_cols[-1] == "superseded_at"
    capture_cols = [row[1] for row in fresh.execute("PRAGMA table_info(gold_captures)")]
    recapture_cols = [row[1] for row in fresh.execute("PRAGMA table_info(gold_recaptures)")]
    assert recapture_cols == capture_cols
    assert [row[1] for row in fresh.execute("PRAGMA table_info(gold_recapture_units)")] == [
        row[1] for row in fresh.execute("PRAGMA table_info(gold_capture_units)")
    ]
    assert [row[1] for row in fresh.execute("PRAGMA table_info(gold_recapture_history)")] == [
        row[1] for row in fresh.execute("PRAGMA table_info(gold_capture_history)")
    ]
