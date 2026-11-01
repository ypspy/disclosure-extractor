"""골드 문서의 추출기 버전별 facts 스냅샷."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.v19_fields import EXTRACTOR_VERSION


def capture(conn: sqlite3.Connection, run_id: str, version: str | None = None) -> int:
    """표본 문서를 스냅샷으로 복사한다. 이미 있으면 건너뛰고, 버전이 다르면 거부한다."""
    requested = version or EXTRACTOR_VERSION
    samples = conn.execute(
        "SELECT rcept_no, dcm_no FROM gold_samples WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    pending: list[tuple[str, str, dict[str, Any]]] = []
    for sample in samples:
        exists = conn.execute(
            """
            SELECT 1 FROM extractor_snapshots
            WHERE extractor_version = ? AND rcept_no = ? AND dcm_no = ?
            """,
            (requested, sample["rcept_no"], sample["dcm_no"]),
        ).fetchone()
        if exists is not None:
            continue
        fact = conn.execute(
            """
            SELECT * FROM cat.audit_report_facts
            WHERE rcept_no = ? AND dcm_no = ?
            """,
            (sample["rcept_no"], sample["dcm_no"]),
        ).fetchone()
        if fact is None:
            raise ValueError(
                f"카탈로그에 없는 문서입니다: {sample['rcept_no']}/{sample['dcm_no']}"
            )
        if fact["extractor_version"] != requested:
            raise ValueError(
                "카탈로그 추출기 버전 "
                f"({fact['extractor_version']})이 요청({requested})과 다릅니다."
            )
        pending.append((sample["rcept_no"], sample["dcm_no"], dict(fact)))
    captured_at = datetime.now(UTC).isoformat()
    for rcept_no, dcm_no, payload in pending:
        conn.execute(
            """
            INSERT INTO extractor_snapshots (
                extractor_version, rcept_no, dcm_no, payload, captured_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                requested,
                rcept_no,
                dcm_no,
                json.dumps(payload, ensure_ascii=False),
                captured_at,
            ),
        )
    conn.commit()
    return len(pending)


def load_snapshot(
    conn: sqlite3.Connection,
    version: str,
    rcept_no: str,
    dcm_no: str,
) -> dict[str, Any] | None:
    """스냅샷 JSON을 읽는다. 없으면 None."""
    row = conn.execute(
        """
        SELECT payload, extractor_version FROM extractor_snapshots
        WHERE extractor_version = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (version, rcept_no, dcm_no),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    payload["extractor_version"] = row["extractor_version"]
    return payload


def versions(conn: sqlite3.Connection) -> list[str]:
    """저장된 추출기 버전 목록."""
    rows = conn.execute(
        "SELECT DISTINCT extractor_version FROM extractor_snapshots ORDER BY 1"
    ).fetchall()
    return [row[0] for row in rows]
