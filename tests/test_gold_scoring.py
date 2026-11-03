"""Wilson 하한, 희소 필드 풀링, 단위 오류."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.scoring import metrics, score, wilson

_VERSION = "audit_opinion.v19"


def test_wilson_known_values() -> None:
    assert round(wilson(400, 400)[0], 4) == 0.9905
    assert round(wilson(399, 400)[0], 4) == 0.9860
    assert round(wilson(300, 300)[0], 4) == 0.9874
    assert wilson(383, 383)[0] >= 0.99
    # z=1.96이면 오류 0건 하한이 0.99 이상인 최소 n은 381이다.
    # 계획의 382 불통과는 계산과 달라 380/381로 고정한다.
    assert wilson(381, 381)[0] >= 0.99 > wilson(380, 380)[0]


def _prepare(tmp_path, *, sparse: list[tuple[str, str]], fp_in: str | None, case: str):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    run_id = "gold-test"
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES (?, 'gold-test', ?, 'x', '{}', ?, '{}')
        """,
        (
            run_id,
            now,
            json.dumps(
                {"sparse_fields": [list(item) for item in sparse]}, ensure_ascii=False
            ),
        ),
    )
    docs: list[dict[str, object]] = []
    if case == "pooled":
        docs.append(_doc("P1A", "1", "P1", "main", {}))
        docs.append(_doc("P7A", "1", "P7", "main", {}))
    elif case == "unit":
        docs.append(_doc("U1", "1", "P7", "main", {}))
    elif case == "na":
        docs.append(_doc("N1", "1", "P7", "main", {}))
    elif case == "oversample":
        docs.append(_doc("M1", "1", "P7", "main", {}))
        docs.append(
            _doc(
                "O1",
                "1",
                "P6",
                "oversample",
                {"oversample_for": "icfr:opinion", "field_weight": 2},
            )
        )
    for doc in docs:
        conn.execute(
            """
            INSERT INTO gold_samples (
                run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
                sample_hash, mode, role, queue_order, status, meta
            ) VALUES (?, ?, ?, ?, NULL, 's', 1, 'h', 'prefill', ?, 1, 'todo', ?)
            """,
            (
                run_id,
                doc["rcept"],
                doc["dcm"],
                doc["period"],
                doc["role"],
                json.dumps(doc["meta"], ensure_ascii=False),
            ),
        )
        payload = _fact(doc, case=case, fp_in=fp_in)
        conn.execute(
            """
            INSERT INTO extractor_snapshots (
                extractor_version, rcept_no, dcm_no, payload, captured_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                _VERSION,
                doc["rcept"],
                doc["dcm"],
                json.dumps(payload, ensure_ascii=False),
                now,
            ),
        )
        _labels(conn, doc, case=case, fp_in=fp_in, labeled_at=now)
    conn.commit()
    return conn, run_id


def _doc(rcept: str, dcm: str, period: str, role: str, meta: dict) -> dict[str, object]:
    return {"rcept": rcept, "dcm": dcm, "period": period, "role": role, "meta": meta}


def _fact(doc: dict[str, object], *, case: str, fp_in: str | None) -> dict[str, object]:
    accounts = [
        {
            "account": "inventory",
            "period": "current",
            "raw": "(1,234)",
            "unit_raw": "천원",
            "value": -1234,
        }
    ]
    return {
        "rcept_no": doc["rcept"],
        "dcm_no": doc["dcm"],
        "extractor_version": _VERSION,
        "auditor_resolved": "삼일회계법인",
        "auditor_status": "ok",
        "icfr_engagement": "engaged",
        "icfr_opinion_code": "unqualified",
        "icfr_status": "ok",
        "accounts": accounts,
        "accounts_status": "ok",
    }


def _label(conn, doc, bundle, subject, verdict, gold_value, labeled_at: str) -> None:
    conn.execute(
        """
        INSERT INTO gold_labels (
            rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
            shown_extractor_version, note, labeled_at
        ) VALUES (?, ?, ?, ?, 'prefill', ?, ?, ?, ?, '', ?)
        """,
        (
            doc["rcept"],
            doc["dcm"],
            bundle,
            subject,
            verdict,
            json.dumps(gold_value, ensure_ascii=False),
            json.dumps(gold_value, ensure_ascii=False),
            _VERSION,
            labeled_at,
        ),
    )


def _labels(conn, doc, *, case: str, fp_in: str | None, labeled_at: str) -> None:
    if case == "pooled":
        wrong = fp_in is not None and doc["period"] == fp_in
        _label(
            conn,
            doc,
            "icfr",
            "opinion",
            "wrong" if wrong else "correct",
            "qualified" if wrong else "unqualified",
            labeled_at,
        )
        return
    if case == "unit":
        _label(
            conn,
            doc,
            "accounts",
            "inventory@current",
            "wrong",
            {"display": "-1234", "unit": "원"},
            labeled_at,
        )
        return
    if case == "na":
        _label(conn, doc, "auditor", "value", "na", None, labeled_at)
        return
    _label(conn, doc, "auditor", "value", "correct", "삼일회계법인", labeled_at)
    if doc["role"] == "main":
        _label(conn, doc, "icfr", "opinion", "correct", "unqualified", labeled_at)


def test_pooled_for_sparse(tmp_path) -> None:
    conn, run_id = _prepare(
        tmp_path, sparse=[("icfr", "opinion")], fp_in=None, case="pooled"
    )
    score(conn, _VERSION)
    rows = metrics(conn, run_id, _VERSION)
    icfr = [row for row in rows if row.bundle == "icfr" and row.subject == "opinion"]
    assert any(row.scope == "pooled" for row in icfr)
    assert all(not row.passed for row in icfr if row.scope == "period")


def test_flagged_period_reported_separately(tmp_path) -> None:
    conn, run_id = _prepare(
        tmp_path, sparse=[("icfr", "opinion")], fp_in="P7", case="pooled"
    )
    score(conn, _VERSION)
    rows = metrics(conn, run_id, _VERSION)
    p7 = [row for row in rows if row.bundle == "icfr" and row.period == "P7"]
    assert p7
    assert p7[0].flag_period_report
    assert "주의" in p7[0].note


def test_unit_error_is_fp(tmp_path) -> None:
    conn, _run_id = _prepare(tmp_path, sparse=[], fp_in=None, case="unit")
    score(conn, _VERSION)
    outcome = conn.execute(
        "SELECT outcome FROM gold_scores WHERE bundle = 'accounts'"
    ).fetchone()[0]
    assert outcome == "fp"


def test_na_with_claim_is_fp(tmp_path) -> None:
    conn, _run_id = _prepare(tmp_path, sparse=[], fp_in=None, case="na")
    score(conn, _VERSION)
    outcome = conn.execute(
        "SELECT outcome FROM gold_scores WHERE bundle = 'auditor'"
    ).fetchone()[0]
    assert outcome == "fp"


def test_oversample_excluded_from_other_fields(tmp_path) -> None:
    conn, run_id = _prepare(
        tmp_path, sparse=[("icfr", "opinion")], fp_in=None, case="oversample"
    )
    score(conn, _VERSION)
    rows = metrics(conn, run_id, _VERSION)
    auditor = [
        row
        for row in rows
        if row.bundle == "auditor" and row.subject == "value" and row.scope == "period"
    ]
    assert auditor
    assert sum(row.n_claim for row in auditor) == 1
