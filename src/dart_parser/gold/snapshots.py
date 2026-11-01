"""캐시 HTML을 추출기에 넣어 버전·커밋과 함께 저장한다."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import dart_parser
from dart_parser.gold.cache import cache_dir
from dart_parser.pipeline import Pipeline


def capture(
    conn: sqlite3.Connection,
    run_id: str,
    cache_root: Path,
    version: str | None = None,
    commit: str | None = None,
) -> int:
    """표본 캐시의 main.html을 추출해 스냅샷으로 넣는다. 이미 있으면 건너뛴다."""
    requested = version or dart_parser.__version__
    revision = commit if commit is not None else git_commit()
    samples = conn.execute(
        "SELECT rcept_no, dcm_no FROM gold_samples WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    pending: list[tuple[str, str, dict[str, Any]]] = []
    pipeline = Pipeline()
    for sample in samples:
        rcept_no = sample["rcept_no"]
        dcm_no = sample["dcm_no"]
        exists = conn.execute(
            """
            SELECT 1 FROM extractor_snapshots
            WHERE extractor_version = ? AND rcept_no = ? AND dcm_no = ?
            """,
            (requested, rcept_no, dcm_no),
        ).fetchone()
        if exists is not None:
            continue
        html_path = cache_dir(cache_root, rcept_no) / "main.html"
        if not html_path.is_file():
            raise ValueError(f"캐시에 원문이 없습니다: {rcept_no}")
        html = html_path.read_text(encoding="utf-8")
        result = pipeline.run_from_html(html, rcept_no=rcept_no, use_fallback=False)
        pending.append(
            (
                rcept_no,
                dcm_no,
                {
                    "extractor_version": requested,
                    "commit": revision,
                    "rcept_no": rcept_no,
                    "dcm_no": dcm_no,
                    "extraction": result.extraction.model_dump(mode="json"),
                },
            )
        )
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


def git_commit() -> str:
    """이 저장소 HEAD. git을 쓸 수 없으면 unknown."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


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
