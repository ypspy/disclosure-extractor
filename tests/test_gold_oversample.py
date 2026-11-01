"""희소 필드 판정과 과표집."""

from __future__ import annotations

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
