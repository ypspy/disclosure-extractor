"""골드 라벨 저장, 이력, 다음 문서 큐.

판정은 gold.db에만 쓴다. extraction_reviews에는 쓰지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.subjects import BUNDLE_KEYS, subjects_for

PREFILL_GAP = 20


def _now() -> str:
    """UTC ISO 시각."""
    return datetime.now(UTC).isoformat()


def _dump(value: Any) -> str | None:
    """JSON 컬럼용 문자열. None은 SQL NULL."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _meta(raw: str | None) -> dict[str, Any]:
    """표본 meta JSON."""
    if not raw:
        return {}
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        return parsed
    return {}


def _sample(
    conn: sqlite3.Connection, run_id: str, rcept_no: str, dcm_no: str
) -> sqlite3.Row:
    """표본 한 행. 없으면 예외."""
    row = conn.execute(
        """
        SELECT * FROM gold_samples
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (run_id, rcept_no, dcm_no),
    ).fetchone()
    if row is None:
        raise ValueError(f"표본에 없는 문서입니다: {rcept_no}/{dcm_no}")
    return row


def _run_stats(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """실행 stats JSON."""
    row = conn.execute(
        "SELECT stats FROM gold_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None or not row[0]:
        return {}
    parsed = json.loads(row[0])
    if isinstance(parsed, dict):
        return parsed
    return {}


def _write_stats(conn: sqlite3.Connection, run_id: str, stats: dict[str, Any]) -> None:
    """실행 stats를 갱신한다."""
    conn.execute(
        "UPDATE gold_runs SET stats = ? WHERE run_id = ?",
        (json.dumps(stats, ensure_ascii=False), run_id),
    )


def required_subjects(
    conn: sqlite3.Connection, run_id: str, rcept_no: str, dcm_no: str
) -> list[tuple[str, str]]:
    """문서에서 판정해야 하는 (묶음, subject). 과표집은 그 필드만."""
    sample = _sample(conn, run_id, rcept_no, dcm_no)
    meta = _meta(sample["meta"])
    token = meta.get("oversample_for")
    if sample["role"] == "oversample" and isinstance(token, str) and ":" in token:
        bundle, subject = token.split(":", 1)
        return [(bundle, subject)]
    required: list[tuple[str, str]] = []
    for bundle in BUNDLE_KEYS:
        for subject in subjects_for(bundle):
            required.append((bundle, subject))
    return required


def save_label(
    conn: sqlite3.Connection,
    *,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    pass_: str,
    verdict: str,
    gold_value: Any,
    shown_value: Any,
    shown_version: str | None,
    evidence: Any = None,
    error_tag: str | None = None,
    note: str = "",
    seconds: int | None = None,
) -> None:
    """라벨을 저장한다. 기존 행은 이력으로 옮기고 덮어쓰지 않는다."""
    existing = conn.execute(
        """
        SELECT * FROM gold_labels
        WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
        """,
        (rcept_no, dcm_no, bundle, subject, pass_),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            INSERT INTO gold_label_history (
                rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
                shown_extractor_version, evidence, error_tag, note, labeled_at, seconds,
                superseded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                existing["rcept_no"],
                existing["dcm_no"],
                existing["bundle"],
                existing["subject"],
                existing["pass"],
                existing["verdict"],
                existing["gold_value"],
                existing["shown_value"],
                existing["shown_extractor_version"],
                existing["evidence"],
                existing["error_tag"],
                existing["note"],
                existing["labeled_at"],
                existing["seconds"],
                _now(),
            ),
        )
        conn.execute(
            """
            DELETE FROM gold_labels
            WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
            """,
            (rcept_no, dcm_no, bundle, subject, pass_),
        )
    conn.execute(
        """
        INSERT INTO gold_labels (
            rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
            shown_extractor_version, evidence, error_tag, note, labeled_at, seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rcept_no,
            dcm_no,
            bundle,
            subject,
            pass_,
            verdict,
            _dump(gold_value),
            _dump(shown_value),
            shown_version,
            _dump(evidence),
            error_tag,
            note or "",
            _now(),
            seconds,
        ),
    )
    conn.commit()


def _passes(meta: dict[str, Any]) -> dict[str, str]:
    """패스별 진행 상태."""
    raw = meta.get("passes")
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return {}


def _needed_passes(sample: sqlite3.Row) -> tuple[str, ...]:
    """이 문서가 끝나려면 필요한 패스."""
    if sample["mode"] == "blind":
        return ("blind", "prefill")
    return ("prefill",)


def complete_doc(
    conn: sqlite3.Connection,
    run_id: str,
    rcept_no: str,
    dcm_no: str,
    pass_: str,
) -> None:
    """한 패스를 완료한다. 미판정 subject가 있으면 거부한다."""
    sample = _sample(conn, run_id, rcept_no, dcm_no)
    missing = [
        f"{bundle}:{subject}"
        for bundle, subject in required_subjects(conn, run_id, rcept_no, dcm_no)
        if conn.execute(
            """
            SELECT 1 FROM gold_labels
            WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
            """,
            (rcept_no, dcm_no, bundle, subject, pass_),
        ).fetchone()
        is None
    ]
    if missing:
        raise ValueError("아직 판정하지 않은 항목이 있어 문서를 완료할 수 없습니다.")
    meta = _meta(sample["meta"])
    passes = _passes(meta)
    passes[pass_] = "done"
    meta["passes"] = passes
    meta.pop("open_pass", None)
    stats = _run_stats(conn, run_id)
    if pass_ == "blind" and sample["mode"] == "blind":
        served = int(stats.get("prefill_served") or 0)
        meta["prefill_not_before"] = served + PREFILL_GAP
    pending = [name for name in _needed_passes(sample) if passes.get(name) != "done"]
    if pending:
        status = "todo"
        finished = None
    else:
        status = "done"
        finished = _now()
    conn.execute(
        """
        UPDATE gold_samples
        SET status = ?, meta = ?, finished_at = ?
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (
            status,
            json.dumps(meta, ensure_ascii=False),
            finished,
            run_id,
            rcept_no,
            dcm_no,
        ),
    )
    conn.commit()


def next_doc(
    conn: sqlite3.Connection, run_id: str, period: str, pass_: str
) -> tuple[str, str] | None:
    """기간 큐에서 다음 문서를 연다. 블라인드 재검수는 20건 뒤에 배치한다."""
    rows = conn.execute(
        """
        SELECT * FROM gold_samples
        WHERE run_id = ? AND period = ?
          AND role IN ('main', 'oversample')
          AND status NOT IN ('excluded', 'skipped', 'done')
        ORDER BY queue_order, rcept_no
        """,
        (run_id, period),
    ).fetchall()
    stats = _run_stats(conn, run_id)
    served = int(stats.get("prefill_served") or 0)
    plain: list[sqlite3.Row] = []
    released: list[sqlite3.Row] = []
    for row in rows:
        meta = _meta(row["meta"])
        passes = _passes(meta)
        if pass_ == "blind":
            if row["mode"] != "blind" or passes.get("blind") == "done":
                continue
            plain.append(row)
            continue
        if passes.get("prefill") == "done":
            continue
        if row["mode"] == "blind":
            if passes.get("blind") != "done":
                continue
            not_before = int(meta.get("prefill_not_before") or 0)
            if served < not_before:
                continue
            released.append(row)
            continue
        plain.append(row)
    if released:
        pick = released[0]
    elif plain:
        pick = plain[0]
    else:
        return None
    meta = _meta(pick["meta"])
    already_open = pick["status"] == "in_progress" and meta.get("open_pass") == pass_
    if pass_ == "prefill" and pick["mode"] != "blind" and not already_open:
        served += 1
        stats["prefill_served"] = served
        _write_stats(conn, run_id, stats)
    meta["open_pass"] = pass_
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'in_progress', meta = ?,
            started_at = COALESCE(started_at, ?)
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (
            json.dumps(meta, ensure_ascii=False),
            _now(),
            run_id,
            pick["rcept_no"],
            pick["dcm_no"],
        ),
    )
    conn.commit()
    return (pick["rcept_no"], pick["dcm_no"])


def exclude_doc(
    conn: sqlite3.Connection,
    run_id: str,
    rcept_no: str,
    dcm_no: str,
    reason: str,
) -> tuple[str, str] | None:
    """문서를 제외하고 같은 층의 예비분을 본표본으로 올린다."""
    sample = _sample(conn, run_id, rcept_no, dcm_no)
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'excluded', exclude_reason = ?
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (reason, run_id, rcept_no, dcm_no),
    )
    reserve = conn.execute(
        """
        SELECT rcept_no, dcm_no FROM gold_samples
        WHERE run_id = ? AND stratum = ? AND role = 'reserve' AND status = 'todo'
        ORDER BY sample_hash
        LIMIT 1
        """,
        (run_id, sample["stratum"]),
    ).fetchone()
    if reserve is None:
        conn.commit()
        return None
    conn.execute(
        """
        UPDATE gold_samples
        SET role = 'main', queue_order = ?
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (sample["queue_order"], run_id, reserve["rcept_no"], reserve["dcm_no"]),
    )
    conn.commit()
    return (reserve["rcept_no"], reserve["dcm_no"])
