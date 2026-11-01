"""층화 표본. 같은 시드와 같은 카탈로그 스냅샷이면 같은 표본이 나온다."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dart_parser.gold.db import catalog_file
from dart_parser.gold.periods import assign_period, layout_era, period_dtd_mismatch
from dart_parser.gold.subjects import (
    BUNDLE_KEYS,
    extract_predicted,
    extraction_status,
    subjects_for,
)
from dart_parser.gold.v19_fields import status_attr

POPULATION_SQL = """
SELECT
    d.rcept_no AS rcept_no,
    e.dcm_no AS dcm_no,
    MAX(d.report_type) AS source_report_type,
    CASE
        WHEN MAX(d.report_type) = 'F002'
          OR IFNULL(MAX(d.report_nm), '') LIKE '%연결%'
        THEN 'consolidated'
        ELSE 'separate'
    END AS fs_scope,
    '' AS opinion_resolved,
    MAX(d.rcept_dt) AS rcept_dt,
    MAX(d.year_end) AS year_end,
    MAX(d.correction_type) AS correction_type,
    MAX(d.corp_code) AS corp_code,
    MAX(d.report_nm) AS report_nm,
    MAX(c.corp_cls) AS corp_cls,
    MAX(e.dtd) AS dtd,
    MAX(CASE
        WHEN e.section_name LIKE '%핵심감사사항%'
         AND e.section_name NOT LIKE '%수주산업%'
        THEN 1 ELSE 0 END) AS kam,
    '' AS review_signals
FROM cat.disclosures d
JOIN cat.entries e ON e.rcept_no = d.rcept_no
LEFT JOIN cat.corps c ON c.corp_code = d.corp_code
WHERE d.report_type IN ('F001', 'F002', 'A001')
  AND IFNULL(d.report_nm, '') NOT LIKE '%감사의감사보고서%'
  AND IFNULL(e.dcm_no, '') != ''
GROUP BY d.rcept_no, e.dcm_no
"""

_WINDOWS = (
    (20150101, 20150430),
    (20190101, 20190331),
    (20240226, 20240308),
    (20090101, 20090228),
)

# 설계 기본은 기간당 400건. 더 작은 실행은 최소할당을 같은 비율로 줄인다.
_DESIGN_PERIOD = 400
_HOLDOUT_RATIO = 0.20


@dataclass
class SampleParams:
    """표본 추출 파라미터."""

    seed: str = "gold-2026-10"
    per_period: int = 400
    blind_ratio: float = 0.10
    reserve_ratio: float = 0.10
    min_alloc: int = 15
    p4b_min: int = 80
    holdout_ratio: float = _HOLDOUT_RATIO


@dataclass
class PopRow:
    """모집단 한 문서."""

    rcept_no: str
    dcm_no: str
    period: str
    sub_period: str | None
    stratum: str
    scope: str
    form: str
    market: str
    kam: int
    opinion_nonclean: int
    correction: int
    transition: int
    rcept_dt: str
    year_end: str
    corp_code: str
    dtd: str
    review_signals: str
    layout: str | None
    dtd_mismatch: bool


@dataclass
class _Chosen:
    """기간 안에 뽑힌 문서."""

    row: PopRow
    role: str
    mode: str
    weight: float
    queue_order: int = 0
    holdout: int = 0
    sample_hash: str = ""


def rank_hash(seed: str, *parts: str) -> int:
    """시드와 키로 안정적인 순위를 만든다."""
    digest = hashlib.sha256("|".join((seed, *parts)).encode()).hexdigest()
    return int(digest[:16], 16)


def _sample_hash(seed: str, rcept_no: str, dcm_no: str) -> str:
    """표본 행에 저장하는 16자리 해시."""
    return hashlib.sha256(f"{seed}|{rcept_no}|{dcm_no}".encode()).hexdigest()[:16]


def allocate(counts: dict[str, int], n: int, min_alloc: int) -> dict[str, int]:
    """최소할당 뒤 최대잔여법으로 n건을 나눈다. 모집단보다 많이 주지 않는다."""
    keys = sorted(counts)
    populations = {key: max(0, int(counts[key])) for key in keys}
    total = sum(populations.values())
    if n <= 0 or total <= 0:
        return {key: 0 for key in keys}
    target = min(int(n), total)
    alloc = {key: min(max(int(min_alloc), 0), populations[key]) for key in keys}
    while sum(alloc.values()) > target:
        reducible = [key for key in keys if alloc[key] > 0]
        key = max(reducible, key=lambda item: (populations[item], alloc[item], item))
        alloc[key] -= 1
    remaining = target - sum(alloc.values())
    capacity = {key: populations[key] - alloc[key] for key in keys}
    cap_total = sum(capacity.values())
    if remaining <= 0 or cap_total <= 0:
        return alloc
    raw = {key: remaining * capacity[key] / cap_total for key in keys}
    floors = {key: int(math.floor(raw[key])) for key in keys}
    for key in keys:
        alloc[key] += floors[key]
    left = remaining - sum(floors.values())
    order = sorted(
        keys,
        key=lambda key: (raw[key] - floors[key], capacity[key], key),
        reverse=True,
    )
    for key in order:
        if left <= 0:
            break
        if populations[key] - alloc[key] <= 0:
            continue
        alloc[key] += 1
        left -= 1
    return alloc


def _scaled(value: int, per_period: int) -> int:
    """400건 설계의 최소할당을 이번 기간 크기에 맞춘다."""
    if per_period >= _DESIGN_PERIOD:
        return value
    return max(1, int(round(value * per_period / _DESIGN_PERIOD)))


def _day_number(rcept_dt: str) -> int:
    digits = "".join(ch for ch in (rcept_dt or "") if ch.isdigit())
    return int(digits[:8]) if len(digits) >= 8 else 0


def _in_transition(rcept_dt: str) -> bool:
    day = _day_number(rcept_dt)
    return any(start <= day <= end for start, end in _WINDOWS)


def _market(corp_cls: str | None) -> str:
    if corp_cls in {"Y", "K"}:
        return corp_cls
    return "O"


def stratum_key(row: PopRow) -> str:
    """층 키. P6·P7만 KAM·의견·정정을 붙인다."""
    parts = [
        row.period,
        row.sub_period or "-",
        row.scope,
        row.form,
        row.market,
    ]
    if row.period in {"P6", "P7"}:
        parts.extend(
            [
                f"kam{row.kam}",
                f"op{row.opinion_nonclean}",
                f"corr{row.correction}",
            ]
        )
    if row.transition:
        parts.append("tr=1")
    return "|".join(parts)


def _pop_from_sql(record: sqlite3.Row) -> PopRow | None:
    """모집단 쿼리 한 줄을 기간이 있는 PopRow로 만든다. OUT은 None."""
    correction = 1 if (record["correction_type"] or "").strip() else 0
    period, sub = assign_period(
        record["rcept_dt"] or "",
        record["year_end"],
        record["dtd"],
        is_correction=bool(correction),
    )
    if period == "OUT":
        return None
    report_type = record["source_report_type"] or ""
    scope = "consolidated" if record["fs_scope"] == "consolidated" else "separate"
    form = "attached" if report_type == "A001" else "standalone"
    opinion = (record["opinion_resolved"] or "").strip()
    nonclean = 0 if opinion in {"", "unqualified"} else 1
    row = PopRow(
        rcept_no=record["rcept_no"],
        dcm_no=record["dcm_no"],
        period=period,
        sub_period=sub,
        stratum="",
        scope=scope,
        form=form,
        market=_market(record["corp_cls"]),
        kam=int(record["kam"] or 0),
        opinion_nonclean=nonclean,
        correction=correction,
        transition=1 if _in_transition(record["rcept_dt"] or "") else 0,
        rcept_dt=record["rcept_dt"] or "",
        year_end=record["year_end"] or "",
        corp_code=record["corp_code"] or "",
        dtd=record["dtd"] or "",
        review_signals=record["review_signals"] or "",
        layout=layout_era(record["year_end"]),
        dtd_mismatch=period_dtd_mismatch(period, record["dtd"]),
    )
    row.stratum = stratum_key(row)
    return row


def load_population(conn: sqlite3.Connection) -> list[PopRow]:
    """읽기 전용 카탈로그에서 골드 모집단을 읽는다."""
    rows: list[PopRow] = []
    for record in conn.execute(POPULATION_SQL):
        parsed = _pop_from_sql(record)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _boost(
    alloc: dict[str, int], counts: dict[str, int], keys: set[str], floor: int
) -> None:
    """특정 층 묶음이 floor 미만이면 다른 층에서 자리를 옮긴다."""
    current = sum(alloc.get(key, 0) for key in keys)
    need = floor - current
    while need > 0:
        donors = [key for key in alloc if key not in keys and alloc[key] > 0]
        receivers = [key for key in keys if alloc.get(key, 0) < counts.get(key, 0)]
        if not donors or not receivers:
            return
        donor = max(donors, key=lambda key: (alloc[key], key))
        receiver = max(receivers, key=lambda key: (counts[key] - alloc[key], key))
        alloc[donor] -= 1
        alloc[receiver] += 1
        need -= 1


def _mark_fraction(rows: list[_Chosen], seed: str, label: str, ratio: float) -> None:
    """층 비례로 ratio만큼 골라 표시 함수를 호출할 대상을 고른다."""
    if not rows or ratio <= 0:
        return
    target = int(round(len(rows) * ratio))
    if target <= 0:
        return
    grouped: dict[str, list[_Chosen]] = {}
    for item in rows:
        grouped.setdefault(item.row.stratum, []).append(item)
    quotas = allocate({key: len(group) for key, group in grouped.items()}, target, 0)
    chosen: set[tuple[str, str]] = set()
    for key, group in grouped.items():
        ordered = sorted(
            group,
            key=lambda item: rank_hash(seed, label, item.row.rcept_no, item.row.dcm_no),
        )
        for item in ordered[: quotas.get(key, 0)]:
            chosen.add((item.row.rcept_no, item.row.dcm_no))
    if label == "blind":
        for item in rows:
            if (item.row.rcept_no, item.row.dcm_no) in chosen:
                item.mode = "blind"
    if label == "holdout":
        for item in rows:
            if (item.row.rcept_no, item.row.dcm_no) in chosen:
                item.holdout = 1


def _interleave(rows: list[_Chosen]) -> None:
    """블라인드가 연속되지 않도록 10번째마다 끼운다."""
    ordered = sorted(
        rows,
        key=lambda item: (
            rank_hash("queue", item.row.rcept_no, item.row.dcm_no),
            item.row.rcept_no,
        ),
    )
    plain = [item for item in ordered if item.mode != "blind"]
    blind = [item for item in ordered if item.mode == "blind"]
    merged: list[_Chosen] = []
    plain_index = 0
    blind_index = 0
    step = 0
    while plain_index < len(plain) or blind_index < len(blind):
        step += 1
        if step % 10 == 0 and blind_index < len(blind):
            merged.append(blind[blind_index])
            blind_index += 1
            continue
        if plain_index < len(plain):
            merged.append(plain[plain_index])
            plain_index += 1
            continue
        merged.append(blind[blind_index])
        blind_index += 1
    for index, item in enumerate(merged, start=1):
        item.queue_order = index


def _choose_period(rows: list[PopRow], params: SampleParams) -> list[_Chosen]:
    """한 기간에서 본표본·예비·블라인드·홀드아웃을 고른다."""
    grouped: dict[str, list[PopRow]] = {}
    for row in rows:
        grouped.setdefault(row.stratum, []).append(row)
    counts = {key: len(group) for key, group in grouped.items()}
    minimum = _scaled(params.min_alloc, params.per_period)
    alloc = allocate(counts, min(params.per_period, sum(counts.values())), minimum)
    if rows and rows[0].period == "P4":
        p4b = {key for key in alloc if key.split("|")[1] == "P4b"}
        floor = min(_scaled(params.p4b_min, params.per_period), params.per_period)
        _boost(alloc, counts, p4b, floor)
    chosen: list[_Chosen] = []
    reserves: list[_Chosen] = []
    for key, group in grouped.items():
        quota = alloc.get(key, 0)
        if quota <= 0:
            continue
        ordered = sorted(
            group,
            key=lambda row: (
                rank_hash(params.seed, row.rcept_no, row.dcm_no),
                row.rcept_no,
            ),
        )
        main_rows = ordered[:quota]
        reserve_n = min(
            len(ordered) - len(main_rows),
            int(math.ceil(len(main_rows) * params.reserve_ratio)),
        )
        weight = (len(group) / len(main_rows)) if main_rows else 0.0
        for row in main_rows:
            chosen.append(
                _Chosen(
                    row=row,
                    role="main",
                    mode="prefill",
                    weight=weight,
                    sample_hash=_sample_hash(params.seed, row.rcept_no, row.dcm_no),
                )
            )
        for row in ordered[quota : quota + reserve_n]:
            reserves.append(
                _Chosen(
                    row=row,
                    role="reserve",
                    mode="prefill",
                    weight=weight,
                    sample_hash=_sample_hash(params.seed, row.rcept_no, row.dcm_no),
                )
            )
    _mark_fraction(chosen, params.seed, "blind", params.blind_ratio)
    _mark_fraction(chosen, params.seed, "holdout", params.holdout_ratio)
    _interleave(chosen)
    base = len(chosen) + 1
    for offset, item in enumerate(
        sorted(reserves, key=lambda item: (item.row.stratum, item.sample_hash))
    ):
        item.queue_order = base + offset
    return chosen + reserves


def _catalog_as_of(conn: sqlite3.Connection) -> str:
    """카탈로그 파일 수정 시각을 UTC ISO 문자열로 돌려준다."""
    path = catalog_file(conn)
    if path is None or not path.exists():
        return ""
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return stamp.isoformat()


def _meta(item: _Chosen, catalog_as_of: str) -> dict[str, Any]:
    """표본 메타. 시장은 현재 태그를 쓰고, 구서식 정정은 별도 층으로 나누지 않는다."""
    row = item.row
    signals = [part for part in row.review_signals.split(",") if part]
    return {
        "dtd": row.dtd,
        "fye": row.year_end,
        "layout_era": row.layout,
        "kam": row.kam,
        "market_at_filing": row.market,
        "market_source": "current_tag",
        "in_extraction_reviews": 1 if signals else 0,
        "review_signals": signals,
        "correction_group": f"{row.corp_code}|{row.year_end}",
        "period_dtd_mismatch": row.dtd_mismatch,
        "is_correction": row.correction,
        "catalog_as_of": catalog_as_of,
        "holdout": item.holdout,
        "scope": row.scope,
        "form": row.form,
    }


def build_sample(conn: sqlite3.Connection, params: SampleParams | None = None) -> str:
    """모집단을 읽어 gold_runs·gold_samples를 다시 쓰고 run_id를 돌려준다."""
    settings = params or SampleParams()
    population = load_population(conn)
    by_period: dict[str, list[PopRow]] = {}
    for row in population:
        by_period.setdefault(row.period, []).append(row)
    as_of = _catalog_as_of(conn)
    picked: list[_Chosen] = []
    stats: dict[str, Any] = {"by_period": {}, "by_stratum": {}}
    for period in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
        rows = by_period.get(period, [])
        chosen = _choose_period(rows, settings)
        picked.extend(chosen)
        mains = [item for item in chosen if item.role == "main"]
        stats["by_period"][period] = {
            "N": len(rows),
            "n": len(mains),
            "blind": sum(1 for item in mains if item.mode == "blind"),
            "reserve": sum(1 for item in chosen if item.role == "reserve"),
            "holdout": sum(1 for item in mains if item.holdout),
        }
    stratum_pop: dict[str, int] = {}
    for row in population:
        stratum_pop[row.stratum] = stratum_pop.get(row.stratum, 0) + 1
    stratum_n: dict[str, int] = {}
    for item in picked:
        if item.role == "main":
            stratum_n[item.row.stratum] = stratum_n.get(item.row.stratum, 0) + 1
    for key, size in sorted(stratum_pop.items()):
        stats["by_stratum"][key] = {"N": size, "n": stratum_n.get(key, 0)}
    snapshot = {
        "catalog_as_of": as_of,
        "size": catalog_file(conn).stat().st_size if catalog_file(conn) else None,
    }
    run_params = {
        "seed": settings.seed,
        "per_period": settings.per_period,
        "blind_ratio": settings.blind_ratio,
        "reserve_ratio": settings.reserve_ratio,
        "min_alloc": settings.min_alloc,
        "p4b_min": settings.p4b_min,
        "holdout_ratio": settings.holdout_ratio,
        "sparse_fields": [],
        "strata": "period|sub|scope|form|market|kam|opinion|correction|tr",
    }
    run_id = settings.seed
    conn.execute("DELETE FROM gold_samples WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM gold_runs WHERE run_id = ?", (run_id,))
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            settings.seed,
            datetime.now(UTC).isoformat(),
            hashlib.sha256(POPULATION_SQL.encode()).hexdigest(),
            json.dumps(snapshot, ensure_ascii=False),
            json.dumps(run_params, ensure_ascii=False),
            json.dumps(stats, ensure_ascii=False),
        ),
    )
    for item in picked:
        conn.execute(
            """
            INSERT INTO gold_samples (
                run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
                sample_hash, mode, role, queue_order, status, exclude_reason, meta,
                started_at, finished_at, active_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'todo', NULL, ?, NULL, NULL, NULL)
            """,
            (
                run_id,
                item.row.rcept_no,
                item.row.dcm_no,
                item.row.period,
                item.row.sub_period,
                item.row.stratum,
                item.weight,
                item.sample_hash,
                item.mode,
                item.role,
                item.queue_order,
                json.dumps(_meta(item, as_of), ensure_ascii=False),
            ),
        )
    conn.commit()
    return run_id


_SECTION_NEEDLES: dict[str, tuple[str, ...]] = {
    "company_name": ("표지",),
    "document_title": ("표지",),
    "fiscal_term": ("표지",),
    "auditor": ("감사의견", "독립된"),
    "opinion": ("감사의견", "독립된"),
    "gaap": ("감사의견", "독립된"),
    "audit_report_date": ("감사의견", "독립된"),
    "current_period": ("표지",),
    "hours": ("외부감사 실시내용", "감사투입"),
    "activities": ("외부감사 실시내용", "주요감사실시"),
    "communications": ("외부감사 실시내용", "커뮤니케이션"),
    "accounts": ("재무상태표", "대차대조표", "손익계산서"),
    "icfr": ("내부회계관리제도",),
    "going_concern": ("계속기업", "강조사항", "감사의견"),
    "subsidiary": ("종속기업",),
    "notes_toc": ("주석",),
}


def _needles(bundle: str, subject: str) -> tuple[str, ...]:
    """필드가 문서에 있다는 섹션 제목."""
    if bundle == "accounts":
        account = subject.split("@", 1)[0]
        if account in {"revenue", "operating_income", "net_income"}:
            return ("손익계산서",)
        return ("재무상태표", "대차대조표")
    return _SECTION_NEEDLES.get(bundle, ())


def _section_hit(fact: dict[str, Any], bundle: str, subject: str) -> bool:
    """엔트리 제목에 그 필드 섹션이 있는지."""
    names = fact.get("_sections")
    if not isinstance(names, list):
        return False
    blob = " ".join(str(name) for name in names)
    if not any(needle in blob for needle in _needles(bundle, subject)):
        return False
    if bundle == "subsidiary":
        report_type = str(fact.get("report_type") or "")
        report_nm = str(fact.get("report_nm") or "")
        return report_type == "F002" or "연결" in report_nm
    return True


def is_claim(fact: dict[str, Any], bundle: str, subject: str) -> bool:
    """예측값이 있고, 표준 스냅샷이면 status가 found일 때 주장으로 본다."""
    if isinstance(fact.get("_sections"), list):
        return _section_hit(fact, bundle, subject)
    if extract_predicted(fact, bundle, subject) is None:
        return False
    status = extraction_status(fact, bundle)
    if status is not None:
        return status == "found"
    if bundle == "icfr":
        return fact.get("icfr_status") == "ok"
    try:
        column = status_attr(bundle)
    except KeyError:
        return True
    if column in fact:
        return fact.get(column) == "ok"
    return True


def _section_predicate(bundle: str, subject: str) -> str:
    """문서 위치(엔트리 제목)로 필드가 있는 문서를 고른다."""
    needles = _needles(bundle, subject)
    parts = [f"e.section_name LIKE '%{needle}%'" for needle in needles]
    clause = "(" + " OR ".join(parts) + ")" if parts else "1 = 0"
    if bundle == "subsidiary":
        clause += " AND (d.report_type = 'F002' OR IFNULL(d.report_nm, '') LIKE '%연결%')"
    return clause


def _load_sample_facts(
    conn: sqlite3.Connection, run_id: str
) -> list[tuple[sqlite3.Row, dict[str, Any]]]:
    """이번 실행의 표본과 카탈로그 섹션 제목을 짝짓는다."""
    samples = conn.execute(
        """
        SELECT period, role, rcept_no, dcm_no
        FROM gold_samples
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    paired: list[tuple[sqlite3.Row, dict[str, Any]]] = []
    for sample in samples:
        rows = conn.execute(
            """
            SELECT e.section_name AS section_name,
                   d.report_type AS report_type,
                   d.report_nm AS report_nm
            FROM cat.entries e
            JOIN cat.disclosures d ON d.rcept_no = e.rcept_no
            WHERE e.rcept_no = ? AND IFNULL(e.dcm_no, '') = IFNULL(?, '')
            """,
            (sample["rcept_no"], sample["dcm_no"]),
        ).fetchall()
        paired.append(
            (
                sample,
                {
                    "_sections": [row["section_name"] or "" for row in rows],
                    "report_type": rows[0]["report_type"] if rows else "",
                    "report_nm": rows[0]["report_nm"] if rows else "",
                },
            )
        )
    return paired


def find_sparse_fields(
    conn: sqlite3.Connection,
    run_id: str,
    threshold: int = 383,
) -> list[tuple[str, str]]:
    """풀링 또는 기간 claim이 threshold 미만인 (묶음, subject)를 찾는다."""
    paired = [
        item
        for item in _load_sample_facts(conn, run_id)
        if item[0]["role"] in {"main", "oversample"}
    ]
    periods = {sample["period"] for sample, _fact in paired if sample["role"] == "main"}
    sparse: list[tuple[str, str]] = []
    for bundle in BUNDLE_KEYS:
        for subject in subjects_for(bundle):
            by_period: dict[str, int] = {period: 0 for period in periods}
            for sample, fact in paired:
                if not is_claim(fact, bundle, subject):
                    continue
                period = sample["period"]
                by_period[period] = by_period.get(period, 0) + 1
            pooled = sum(by_period.values())
            period_short = (
                any(count < threshold for count in by_period.values())
                if by_period
                else True
            )
            if pooled < threshold or period_short:
                sparse.append((bundle, subject))
    return sparse


def _remember_sparse(
    conn: sqlite3.Connection, run_id: str, bundle: str, subject: str
) -> None:
    """실행 파라미터에 희소 필드를 고정한다."""
    row = conn.execute(
        "SELECT params FROM gold_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return
    params = json.loads(row[0])
    fields = params.setdefault("sparse_fields", [])
    token = [bundle, subject]
    if token not in fields:
        fields.append(token)
    conn.execute(
        "UPDATE gold_runs SET params = ? WHERE run_id = ?",
        (json.dumps(params, ensure_ascii=False), run_id),
    )


def oversample(
    conn: sqlite3.Connection,
    run_id: str,
    field: tuple[str, str],
    target: int = 383,
) -> int:
    """희소 필드 claim이 target이 될 때까지 해당 필드가 있는 문서를 더 뽑는다."""
    bundle, subject = field
    _remember_sparse(conn, run_id, bundle, subject)
    paired = [
        item
        for item in _load_sample_facts(conn, run_id)
        if item[0]["role"] in {"main", "oversample"}
        and is_claim(item[1], bundle, subject)
    ]
    need = target - len(paired)
    if need <= 0:
        conn.commit()
        return 0
    run = conn.execute(
        "SELECT seed FROM gold_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    seed = run["seed"] if run else "gold-2026-10"
    section_sql = _section_predicate(bundle, subject)
    candidates = conn.execute(
        f"""
        SELECT
            d.rcept_no AS rcept_no,
            e.dcm_no AS dcm_no,
            MAX(d.report_type) AS source_report_type,
            CASE
                WHEN MAX(d.report_type) = 'F002'
                  OR IFNULL(MAX(d.report_nm), '') LIKE '%연결%'
                THEN 'consolidated'
                ELSE 'separate'
            END AS fs_scope,
            MAX(d.rcept_dt) AS rcept_dt,
            MAX(d.year_end) AS year_end,
            MAX(d.correction_type) AS correction_type,
            MAX(d.corp_code) AS corp_code,
            MAX(c.corp_cls) AS corp_cls,
            MAX(e.dtd) AS dtd
        FROM cat.disclosures d
        JOIN cat.entries e ON e.rcept_no = d.rcept_no
        LEFT JOIN cat.corps c ON c.corp_code = d.corp_code
        WHERE d.report_type IN ('F001', 'F002', 'A001')
          AND IFNULL(d.report_nm, '') NOT LIKE '%감사의감사보고서%'
          AND IFNULL(e.dcm_no, '') != ''
          AND {section_sql}
          AND NOT EXISTS (
              SELECT 1 FROM gold_samples s
              WHERE s.run_id = ? AND s.rcept_no = d.rcept_no AND s.dcm_no = e.dcm_no
          )
        GROUP BY d.rcept_no, e.dcm_no
        """,
        (run_id,),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for record in candidates:
        period, _sub = assign_period(
            record["rcept_dt"] or "",
            record["year_end"],
            record["dtd"],
            is_correction=bool((record["correction_type"] or "").strip()),
        )
        if period == "OUT":
            continue
        grouped.setdefault(period, []).append(record)
    quotas = allocate({key: len(rows) for key, rows in grouped.items()}, need, 0)
    as_of_row = conn.execute(
        """
        SELECT json_extract(meta, '$.catalog_as_of')
        FROM gold_samples WHERE run_id = ? AND json_extract(meta, '$.catalog_as_of') IS NOT NULL
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    as_of = as_of_row[0] if as_of_row else _catalog_as_of(conn)
    next_order = conn.execute(
        "SELECT COALESCE(MAX(queue_order), 0) FROM gold_samples WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    added = 0
    for period, rows in grouped.items():
        quota = quotas.get(period, 0)
        if quota <= 0:
            continue
        ordered = sorted(
            rows,
            key=lambda record: rank_hash(
                seed,
                "oversample",
                bundle,
                subject,
                record["rcept_no"],
                record["dcm_no"],
            ),
        )
        picked = ordered[:quota]
        weight = (len(rows) / len(picked)) if picked else 0.0
        for record in picked:
            next_order += 1
            meta = {
                "oversample_for": f"{bundle}:{subject}",
                "field_weight": weight,
                "catalog_as_of": as_of,
                "dtd": record["dtd"] or "",
                "fye": record["year_end"] or "",
                "layout_era": layout_era(record["year_end"]),
                "in_extraction_reviews": 0,
                "review_signals": [],
                "market_source": "current_tag",
                "holdout": 0,
            }
            conn.execute(
                """
                INSERT INTO gold_samples (
                    run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
                    sample_hash, mode, role, queue_order, status, exclude_reason, meta,
                    started_at, finished_at, active_seconds
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, 'prefill', 'oversample', ?, 'todo', NULL, ?,
                          NULL, NULL, NULL)
                """,
                (
                    run_id,
                    record["rcept_no"],
                    record["dcm_no"],
                    period,
                    f"oversample|{bundle}:{subject}|{period}",
                    weight,
                    _sample_hash(seed, record["rcept_no"], record["dcm_no"]),
                    next_order,
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            added += 1
    conn.commit()
    return added


def render_stats(conn: sqlite3.Connection, run_id: str) -> str:
    """층별 모집단·표본 수를 텍스트로 만든다."""
    row = conn.execute(
        "SELECT stats FROM gold_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return ""
    stats = json.loads(row[0])
    lines = ["period  N  n  blind  reserve  holdout"]
    for period, item in stats.get("by_period", {}).items():
        lines.append(
            f"{period}  {item['N']}  {item['n']}  {item['blind']}  "
            f"{item['reserve']}  {item['holdout']}"
        )
    return "\n".join(lines)
