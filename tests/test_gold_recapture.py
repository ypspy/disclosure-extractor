"""재입수 대상, 일치 리포트, 판정, 최종 입수 라벨."""

from __future__ import annotations

import json

from dart_parser.fallback.schemas import HoursCell
from dart_parser.gold.capture_store import save_capture
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.recapture import (
    ConsistencyRow,
    disagreements,
    eligible,
    save_adjudication,
)
from dart_parser.gold.scoring import (
    capture_labels,
    final_capture_labels,
    pending_capture_adjudication,
    score,
    wilson,
)

_VERSION = "recapture-score"


def _db(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-12T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    return conn


def _sample(
    conn,
    rcept: str,
    *,
    finished: str,
    queue: int,
    mode: str = "blind",
    period: str = "P1",
    run_id: str = "run",
    role: str = "main",
    status: str = "done",
    dcm: str = "D",
) -> None:
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta, finished_at
        ) VALUES (?, ?, ?, ?, 's', 1, ?, ?, ?, ?, ?, '{}', ?)
        """,
        (run_id, rcept, dcm, period, f"h{queue}{rcept}", mode, role, queue, status, finished),
    )


def _later(
    conn,
    count: int,
    *,
    period: str = "P1",
    run_id: str = "run",
    mode: str = "blind",
    finished: str = "2026-06-01T00:00:00+00:00",
    queue_base: int = 100,
) -> None:
    for index in range(count):
        _sample(
            conn,
            f"{run_id}{period}{mode}{queue_base}{index}",
            finished=finished,
            queue=queue_base + index,
            mode=mode,
            period=period,
            run_id=run_id,
        )


def _cell(
    conn,
    rcept: str,
    bundle: str,
    subject: str,
    status: str,
    value,
    *,
    capture_pass: int = 1,
    dcm: str = "D",
) -> None:
    table = "gold_captures" if capture_pass == 1 else "gold_recaptures"
    conn.execute(
        f"""
        INSERT INTO {table} (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, '', 't')
        """,
        (
            rcept,
            dcm,
            bundle,
            subject,
            status,
            None if value is None else json.dumps(value, ensure_ascii=False),
        ),
    )


def _done_recapture(conn, rcept: str, *, run_id: str = "run", dcm: str = "D") -> None:
    conn.execute(
        """
        INSERT INTO gold_recapture_status (
            run_id, rcept_no, dcm_no, status, started_at, finished_at
        ) VALUES (?, ?, ?, 'done', 't', 't')
        """,
        (run_id, rcept, dcm),
    )


def _row(report: list[ConsistencyRow], period: str, bundle: str, subject: str) -> ConsistencyRow:
    found = [
        item
        for item in report
        if item.period == period and item.bundle == bundle and item.subject == subject
    ]
    assert len(found) == 1
    return found[0]


def test_blind_document_becomes_eligible_after_twenty_later_finishes(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "TARGET", finished="2026-01-01T00:00:00+00:00", queue=1)
    _later(conn, 19)
    _sample(conn, "OTHER-PERIOD", finished="2026-07-01T00:00:00+00:00", queue=1, period="P2")
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('other', 'seed', '2026-11-12T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    _sample(
        conn,
        "OTHER-RUN",
        finished="2026-07-01T00:00:00+00:00",
        queue=1,
        run_id="other",
    )
    conn.commit()
    assert eligible(conn, "run", "TARGET", "D") is False
    _sample(conn, "TWENTIETH", finished="2026-06-02T00:00:00+00:00", queue=90)
    _sample(conn, "PREFILL", finished="2026-08-01T00:00:00+00:00", queue=2, mode="prefill")
    _later(
        conn,
        20,
        mode="prefill",
        finished="2026-09-01T00:00:00+00:00",
        queue_base=300,
    )
    conn.commit()
    assert eligible(conn, "run", "TARGET", "D") is True
    assert eligible(conn, "run", "PREFILL", "D") is False
    assert eligible(conn, "run", "OTHER-PERIOD", "D") is False
    _sample(conn, "RESERVE", finished="2026-01-01T00:00:00+00:00", queue=4, role="reserve")
    conn.commit()
    assert eligible(conn, "run", "RESERVE", "D") is False


def test_consistency_rules_drop_double_gaps_and_sum_periods(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "A", finished="2026-01-01T00:00:00+00:00", queue=1, period="P1")
    _sample(conn, "B", finished="2026-01-02T00:00:00+00:00", queue=2, period="P2")
    _sample(conn, "OPEN", finished="2026-01-03T00:00:00+00:00", queue=3, period="P1")
    _done_recapture(conn, "A")
    _done_recapture(conn, "B")
    conn.execute(
        """
        INSERT INTO gold_recapture_status (
            run_id, rcept_no, dcm_no, status, started_at, finished_at
        ) VALUES ('run', 'OPEN', 'D', 'in_progress', 't', NULL)
        """
    )
    _cell(conn, "A", "auditor", "value", "found", "주식회사 삼일회계법인")
    _cell(conn, "A", "auditor", "value", "found", "삼일회계법인", capture_pass=2)
    _cell(
        conn,
        "A",
        "accounts",
        "inventory@current",
        "found",
        {"value": 10.0, "unit_scale": 1000, "raw": "가"},
    )
    _cell(
        conn,
        "A",
        "accounts",
        "inventory@current",
        "found",
        {"value": 10.0, "unit_scale": 1000, "raw": "나"},
        capture_pass=2,
    )
    _cell(
        conn,
        "A",
        "accounts",
        "revenue@current",
        "found",
        {"value": 10.0, "unit_scale": 1},
    )
    _cell(
        conn,
        "A",
        "accounts",
        "revenue@current",
        "found",
        {"value": 10.0, "unit_scale": 1000},
        capture_pass=2,
    )
    _cell(conn, "A", "notes_toc", "value", "found", {"count": 1, "titles": ["  일반  사항"]})
    _cell(
        conn,
        "A",
        "notes_toc",
        "value",
        "found",
        {"count": 1, "titles": ["일반 사항"]},
        capture_pass=2,
    )
    _cell(conn, "A", "going_concern", "value", "not_applicable", None)
    _cell(conn, "A", "going_concern", "value", "found", 0, capture_pass=2)
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 6.0)
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0, capture_pass=2)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 7.0, capture_pass=2)
    _cell(conn, "A", "activities", "planning", "found", "있음")
    _cell(conn, "A", "activities", "planning", "found", "다른 문장", capture_pass=2)
    _cell(conn, "A", "subsidiary", "value", "not_in_regime", None)
    _cell(conn, "A", "subsidiary", "value", "not_in_regime", None, capture_pass=2)
    _cell(conn, "A", "opinion", "value", "found", "적정")
    _cell(conn, "A", "company_name", "value", "not_applicable", None)
    _cell(conn, "A", "company_name", "value", "not_applicable", None, capture_pass=2)
    _cell(conn, "A", "audit_report_date", "value", "found", "2024-03-15T09:00:00")
    _cell(conn, "A", "audit_report_date", "value", "found", "2024-03-15", capture_pass=2)
    _cell(conn, "A", "communications", "has_audit_committee", "not_applicable", None)
    _cell(conn, "A", "communications", "items", "not_applicable", None)
    _cell(conn, "A", "communications", "has_audit_committee", "found", True, capture_pass=2)
    _cell(conn, "A", "fiscal_term", "value", "found", "제10기")
    _cell(conn, "A", "fiscal_term", "value", "found", "제11기", capture_pass=2)
    _cell(conn, "B", "auditor", "value", "found", "삼일")
    _cell(conn, "B", "auditor", "value", "found", "한영", capture_pass=2)
    _cell(conn, "B", "going_concern", "value", "found", 1)
    _cell(conn, "B", "going_concern", "value", "found", 0, capture_pass=2)
    _cell(conn, "OPEN", "auditor", "value", "found", "열림1차")
    _cell(conn, "OPEN", "auditor", "value", "found", "열림2차", capture_pass=2)
    conn.commit()

    from dart_parser.gold.recapture import consistency_report

    report = consistency_report(conn, "run")
    auditor = _row(report, "P1", "auditor", "value")
    assert (auditor.n, auditor.agree) == (1, 1)
    assert auditor.wilson_lo == wilson(1, 1)[0]
    assert _row(report, "P1", "accounts", "inventory@current").agree == 1
    revenue = _row(report, "P1", "accounts", "revenue@current")
    assert (revenue.n, revenue.agree) == (1, 0)
    assert _row(report, "P1", "notes_toc", "value").agree == 1
    assert _row(report, "P1", "going_concern", "value").agree == 1
    assert _row(report, "P2", "going_concern", "value").agree == 0
    combined_concern = _row(report, "", "going_concern", "value")
    assert (combined_concern.n, combined_concern.agree) == (2, 1)
    assert combined_concern.rate == 0.5
    assert combined_concern.wilson_lo == wilson(1, 2)[0]
    hours = _row(report, "P1", "hours", "table")
    assert (hours.n, hours.agree) == (1, 0)
    assert _row(report, "P1", "activities", "table").agree == 1
    assert _row(report, "P1", "opinion", "value").agree == 0
    assert _row(report, "P1", "company_name", "value").agree == 1
    assert _row(report, "P1", "audit_report_date", "value").agree == 1
    assert _row(report, "P1", "communications", "table").agree == 0
    assert _row(report, "P1", "fiscal_term", "value").agree == 0
    assert not any(item.bundle == "subsidiary" for item in report)
    assert not any(
        item.period == "P1" and item.bundle == "auditor" and item.n == 2 for item in report
    )
    auditors = _row(report, "", "auditor", "value")
    assert (auditors.n, auditors.agree) == (2, 1)


def test_adjudication_replaces_only_the_chosen_second_pass(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "A", finished="2026-01-01T00:00:00+00:00", queue=1)
    _done_recapture(conn, "A")
    _cell(conn, "A", "company_name", "value", "found", "1차회사")
    _cell(conn, "A", "company_name", "value", "found", "1차회사", capture_pass=2)
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 6.0)
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0, capture_pass=2)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 7.0, capture_pass=2)
    conn.commit()
    found = disagreements(conn, "run")
    assert [(item.rcept_no, item.bundle, item.subject) for item in found] == [
        ("A", "hours", "table")
    ]
    assert found[0].first is not None and found[0].first.gold_value == [120.0, 6.0]
    assert found[0].second is not None and found[0].second.gold_value == [120.0, 7.0]
    pending = pending_capture_adjudication(conn)
    assert pending == [("A", "D", "hours", "table")]
    labels = {
        (item.bundle, item.subject): item.gold_value
        for item in final_capture_labels(conn)
    }
    assert ("hours", "table") not in labels
    assert labels[("company_name", "value")] == "1차회사"
    assert save_adjudication(
        conn, "A", "D", "company_name", "value", 2, "일치 항목", run_id="run"
    ) is False
    assert save_adjudication(conn, "A", "D", "hours", "table", 2, "인원을 따른다", run_id="run")
    assert save_adjudication(conn, "A", "D", "hours", "table", 1, "시간을 따른다", run_id="run")
    history = conn.execute(
        """
        SELECT chosen_pass, note FROM gold_adjudication_history ORDER BY rowid
        """
    ).fetchall()
    assert history[0][0] == 2
    assert history[0][1] == "인원을 따른다"
    current = conn.execute(
        "SELECT chosen_pass, note FROM gold_adjudications"
    ).fetchone()
    assert current[0] == 1
    assert current[1] == "시간을 따른다"
    assert pending_capture_adjudication(conn) == []
    chosen = {
        (item.bundle, item.subject): item.gold_value
        for item in final_capture_labels(conn)
    }
    assert chosen[("hours", "table")] == [120.0, 6.0]
    save_adjudication(conn, "A", "D", "hours", "table", 2, "다시 2차", run_id="run")
    replaced = {
        (item.bundle, item.subject): item.gold_value
        for item in final_capture_labels(conn)
    }
    assert replaced[("hours", "table")] == [120.0, 7.0]
    assert replaced[("company_name", "value")] == "1차회사"


def test_scores_without_recapture_match_the_first_pass(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "A", finished="2026-01-01T00:00:00+00:00", queue=1)
    _cell(conn, "A", "opinion", "value", "found", "적정")
    conn.execute(
        """
        INSERT INTO extractor_snapshots (
            extractor_version, rcept_no, dcm_no, payload, captured_at
        ) VALUES (?, 'A', 'D', ?, 't')
        """,
        (
            _VERSION,
            json.dumps(
                {"extraction": {"opinion": {"status": "found", "value": "적정"}}},
                ensure_ascii=False,
            ),
        ),
    )
    conn.commit()
    first = list(capture_labels(conn, capture_pass=1))
    assert list(capture_labels(conn, capture_pass=2)) == []
    final = [(item.bundle, item.subject, item.gold_value) for item in final_capture_labels(conn)]
    assert final == [(item.bundle, item.subject, item.gold_value) for item in first]
    assert score(conn, _VERSION, source="captures") == 1
    outcome = conn.execute("SELECT outcome FROM gold_scores").fetchone()[0]
    assert outcome == "tp"


def test_second_pass_labels_come_only_from_finished_recaptures(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "A", finished="2026-01-01T00:00:00+00:00", queue=1)
    _done_recapture(conn, "A")
    _cell(conn, "A", "opinion", "value", "found", "적정", capture_pass=2)
    _cell(conn, "A", "opinion", "value", "found", "한정")
    conn.commit()
    second = list(capture_labels(conn, capture_pass=2))
    assert [item.gold_value for item in second] == ["적정"]
    assert save_capture(conn, "A", "D", "company_name", "value", "숨은1차")
    assert "숨은1차" not in [item.gold_value for item in capture_labels(conn, capture_pass=2)]


def test_headcount_snapshot_is_a_false_positive_after_adjudication(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "A", finished="2026-01-01T00:00:00+00:00", queue=1)
    _done_recapture(conn, "A")
    cells = [
        HoursCell(
            role="합계",
            role_key="total",
            metric="감사시간",
            metric_key="audit_hours",
            period="current",
            value=120.0,
        ).model_dump(),
        HoursCell(
            role="합계",
            role_key="total",
            metric="투입인원",
            metric_key="headcount",
            period="current",
            value=7.0,
        ).model_dump(),
    ]
    conn.execute(
        """
        INSERT INTO extractor_snapshots (
            extractor_version, rcept_no, dcm_no, payload, captured_at
        ) VALUES (?, 'A', 'D', ?, 't')
        """,
        (
            _VERSION,
            json.dumps(
                {"extraction": {"hours": {"status": "found", "value": {"cells": cells}}}},
                ensure_ascii=False,
            ),
        ),
    )
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 6.0)
    _cell(conn, "A", "hours", "total|audit_hours|current", "found", 120.0, capture_pass=2)
    _cell(conn, "A", "hours", "total|headcount|current", "found", 7.0, capture_pass=2)
    conn.commit()
    save_adjudication(conn, "A", "D", "hours", "table", 2, "인원만 다르다", run_id="run")
    score(conn, _VERSION, source="captures")
    outcome = conn.execute(
        """
        SELECT outcome FROM gold_scores
        WHERE bundle = 'hours' AND subject = 'table'
        """
    ).fetchone()[0]
    assert outcome == "tp"
