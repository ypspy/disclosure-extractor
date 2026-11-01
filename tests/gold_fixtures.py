"""골드 테스트용 임시 카탈로그. 실제 dart_catalog.db는 열지 않는다."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dart_parser.gold.v19_fields import EXTRACTOR_VERSION

_FACTS_COLUMNS: tuple[str, ...] = (
    "rcept_no",
    "dcm_no",
    "source_report_type",
    "fs_scope",
    "cover_entry_id",
    "opinion_entry_id",
    "activity_entry_id",
    "a001_opinion_entry_id",
    "a001_cover_entry_id",
    "auditor_resolved",
    "auditor_status",
    "auditor_source",
    "opinion_raw",
    "opinion_resolved",
    "opinion_status",
    "opinion_source",
    "audit_report_date",
    "audit_report_date_raw",
    "audit_report_date_candidates",
    "audit_report_date_status",
    "gaap_raw",
    "gaap_resolved",
    "gaap_status",
    "gaap_source",
    "current_period_raw",
    "current_period_resolved",
    "current_period_status",
    "hours",
    "activities",
    "communications",
    "hours_status",
    "activities_status",
    "communications_status",
    "bs_entry_id",
    "is_entry_id",
    "fs_parent_entry_id",
    "accounts",
    "accounts_status",
    "icfr_entry_id",
    "icfr_engagement",
    "icfr_opinion_code",
    "icfr_status",
    "going_concern",
    "going_concern_status",
    "going_concern_raw",
    "going_concern_source",
    "subsidiary_count",
    "subsidiary_status",
    "subsidiary_source",
    "notes_entry_id",
    "a001_affiliate_entry_id",
    "fetch_status",
    "conflicts",
    "extractor_version",
)


def _connect(path: Path) -> sqlite3.Connection:
    """임시 카탈로그 파일을 만들고 연결한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """표본기가 읽는 최소 테이블만 만든다."""
    columns = ", ".join(f"{name} TEXT" for name in _FACTS_COLUMNS)
    conn.executescript(f"""
        CREATE TABLE disclosures (
            rcept_no TEXT PRIMARY KEY,
            corp_code TEXT,
            corp_name TEXT,
            report_nm TEXT,
            report_type TEXT,
            correction_type TEXT,
            rcept_dt TEXT,
            year_end TEXT
        );
        CREATE TABLE corps (
            corp_code TEXT PRIMARY KEY,
            corp_name TEXT,
            corp_cls TEXT
        );
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            section_name TEXT,
            ele_id TEXT,
            dtd TEXT,
            viewer_url TEXT
        );
        CREATE TABLE audit_report_facts (
            {columns},
            PRIMARY KEY (rcept_no, dcm_no)
        );
        CREATE TABLE extraction_reviews (
            rcept_no TEXT,
            dcm_no TEXT,
            bundle TEXT,
            signal TEXT,
            subject TEXT,
            extractor_version TEXT
        );
        """)


def make_catalog(tmp_path: Path) -> Path:
    """읽기 전용 ATTACH 테스트에 쓰는 작은 카탈로그를 만든다."""
    path = Path(tmp_path) / "catalog.db"
    conn = _connect(path)
    _create_tables(conn)
    conn.execute("""
        INSERT INTO disclosures (rcept_no, corp_code, rcept_dt, year_end, report_type)
        VALUES ('20240101000001', 'C0001', '20240315', '2023.12', 'F001')
        """)
    conn.execute(
        "INSERT INTO corps (corp_code, corp_name, corp_cls) VALUES ('C0001', '표본', 'Y')"
    )
    conn.commit()
    conn.close()
    return path


def _year_end_for(year: int, index: int) -> str:
    """접수연도에 맞는 결산월. 일부 정정은 구결산으로 둔다."""
    if year >= 2019 and index % 19 == 0:
        return "2017.12"
    return f"{year - 1}.12"


def _rcept_dt(year: int, index: int) -> str:
    """연도 안에서 기간 경계가 갈리도록 접수일을 만든다."""
    if year == 1999:
        return f"199906{(index % 27) + 1:02d}"
    if year == 2024 and index < 20:
        return f"202402{(index % 10) + 10:02d}"
    if year == 2024:
        return f"202403{(index % 20) + 1:02d}"
    month = (index % 12) + 1
    day = (index % 27) + 1
    return f"{year}{month:02d}{day:02d}"


def _insert_fact(
    conn: sqlite3.Connection,
    *,
    rcept_no: str,
    dcm_no: str,
    report_type: str,
    fs_scope: str,
    rcept_dt: str,
    year_end: str,
    corp_code: str,
    corp_cls: str,
    correction: str,
    fetch_status: str,
    icfr_ok: bool,
    review: bool,
    kam: str | None,
    dtd: str,
) -> None:
    """문서 1건의 공시·엔트리·facts를 넣는다."""
    conn.execute(
        """
        INSERT INTO disclosures (
            rcept_no, corp_code, corp_name, report_nm, report_type,
            correction_type, rcept_dt, year_end
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rcept_no,
            corp_code,
            "표본회사",
            "감사보고서",
            report_type,
            correction,
            rcept_dt,
            year_end,
        ),
    )
    cover_id = f"{rcept_no}:{dcm_no}:cover"
    opinion_id = f"{rcept_no}:{dcm_no}:opinion"
    activity_id = f"{rcept_no}:{dcm_no}:activity"
    bs_id = f"{rcept_no}:{dcm_no}:bs"
    is_id = f"{rcept_no}:{dcm_no}:is"
    viewer = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}&dcmNo={dcm_no}"
    for entry_id, section, ele in (
        (cover_id, "표지", "1"),
        (opinion_id, "감사의견", "2"),
        (activity_id, "외부감사 실시내용", "3"),
        (bs_id, "재무상태표", "4"),
        (is_id, "손익계산서", "5"),
    ):
        conn.execute(
            """
            INSERT INTO entries (
                entry_id, rcept_no, dcm_no, section_name, ele_id, dtd, viewer_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (entry_id, rcept_no, dcm_no, section, ele, dtd, viewer),
        )
    if kam:
        conn.execute(
            """
            INSERT INTO entries (
                entry_id, rcept_no, dcm_no, section_name, ele_id, dtd, viewer_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{rcept_no}:{dcm_no}:kam", rcept_no, dcm_no, kam, "9", dtd, viewer),
        )
    accounts = [
        {
            "account": "inventory",
            "period": "current",
            "raw": "1,234",
            "unit_raw": "천원",
            "unit_scale": 1000,
            "value": 1234000,
        },
        {
            "account": "total_asset",
            "period": "current",
            "raw": "10",
            "unit_raw": "백만원",
            "value": 10000000,
        },
        {
            "account": "total_asset",
            "period": "prior",
            "raw": "9",
            "unit_raw": "백만원",
            "value": 9000000,
        },
    ]
    hours: list[dict[str, object]] = []
    hours_status = "not_found"
    if rcept_dt >= "20150101":
        hours_status = "ok"
        hours = [
            {
                "role": "total",
                "metric": "audit",
                "period": "current",
                "value": 100,
                "raw": "100",
            },
            {
                "role": "total",
                "metric": "headcount",
                "period": "current",
                "value": 5,
                "raw": "5",
            },
        ]
    values = {
        "rcept_no": rcept_no,
        "dcm_no": dcm_no,
        "source_report_type": report_type,
        "fs_scope": fs_scope,
        "cover_entry_id": cover_id,
        "opinion_entry_id": opinion_id,
        "activity_entry_id": activity_id,
        "a001_opinion_entry_id": "",
        "a001_cover_entry_id": "",
        "auditor_resolved": "삼일회계법인",
        "auditor_status": "ok",
        "auditor_source": "cover",
        "opinion_raw": "적정",
        "opinion_resolved": "qualified" if correction == "정정" else "unqualified",
        "opinion_status": "ok",
        "opinion_source": "opinion",
        "audit_report_date": "2024-03-01",
        "audit_report_date_raw": "2024년 3월 1일",
        "audit_report_date_candidates": "[]",
        "audit_report_date_status": "ok",
        "gaap_raw": "K-IFRS",
        "gaap_resolved": "k-ifrs",
        "gaap_status": "ok",
        "gaap_source": "opinion",
        "current_period_raw": year_end,
        "current_period_resolved": f"({year_end})",
        "current_period_status": "ok",
        "hours": json.dumps(hours, ensure_ascii=False),
        "activities": "[]",
        "communications": "{}",
        "hours_status": hours_status,
        "activities_status": hours_status,
        "communications_status": hours_status,
        "bs_entry_id": bs_id,
        "is_entry_id": is_id,
        "fs_parent_entry_id": "",
        "accounts": json.dumps(accounts, ensure_ascii=False),
        "accounts_status": "ok",
        "icfr_entry_id": "",
        "icfr_engagement": "engaged" if icfr_ok else "",
        "icfr_opinion_code": "unqualified" if icfr_ok else "",
        "icfr_status": "ok" if icfr_ok else "not_found",
        "going_concern": "0",
        "going_concern_status": "ok",
        "going_concern_raw": "",
        "going_concern_source": "opinion",
        "subsidiary_count": "3" if fs_scope == "consolidated" else "",
        "subsidiary_status": "ok" if fs_scope == "consolidated" else "not_applicable",
        "subsidiary_source": "notes",
        "notes_entry_id": "",
        "a001_affiliate_entry_id": "",
        "fetch_status": fetch_status,
        "conflicts": "[]",
        "extractor_version": EXTRACTOR_VERSION,
    }
    columns = ", ".join(_FACTS_COLUMNS)
    placeholders = ", ".join("?" for _ in _FACTS_COLUMNS)
    conn.execute(
        f"INSERT INTO audit_report_facts ({columns}) VALUES ({placeholders})",
        tuple(values[name] for name in _FACTS_COLUMNS),
    )
    if review:
        conn.execute(
            """
            INSERT INTO extraction_reviews (
                rcept_no, dcm_no, bundle, signal, subject, extractor_version
            ) VALUES (?, ?, 'hours', 'hours_nonpositive', 'audit_current_total', ?)
            """,
            (rcept_no, dcm_no, EXTRACTOR_VERSION),
        )


def make_population(tmp_path: Path, n_per_year: int = 60) -> Path:
    """기간별 합성 모집단. 같은 경로에 이미 있으면 다시 만들지 않는다."""
    path = Path(tmp_path) / "population.db"
    if path.exists():
        return path
    conn = _connect(path)
    _create_tables(conn)
    for slot in range(10):
        conn.execute(
            "INSERT INTO corps (corp_code, corp_name, corp_cls) VALUES (?, ?, ?)",
            (f"C{slot:04d}", f"회사{slot}", ("Y", "K", "E")[slot % 3]),
        )
    report_cycle = ("F001", "F002", "A001")
    for year in (1999, *range(2000, 2026)):
        for index in range(n_per_year):
            report_type = report_cycle[index % 3]
            if report_type == "F002":
                scope = "consolidated"
            elif report_type == "A001" and index % 2 == 0:
                scope = "consolidated"
            else:
                scope = "separate"
            rcept_dt = _rcept_dt(year, index)
            rcept_no = f"{rcept_dt}{index:06d}"
            dcm_no = f"{year}{index:04d}"
            correction = "정정" if index % 19 == 0 else ""
            if rcept_dt >= "20240229":
                dtd = "dart4.xsd"
            elif year >= 2009:
                dtd = "dart3.xsd"
            else:
                dtd = "dart2.dtd"
            kam = None
            if year >= 2016 and index % 5 == 0:
                kam = "핵심감사사항"
            elif year >= 2016 and index % 5 == 1:
                kam = "수주산업 핵심감사사항"
            _insert_fact(
                conn,
                rcept_no=rcept_no,
                dcm_no=dcm_no,
                report_type=report_type,
                fs_scope=scope,
                rcept_dt=rcept_dt,
                year_end=_year_end_for(year, index),
                corp_code=f"C{index % 10:04d}",
                corp_cls=("Y", "K", "E")[index % 3],
                correction=correction,
                fetch_status="fail" if index % 23 == 0 else "ok",
                icfr_ok=index % 10 == 0,
                review=index % 2 == 0,
                kam=kam,
                dtd=dtd,
            )
    _insert_fact(
        conn,
        rcept_no="20200315000099",
        dcm_no="20209999",
        report_type="F003",
        fs_scope="separate",
        rcept_dt="20200315",
        year_end="2019.12",
        corp_code="C0000",
        corp_cls="Y",
        correction="",
        fetch_status="ok",
        icfr_ok=True,
        review=False,
        kam=None,
        dtd="dart3.xsd",
    )
    conn.commit()
    conn.close()
    return path


def run_sample(
    tmp_path: Path, seed: str, per_period: int = 40
) -> tuple[sqlite3.Connection, str]:
    """합성 모집단으로 표본을 만들고 연결과 run_id를 돌려준다."""
    from dart_parser.gold.db import migrate, open_gold
    from dart_parser.gold.sampler import SampleParams, build_sample

    catalog = make_population(tmp_path)
    conn = open_gold(Path(tmp_path) / f"{seed}.db", catalog)
    migrate(conn)
    run_id = build_sample(conn, SampleParams(seed=seed, per_period=per_period))
    return conn, run_id


def first_main(conn: sqlite3.Connection) -> dict[str, str]:
    """같은 층에 예비분이 있는 첫 본표본을 고른다."""
    row = conn.execute("""
        SELECT s.rcept_no, s.dcm_no
        FROM gold_samples s
        WHERE s.role = 'main'
          AND EXISTS (
            SELECT 1 FROM gold_samples r
            WHERE r.run_id = s.run_id
              AND r.stratum = s.stratum
              AND r.role = 'reserve'
          )
        ORDER BY s.queue_order, s.rcept_no
        LIMIT 1
        """).fetchone()
    if row is None:
        raise AssertionError("예비분이 있는 본표본이 없습니다.")
    return {"rcept_no": row[0], "dcm_no": row[1]}


def first_rcept(conn: sqlite3.Connection) -> str:
    """표본의 첫 접수번호를 돌려준다."""
    row = conn.execute(
        "SELECT rcept_no FROM gold_samples ORDER BY rcept_no LIMIT 1"
    ).fetchone()
    if row is None:
        raise AssertionError("표본이 비어 있습니다.")
    return str(row[0])
