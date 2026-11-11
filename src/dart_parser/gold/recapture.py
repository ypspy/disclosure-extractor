"""블라인드 재입수 대상, 일치 리포트, 불일치 판정.

재입수 값은 gold_recaptures에만 있다. 이 모듈은 네트워크와 샘플러를 호출하지 않는다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.capture_store import load_captures
from dart_parser.gold.labels import PREFILL_GAP
from dart_parser.gold.scoring import (
    Label,
    document_labels,
    gold_values_agree,
    wilson,
)

_ROLES = frozenset({"main", "oversample"})


@dataclass(frozen=True)
class ConsistencyRow:
    """필드·기간 하나의 일치 집계. 통과 판정에는 쓰지 않는다."""

    period: str
    bundle: str
    subject: str
    n: int
    agree: int
    rate: float
    wilson_lo: float


@dataclass(frozen=True)
class Disagreement:
    """재입수가 끝난 문서에서 1차와 2차가 다른 채점 키."""

    rcept_no: str
    dcm_no: str
    bundle: str
    subject: str
    period: str
    first: Label | None
    second: Label | None


def eligible(conn: sqlite3.Connection, run_id: str, rcept_no: str, dcm_no: str) -> bool:
    """블라인드 본표본·과표집이고, 같은 실행·기간에 더 늦게 끝난 문서가 20건 이상."""
    row = conn.execute(
        """
        SELECT mode, role, status, period, finished_at
        FROM gold_samples
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (run_id, rcept_no, dcm_no),
    ).fetchone()
    if row is None or row["finished_at"] is None:
        return False
    if row["mode"] != "blind" or row["role"] not in _ROLES or row["status"] != "done":
        return False
    later = conn.execute(
        """
        SELECT COUNT(*)
        FROM gold_samples
        WHERE run_id = ? AND period = ? AND status = 'done'
          AND finished_at > ?
          AND NOT (rcept_no = ? AND dcm_no = ?)
        """,
        (run_id, row["period"], row["finished_at"], rcept_no, dcm_no),
    ).fetchone()
    return later is not None and int(later[0]) >= PREFILL_GAP


def recapture_in_progress(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM gold_recapture_status
        WHERE rcept_no = ? AND dcm_no = ? AND status = 'in_progress'
        LIMIT 1
        """,
        (rcept_no, dcm_no),
    ).fetchone()
    return row is not None


def can_open_recapture(conn: sqlite3.Connection, run_id: str, rcept_no: str, dcm_no: str) -> bool:
    """재입수 행이 있으면 대상 조건과 상관없이 이어 할 수 있다."""
    started = conn.execute(
        """
        SELECT 1 FROM gold_recapture_status
        WHERE rcept_no = ? AND dcm_no = ?
        LIMIT 1
        """,
        (rcept_no, dcm_no),
    ).fetchone()
    if started is not None:
        return True
    return eligible(conn, run_id, rcept_no, dcm_no)


def next_recapture(conn: sqlite3.Connection, period: str) -> tuple[str, str] | None:
    """진행 중인 재입수를 먼저, 없으면 대상 문서를 queue_order로 고른다. 쓰지 않는다."""
    current = conn.execute(
        """
        SELECT s.rcept_no, s.dcm_no
        FROM gold_recapture_status r
        JOIN gold_samples s
          ON s.run_id = r.run_id AND s.rcept_no = r.rcept_no AND s.dcm_no = r.dcm_no
        WHERE r.status = 'in_progress' AND s.period = ?
        ORDER BY s.queue_order, s.rcept_no
        LIMIT 1
        """,
        (period,),
    ).fetchone()
    if current is not None:
        return str(current["rcept_no"]), str(current["dcm_no"])
    waiting = conn.execute(
        """
        SELECT run_id, rcept_no, dcm_no
        FROM gold_samples
        WHERE period = ?
          AND mode = 'blind'
          AND role IN ('main', 'oversample')
          AND status = 'done'
          AND NOT EXISTS (
              SELECT 1 FROM gold_recapture_status r
              WHERE r.run_id = gold_samples.run_id
                AND r.rcept_no = gold_samples.rcept_no
                AND r.dcm_no = gold_samples.dcm_no
          )
        ORDER BY queue_order, rcept_no
        """,
        (period,),
    ).fetchall()
    for row in waiting:
        if eligible(conn, str(row["run_id"]), str(row["rcept_no"]), str(row["dcm_no"])):
            return str(row["rcept_no"]), str(row["dcm_no"])
    return None


def recapture_progress(conn: sqlite3.Connection, period: str) -> tuple[int, int]:
    """기간의 재입수 완료 수와 대상 수. 이어 하는 문서도 대상에 넣는다."""
    samples = conn.execute(
        """
        SELECT run_id, rcept_no, dcm_no
        FROM gold_samples
        WHERE period = ?
        """,
        (period,),
    ).fetchall()
    done = 0
    target = 0
    for sample in samples:
        status = conn.execute(
            """
            SELECT status FROM gold_recapture_status
            WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
            """,
            (sample["run_id"], sample["rcept_no"], sample["dcm_no"]),
        ).fetchone()
        if status is not None or eligible(
            conn, str(sample["run_id"]), str(sample["rcept_no"]), str(sample["dcm_no"])
        ):
            target += 1
        if status is not None and status["status"] == "done":
            done += 1
    return done, target


def consistency_report(conn: sqlite3.Connection, run_id: str) -> list[ConsistencyRow]:
    """재입수가 done인 문서만 필드·기간별로 센다. 통과선 계산에 쓰지 않는다."""
    tallies = _compare(conn, run_id)
    combined: dict[tuple[str, str], list[int]] = {}
    rows: list[ConsistencyRow] = []
    for (period, bundle, subject), (count, agreed) in sorted(tallies.items()):
        rows.append(_consistency_row(period, bundle, subject, count, agreed))
        bucket = combined.setdefault((bundle, subject), [0, 0])
        bucket[0] += count
        bucket[1] += agreed
    for (bundle, subject), (count, agreed) in sorted(combined.items()):
        rows.append(_consistency_row("", bundle, subject, count, agreed))
    return rows


def disagreements(conn: sqlite3.Connection, run_id: str) -> list[Disagreement]:
    """불일치한 문서·묶음·subject. 1차와 2차 라벨을 함께 담는다."""
    found: list[Disagreement] = []
    for doc in _done_documents(conn, run_id):
        left, right = _label_pair(conn, str(doc["rcept_no"]), str(doc["dcm_no"]))
        for bundle, subject in sorted(set(left) | set(right)):
            first = left.get((bundle, subject))
            second = right.get((bundle, subject))
            if gold_values_agree(bundle, subject, first, second) is not False:
                continue
            found.append(
                Disagreement(
                    str(doc["rcept_no"]),
                    str(doc["dcm_no"]),
                    bundle,
                    subject,
                    str(doc["period"]),
                    first,
                    second,
                )
            )
    return found


def save_adjudication(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    chosen_pass: int,
    note: str,
    *,
    run_id: str,
) -> bool:
    """불일치 키만 판정한다. 이전 판정은 이력에 복사하고 한 번만 commit 한다."""
    if chosen_pass not in {1, 2} or not str(note).strip():
        return False
    key = (rcept_no, dcm_no, bundle, subject)
    if key not in {
        (item.rcept_no, item.dcm_no, item.bundle, item.subject)
        for item in disagreements(conn, run_id)
    }:
        return False

    def work() -> bool:
        previous = conn.execute(
            """
            SELECT * FROM gold_adjudications
            WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
            """,
            key,
        ).fetchone()
        now = _now()
        if previous is not None:
            conn.execute(
                """
                INSERT INTO gold_adjudication_history (
                    rcept_no, dcm_no, bundle, subject, chosen_pass, note,
                    decided_at, superseded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    previous["rcept_no"],
                    previous["dcm_no"],
                    previous["bundle"],
                    previous["subject"],
                    previous["chosen_pass"],
                    previous["note"],
                    previous["decided_at"],
                    now,
                ),
            )
        conn.execute(
            """
            INSERT INTO gold_adjudications (
                rcept_no, dcm_no, bundle, subject, chosen_pass, note, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (rcept_no, dcm_no, bundle, subject) DO UPDATE SET
                chosen_pass = excluded.chosen_pass,
                note = excluded.note,
                decided_at = excluded.decided_at
            """,
            (rcept_no, dcm_no, bundle, subject, chosen_pass, note, now),
        )
        return True

    return bool(_finish(conn, work))


def _compare(conn: sqlite3.Connection, run_id: str) -> dict[tuple[str, str, str], list[int]]:
    tallies: dict[tuple[str, str, str], list[int]] = {}
    for doc in _done_documents(conn, run_id):
        left, right = _label_pair(conn, str(doc["rcept_no"]), str(doc["dcm_no"]))
        for bundle, subject in set(left) | set(right):
            result = gold_values_agree(
                bundle, subject, left.get((bundle, subject)), right.get((bundle, subject))
            )
            if result is None:
                continue
            slot = tallies.setdefault((str(doc["period"]), bundle, subject), [0, 0])
            slot[0] += 1
            if result:
                slot[1] += 1
    return tallies


def _done_documents(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT s.rcept_no, s.dcm_no, s.period
            FROM gold_recapture_status r
            JOIN gold_samples s
              ON s.run_id = r.run_id
             AND s.rcept_no = r.rcept_no
             AND s.dcm_no = r.dcm_no
            WHERE r.run_id = ? AND r.status = 'done'
            """,
            (run_id,),
        )
    )


def _label_pair(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str
) -> tuple[dict[tuple[str, str], Label], dict[tuple[str, str], Label]]:
    left_rows = _stored_rows(conn, rcept_no, dcm_no, 1)
    right_rows = _stored_rows(conn, rcept_no, dcm_no, 2)
    left = {
        (label.bundle, label.subject): label
        for label in document_labels(rcept_no, dcm_no, left_rows)
    }
    right = {
        (label.bundle, label.subject): label
        for label in document_labels(rcept_no, dcm_no, right_rows)
    }
    return left, right


def _stored_rows(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str, capture_pass: int
) -> dict[tuple[str, str], dict[str, Any]]:
    loaded = load_captures(conn, rcept_no, dcm_no, capture_pass=capture_pass)
    return {
        key: {"status": row["status"], "value": row["value"]}
        for key, row in loaded.items()
    }


def _stored_rows(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str, capture_pass: int
) -> dict[tuple[str, str], dict[str, Any]]:
    loaded = load_captures(conn, rcept_no, dcm_no, capture_pass=capture_pass)
    return {
        key: {"status": row["status"], "value": row["value"]}
        for key, row in loaded.items()
    }


def _consistency_row(
    period: str, bundle: str, subject: str, count: int, agreed: int
) -> ConsistencyRow:
    rate = agreed / count if count else 0.0
    return ConsistencyRow(
        period=period,
        bundle=bundle,
        subject=subject,
        n=count,
        agree=agreed,
        rate=rate,
        wilson_lo=wilson(agreed, count)[0],
    )


def _finish(conn: sqlite3.Connection, work: Any) -> Any:
    try:
        result = work()
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _now() -> str:
    return datetime.now(UTC).isoformat()
