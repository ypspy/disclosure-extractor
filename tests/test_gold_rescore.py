"""추출기 버전이 바뀌었을 때의 재채점과 표 재검수 큐."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from dart_parser.fallback.schemas import HoursCell
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.scoring import rescore, table_carryover

_OLD = "audit_opinion.v19"
_NEW = "audit_opinion.v20"


def _hours(audit: int, headcount: int, extra: bool = False) -> list[dict[str, object]]:
    rows = [
        {
            "role": "total",
            "metric": "audit",
            "period": "current",
            "value": audit,
            "raw": str(audit),
        },
        {
            "role": "total",
            "metric": "headcount",
            "period": "current",
            "value": headcount,
            "raw": str(headcount),
        },
    ]
    if extra:
        rows.append(
            {
                "role": "cpa",
                "metric": "audit",
                "period": "current",
                "value": 1,
                "raw": "1",
            }
        )
    return rows


def _hours_cell(
    role: str,
    role_key: str,
    metric: str,
    metric_key: str,
    value: float,
) -> dict[str, object]:
    """실제 추출기 스냅샷과 같은 HoursCell.model_dump()."""
    dumped = HoursCell(
        role=role,
        role_key=role_key,
        metric=metric,
        metric_key=metric_key,
        period="current",
        value=value,
    ).model_dump()
    assert dumped["period"] == "current"
    return dumped


def _hours_cell_snapshot(audit: float, headcount: float) -> list[dict[str, object]]:
    return [
        _hours_cell("합계", "total", "감사시간", "audit_hours", audit),
        _hours_cell("합계", "total", "투입인원", "headcount", headcount),
    ]


def _prepare(
    tmp_path,
    *,
    old_hours,
    new_hours,
    scalar_new: str = "unqualified",
    label_gold: dict[str, object] | None = None,
):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('gold-test', 'gold-test', ?, 'x', '{}', '{}', '{}')
        """,
        (now,),
    )
    conn.execute("""
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES ('gold-test', 'R1', 'D1', 'P7', 's', 1, 'h', 'prefill', 'main', 1, 'todo', '{}')
        """)
    for version, hours, opinion in (
        (_OLD, old_hours, "unqualified"),
        (_NEW, new_hours, scalar_new),
    ):
        payload = {
            "extractor_version": version,
            "rcept_no": "R1",
            "dcm_no": "D1",
            "hours": hours,
            "hours_status": "ok",
            "opinion_resolved": opinion,
            "opinion_status": "ok",
        }
        conn.execute(
            """
            INSERT INTO extractor_snapshots (
                extractor_version, rcept_no, dcm_no, payload, captured_at
            ) VALUES (?, 'R1', 'D1', ?, ?)
            """,
            (version, json.dumps(payload, ensure_ascii=False), now),
        )
    conn.execute(
        """
        INSERT INTO gold_labels (
            rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
            shown_extractor_version, note, labeled_at
        ) VALUES ('R1', 'D1', 'hours', 'table', 'prefill', 'correct', ?, ?, ?, '', ?)
        """,
        (
            json.dumps(
                label_gold
                if label_gold is not None
                else {"verdict": "correct", "audit_hours": 100, "headcount": 5},
                ensure_ascii=False,
            ),
            json.dumps(_hours(100, 5), ensure_ascii=False),
            _OLD,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO gold_labels (
            rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
            shown_extractor_version, note, labeled_at
        ) VALUES ('R1', 'D1', 'opinion', 'value', 'prefill', 'correct', ?, ?, ?, '', ?)
        """,
        (json.dumps("unqualified"), json.dumps("unqualified"), _OLD, now),
    )
    conn.commit()
    return conn


def _queue_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM gold_rereview").fetchone()[0]


def _outcome(conn, version: str, bundle: str) -> str:
    row = conn.execute(
        """
        SELECT outcome FROM gold_scores
        WHERE extractor_version = ? AND bundle = ?
        """,
        (version, bundle),
    ).fetchone()
    assert row is not None
    return row[0]


def test_identical_table_carries_over(tmp_path) -> None:
    conn = _prepare(tmp_path, old_hours=_hours(100, 5), new_hours=_hours(100, 5))
    rescore(conn, _NEW)
    assert table_carryover(conn, _OLD, _NEW) == []
    assert _queue_count(conn) == 0
    assert _outcome(conn, _NEW, "hours") == "tp"


def test_hours_key_value_mismatch_auto_fp(tmp_path) -> None:
    conn = _prepare(tmp_path, old_hours=_hours(100, 5), new_hours=_hours(90, 5))
    rescore(conn, _NEW)
    assert _outcome(conn, _NEW, "hours") == "fp"
    assert _queue_count(conn) == 0


def test_hours_changed_but_key_match_queued(tmp_path) -> None:
    conn = _prepare(
        tmp_path, old_hours=_hours(100, 5), new_hours=_hours(100, 5, extra=True)
    )
    queued = table_carryover(conn, _OLD, _NEW)
    assert len(queued) == 1
    assert queued[0].bundle == "hours"
    assert _queue_count(conn) == 1


def test_hours_cell_audit_only_change_does_not_carry_over(tmp_path) -> None:
    """HoursCell 스냅샷에서 감사시간만 바뀌면 라벨을 이월하지 않는다."""
    conn = _prepare(
        tmp_path,
        old_hours=_hours_cell_snapshot(100.0, 5.0),
        new_hours=_hours_cell_snapshot(90.0, 5.0),
        label_gold={"verdict": "correct"},
    )
    queued = table_carryover(conn, _OLD, _NEW)
    assert queued == []
    assert _queue_count(conn) == 0
    assert _outcome(conn, _NEW, "hours") == "fp"


def test_hours_cell_headcount_only_change_does_not_carry_over(tmp_path) -> None:
    """HoursCell 스냅샷에서 인원만 바뀌면 라벨을 이월하지 않는다."""
    conn = _prepare(
        tmp_path,
        old_hours=_hours_cell_snapshot(100.0, 5.0),
        new_hours=_hours_cell_snapshot(100.0, 6.0),
        label_gold={"verdict": "correct"},
    )
    queued = table_carryover(conn, _OLD, _NEW)
    assert queued == []
    assert _queue_count(conn) == 0
    assert _outcome(conn, _NEW, "hours") == "fp"


def test_scalar_rescored_without_human(tmp_path) -> None:
    conn = _prepare(
        tmp_path,
        old_hours=_hours(100, 5),
        new_hours=_hours(100, 5),
        scalar_new="qualified",
    )
    before = conn.execute("SELECT count(*) FROM gold_labels").fetchone()[0]
    rescore(conn, _NEW)
    assert _outcome(conn, _NEW, "opinion") == "fp"
    assert conn.execute("SELECT count(*) FROM gold_labels").fetchone()[0] == before
