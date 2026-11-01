"""골드 채점, Wilson 하한, 희소 필드 풀링, 블라인드 비교."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.matching import matches
from dart_parser.gold.periods import FLAGGED_SAMPLE_PERIODS
from dart_parser.gold.sampler import is_claim
from dart_parser.gold.snapshots import load_snapshot, versions
from dart_parser.gold.subjects import TABLE_BUNDLES, extract_predicted

_PASS_LINE = 0.99


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 구간. n이 0이면 (0, 1)."""
    if n <= 0:
        return (0.0, 1.0)
    proportion = k / n
    denom = 1 + z * z / n
    center = proportion + z * z / (2 * n)
    margin = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n))
    return ((center - margin) / denom, (center + margin) / denom)


@dataclass
class Label:
    """채점에 쓰는 최종 라벨."""

    rcept_no: str
    dcm_no: str
    bundle: str
    subject: str
    pass_: str
    verdict: str
    gold_value: Any
    shown_value: Any


@dataclass
class MetricRow:
    """기간 또는 풀링 셀 하나."""

    scope: str
    period: str
    bundle: str
    subject: str
    n_claim: int
    tp: int
    fp: int
    precision: float
    lo: float
    hi: float
    weighted_lo: float
    n_eff: float
    passed: bool
    flag_period_report: bool
    note: str


def _loads(value: Any) -> Any:
    """TEXT JSON을 풀어 준다."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _same(left: Any, right: Any) -> bool:
    """두 정답 값이 같은지."""
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right, ensure_ascii=False, sort_keys=True
    )


def gold_final(conn: sqlite3.Connection) -> Iterator[Label]:
    """불일치가 없으면 최종 라벨을 돌려준다. 불일치는 adjudication이 있을 때만 포함한다."""
    rows = conn.execute("SELECT * FROM gold_labels").fetchall()
    grouped: dict[tuple[str, str, str, str], dict[str, sqlite3.Row]] = {}
    for row in rows:
        key = (row["rcept_no"], row["dcm_no"], row["bundle"], row["subject"])
        grouped.setdefault(key, {})[row["pass"]] = row
    for passes in grouped.values():
        chosen = _choose_pass(passes)
        if chosen is None:
            continue
        yield Label(
            rcept_no=chosen["rcept_no"],
            dcm_no=chosen["dcm_no"],
            bundle=chosen["bundle"],
            subject=chosen["subject"],
            pass_=chosen["pass"],
            verdict=chosen["verdict"],
            gold_value=_loads(chosen["gold_value"]),
            shown_value=_loads(chosen["shown_value"]),
        )


def _choose_pass(passes: dict[str, sqlite3.Row]) -> sqlite3.Row | None:
    """한 subject의 최종 패스. 블라인드·prefill이 다르고 재검토가 없으면 뺀다."""
    if "adjudication" in passes:
        return passes["adjudication"]
    blind = passes.get("blind")
    prefill = passes.get("prefill")
    if blind is not None and prefill is not None:
        if blind["verdict"] != prefill["verdict"] or not _same(
            _loads(blind["gold_value"]), _loads(prefill["gold_value"])
        ):
            return None
        return prefill
    if prefill is not None:
        return prefill
    return blind


def pending_adjudication(conn: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    """블라인드와 prefill이 다른데 재검토 라벨이 없는 키."""
    rows = conn.execute("SELECT * FROM gold_labels").fetchall()
    grouped: dict[tuple[str, str, str, str], dict[str, sqlite3.Row]] = {}
    for row in rows:
        key = (row["rcept_no"], row["dcm_no"], row["bundle"], row["subject"])
        grouped.setdefault(key, {})[row["pass"]] = row
    pending: list[tuple[str, str, str, str]] = []
    for key, passes in grouped.items():
        if "adjudication" in passes or "blind" not in passes or "prefill" not in passes:
            continue
        blind = passes["blind"]
        prefill = passes["prefill"]
        if blind["verdict"] != prefill["verdict"] or not _same(
            _loads(blind["gold_value"]), _loads(prefill["gold_value"])
        ):
            pending.append(key)
    return pending


def _outcome(verdict: str, claim: bool, agreed: bool) -> str:
    """tp/fp/fn/tn/abstain."""
    if verdict == "unsure":
        return "abstain"
    if verdict == "na":
        if claim:
            return "fp"
        return "tn"
    if not claim:
        return "fn"
    if agreed:
        return "tp"
    return "fp"


def score(conn: sqlite3.Connection, version: str) -> int:
    """최종 라벨과 스냅샷으로 gold_scores를 다시 만든다."""
    conn.execute("DELETE FROM gold_scores WHERE extractor_version = ?", (version,))
    scored_at = datetime.now(UTC).isoformat()
    count = 0
    for label in gold_final(conn):
        snapshot = load_snapshot(conn, version, label.rcept_no, label.dcm_no)
        if snapshot is None:
            continue
        predicted = extract_predicted(snapshot, label.bundle, label.subject)
        claim = is_claim(snapshot, label.bundle, label.subject)
        agreed = matches(label.bundle, label.subject, predicted, label.gold_value)
        outcome = _outcome(label.verdict, claim, agreed)
        conn.execute(
            """
            INSERT INTO gold_scores (
                extractor_version, rcept_no, dcm_no, bundle, subject, predicted, outcome, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version,
                label.rcept_no,
                label.dcm_no,
                label.bundle,
                label.subject,
                json.dumps(predicted, ensure_ascii=False),
                outcome,
                scored_at,
            ),
        )
        count += 1
    conn.commit()
    return count


def _sparse_keys(conn: sqlite3.Connection, run_id: str) -> set[tuple[str, str]]:
    """실행에 고정된 희소 필드."""
    row = conn.execute(
        "SELECT params FROM gold_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None or not row[0]:
        return set()
    params = json.loads(row[0])
    found: set[tuple[str, str]] = set()
    for item in params.get("sparse_fields") or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            found.add((str(item[0]), str(item[1])))
    return found


def _weight(meta: dict[str, Any], stratum_weight: float) -> float:
    """과표집은 필드 가중치, 본표본은 층 가중치."""
    field_weight = meta.get("field_weight")
    if isinstance(field_weight, (int, float)) and field_weight > 0:
        return float(field_weight)
    return float(stratum_weight or 0) or 1.0


def _cell(records: list[dict[str, Any]]) -> tuple[int, int, int, float, float]:
    """tp, fp, n, 가중 하한, 유효표본수."""
    tp = sum(1 for item in records if item["outcome"] == "tp")
    fp = sum(1 for item in records if item["outcome"] == "fp")
    claims = [item for item in records if item["outcome"] in {"tp", "fp"}]
    weights = [(item["weight"], item["outcome"] == "tp") for item in claims]
    if not weights:
        return tp, fp, 0, 0.0, 0.0
    claim_w = sum(weight for weight, _tp in weights)
    tp_w = sum(weight for weight, is_tp in weights if is_tp)
    proportion = tp_w / claim_w if claim_w else 0.0
    sum_sq = sum(weight * weight for weight, _tp in weights)
    n_eff = (claim_w * claim_w / sum_sq) if sum_sq else 0.0
    weighted_lo = wilson(proportion * n_eff, n_eff)[0] if n_eff else 0.0
    return tp, fp, len(claims), weighted_lo, n_eff


def _flag(period: str, fp: int, n_claim: int, overall_fp: int, overall_n: int) -> bool:
    """서식 변화 기간이거나 오류가 전체의 두 배를 넘으면 따로 보고한다."""
    if period in FLAGGED_SAMPLE_PERIODS:
        return True
    if n_claim <= 0 or overall_n <= 0:
        return False
    return (fp / n_claim) > 2 * (overall_fp / overall_n)


def metrics(conn: sqlite3.Connection, run_id: str, version: str) -> list[MetricRow]:
    """기간 셀과 희소 필드 풀링 셀을 만든다."""
    sparse = _sparse_keys(conn, run_id)
    rows = conn.execute(
        """
        SELECT s.period, s.role, s.stratum_weight, s.meta,
               g.bundle, g.subject, g.outcome
        FROM gold_scores g
        JOIN gold_samples s
          ON s.rcept_no = g.rcept_no AND s.dcm_no = g.dcm_no AND s.run_id = ?
        WHERE g.extractor_version = ?
        """,
        (run_id, version),
    ).fetchall()
    parsed: list[dict[str, Any]] = []
    for row in rows:
        meta = json.loads(row["meta"] or "{}")
        parsed.append(
            {
                "period": row["period"],
                "role": row["role"],
                "bundle": row["bundle"],
                "subject": row["subject"],
                "outcome": row["outcome"],
                "weight": _weight(meta, row["stratum_weight"]),
                "oversample_for": meta.get("oversample_for"),
            }
        )
    keys = {(item["bundle"], item["subject"]) for item in parsed} | sparse
    periods = sorted({item["period"] for item in parsed if item["role"] == "main"})
    result: list[MetricRow] = []
    for bundle, subject in sorted(keys):
        field = f"{bundle}:{subject}"
        pooled_records: list[dict[str, Any]] = []
        period_rows: list[MetricRow] = []
        for period in periods:
            records = [
                item
                for item in parsed
                if item["bundle"] == bundle
                and item["subject"] == subject
                and item["period"] == period
                and item["role"] == "main"
            ]
            period_rows.append(
                _metric_row("period", period, bundle, subject, records, False)
            )
            pooled_records.extend(records)
        for item in parsed:
            if item["role"] != "oversample":
                continue
            if item["bundle"] != bundle or item["subject"] != subject:
                continue
            if item["oversample_for"] != field:
                continue
            pooled_records.append(item)
        overall_fp = sum(row.fp for row in period_rows)
        overall_n = sum(row.n_claim for row in period_rows)
        is_sparse = (bundle, subject) in sparse
        for row in period_rows:
            flagged = _flag(row.period, row.fp, row.n_claim, overall_fp, overall_n)
            caution = flagged and row.fp >= 1
            if is_sparse:
                note = "pooled; 주의" if caution else "pooled"
                passed = False
            else:
                note = "주의" if caution else ""
                passed = row.lo >= _PASS_LINE
            result.append(
                MetricRow(
                    scope="period",
                    period=row.period,
                    bundle=bundle,
                    subject=subject,
                    n_claim=row.n_claim,
                    tp=row.tp,
                    fp=row.fp,
                    precision=row.precision,
                    lo=row.lo,
                    hi=row.hi,
                    weighted_lo=row.weighted_lo,
                    n_eff=row.n_eff,
                    passed=passed,
                    flag_period_report=flagged,
                    note=note,
                )
            )
        if is_sparse:
            pooled = _metric_row("pooled", "", bundle, subject, pooled_records, True)
            result.append(pooled)
    return result


def _metric_row(
    scope: str,
    period: str,
    bundle: str,
    subject: str,
    records: list[dict[str, Any]],
    use_weighted_pass: bool,
) -> MetricRow:
    """집계 숫자로 지표 행을 만든다."""
    tp, fp, n_claim, weighted_lo, n_eff = _cell(records)
    precision = (tp / n_claim) if n_claim else 0.0
    lo, hi = wilson(tp, n_claim) if n_claim else (0.0, 1.0)
    passed = weighted_lo >= _PASS_LINE if use_weighted_pass else lo >= _PASS_LINE
    return MetricRow(
        scope=scope,
        period=period,
        bundle=bundle,
        subject=subject,
        n_claim=n_claim,
        tp=tp,
        fp=fp,
        precision=precision,
        lo=lo,
        hi=hi,
        weighted_lo=weighted_lo,
        n_eff=n_eff,
        passed=passed,
        flag_period_report=False,
        note="",
    )


def blind_report(conn: sqlite3.Connection, version: str) -> list[dict[str, Any]]:
    """블라인드와 prefill이 둘 다 있는 필드의 일치·앵커링 요약."""
    rows = conn.execute("SELECT * FROM gold_labels").fetchall()
    grouped: dict[tuple[str, str, str, str], dict[str, sqlite3.Row]] = {}
    for row in rows:
        key = (row["rcept_no"], row["dcm_no"], row["bundle"], row["subject"])
        grouped.setdefault(key, {})[row["pass"]] = row
    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for key, passes in grouped.items():
        blind = passes.get("blind")
        prefill = passes.get("prefill")
        if blind is None or prefill is None:
            continue
        bundle, subject = key[2], key[3]
        bucket = buckets.setdefault(
            (bundle, subject),
            {"n": 0, "agree": 0, "anchored": 0},
        )
        bucket["n"] += 1
        if blind["verdict"] == prefill["verdict"] and _same(
            _loads(blind["gold_value"]), _loads(prefill["gold_value"])
        ):
            bucket["agree"] += 1
        snapshot = load_snapshot(conn, version, key[0], key[1])
        if snapshot is None:
            continue
        predicted = extract_predicted(snapshot, bundle, subject)
        blind_value = _loads(blind["gold_value"])
        extractor_wrong = not matches(bundle, subject, predicted, blind_value)
        if extractor_wrong and prefill["verdict"] == "correct":
            bucket["anchored"] += 1
    report: list[dict[str, Any]] = []
    for (bundle, subject), bucket in sorted(buckets.items()):
        report.append(
            {
                "bundle": bundle,
                "subject": subject,
                "n": bucket["n"],
                "agree": bucket["agree"],
                "anchored": bucket["anchored"],
            }
        )
    return report


@dataclass
class ReReview:
    """표가 바뀌어 사람이 다시 봐야 하는 항목."""

    rcept_no: str
    dcm_no: str
    bundle: str
    subject: str
    reason: str


def _canon(value: Any) -> str:
    """표 JSON을 비교용 문자열로 만든다."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _hours_keys(table: Any) -> tuple[Any, Any]:
    """총 감사시간·투입 인원(당기, 합계)."""
    audit = None
    headcount = None
    if not isinstance(table, list):
        return (audit, headcount)
    for cell in table:
        if not isinstance(cell, dict):
            continue
        if cell.get("role") != "total" or cell.get("period") != "current":
            continue
        if cell.get("metric") == "audit":
            audit = cell.get("value")
        if cell.get("metric") == "headcount":
            headcount = cell.get("value")
    return (audit, headcount)


def _answer_keys(gold_value: Any, old_table: Any) -> tuple[Any, Any]:
    """라벨에 핵심값이 있으면 그것을, 없으면 이전 스냅샷을 정답으로 본다."""
    if isinstance(gold_value, dict) and "audit_hours" in gold_value:
        return (gold_value.get("audit_hours"), gold_value.get("headcount"))
    return _hours_keys(old_table)


def _write_score(
    conn: sqlite3.Connection,
    version: str,
    label: Label,
    predicted: Any,
    outcome: str,
) -> None:
    """한 subject의 채점 행을 교체한다."""
    conn.execute(
        """
        DELETE FROM gold_scores
        WHERE extractor_version = ? AND rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
        """,
        (version, label.rcept_no, label.dcm_no, label.bundle, label.subject),
    )
    conn.execute(
        """
        INSERT INTO gold_scores (
            extractor_version, rcept_no, dcm_no, bundle, subject, predicted, outcome, scored_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version,
            label.rcept_no,
            label.dcm_no,
            label.bundle,
            label.subject,
            json.dumps(predicted, ensure_ascii=False),
            outcome,
            datetime.now(UTC).isoformat(),
        ),
    )


def table_carryover(
    conn: sqlite3.Connection, old_version: str, new_version: str
) -> list[ReReview]:
    """표가 같으면 판정을 넘기고, hours 핵심값이 다르면 FP, 나머진 재검수 큐로 보낸다."""
    conn.execute(
        "DELETE FROM gold_rereview WHERE extractor_version = ?", (new_version,)
    )
    queued: list[ReReview] = []
    created_at = datetime.now(UTC).isoformat()
    for label in gold_final(conn):
        if label.bundle not in TABLE_BUNDLES:
            continue
        old_snap = load_snapshot(conn, old_version, label.rcept_no, label.dcm_no)
        new_snap = load_snapshot(conn, new_version, label.rcept_no, label.dcm_no)
        if new_snap is None:
            continue
        old_table = (
            extract_predicted(old_snap, label.bundle, label.subject)
            if old_snap
            else None
        )
        new_table = extract_predicted(new_snap, label.bundle, label.subject)
        if _canon(old_table) == _canon(new_table):
            if label.verdict == "correct":
                outcome = "tp"
            elif label.verdict == "wrong":
                outcome = "fp"
            else:
                outcome = "abstain"
            _write_score(conn, new_version, label, new_table, outcome)
            continue
        if label.bundle == "hours" and _hours_keys(new_table) != _answer_keys(
            label.gold_value, old_table
        ):
            _write_score(conn, new_version, label, new_table, "fp")
            continue
        reason = "hours 핵심값은 같고 표가 달라졌습니다."
        if label.bundle != "hours":
            reason = "이전 버전과 표가 달라 다시 확인이 필요합니다."
        review = ReReview(
            label.rcept_no, label.dcm_no, label.bundle, label.subject, reason
        )
        queued.append(review)
        conn.execute(
            """
            INSERT INTO gold_rereview (
                extractor_version, rcept_no, dcm_no, bundle, subject, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_version,
                review.rcept_no,
                review.dcm_no,
                review.bundle,
                review.subject,
                review.reason,
                created_at,
            ),
        )
        _write_score(conn, new_version, label, new_table, "abstain")
    conn.commit()
    return queued


def rescore(conn: sqlite3.Connection, new_version: str) -> int:
    """스칼라·계정은 자동으로 다시 채점하고, 표는 승계 규칙으로 처리한다."""
    written = score(conn, new_version)
    older = [version for version in versions(conn) if version != new_version]
    if older:
        table_carryover(conn, older[0], new_version)
    return written
