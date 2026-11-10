# Gold Audit-Leaf Population Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 골드 모집단과 희소 필드 추가 추출이 감사보고서 문서 리프만 고르게 한다.

**Architecture:** 문서명 판정은 `audit_document.py` 한 곳에 둔다. 파이썬 함수 `classify_audit_document`와 SQLite 조건이 같은 통과 규칙을 쓴다. `sampler.py`의 모집단 쿼리와 `oversample()`은 그 조건으로 문서번호를 남기고, 별도·연결은 접수 제목이 아니라 그 판정으로 정한다.

**Tech Stack:** Python 3.11+, SQLite, pytest, ruff. 문자 정리는 `normalize_text`.

## Global Constraints

- 명세: `docs/superpowers/specs/2026-11-10-gold-audit-leaf-population-design.md`
- 행 키는 `(rcept_no, dcm_no)`다.
- 접수 조건은 `report_type IN ('F001','F002','A001')`, `report_nm`에 `감사의감사보고서`가 있으면 제외, 빈 `dcm_no` 제외.
- 문서명 절차: `normalize_text` → ASCII 공백 삭제 → `[기재정정]`, `[첨부정정]`, `[정정]` 순서로 삭제 → `감사의감사`면 탈락 → `감사보고서`가 있을 때만 통과 → `연결`이 있으면 `consolidated`, 없으면 `separate`.
- SQL은 `normalize_text`를 호출하지 않는다. 공백·NBSP·전각 공백·제로폭을 지우고 같은 접두 삭제와 같은 부분 문자열 검사를 한다.
- 한 문서번호에 통과한 이름이 여러 개면, 하나라도 `consolidated`이면 범위는 `consolidated`다.
- 기간 할당, 시드, 블라인드, 예비, 홀드아웃, 검수 화면, `HANDOFF.md`는 바꾸지 않는다.
- 카탈로그는 읽기 전용이다. 네트워크와 LLM 호출을 넣지 않는다.
- 작업 끝에 `python -m pytest`와 `ruff check .`를 통과시킨다.

---

### Task 1: 문서명 판정

**Files:**
- Create: `src/dart_parser/gold/audit_document.py`
- Test: `tests/test_gold_audit_document.py`

**Interfaces:**
- Consumes: `dart_parser.normalizer.cleaner.normalize_text`
- Produces:
  - `classify_audit_document(name: str | None) -> Literal["separate", "consolidated"] | None`
  - `audit_document_predicate_sql(column: str) -> str` — 통과하면 참인 SQL 식. `column`은 `e.document_name`처럼 식별자다.
  - `audit_document_consolidated_sql(column: str) -> str` — 통과하고 `연결`이 있으면 참인 SQL 식.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_audit_document.py`를 만든다.

```python
"""감사보고서 문서명 판정은 파이썬과 SQL이 같다."""

from __future__ import annotations

import sqlite3

from dart_parser.gold.audit_document import (
    audit_document_consolidated_sql,
    audit_document_predicate_sql,
    classify_audit_document,
)

_NAMES = (
    ("감사보고서", "separate"),
    ("[정정] 감사보고서", "separate"),
    ("연결감사보고서", "consolidated"),
    ("[정정] 연결감사보고서", "consolidated"),
    ("외국법인등의연결감사보고서", "consolidated"),
    ("사업보고서", None),
    ("정관", None),
    ("기업개황자료", None),
    ("영업보고서", None),
    ("감사의감사보고서", None),
    ("감사\u00a0보고서", "separate"),
    ("감사\u3000보고서", "separate"),
    ("감사\u200b보고서", "separate"),
    (None, None),
    ("", None),
)


def test_classify_audit_document_name_table() -> None:
    for name, expected in _NAMES:
        assert classify_audit_document(name) == expected


def test_sql_predicate_matches_python() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE docs (document_name TEXT)")
    predicate = audit_document_predicate_sql("document_name")
    consolidated = audit_document_consolidated_sql("document_name")
    for name, expected in _NAMES:
        conn.execute("DELETE FROM docs")
        conn.execute("INSERT INTO docs (document_name) VALUES (?)", (name,))
        hit, cons = conn.execute(
            f"SELECT {predicate}, {consolidated} FROM docs"
        ).fetchone()
        assert bool(hit) is (expected is not None)
        assert bool(cons) is (expected == "consolidated")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_audit_document.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'dart_parser.gold.audit_document'`

- [ ] **Step 3: Write minimal implementation**

`src/dart_parser/gold/audit_document.py`를 만든다.

```python
"""감사보고서 문서명 판정.

파이썬과 SQLite 조건이 같은 순서로 접두를 지우고 같은 부분 문자열을 본다.
"""

from __future__ import annotations

from typing import Literal

from dart_parser.normalizer.cleaner import normalize_text

AuditScope = Literal["separate", "consolidated"]

_TAGS = ("[기재정정]", "[첨부정정]", "[정정]")
# normalize_text가 공백으로 바꾸거나 지우는 문자. SQL은 그 함수를 호출하지 않는다.
_SQL_STRIP = (
    " ",
    "\t",
    "\r",
    "\n",
    "\u00a0",
    "\u3000",
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
)


def _prepare(name: str | None) -> str:
    """비교용 문서명. 비어 있으면 빈 문자열."""
    text = normalize_text(name).replace(" ", "")
    for tag in _TAGS:
        text = text.replace(tag, "")
    return text


def classify_audit_document(name: str | None) -> AuditScope | None:
    """감사보고서 문서면 별도·연결을, 아니면 None을 돌려준다."""
    text = _prepare(name)
    if "감사의감사" in text or "감사보고서" not in text:
        return None
    if "연결" in text:
        return "consolidated"
    return "separate"


def _ident(column: str) -> str:
    """`document_name` 또는 `e.document_name`만 허용한다."""
    parts = column.split(".")
    if not 1 <= len(parts) <= 2 or not all(part.isidentifier() for part in parts):
        raise ValueError(f"document name column: {column}")
    return column


def normalized_document_sql(column: str) -> str:
    """문서명에서 공백과 정정 접두를 뺀 SQL 식."""
    expr = f"IFNULL({_ident(column)}, '')"
    for ch in _SQL_STRIP:
        expr = f"REPLACE({expr}, char({ord(ch)}), '')"
    for tag in _TAGS:
        expr = f"REPLACE({expr}, '{tag}', '')"
    return expr


def audit_document_predicate_sql(column: str) -> str:
    """감사보고서 문서면 참인 SQL 식."""
    norm = normalized_document_sql(column)
    return f"(INSTR({norm}, '감사의감사') = 0 AND INSTR({norm}, '감사보고서') > 0)"


def audit_document_consolidated_sql(column: str) -> str:
    """통과한 문서명에 `연결`이 있으면 참인 SQL 식."""
    norm = normalized_document_sql(column)
    return f"({audit_document_predicate_sql(column)} AND INSTR({norm}, '연결') > 0)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_audit_document.py -v`

Expected: PASS, 2 tests.

Run: `python -m ruff check src/dart_parser/gold/audit_document.py tests/test_gold_audit_document.py`

Expected: no findings.

- [ ] **Step 5: Commit**

```powershell
git add src/dart_parser/gold/audit_document.py tests/test_gold_audit_document.py
git commit -m "feat: classify audit-report document names"
```

---

### Task 2: 모집단은 감사보고서 문서만

**Files:**
- Modify: `src/dart_parser/gold/sampler.py` (`POPULATION_SQL`, `_pop_from_sql`)
- Modify: `tests/test_gold_population.py`
- Modify: `tests/gold_fixtures.py` (`entries.document_name`과 합성 문서의 문서명)
- Test: `tests/test_gold_population.py`

**Interfaces:**
- Consumes: `audit_document_predicate_sql`, `audit_document_consolidated_sql`
- Produces: `load_population` 행의 `scope`는 문서명 판정이다. `form`은 `A001`이면 `attached`, 아니면 `standalone`이다.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_population.py`의 기존 엔트리 스키마에 `document_name`을 넣고, 남길 `F001` 행의 문서명을 `감사보고서`로 둔다. 그 아래에 테스트를 추가한다.

기존 `CREATE TABLE entries`를 다음으로 바꾼다.

```python
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            document_name TEXT,
            section_name TEXT,
            dtd TEXT
        );
```

기존 세 `INSERT INTO entries VALUES`에 문서명을 한 칸 넣는다. 첫 행만 `감사보고서`다.

```python
        INSERT INTO entries VALUES (
            'e1', '20200315000001', '77', '감사보고서', '표지', 'dart3.xsd'
        );
        INSERT INTO entries VALUES (
            'e2', '20200315000002', '88', '연결감사보고서', '표지', 'dart3.xsd'
        );
        INSERT INTO entries VALUES (
            'e3', '20200315000003', '99', '감사의감사보고서', '표지', 'dart3.xsd'
        );
```

파일 끝에 추가한다.

```python
def _catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog.db"
    conn = sqlite3.connect(catalog)
    conn.executescript(
        """
        CREATE TABLE disclosures (
            rcept_no TEXT PRIMARY KEY,
            corp_code TEXT,
            report_nm TEXT,
            report_type TEXT,
            correction_type TEXT,
            rcept_dt TEXT,
            year_end TEXT
        );
        CREATE TABLE corps (
            corp_code TEXT PRIMARY KEY,
            corp_cls TEXT
        );
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            document_name TEXT,
            section_name TEXT,
            dtd TEXT
        );
        INSERT INTO corps VALUES ('C1', 'Y');
        """
    )
    conn.commit()
    conn.close()
    return catalog


def _filing(
    conn: sqlite3.Connection,
    rcept_no: str,
    report_type: str,
    correction: str,
    docs: list[tuple[str, str]],
) -> None:
    conn.execute(
        """
        INSERT INTO disclosures VALUES (?, 'C1', ?, ?, ?, '20200315', '2019.12')
        """,
        (rcept_no, docs[0][1], report_type, correction),
    )
    for index, (dcm_no, document_name) in enumerate(docs):
        conn.execute(
            """
            INSERT INTO entries VALUES (?, ?, ?, ?, '표지', 'dart3.xsd')
            """,
            (f"{rcept_no}-{index}", rcept_no, dcm_no, document_name),
        )


def test_population_keeps_only_audit_report_leaves(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    conn = sqlite3.connect(catalog)
    _filing(
        conn,
        "A",
        "A001",
        "",
        [
            ("1", "사업보고서"),
            ("2", "정관"),
            ("3", "감사보고서"),
            ("4", "연결감사보고서"),
            ("5", "감사의감사보고서"),
        ],
    )
    _filing(conn, "B", "A001", "기재정정", [("6", "사업보고서")])
    _filing(conn, "C0", "A001", "", [("7", "감사보고서")])
    _filing(conn, "C1", "A001", "기재정정", [("8", "[정정] 연결감사보고서")])
    _filing(
        conn,
        "D",
        "F001",
        "",
        [("9", "기업개황자료"), ("10", "감사보고서")],
    )
    _filing(
        conn,
        "E",
        "A001",
        "",
        [("11", "감사보고서"), ("11", "연결감사보고서")],
    )
    conn.commit()
    conn.close()
    gold = open_gold(tmp_path / "gold.db", catalog)
    rows = {(row.rcept_no, row.dcm_no): row for row in load_population(gold)}
    assert set(rows) == {("A", "3"), ("A", "4"), ("C0", "7"), ("C1", "8"), ("D", "10"), ("E", "11")}
    assert rows[("A", "3")].scope == "separate"
    assert rows[("A", "3")].form == "attached"
    assert rows[("A", "4")].scope == "consolidated"
    assert rows[("C0", "7")].scope == "separate"
    assert rows[("C1", "8")].scope == "consolidated"
    assert rows[("D", "10")].scope == "separate"
    assert rows[("D", "10")].form == "standalone"
    assert rows[("E", "11")].scope == "consolidated"
```

`_filing`이 같은 `dcm_no`에 문서명을 두 번 넣으므로 `E`의 `11`은 엔트리 두 개다. `docs[0][1]`이 접수 제목이 된다. `E`의 제목은 `감사보고서`라서, 예전 제목 기준 범위라면 `separate`다. 문서명 기준이면 `consolidated`다.

파일 상단에 `from pathlib import Path`를 추가한다.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_population.py -v`

Expected: FAIL. 기존 테스트는 `document_name` 열이 없는 쿼리 때문에 `OperationalError`이거나, 새 테스트는 `A`의 사업보고서까지 포함하고 `("E", "11")`의 `scope`가 `separate`다.

- [ ] **Step 3: Write minimal implementation**

`sampler.py` 상단 import에 다음을 추가한다.

```python
from dart_parser.gold.audit_document import (
    audit_document_consolidated_sql,
    audit_document_predicate_sql,
)
```

`POPULATION_SQL`을 다음으로 바꾼다. `fs_scope` CASE는 넣지 않는다.

```python
_AUDIT_PREDICATE = audit_document_predicate_sql("e.document_name")
_AUDIT_CONSOLIDATED = audit_document_consolidated_sql("e.document_name")

POPULATION_SQL = f"""
SELECT
    d.rcept_no AS rcept_no,
    e.dcm_no AS dcm_no,
    MAX(d.report_type) AS source_report_type,
    MAX(CASE WHEN {_AUDIT_PREDICATE} THEN 1 ELSE 0 END) AS audit_hit,
    MAX(CASE WHEN {_AUDIT_CONSOLIDATED} THEN 1 ELSE 0 END) AS audit_consolidated,
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
HAVING audit_hit = 1
"""
```

`_pop_from_sql`에서 `scope` 한 줄을 바꾼다.

```python
    scope = "consolidated" if int(record["audit_consolidated"] or 0) else "separate"
```

`tests/gold_fixtures.py`의 `CREATE TABLE entries`에 `document_name TEXT`를 `dcm_no` 다음에 넣는다.

```python
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            document_name TEXT,
            section_name TEXT,
            ele_id TEXT,
            dtd TEXT,
            viewer_url TEXT
        );
```

`_add_document`가 엔트리를 넣기 전에 문서명을 정한다.

```python
    document_name = "연결감사보고서" if fs_scope == "consolidated" else "감사보고서"
```

그 함수 안의 `INSERT INTO entries` 네 곳 모두 컬럼과 값에 `document_name`을 넣는다. 값은 위에서 정한 `document_name`이다. 섹션이 달라도 한 문서번호의 문서명은 같다.

```python
            INSERT INTO entries (
                entry_id, rcept_no, dcm_no, document_name, section_name, ele_id, dtd, viewer_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
```

튜플에는 `document_name`을 `dcm_no` 다음에 넣는다. 종속기업 섹션 insert도 포함한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_population.py tests/test_gold_oversample.py tests/test_gold_cache.py -q`

Expected: PASS. `run_sample`을 쓰는 테스트는 `test_gold_oversample.py`와 `test_gold_cache.py`다.

Run: `python -m ruff check src/dart_parser/gold/sampler.py tests/test_gold_population.py tests/gold_fixtures.py`

Expected: no findings.

- [ ] **Step 5: Commit**

```powershell
git add src/dart_parser/gold/sampler.py tests/test_gold_population.py tests/gold_fixtures.py
git commit -m "feat: keep only audit-report leaves in the gold population"
```

---

### Task 3: 추가 추출도 같은 문서만

**Files:**
- Modify: `src/dart_parser/gold/sampler.py` (`oversample` 후보 조회와 `meta`)
- Test: `tests/test_gold_oversample.py`

**Interfaces:**
- Consumes: `audit_document_predicate_sql("e.document_name")`, `audit_document_consolidated_sql("e.document_name")`, `open_gold`, `migrate`
- Produces: `oversample`이 넣는 `gold_samples.meta`의 `scope`는 `separate` 또는 `consolidated`다. 사업보고서 문서는 후보가 아니다.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_oversample.py`에 추가한다.

```python
import json
import sqlite3
from pathlib import Path

from dart_parser.gold.db import migrate, open_gold


def test_oversample_skips_non_audit_documents(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.db"
    cat = sqlite3.connect(catalog)
    cat.executescript(
        """
        CREATE TABLE disclosures (
            rcept_no TEXT PRIMARY KEY,
            corp_code TEXT,
            report_nm TEXT,
            report_type TEXT,
            correction_type TEXT,
            rcept_dt TEXT,
            year_end TEXT
        );
        CREATE TABLE corps (
            corp_code TEXT PRIMARY KEY,
            corp_cls TEXT
        );
        CREATE TABLE entries (
            entry_id TEXT PRIMARY KEY,
            rcept_no TEXT,
            dcm_no TEXT,
            document_name TEXT,
            section_name TEXT,
            dtd TEXT
        );
        INSERT INTO corps VALUES ('C1', 'Y');
        INSERT INTO disclosures VALUES
            ('R1', 'C1', '감사보고서', 'F001', '', '20200315', '2019.12'),
            ('R2', 'C1', '사업보고서', 'A001', '', '20200316', '2019.12');
        INSERT INTO entries VALUES
            ('a', 'R1', 'D1', '감사보고서', '내부회계관리제도', 'dart3.xsd'),
            ('b', 'R2', 'D2', '사업보고서', '내부회계관리제도', 'dart3.xsd');
        """
    )
    cat.commit()
    cat.close()
    conn = open_gold(tmp_path / "gold.db", catalog)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'gold-2026-10', '2026-11-10T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, sub_period, stratum, stratum_weight,
            sample_hash, mode, role, queue_order, status, exclude_reason, meta,
            started_at, finished_at, active_seconds
        ) VALUES (
            'run', 'KEEP', 'KEEP', 'P6', NULL, 's', 1, 'hash', 'prefill', 'main',
            1, 'todo', NULL, '{}', NULL, NULL, NULL
        )
        """
    )
    conn.commit()
    added = oversample(conn, "run", ("icfr", "opinion"), target=5)
    rows = conn.execute(
        """
        SELECT rcept_no, dcm_no, meta
        FROM gold_samples
        WHERE role = 'oversample'
        """
    ).fetchall()
    assert added == 1
    assert [(row[0], row[1]) for row in rows] == [("R1", "D1")]
    assert json.loads(rows[0][2])["scope"] == "separate"
```

`icfr` / `opinion`의 섹션 바늘은 `내부회계관리제도`다. 두 문서 모두 그 섹션을 가진다. 필터가 없으면 `R2`도 들어갈 수 있다.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_oversample.py::test_oversample_skips_non_audit_documents -v`

Expected: FAIL. `added`가 2이거나, `meta`에 `scope`가 없다.

- [ ] **Step 3: Write minimal implementation**

`oversample`의 후보 `SELECT`에서 `report_type` / `report_nm`으로 `fs_scope`를 만드는 `CASE`를 제거한다. SELECT 목록에 다음을 넣는다.

```python
    predicate = audit_document_predicate_sql("e.document_name")
    consolidated = audit_document_consolidated_sql("e.document_name")
```

조회문은 이 두 식을 쓴다.

```sql
MAX(CASE WHEN {consolidated} THEN 1 ELSE 0 END) AS audit_consolidated
```

`WHERE`의 기존 조건 끝에 다음을 붙인다.

```sql
AND {predicate}
```

`{predicate}`와 `{consolidated}`는 f-string으로 넣는다. `section_sql`은 그대로 `AND`로 이어진다.

고른 행의 `meta`에 범위를 넣는다.

```python
            scope = "consolidated" if int(record["audit_consolidated"] or 0) else "separate"
            meta = {
                "oversample_for": f"{bundle}:{subject}",
                "field_weight": weight,
                "catalog_as_of": as_of,
                "scope": scope,
                "dtd": record["dtd"] or "",
                "fye": record["year_end"] or "",
                "layout_era": layout_era(record["year_end"]),
                "in_extraction_reviews": 0,
                "review_signals": [],
                "market_source": "current_tag",
                "holdout": 0,
            }
```

`meta`에 이미 있는 키는 유지하고 `scope`만 추가한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_oversample.py tests/test_gold_population.py tests/test_gold_audit_document.py -q`

Expected: PASS.

Run: `python -m pytest -q`

Expected: PASS.

Run: `python -m ruff check .`

Expected: no findings.

- [ ] **Step 5: Commit**

```powershell
git add src/dart_parser/gold/sampler.py tests/test_gold_oversample.py
git commit -m "feat: oversample audit-report documents only"
```
