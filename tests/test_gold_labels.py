"""골드 라벨은 매핑표 subject를 받고 한정 의견을 저장한다."""

from __future__ import annotations

from datetime import UTC, datetime

from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.labels import required_subjects, save_label


def _conn(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', ?, 'x', '{}', '{}', '{}')
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES ('run', 'R1', 'D1', 'P7', 's', 1, 'h', 'prefill', 'main', 1, 'todo', '{}')
        """
    )
    conn.commit()
    return conn


def test_required_subjects_follow_the_field_map(tmp_path) -> None:
    conn = _conn(tmp_path)
    required = required_subjects(conn, "run", "R1", "D1")
    assert ("company_name", "value") in required
    assert ("document_title", "value") in required
    assert ("fiscal_term", "value") in required
    assert ("notes_toc", "value") in required
    assert ("accounts", "revenue@current") in required
    assert ("accounts", "operating_income@prior") in required
    assert len(required) == 42


def test_label_stores_qualified_opinion(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_label(
        conn,
        rcept_no="R1",
        dcm_no="D1",
        bundle="opinion",
        subject="value",
        pass_="prefill",
        verdict="correct",
        gold_value="한정",
        shown_value="한정",
        shown_version="0.1.0",
    )
    stored = conn.execute("SELECT gold_value FROM gold_labels").fetchone()[0]
    assert "한정" in stored
