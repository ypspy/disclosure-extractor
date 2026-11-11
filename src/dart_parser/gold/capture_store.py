"""gold_captures 읽기·쓰기. gold_labels는 쓰지 않는다."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.capture import SCALES, known_subject, money_group, parse_click

_ABSENT = frozenset({"not_applicable", "not_in_regime"})


def save_capture(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    text: str,
) -> bool:
    scale = None
    group = money_group(bundle, subject)
    if group is not None:
        scale = load_units(conn, rcept_no, dcm_no).get(group)
    engagement = _engagement(conn, rcept_no, dcm_no)
    parsed = parse_click(
        bundle,
        subject,
        text,
        unit_scale=scale,
        icfr_engagement=engagement,
    )
    if parsed is None:
        return False
    if (bundle, subject) in {("notes_toc", "value"), ("communications", "items")}:
        parsed = _append(conn, rcept_no, dcm_no, bundle, subject, parsed)
    _upsert(conn, rcept_no, dcm_no, bundle, subject, "found", parsed, text)
    if bundle == "icfr" and subject == "engagement" and parsed != engagement:
        clear_capture(conn, rcept_no, dcm_no, "icfr", "opinion")
    return True


def set_capture_status(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    status: str,
) -> bool:
    if status not in _ABSENT or not known_subject(bundle, subject):
        return False
    _upsert(conn, rcept_no, dcm_no, bundle, subject, status, None, "")
    return True


def clear_capture(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
) -> None:
    conn.execute(
        """
        DELETE FROM gold_captures
        WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
        """,
        (rcept_no, dcm_no, bundle, subject),
    )
    conn.commit()


def set_unit(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    unit_group: str,
    unit_scale: int,
) -> bool:
    if unit_group not in {"bs", "is"} or unit_scale not in SCALES:
        return False
    conn.execute(
        """
        INSERT INTO gold_capture_units (rcept_no, dcm_no, unit_group, unit_scale)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (rcept_no, dcm_no, unit_group)
        DO UPDATE SET unit_scale = excluded.unit_scale
        """,
        (rcept_no, dcm_no, unit_group, unit_scale),
    )
    for row in load_captures(conn, rcept_no, dcm_no).values():
        if row["status"] != "found" or money_group(row["bundle"], row["subject"]) != unit_group:
            continue
        amount = json.loads(row["value"])
        amount["unit_scale"] = unit_scale
        amount["value_won"] = None if amount.get("value") is None else amount["value"] * unit_scale
        conn.execute(
            """
            UPDATE gold_captures SET value = ?, updated_at = ?
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
    conn.commit()
    return True


def load_captures(
    conn: sqlite3.Connection, rcept_no: str, dcm_no: str
) -> dict[tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT bundle, subject, status, value, evidence
        FROM gold_captures
        WHERE rcept_no = ? AND dcm_no = ?
        """,
        (rcept_no, dcm_no),
    )
    return {(str(row["bundle"]), str(row["subject"])): row for row in rows}


def load_units(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT unit_group, unit_scale FROM gold_capture_units
        WHERE rcept_no = ? AND dcm_no = ?
        """,
        (rcept_no, dcm_no),
    )
    return {str(row["unit_group"]): int(row["unit_scale"]) for row in rows}


def _engagement(conn: sqlite3.Connection, rcept_no: str, dcm_no: str) -> str | None:
    row = load_captures(conn, rcept_no, dcm_no).get(("icfr", "engagement"))
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
) -> Any:
    current = load_captures(conn, rcept_no, dcm_no).get((bundle, subject))
    if bundle == "notes_toc":
        titles: list[str] = []
        if current is not None and current["status"] == "found" and current["value"]:
            titles = list(json.loads(current["value"]).get("titles") or [])
        titles.append(str(parsed))
        return {"count": len(titles), "titles": titles}
    items: list[dict[str, Any]] = []
    if current is not None and current["status"] == "found" and current["value"]:
        items = list(json.loads(current["value"]))
    item = dict(parsed)
    item["round"] = len(items) + 1
    items.append(item)
    return items


def _upsert(
    conn: sqlite3.Connection,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    status: str,
    value: Any,
    evidence: str,
) -> None:
    conn.execute(
        """
        INSERT INTO gold_captures (
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
    conn.commit()


def _now() -> str:
    return datetime.now(UTC).isoformat()
