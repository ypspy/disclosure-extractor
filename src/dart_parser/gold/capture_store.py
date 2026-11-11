"""gold_captures 읽기·쓰기. gold_labels는 쓰지 않는다.

``capture_pass`` 1은 1차 테이블, 2는 재입수 테이블이다.
테이블 이름은 이 매핑에서만 고르고, 호출 값을 SQL에 붙이지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.capture import SCALES, known_subject, money_group, parse_click
from dart_parser.normalizer.cleaner import normalize_text

_ABSENT = frozenset({"not_applicable", "not_in_regime"})
_LISTS = {("notes_toc", "value"), ("communications", "items")}
_PASS_TABLES: dict[int, tuple[str, str, str]] = {
    1: ("gold_captures", "gold_capture_units", "gold_capture_history"),
    2: ("gold_recaptures", "gold_recapture_units", "gold_recapture_history"),
}


class _Unchanged:
    """이미 있는 제목·회차라 다시 붙이지 않는다."""


_UNCHANGED = _Unchanged()


def _tables(capture_pass: int) -> tuple[str, str, str]:
    try:
        return _PASS_TABLES[capture_pass]
    except KeyError as exc:
        raise ValueError("capture_pass는 1 또는 2입니다.") from exc


def save_capture(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    text: str,
    *,
    capture_pass: int = 1,
) -> bool:
    rows_table, _units_table, history_table = _tables(capture_pass)
    scale = None
    group = money_group(bundle, subject)
    if group is not None:
        scale = load_units(conn, rcept_no, dcm_no, capture_pass=capture_pass).get(group)
    engagement = _engagement(conn, rcept_no, dcm_no, capture_pass)
    parsed = parse_click(
        bundle,
        subject,
        text,
        unit_scale=scale,
        icfr_engagement=engagement,
    )
    if parsed is None:
        return False
    if (bundle, subject) in _LISTS:
        appended = _append(conn, rcept_no, dcm_no, bundle, subject, parsed, capture_pass)
        if appended is _UNCHANGED:
            return True
        parsed = appended

    def work() -> bool:
        previous = _row(conn, rcept_no, dcm_no, bundle, subject, rows_table)
        if previous is not None:
            _history(conn, previous, "update", history_table)
        _upsert(conn, rcept_no, dcm_no, bundle, subject, "found", parsed, text, rows_table)
        if bundle == "icfr" and subject == "engagement" and parsed != engagement:
            opinion = _row(conn, rcept_no, dcm_no, "icfr", "opinion", rows_table)
            if opinion is not None:
                _history(conn, opinion, "clear", history_table)
                _delete(conn, rcept_no, dcm_no, "icfr", "opinion", rows_table)
        _mark_progress(conn, rcept_no, dcm_no, capture_pass=capture_pass, reopen_done=False)
        return True

    return bool(_finish(conn, work))


def set_capture_status(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    status: str,
    *,
    capture_pass: int = 1,
) -> bool:
    if status not in _ABSENT or not known_subject(bundle, subject):
        return False
    rows_table, _units_table, history_table = _tables(capture_pass)

    def work() -> bool:
        previous = _row(conn, rcept_no, dcm_no, bundle, subject, rows_table)
        if previous is not None:
            _history(conn, previous, "update", history_table)
        _upsert(conn, rcept_no, dcm_no, bundle, subject, status, None, "", rows_table)
        _mark_progress(conn, rcept_no, dcm_no, capture_pass=capture_pass, reopen_done=True)
        return True

    return bool(_finish(conn, work))


def clear_capture(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    *,
    capture_pass: int = 1,
) -> None:
    rows_table, _units_table, history_table = _tables(capture_pass)

    def work() -> None:
        previous = _row(conn, rcept_no, dcm_no, bundle, subject, rows_table)
        if previous is None:
            return
        _history(conn, previous, "clear", history_table)
        _delete(conn, rcept_no, dcm_no, bundle, subject, rows_table)
        _mark_progress(conn, rcept_no, dcm_no, capture_pass=capture_pass, reopen_done=True)

    _finish(conn, work)


def remove_list_item(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    index: int,
    *,
    capture_pass: int = 1,
) -> bool:
    """주석 제목 또는 커뮤니케이션 회차 하나를 지우고 이력을 남긴다.

    마지막 항목이면 개수 0인 found로 남기지 않고 행을 지운다.
    """
    if (bundle, subject) not in _LISTS or index < 0:
        return False
    rows_table, _units_table, history_table = _tables(capture_pass)

    def work() -> bool:
        previous = _row(conn, rcept_no, dcm_no, bundle, subject, rows_table)
        if previous is None or previous["status"] != "found" or not previous["value"]:
            return False
        parsed = json.loads(previous["value"])
        if bundle == "notes_toc":
            titles = list(parsed.get("titles") or [])
            if index >= len(titles):
                return False
            del titles[index]
            empty = not titles
            value: Any = {"count": len(titles), "titles": titles}
        else:
            items = [item for item in parsed if isinstance(item, dict)]
            if index >= len(items):
                return False
            del items[index]
            for number, item in enumerate(items, start=1):
                item["round"] = number
            empty = not items
            value = items
        if empty:
            _history(conn, previous, "clear", history_table)
            _delete(conn, rcept_no, dcm_no, bundle, subject, rows_table)
            _mark_progress(conn, rcept_no, dcm_no, capture_pass=capture_pass, reopen_done=True)
            return True
        _history(conn, previous, "update", history_table)
        _upsert(
            conn,
            rcept_no,
            dcm_no,
            bundle,
            subject,
            "found",
            value,
            previous["evidence"],
            rows_table,
        )
        _mark_progress(conn, rcept_no, dcm_no, capture_pass=capture_pass, reopen_done=False)
        return True

    return bool(_finish(conn, work))


def set_unit(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    unit_group: str,
    unit_scale: int,
    *,
    capture_pass: int = 1,
) -> bool:
    if unit_group not in {"bs", "is"} or unit_scale not in SCALES:
        return False
    rows_table, units_table, history_table = _tables(capture_pass)

    def work() -> bool:
        conn.execute(
            f"""
            INSERT INTO {units_table} (rcept_no, dcm_no, unit_group, unit_scale)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (rcept_no, dcm_no, unit_group)
            DO UPDATE SET unit_scale = excluded.unit_scale
            """,
            (rcept_no, dcm_no, unit_group, unit_scale),
        )
        rows = conn.execute(
            f"""
            SELECT * FROM {rows_table}
            WHERE rcept_no = ? AND dcm_no = ? AND status = 'found'
            """,
            (rcept_no, dcm_no),
        ).fetchall()
        for row in rows:
            if money_group(row["bundle"], row["subject"]) != unit_group or not row["value"]:
                continue
            _history(conn, row, "unit", history_table)
            amount = json.loads(row["value"])
            amount["unit_scale"] = unit_scale
            amount["value_won"] = (
                None if amount.get("value") is None else amount["value"] * unit_scale
            )
            conn.execute(
                f"""
                UPDATE {rows_table} SET value = ?, updated_at = ?
                WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
                """,
                (
                    json.dumps(amount, ensure_ascii=False),
                    _now(),
                    rcept_no,
                    dcm_no,
                    row["bundle"],
                    row["subject"],
                ),
            )
        return True

    return bool(_finish(conn, work))


def finish_recapture(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> bool:
    """재입수를 done으로 닫는다. gold_samples는 바꾸지 않는다."""

    def work() -> bool:
        run_id = _sample_run(conn, rcept_no, dcm_no)
        if run_id is None:
            return False
        now = _now()
        conn.execute(
            """
            INSERT INTO gold_recapture_status (
                run_id, rcept_no, dcm_no, status, started_at, finished_at
            ) VALUES (?, ?, ?, 'done', ?, ?)
            ON CONFLICT (run_id, rcept_no, dcm_no) DO UPDATE SET
                status = 'done',
                finished_at = excluded.finished_at,
                started_at = COALESCE(gold_recapture_status.started_at, excluded.started_at)
            """,
            (run_id, rcept_no, dcm_no, now, now),
        )
        return True

    return bool(_finish(conn, work))


def load_captures(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
) -> dict[tuple[str, str], sqlite3.Row]:
    rows_table, _units_table, _history_table = _tables(capture_pass)
    rows = conn.execute(
        f"""
        SELECT bundle, subject, status, value, evidence
        FROM {rows_table}
        WHERE rcept_no = ? AND dcm_no = ?
        """,
        (rcept_no, dcm_no),
    )
    return {(str(row["bundle"]), str(row["subject"])): row for row in rows}


def load_units(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
) -> dict[str, int]:
    _rows_table, units_table, _history_table = _tables(capture_pass)
    rows = conn.execute(
        f"""
        SELECT unit_group, unit_scale FROM {units_table}
        WHERE rcept_no = ? AND dcm_no = ?
        """,
        (rcept_no, dcm_no),
    )
    return {str(row["unit_group"]): int(row["unit_scale"]) for row in rows}


def _finish(conn: sqlite3.Connection, work: Callable[[], Any]) -> Any:
    """이전 행을 이력에 복사한 뒤 바꾸고, 한 번만 commit 한다."""
    try:
        result = work()
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _engagement(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str, capture_pass: int
) -> str | None:
    row = load_captures(conn, rcept_no, dcm_no, capture_pass=capture_pass).get(
        ("icfr", "engagement")
    )
    if row is None or row["status"] != "found" or not row["value"]:
        return None
    parsed = json.loads(row["value"])
    if parsed in {"audit", "review"}:
        return str(parsed)
    return None


def _append(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    parsed: Any,
    capture_pass: int,
) -> Any:
    current = load_captures(conn, rcept_no, dcm_no, capture_pass=capture_pass).get(
        (bundle, subject)
    )
    if bundle == "notes_toc":
        titles: list[str] = []
        if current is not None and current["status"] == "found" and current["value"]:
            titles = list(json.loads(current["value"]).get("titles") or [])
        if any(normalize_text(title) == normalize_text(str(parsed)) for title in titles):
            return _UNCHANGED
        titles.append(str(parsed))
        return {"count": len(titles), "titles": titles}
    items: list[dict[str, Any]] = []
    if current is not None and current["status"] == "found" and current["value"]:
        items = [item for item in json.loads(current["value"]) if isinstance(item, dict)]
    raw = str(parsed.get("raw") if isinstance(parsed, dict) else parsed)
    if any(normalize_text(str(item.get("raw") or "")) == normalize_text(raw) for item in items):
        return _UNCHANGED
    item = dict(parsed)
    item["round"] = len(items) + 1
    items.append(item)
    return items


def _row(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    rows_table: str,
) -> sqlite3.Row | None:
    return conn.execute(
        f"""
        SELECT * FROM {rows_table}
        WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
        """,
        (rcept_no, dcm_no, bundle, subject),
    ).fetchone()


def _history(conn: sqlite3.Connection, row: sqlite3.Row, action: str, history_table: str) -> None:
    conn.execute(
        f"""
        INSERT INTO {history_table} (
            rcept_no, dcm_no, bundle, subject, status, value, evidence,
            updated_at, action, superseded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["rcept_no"],
            row["dcm_no"],
            row["bundle"],
            row["subject"],
            row["status"],
            row["value"],
            row["evidence"],
            row["updated_at"],
            action,
            _now(),
        ),
    )


def _upsert(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    status: str,
    value: Any,
    evidence: str,
    rows_table: str,
) -> None:
    conn.execute(
        f"""
        INSERT INTO {rows_table} (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (rcept_no, dcm_no, bundle, subject)
        DO UPDATE SET
            status = excluded.status,
            value = excluded.value,
            evidence = excluded.evidence,
            updated_at = excluded.updated_at
        """,
        (
            rcept_no,
            dcm_no,
            bundle,
            subject,
            status,
            None if value is None else json.dumps(value, ensure_ascii=False),
            evidence,
            _now(),
        ),
    )


def _delete(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    rows_table: str,
) -> None:
    conn.execute(
        f"""
        DELETE FROM {rows_table}
        WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
        """,
        (rcept_no, dcm_no, bundle, subject),
    )


def _mark_progress(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int,
    reopen_done: bool,
) -> None:
    if capture_pass == 1:
        _mark_started(conn, rcept_no, dcm_no, reopen_done=reopen_done)
        return
    _mark_recapture(conn, rcept_no, dcm_no, reopen_done=reopen_done)


def _mark_started(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str, *, reopen_done: bool = False
) -> None:
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'in_progress',
            started_at = COALESCE(started_at, ?)
        WHERE rcept_no = ? AND dcm_no = ?
          AND status NOT IN ('done', 'excluded', 'skipped')
        """,
        (_now(), rcept_no, dcm_no),
    )
    if not reopen_done:
        return
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'in_progress',
            finished_at = NULL,
            started_at = COALESCE(started_at, ?)
        WHERE rcept_no = ? AND dcm_no = ?
          AND status = 'done'
        """,
        (_now(), rcept_no, dcm_no),
    )


def _mark_recapture(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str, *, reopen_done: bool
) -> None:
    """첫 쓰기는 in_progress다. done을 되돌리는 쓰기는 finished_at을 비운다."""
    run_id = _sample_run(conn, rcept_no, dcm_no)
    if run_id is None:
        return
    now = _now()
    if reopen_done:
        conn.execute(
            """
            INSERT INTO gold_recapture_status (
                run_id, rcept_no, dcm_no, status, started_at, finished_at
            ) VALUES (?, ?, ?, 'in_progress', ?, NULL)
            ON CONFLICT (run_id, rcept_no, dcm_no) DO UPDATE SET
                status = 'in_progress',
                finished_at = NULL,
                started_at = COALESCE(gold_recapture_status.started_at, excluded.started_at)
            """,
            (run_id, rcept_no, dcm_no, now),
        )
        return
    conn.execute(
        """
        INSERT INTO gold_recapture_status (
            run_id, rcept_no, dcm_no, status, started_at, finished_at
        ) VALUES (?, ?, ?, 'in_progress', ?, NULL)
        ON CONFLICT (run_id, rcept_no, dcm_no) DO UPDATE SET
            started_at = COALESCE(gold_recapture_status.started_at, excluded.started_at)
        """,
        (run_id, rcept_no, dcm_no, now),
    )


def _sample_run(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> str | None:
    row = conn.execute(
        """
        SELECT run_id FROM gold_samples
        WHERE rcept_no = ? AND dcm_no = ?
        ORDER BY queue_order
        LIMIT 1
        """,
        (rcept_no, dcm_no),
    ).fetchone()
    if row is None:
        return None
    return str(row["run_id"])


def _now() -> str:
    return datetime.now(UTC).isoformat()
