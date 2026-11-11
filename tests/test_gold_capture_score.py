"""입수 채점은 끝난 문서만 쓰고, 기존 라벨 채점은 그대로다."""

from __future__ import annotations

import json

from dart_parser.fallback.schemas import HoursCell
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.scoring import capture_labels, metrics, score

_VERSION = "capture-score"


def _db(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-11T00:00:00+00:00', 'x', '{}', '{}', '{}')
        """
    )
    return conn


def _sample(conn, rcept: str, *, status: str = "done", period: str = "P7") -> None:
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES ('run', ?, 'D', ?, 's', 1, 'h', 'prefill', 'main', 1, ?, '{}')
        """,
        (rcept, period, status),
    )


def _snapshot(conn, rcept: str, extraction: dict) -> None:
    conn.execute(
        """
        INSERT INTO extractor_snapshots (
            extractor_version, rcept_no, dcm_no, payload, captured_at
        ) VALUES (?, ?, 'D', ?, '2026-11-11T00:00:00+00:00')
        """,
        (_VERSION, rcept, json.dumps({"extraction": extraction}, ensure_ascii=False)),
    )


def _capture(conn, rcept: str, bundle: str, subject: str, status: str, value) -> None:
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (?, 'D', ?, ?, ?, ?, '', 't')
        """,
        (
            rcept,
            bundle,
            subject,
            status,
            None if value is None else json.dumps(value, ensure_ascii=False),
        ),
    )


def _outcomes(conn) -> dict[tuple[str, str, str], str]:
    rows = conn.execute(
        "SELECT rcept_no, bundle, subject, outcome FROM gold_scores"
    ).fetchall()
    return {(row[0], row[1], row[2]): row[3] for row in rows}


def test_capture_rules_write_gold_scores(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "ACC")
    _snapshot(
        conn,
        "ACC",
        {
            "accounts": {
                "status": "found",
                "value": {
                    "inventory": {
                        "current": {"value": 10.0, "unit_scale": 1000},
                        "prior": {"value": 1.0, "unit_scale": 1},
                    },
                    "revenue": {"current": {"value": 5.0, "unit_scale": 1}},
                },
            }
        },
    )
    _capture(
        conn,
        "ACC",
        "accounts",
        "inventory@current",
        "found",
        {"value": 10.0, "unit_scale": 1000},
    )
    _capture(
        conn,
        "ACC",
        "accounts",
        "inventory@prior",
        "found",
        {"value": 10.0, "unit_scale": 1000},
    )
    _capture(conn, "ACC", "accounts", "revenue@current", "not_applicable", None)
    _capture(conn, "ACC", "accounts", "revenue@prior", "not_in_regime", None)

    _sample(conn, "NOTE")
    _snapshot(
        conn,
        "NOTE",
        {"notes_toc": {"status": "found", "value": {"count": 2, "titles": ["일반 사항", "재고"]}}},
    )
    _capture(
        conn,
        "NOTE",
        "notes_toc",
        "value",
        "found",
        {"count": 2, "titles": ["  일반   사항 ", "재고"]},
    )

    _sample(conn, "NOTE2")
    _snapshot(
        conn,
        "NOTE2",
        {"notes_toc": {"status": "found", "value": {"count": 1, "titles": ["재고"]}}},
    )
    _capture(
        conn,
        "NOTE2",
        "notes_toc",
        "value",
        "found",
        {"count": 2, "titles": ["일반", "재고"]},
    )

    _sample(conn, "GC")
    _snapshot(conn, "GC", {"going_concern": {"status": "found", "value": 0}})
    _capture(conn, "GC", "going_concern", "value", "not_applicable", None)

    _sample(conn, "GC1")
    _snapshot(conn, "GC1", {"going_concern": {"status": "found", "value": 1}})
    _capture(conn, "GC1", "going_concern", "value", "found", 1)

    _sample(conn, "HOUR")
    _snapshot(
        conn,
        "HOUR",
        {
            "hours": {
                "status": "found",
                "value": {
                    "cells": [
                        {"role": "total", "period": "current", "metric": "audit", "value": 100.0},
                        {
                            "role": "total",
                            "period": "current",
                            "metric": "headcount",
                            "value": 4.0,
                        },
                    ]
                },
            }
        },
    )
    _capture(conn, "HOUR", "hours", "total|audit_hours|current", "found", 100.0)
    _capture(conn, "HOUR", "hours", "total|headcount|current", "found", 4.0)

    _sample(conn, "ACT")
    _snapshot(conn, "ACT", {"activities": {"status": "found", "value": {"planning": "있음"}}})
    _capture(conn, "ACT", "activities", "planning", "found", "있음")

    _sample(conn, "ACT0")
    _snapshot(conn, "ACT0", {"activities": {"status": "found", "value": {"planning": "있음"}}})
    _capture(conn, "ACT0", "activities", "planning", "not_applicable", None)

    _sample(conn, "COM")
    _snapshot(conn, "COM", {"communications": {"status": "not_applicable", "value": None}})
    _capture(conn, "COM", "communications", "items", "not_applicable", None)
    _capture(conn, "COM", "communications", "has_audit_committee", "not_applicable", None)

    _sample(conn, "SKIP", status="todo")
    _snapshot(conn, "SKIP", {"opinion": {"status": "found", "value": "적정"}})
    _capture(conn, "SKIP", "opinion", "value", "found", "적정")

    _sample(conn, "REG")
    _snapshot(conn, "REG", {"subsidiary": {"status": "found", "value": 3}})
    _capture(conn, "REG", "subsidiary", "value", "not_in_regime", None)
    conn.commit()

    assert list(capture_labels(conn, capture_pass=2)) == []
    score(conn, _VERSION, source="captures")
    outcomes = _outcomes(conn)
    assert outcomes[("ACC", "accounts", "inventory@current")] == "tp"
    assert outcomes[("ACC", "accounts", "inventory@prior")] == "fp"
    assert outcomes[("ACC", "accounts", "revenue@current")] == "fp"
    assert ("ACC", "accounts", "revenue@prior") not in outcomes
    assert outcomes[("NOTE", "notes_toc", "value")] == "tp"
    assert outcomes[("NOTE2", "notes_toc", "value")] == "fp"
    assert outcomes[("GC", "going_concern", "value")] == "tp"
    assert outcomes[("GC1", "going_concern", "value")] == "tp"
    assert outcomes[("HOUR", "hours", "table")] == "tp"
    assert outcomes[("ACT", "activities", "table")] == "tp"
    assert outcomes[("ACT0", "activities", "table")] == "fp"
    assert outcomes[("COM", "communications", "table")] == "tn"
    assert ("SKIP", "opinion", "value") not in outcomes
    assert ("REG", "subsidiary", "value") not in outcomes
    assert metrics(conn, "run", _VERSION)


def test_label_scores_stay_the_same(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "L1")
    _snapshot(
        conn,
        "L1",
        {
            "opinion": {"status": "found", "value": "적정"},
            "company_name": {"status": "found", "value": "가나"},
        },
    )
    for bundle, subject, verdict, value in (
        ("opinion", "value", "value", "적정"),
        ("company_name", "value", "value", "다른이름"),
    ):
        conn.execute(
            """
            INSERT INTO gold_labels (
                rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value,
                shown_value, evidence, note, labeled_at
            ) VALUES ('L1', 'D', ?, ?, 'prefill', ?, ?, NULL, '', '', 't')
            """,
            (bundle, subject, verdict, json.dumps(value, ensure_ascii=False)),
        )
    conn.commit()
    assert score(conn, _VERSION) == 2
    assert _outcomes(conn) == {
        ("L1", "opinion", "value"): "tp",
        ("L1", "company_name", "value"): "fp",
    }
    period = [row for row in metrics(conn, "run", _VERSION) if row.bundle == "opinion"]
    assert period[0].tp == 1
    assert period[0].fp == 0
    assert period[0].n_claim == 1
    assert score(conn, _VERSION, source="labels") == 2
    assert _outcomes(conn)[("L1", "opinion", "value")] == "tp"
    assert _outcomes(conn)[("L1", "company_name", "value")] == "fp"


def _hours_cell(
    role: str,
    role_key: str,
    metric: str,
    metric_key: str,
    value: float,
    *,
    period: str = "current",
) -> dict:
    return HoursCell(
        role=role,
        role_key=role_key,
        metric=metric,
        metric_key=metric_key,
        period=period,  # type: ignore[arg-type]
        value=value,
    ).model_dump()


def test_capture_hours_reads_hours_cell_snapshots(tmp_path) -> None:
    conn = _db(tmp_path)
    shared = [
        _hours_cell("합계", "total", "투입인원", "headcount", 6.0),
        _hours_cell("업무수행이사", "engagement_partner", "감사시간", "audit_hours", 9.0),
        _hours_cell("합계", "total", "감사시간", "audit_hours", 1.0, period="prior"),
    ]
    for rcept, audit in (("HOK", 120.0), ("HBAD", 99.0)):
        _sample(conn, rcept)
        _snapshot(
            conn,
            rcept,
            {
                "hours": {
                    "status": "found",
                    "value": {
                        "cells": [
                            _hours_cell("합계", "total", "감사시간", "audit_hours", audit),
                            *shared,
                        ]
                    },
                }
            },
        )
        _capture(conn, rcept, "hours", "total|audit_hours|current", "found", 120.0)
        _capture(conn, rcept, "hours", "total|headcount|current", "found", 6.0)
    conn.commit()
    score(conn, _VERSION, source="captures")
    outcomes = _outcomes(conn)
    assert outcomes[("HOK", "hours", "table")] == "tp"
    assert outcomes[("HBAD", "hours", "table")] == "fp"


def test_capture_hours_headcount_only_mismatch_is_fp(tmp_path) -> None:
    conn = _db(tmp_path)
    _sample(conn, "HHEAD")
    _snapshot(
        conn,
        "HHEAD",
        {
            "hours": {
                "status": "found",
                "value": {
                    "cells": [
                        _hours_cell("합계", "total", "감사시간", "audit_hours", 120.0),
                        _hours_cell("합계", "total", "투입인원", "headcount", 7.0),
                    ]
                },
            }
        },
    )
    _capture(conn, "HHEAD", "hours", "total|audit_hours|current", "found", 120.0)
    _capture(conn, "HHEAD", "hours", "total|headcount|current", "found", 6.0)
    conn.commit()
    score(conn, _VERSION, source="captures")
    assert _outcomes(conn)[("HHEAD", "hours", "table")] == "fp"
