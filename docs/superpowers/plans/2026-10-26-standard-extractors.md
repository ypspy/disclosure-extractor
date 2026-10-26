# Standard Extractors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `standard` 과제의 식별·12묶음(`accounts`는 13계정)·주석 목차를 규칙 엔진으로 채워 `StandardExtraction`을 닫는다.

**Architecture:** 파이프라인은 HTML을 평탄화한 뒤 **구간 라우터**로 창을 자르고, 묶음별 추출기가 `Item`/`Icfr`/`Subsidiary`만 반환한다. 앞 작업이 만든 `ExtractionContext`(`fs_scope`, `fiscal_year`, `corp_form`, `sections`)를 뒤 작업이 게이트에 쓴다. 검증 실패 시에만 그 창을 SLM에 넘긴다.

**Tech Stack:** Python 3.11+, lxml/BeautifulSoup, rapidfuzz, pydantic v2, pytest, ruff. 숫자는 `to_number()`, 비교는 `normalize_text()`/`canonical()`, 금액은 `Amount`.

## Global Constraints

- 항목 키는 `docs/standard-extraction-items.md`에 있는 것만 사용한다. 새 키를 만들려면 그 문서를 먼저 고친다.
- 값 정의는 `audit_opinion.v19`(2026-10-23)다.
- `missing`은 실패, `not_applicable`과 `not_in_regime`은 실패가 아니다. 서로 바꾸지 않는다.
- HTML 스타일을 파싱하지 않는다. 표는 `flatten_table_to_grid` 이후에만 읽는다.
- 재무제표 계정은 Open DART XBRL/주요계정 API를 HTML보다 우선한다.
- `Amount`는 항상 `raw`, `value`, `unit_scale`, `value_won`을 같이 저장한다.
- 모듈 import 시 네트워크/LLM 호출을 하지 않는다.
- 추출기마다 pytest를 같이 추가하고, 작업 끝에 `python -m pytest`와 `ruff check .`를 통과시킨다.
- 주석 본문 전량, 계정과목 전량, 사업보고서 본문, 별지 제4호 5절, 내부회계관리제도 운영보고서는 추출하지 않는다.

## File map

| Path | Responsibility |
| --- | --- |
| `src/dart_parser/fallback/schemas.py` | 상태 헬퍼 `item_missing` / `item_not_applicable` / `item_not_in_regime` |
| `src/dart_parser/parser/context.py` | `ExtractionContext` |
| `src/dart_parser/parser/sections.py` | 제목 앵커로 문서 창을 자른다 |
| `src/dart_parser/parser/extractors/identification.py` | 회사명, 제목, 기수, `current_period`, `fs_scope` |
| `src/dart_parser/parser/extractors/accounts.py` | 13계정(FS 10 + IS 3) + 거부 라벨. 파이프라인의 `_extract_accounts`를 이전 |
| `src/dart_parser/parser/extractors/opinion_letter.py` | `auditor`, `opinion`, `gaap`, `audit_report_date` |
| `src/dart_parser/parser/extractors/hours.py` | 별지 제4호 2절 3축 격자 |
| `src/dart_parser/parser/extractors/activities.py` | 별지 제4호 3절 절차 7개 |
| `src/dart_parser/parser/extractors/communications.py` | 별지 제4호 4절 + 옛 공시 `not_in_regime` |
| `src/dart_parser/parser/extractors/icfr.py` | 같은 문서 내부회계 의견 + F001/F002 게이트 |
| `src/dart_parser/parser/extractors/going_concern.py` | 당기 중요한 불확실성 0/1 |
| `src/dart_parser/parser/extractors/subsidiary.py` | 연결 종속기업 수, 별도 `not_applicable` |
| `src/dart_parser/parser/extractors/notes_toc.py` | 주석 제목 목록 (본문 제외) |
| `src/dart_parser/pipeline.py` | 라우터 + 추출기 호출만 |
| `tests/test_<bundle>.py` | 묶음별 mock HTML 테스트 |

의존 순서: 1 공용 골격 → 2 식별 → 3 계정(13) → 4 의견서 → 5–7 별지 제4호 → 8 내부회계 → 9 계속기업 → 10 종속기업 → 11 주석 목차 → 12 파이프라인 조립.

---

### Task 1: ExtractionContext, section windows, status helpers

**Files:**
- Create: `src/dart_parser/parser/context.py`
- Create: `src/dart_parser/parser/sections.py`
- Create: `src/dart_parser/parser/extractors/__init__.py`
- Create: `tests/test_sections.py`
- Modify: `src/dart_parser/fallback/schemas.py` (status helpers after `found`)
- Modify: `src/dart_parser/parser/__init__.py` (export `ExtractionContext`, `locate_sections`)

**Interfaces:**
- Consumes: `Table` from `dart_parser.normalizer.table_grid`; `ExtractionStatus`, `Item` from `fallback.schemas`
- Produces:
  - `item_missing() -> Item[None]`
  - `item_not_applicable() -> Item[None]`
  - `item_not_in_regime() -> Item[None]`
  - `ExtractionContext(html: str, rcept_no: str | None = None, fs_scope: Literal["separate", "consolidated"] | None = None, fiscal_year: int | None = None, corp_form: Literal["F001", "F002"] | None = None, tables: list[Table] = ..., sections: dict[str, str] = ...)`
  - `locate_sections(html: str) -> dict[str, str]` with keys `cover`, `opinion_letter`, `exhibit4_hours`, `exhibit4_activities`, `exhibit4_communications`, `bs`, `is_`, `icfr_opinion`, `going_concern`, `subsidiaries`, `notes_toc`. Missing windows are `""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sections.py
from dart_parser.fallback.schemas import ExtractionStatus, item_not_in_regime
from dart_parser.parser.sections import locate_sections

COVER_AND_EXHIBIT = """
<h1>감사보고서</h1>
<p>제5기 2024.01.01부터 2024.12.31까지</p>
<h2>독립된 감사인의 감사보고서</h2>
<p>의견 적정</p>
<h2>별지 제4호</h2>
<h3>2. 감사 투입 인력 및 시간</h3>
<table><tr><td>품질관리검토자</td></tr></table>
<h3>3. 주요 감사 실시 내용</h3>
<p>전반감사계획</p>
<h3>4. 감사위원회와의 커뮤니케이션</h3>
<p>제1회</p>
"""

def test_status_helper_is_not_failure() -> None:
    item = item_not_in_regime()
    assert item.status is ExtractionStatus.not_in_regime
    assert item.value is None


def test_locate_sections_splits_exhibit4() -> None:
    sections = locate_sections(COVER_AND_EXHIBIT)
    assert "품질관리검토자" in sections["exhibit4_hours"]
    assert "전반감사계획" in sections["exhibit4_activities"]
    assert "제1회" in sections["exhibit4_communications"]
    assert "적정" in sections["opinion_letter"]
    assert "제5기" in sections["cover"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sections.py -v`
Expected: FAIL with `ImportError` (`item_not_in_regime` or `locate_sections` missing)

- [ ] **Step 3: Write minimal implementation**

`schemas.py`에 `found` 바로 아래:

```python
def item_missing() -> Item[None]:
    return Item(status=ExtractionStatus.missing)


def item_not_applicable() -> Item[None]:
    return Item(status=ExtractionStatus.not_applicable)


def item_not_in_regime() -> Item[None]:
    return Item(status=ExtractionStatus.not_in_regime)
```

`context.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from dart_parser.normalizer.table_grid import Table

CorpForm = Literal["F001", "F002"]
FsScope = Literal["separate", "consolidated"]

@dataclass
class ExtractionContext:
    html: str
    rcept_no: str | None = None
    fs_scope: FsScope | None = None
    fiscal_year: int | None = None
    corp_form: CorpForm | None = None
    tables: list[Table] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
```

`sections.py`: `normalize_text`한 헤딩 텍스트를 앵커로 보고, 다음 동급 헤딩 전까지의 HTML을 창으로 자른다. 앵커 예: `독립된 감사인의 감사보고서` → `opinion_letter`; `감사 투입` / `2.`+`시간` → `exhibit4_hours`; `실시 내용` / `3.` → `exhibit4_activities`; `커뮤니케이션` / `4.` → `exhibit4_communications`. 문서 앞부분(첫 의견서 헤딩 전)은 `cover`. 매칭되지 않은 키는 `""`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sections.py -v && python -m ruff check src/dart_parser/parser/context.py src/dart_parser/parser/sections.py src/dart_parser/fallback/schemas.py tests/test_sections.py`
Expected: PASS, ruff clean

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/fallback/schemas.py src/dart_parser/parser/context.py src/dart_parser/parser/sections.py src/dart_parser/parser/extractors/__init__.py src/dart_parser/parser/__init__.py tests/test_sections.py
git commit -m "feat: add extraction context, section windows, and item status helpers"
```

---

### Task 2: Identification, current_period, fs_scope

**Files:**
- Create: `src/dart_parser/parser/extractors/identification.py`
- Create: `tests/test_identification.py`
- Create: `tests/sample_htmls/mock_cover.html`

**Interfaces:**
- Consumes: `ExtractionContext`, `locate_sections`, `Period`, `found`, `item_missing`
- Produces:
  - `class Identification(company_name: Item[str], document_title: Item[str], fiscal_term: Item[str], current_period: Item[Period], fs_scope: Literal["separate", "consolidated"] | None)`
  - `extract_identification(ctx: ExtractionContext) -> Identification`
  - `current_period`와 식별의 보고기간은 동일 객체다. `연결감사보고서` → `fs_scope="consolidated"`, `감사보고서` → `"separate"`. 기수 `제N기`. 기간 `YYYY.MM.DD`~`YYYY.MM.DD`를 `Period(start, end, raw)`로 넣고, `end`의 연도를 나중에 `ctx.fiscal_year`로 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identification.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.identification import extract_identification
from dart_parser.parser.sections import locate_sections

HTML = """
<p>주식회사 예시</p>
<p>감사보고서</p>
<p>제5기 2024.01.01부터 2024.12.31까지</p>
"""

def test_extracts_cover_fields_and_separate_scope() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    result = extract_identification(ctx)
    assert result.company_name.value == "주식회사 예시"
    assert result.document_title.value == "감사보고서"
    assert result.fiscal_term.value == "제5기"
    assert result.current_period.value is not None
    assert result.current_period.value.start == "2024-01-01"
    assert result.current_period.value.end == "2024-12-31"
    assert result.fs_scope == "separate"


def test_consolidated_title_sets_scope() -> None:
    html = "<p>연결감사보고서</p><p>제3기 2023.01.01부터 2023.12.31까지</p>"
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_identification(ctx).fs_scope == "consolidated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identification.py -v`
Expected: FAIL with `ImportError` for `extract_identification`

- [ ] **Step 3: Write minimal implementation**

`identification.py`에서 `cover` 창(없으면 전체 `html`)에 `html_to_text`를 적용한다. 제목은 `연결감사보고서`를 먼저, 그다음 `감사보고서`를 본다. 기수는 `제\s*(\d+)\s*기`. 기간은 `(\d{4})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2}).*?(\d{4})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2})`. 회사명은 제목/기수 줄이 아닌 첫 `주식회사|㈜|.+주식회사` 줄. 매칭 실패 필드는 `item_missing()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_identification.py tests/test_sections.py -v && python -m ruff check src/dart_parser/parser/extractors/identification.py tests/test_identification.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/identification.py tests/test_identification.py tests/sample_htmls/mock_cover.html
git commit -m "feat: extract cover identification, current period, and fs_scope"
```

---

### Task 3: Accounts — 13 lines from BS and IS

**Files:**
- Create: `src/dart_parser/parser/extractors/accounts.py`
- Create: `tests/test_accounts.py`
- Modify: `src/dart_parser/pipeline.py` (`_extract_accounts`를 import로 교체)
- Modify: `src/dart_parser/parser/lexicon.py` (거부 필터를 실제 매칭에 연결). `revenue`/`operating_income` 별칭은 이미 있음

**Interfaces:**
- Consumes: `ExtractionContext.fs_scope`, `RuleEngine`, `detect_period_columns`, `infer_header_row_count`, `stacked_header_labels`, `ACCOUNT_ALIASES`, `ACCOUNT_REJECT_SUBSTRINGS`, `found`, `item_missing`, `Accounts`, `AccountLine`, `Amount`
- Produces:
  - `extract_accounts(ctx: ExtractionContext) -> Item[Accounts]`
  - 13키: FS 10 + `revenue`, `operating_income`, `net_income`. 최상위 `revenue`/`operating_income` 필드는 없다
  - 열: `당기`/`전기`, 또는 `제N기` 중 큰 기수 = 당기. 세 손익 계정도 `AccountLine(current, prior)`
  - `당기순손실`·`영업손실`이고 `value > 0`이면 부호 반전
  - 재무상태표 표에서 FS 10, 손익계산서 표에서 IS 3. `fs_scope=="consolidated"`이면 캡션/선행문에 `연결`이 있는 표를 우선
  - 라벨에 거부 부분문자열이 있으면 그 키를 채우지 않음 (`매출원가`, `영업외`, 계속·중단·귀속 등)
  - XBRL 경로는 이 작업에서 호출하지 않는다. HTML 격자만. API 연결은 후속 작업에서 `source="xbrl"`로 같은 시그니처를 유지한 채 추가한다

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_accounts.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.accounts import extract_accounts

REJECT_HTML = """
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>1,200</td><td>1,000</td></tr>
  <tr><td>부채와자본총계</td><td>1,200</td><td>1,000</td></tr>
  <tr><td>비유동자산</td><td>100</td><td>80</td></tr>
  <tr><td>재고자산충당금</td><td>3</td><td>2</td></tr>
  <tr><td>지배주주당기순이익</td><td>50</td><td>40</td></tr>
  <tr><td>당기순손실</td><td>20</td><td>10</td></tr>
</table>
"""

IS_HTML = """
<p>손익계산서</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>매출액</td><td>3,000</td><td>2,500</td></tr>
  <tr><td>매출원가</td><td>1,800</td><td>1,500</td></tr>
  <tr><td>영업손실</td><td>100</td><td>40</td></tr>
  <tr><td>당기순이익</td><td>80</td><td>50</td></tr>
</table>
"""

def test_rejects_out_of_scope_account_labels() -> None:
    ctx = ExtractionContext(html=REJECT_HTML, tables=extract_tables(REJECT_HTML))
    item = extract_accounts(ctx)
    assert item.status is ExtractionStatus.found
    assert item.value is not None
    assert item.value.total_asset.current.value == 1200.0
    assert item.value.current_asset is None
    assert item.value.inventory is None
    assert item.value.total_equity is None
    assert item.value.net_income.current.value == -20.0


def test_income_statement_lines_join_accounts() -> None:
    ctx = ExtractionContext(
        html=IS_HTML, tables=extract_tables(IS_HTML), fs_scope="separate"
    )
    item = extract_accounts(ctx)
    assert item.value.revenue.current.value == 3000.0
    assert item.value.revenue.current.unit_scale == 1_000_000
    assert item.value.revenue.prior.value == 2500.0
    assert item.value.operating_income.current.value == -100.0
    assert item.value.net_income.current.value == 80.0
```

기존 `tests/test_pipeline.py`의 accounts assertion은 그대로 통과해야 한다. `mock_bs_html` fixture를 `test_accounts.py`에서도 재사용한다.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_accounts.py -v`
Expected: FAIL (`extract_accounts` missing). 현재 `pipeline._extract_accounts`는 `부채와자본총계`를 `total_equity`로 오인할 수 있다.

- [ ] **Step 3: Write minimal implementation**

`accounts.py`에 파이프라인 로직을 옮긴다. 표를 재무상태표/`손익` 후보로 나누고, 연결이면 `연결` 캡션을 우선한다. 행 매칭 전에 `canonical(label)`이 `ACCOUNT_REJECT_SUBSTRINGS`에 걸리면 skip. `영업손실`/`당기순손실`은 양수여도 부호 반전. `pipeline.py`는 `extract_accounts(ctx)`만 호출한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_accounts.py tests/test_pipeline.py tests/test_rule_engine.py tests/test_schemas.py -v && python -m ruff check src/dart_parser/parser/extractors/accounts.py src/dart_parser/pipeline.py tests/test_accounts.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/accounts.py src/dart_parser/pipeline.py src/dart_parser/parser/lexicon.py tests/test_accounts.py
git commit -m "feat: extract 13 research accounts from BS and IS with reject labels"
```

---

### Task 4: Opinion letter — auditor, opinion, gaap, audit_report_date

**Files:**
- Create: `src/dart_parser/parser/extractors/opinion_letter.py`
- Create: `tests/test_opinion_letter.py`

**Interfaces:**
- Consumes: `ctx.sections["opinion_letter"]` (없으면 전체 텍스트), `OPINION_ALIASES`, `GAAP_ALIASES`
- Produces:
  - `class OpinionLetter(auditor: Item[str], opinion: Item[str], gaap: Item[Gaap], audit_report_date: Item[str])`
  - `extract_opinion_letter(ctx: ExtractionContext) -> OpinionLetter`
  - `opinion` 값은 한글 코드 `적정`/`부적정`/`거절`만. 한정은 재무제표 의견이 아님
  - `gaap.value.raw`는 원문, `code`는 `K-IFRS` 또는 `K-GAAP`
  - `audit_report_date`는 의견서 채택일 `YYYY-MM-DD`. 창이 비면 `item_missing()`, 추정 금지
  - 감사인: `회계법인` 또는 `감사반`으로 끝나는 고유명

- [ ] **Step 1: Write the failing test**

```python
# tests/test_opinion_letter.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.opinion_letter import extract_opinion_letter
from dart_parser.parser.sections import locate_sections

HTML = """
<h2>독립된 감사인의 감사보고서</h2>
<p>우리는 한국채택국제회계기준에 따라 작성된 재무제표를 감사하였습니다.</p>
<p>우리의 의견으로는 재무제표는 적정하게 표시하고 있습니다.</p>
<p>2025년 3월 10일</p>
<p>한영회계법인</p>
"""

def test_opinion_letter_fields() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    out = extract_opinion_letter(ctx)
    assert out.auditor.value == "한영회계법인"
    assert out.opinion.value == "적정"
    assert out.gaap.value is not None
    assert out.gaap.value.code == "K-IFRS"
    assert "한국채택국제회계기준" in out.gaap.value.raw
    assert out.audit_report_date.value == "2025-03-10"
```

두 번째 테스트: 날짜 문장 없는 HTML → `audit_report_date.status is ExtractionStatus.missing`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_opinion_letter.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`html_to_text(section)`. `match_anchor`로 의견/GAAP. 날짜는 `(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일` 중 의견서 창의 **마지막** 일자를 채택일로 본다. 감사인은 `(?:\S+회계법인|\S+감사반)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_opinion_letter.py -v && python -m ruff check src/dart_parser/parser/extractors/opinion_letter.py tests/test_opinion_letter.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/opinion_letter.py tests/test_opinion_letter.py
git commit -m "feat: extract auditor, FS opinion, GAAP, and report date from opinion letter"
```

---

### Task 5: Hours — exhibit 4 section 2 axis grid

**Files:**
- Create: `src/dart_parser/parser/extractors/hours.py`
- Create: `tests/test_hours.py`

**Interfaces:**
- Consumes: `ctx.sections["exhibit4_hours"]` 또는 그 창의 표, `HOUR_ROLE_ALIASES`, `HOUR_METRIC_ALIASES`, `HOUR_PERIOD_ALIASES`, `HoursCell`, `HoursTable`, `to_number`
- Produces:
  - `extract_hours(ctx: ExtractionContext) -> Item[HoursTable]`
  - 칸 = `(role, role_key, metric, metric_key, period, value, unmapped)`
  - 축 라벨이 사전에 없으면 그 칸만 `unmapped=True`, `role_key`/`metric_key`/`period`는 `None`
  - 창이 없으면 `item_missing()`
  - 검증(같은 파일 `validate_hours(table: HoursTable) -> ValidationResult`): 역할 `합계` 행의 감사시간 당기 ≈ 구성 역할(합계·기타 제외) 합. 허용오차 1.0

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hours.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.hours import extract_hours
from dart_parser.parser.sections import locate_sections

HTML = """
<h3>2. 감사 투입 인력 및 시간</h3>
<table>
  <tr><th>구분</th><th colspan="2">투입인원수</th><th colspan="2">감사시간</th></tr>
  <tr><th></th><th>당기</th><th>전기</th><th>당기</th><th>전기</th></tr>
  <tr><td>업무수행이사</td><td>1</td><td>1</td><td>100</td><td>90</td></tr>
  <tr><td>등록공인회계사</td><td>3</td><td>2</td><td>400</td><td>350</td></tr>
  <tr><td>합계</td><td>4</td><td>3</td><td>500</td><td>440</td></tr>
</table>
"""

def test_hours_cells_are_role_metric_period() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.found
    partner = [
        c for c in item.value.cells
        if c.role_key == "engagement_partner" and c.metric_key == "audit_hours" and c.period == "current"
    ]
    assert partner[0].value == 100.0
    assert not partner[0].unmapped
```

추가 테스트: 역할 헤더가 `파트너`처럼 사전에 없으면 그 행 칸 `unmapped is True`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hours.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

창에서 표를 평탄화 → 다중 헤더를 `stack_headers` → 각 열을 (metric, period)로, 각 행 라벨을 role로 `match_anchor`. 교점 칸을 `HoursCell`로 append. 미매칭 축은 `unmapped=True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hours.py -v && python -m ruff check src/dart_parser/parser/extractors/hours.py tests/test_hours.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/hours.py tests/test_hours.py
git commit -m "feat: extract exhibit-4 hours as role x metric x period cells"
```

---

### Task 6: Activities — exhibit 4 section 3

**Files:**
- Create: `src/dart_parser/parser/extractors/activities.py`
- Create: `tests/test_activities.py`

**Interfaces:**
- Consumes: `ctx.sections["exhibit4_activities"]`, `ACTIVITY_ALIASES`, `ACTIVITY_KEYS`, `Activities`, `Observation`, `ExternalConfirmations`
- Produces:
  - `extract_activities(ctx: ExtractionContext) -> Item[Activities]`
  - `planning`/`fieldwork`/`tcwg_communication`/`expert`: 실시 내용 문자열
  - `inventory_observation`/`financial_asset_observation`: `Observation(date, place, target)` — 시기/장소/대상 라벨 옆 칸
  - `external_confirmations`: `ExternalConfirmations(financial, receivables_payables, legal, other)`
  - `tcwg_communication`은 4절 회차를 복사하지 않음
  - 창은 있는데 절차 키가 없으면 그 필드만 `None` (묶음은 `found`일 수 있음). 창 자체가 없으면 `item_missing()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_activities.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.activities import extract_activities
from dart_parser.parser.sections import locate_sections

HTML = """
<h3>3. 주요 감사 실시 내용</h3>
<table>
  <tr><td>전반감사계획</td><td>위험평가 및 계획 수립</td></tr>
  <tr><td>현장감사</td><td>2024.11.01~2024.11.15</td></tr>
  <tr><td>재고자산 실사</td><td>시기 2024.12.31 / 장소 본사창고 / 대상 제품</td></tr>
  <tr><td>외부조회</td><td>금융거래 실시 / 채권채무 실시 / 변호사 미실시 / 기타 없음</td></tr>
  <tr><td>지배기구와의 커뮤니케이션</td><td>감사 계획 및 결과 보고</td></tr>
  <tr><td>외부전문가</td><td>해당없음</td></tr>
</table>
"""

def test_activities_seven_procedures() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    item = extract_activities(ctx)
    acts = item.value
    assert acts.planning == "위험평가 및 계획 수립"
    assert acts.inventory_observation is not None
    assert acts.inventory_observation.place == "본사창고"
    assert acts.external_confirmations.legal == "미실시"
    assert acts.tcwg_communication == "감사 계획 및 결과 보고"
    assert "제1회" not in (acts.tcwg_communication or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_activities.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

3절 표를 평탄화해 첫 열을 절차 앵커로 매칭. 실사/조회는 오른쪽 셀을 `시기|장소|대상` 및 `금융거래|채권채무|변호사|기타`로 split. `해당없음`은 빈 문자열이 아니라 원문 유지(숫자 변환하지 않음).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_activities.py -v && python -m ruff check src/dart_parser/parser/extractors/activities.py tests/test_activities.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/activities.py tests/test_activities.py
git commit -m "feat: extract exhibit-4 audit activity procedures"
```

---

### Task 7: Communications — exhibit 4 section 4 and old-form regime

**Files:**
- Create: `src/dart_parser/parser/extractors/communications.py`
- Create: `tests/test_communications.py`

**Interfaces:**
- Consumes: `ctx.sections`의 `exhibit4_hours`, `exhibit4_activities`, `exhibit4_communications`, `Communications`, `CommunicationItem`, `item_missing`, `item_not_in_regime`, `found`
- Produces:
  - `extract_communications(ctx: ExtractionContext) -> Item[Communications]`
  - 2·3절은 있고 4절 창이 비면 `item_not_in_regime()`
  - 4절이 있어야 하는 서식인데 비면 `item_missing()`
  - 4절이 있으면 `has_audit_committee`: 창에 `감사위원회`가 있고 단순 `감사`만 있는 경우가 아니면 True. `감사`만 → False
  - `items`: 회차 행 (`제N회` / `N회`)마다 `CommunicationItem(round, date, raw)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_communications.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.communications import extract_communications
from dart_parser.parser.sections import locate_sections

OLD = """
<h3>2. 감사 투입 인력 및 시간</h3><p>표</p>
<h3>3. 주요 감사 실시 내용</h3><p>계획</p>
"""

NEW = """
<h3>2. 감사 투입 인력 및 시간</h3><p>표</p>
<h3>3. 주요 감사 실시 내용</h3><p>계획</p>
<h3>4. 감사위원회와의 커뮤니케이션</h3>
<table>
  <tr><th>회차</th><th>일자</th></tr>
  <tr><td>제1회</td><td>2024.03.05</td></tr>
  <tr><td>제2회</td><td>2024.11.20</td></tr>
</table>
"""

def test_old_form_without_section4_is_not_in_regime() -> None:
    ctx = ExtractionContext(html=OLD, sections=locate_sections(OLD))
    item = extract_communications(ctx)
    assert item.status is ExtractionStatus.not_in_regime
    assert item.value is None


def test_committee_rounds() -> None:
    ctx = ExtractionContext(html=NEW, sections=locate_sections(NEW))
    item = extract_communications(ctx)
    assert item.value.has_audit_committee is True
    assert [i.round for i in item.value.items] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_communications.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`has_s2 = bool(sections["exhibit4_hours"])`, `has_s3 = bool(sections["exhibit4_activities"])`, `has_s4 = bool(sections["exhibit4_communications"])`. `(has_s2 or has_s3) and not has_s4` → `item_not_in_regime()`. `has_s4`이면 표에서 회차 파싱.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_communications.py -v && python -m ruff check src/dart_parser/parser/extractors/communications.py tests/test_communications.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/communications.py tests/test_communications.py
git commit -m "feat: extract exhibit-4 communications with old-form not_in_regime"
```

---

### Task 8: ICFR — regime gate then same-document opinion leaf

**Files:**
- Create: `src/dart_parser/parser/extractors/icfr.py`
- Create: `tests/test_icfr.py`

**Interfaces:**
- Consumes: `ExtractionContext.corp_form`, `fiscal_year`, `fs_scope`, `sections["icfr_opinion"]`, `Icfr`
- Produces:
  - `icfr_in_regime(ctx: ExtractionContext) -> bool`
  - `extract_icfr(ctx: ExtractionContext) -> Icfr`
  - 게이트: `corp_form=="F001"` 이고 leaf 없음 → `icfr_status=not_in_regime`
  - 게이트: `corp_form=="F002"` 이고 (`fiscal_year` is None or `fiscal_year <= 2022`) 이고 leaf 없음 → `not_in_regime`
  - 수록 대상인데 leaf 없음 → `missing`
  - leaf 있음: 제목에 `검토`면 `icfr_engagement="review"`, 아니면 `"audit"`. 의견 코드는 감사 `적정|부적정|거절`(중요한 취약점 → `부적정`), 검토 `적정|한정|거절|중요한 취약점`
  - `내부회계관리제도 운영보고서`만 있는 창은 leaf로 보지 않음
  - 재무제표 `opinion`과 창을 공유하지 않음. `icfr_opinion` 창만 읽음
  - `fs_scope`는 그 문서 값을 따르며 별도 의견을 연결에 복사하지 않음

- [ ] **Step 1: Write the failing test**

```python
# tests/test_icfr.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.icfr import extract_icfr
from dart_parser.parser.sections import locate_sections

LEAF = """
<h2>독립된 감사인의 내부회계관리제도 감사의견</h2>
<p>중요성의 관점에서 효과적으로 설계 및 운영되고 있습니다. 적정</p>
"""

def test_f001_without_leaf_is_not_in_regime() -> None:
    ctx = ExtractionContext(html="<p>감사보고서</p>", corp_form="F001", sections={})
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.not_in_regime
    assert out.icfr_opinion_code is None


def test_f002_fy2022_without_leaf_is_not_in_regime() -> None:
    ctx = ExtractionContext(
        html="<p>연결감사보고서</p>", corp_form="F002", fiscal_year=2022,
        fs_scope="consolidated", sections={},
    )
    assert extract_icfr(ctx).icfr_status is ExtractionStatus.not_in_regime


def test_in_regime_without_leaf_is_missing() -> None:
    ctx = ExtractionContext(
        html="<p>감사보고서</p>", corp_form="F002", fiscal_year=2024, sections={}
    )
    assert extract_icfr(ctx).icfr_status is ExtractionStatus.missing


def test_audit_opinion_from_same_document_leaf() -> None:
    ctx = ExtractionContext(html=LEAF, fiscal_year=2024, sections=locate_sections(LEAF))
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.found
    assert out.icfr_engagement == "audit"
    assert out.icfr_opinion_code == "적정"


def test_operating_report_is_not_icfr_leaf() -> None:
    html = "<h2>내부회계관리제도 운영보고서</h2><p>이사회 보고</p>"
    ctx = ExtractionContext(html=html, fiscal_year=2024, sections=locate_sections(html))
    assert extract_icfr(ctx).icfr_status is not ExtractionStatus.found
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_icfr.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`sections.py` 앵커에 `내부회계관리제도` + (`감사의견`|`검토의견`)을 `icfr_opinion`으로 추가하고, `운영보고서`는 제외. `extract_icfr`는 게이트 → leaf 텍스트 → engagement/code.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_icfr.py tests/test_sections.py -v && python -m ruff check src/dart_parser/parser/extractors/icfr.py tests/test_icfr.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/icfr.py src/dart_parser/parser/sections.py tests/test_icfr.py
git commit -m "feat: gate and extract ICFR opinion from the same audit report"
```

---

### Task 9: Going concern

**Files:**
- Create: `src/dart_parser/parser/extractors/going_concern.py`
- Create: `tests/test_going_concern.py`

**Interfaces:**
- Consumes: `ctx.sections["going_concern"]` 또는 강조사항/기타사항 창, `Item[int]`
- Produces:
  - `extract_going_concern(ctx: ExtractionContext) -> Item[int]`
  - 당기 중요한 불확실성이 명시되면 `found` + `value=1`, 아니면 `found` + `value=0` (항목은 체제 안에 있고 값은 0/1)
  - 다음이면 반드시 0: 한정·부적정·거절의 근거로만 언급, 전기 인용만, 청산기준 강조사항만
  - 문장에 `계속기업`만 있고 불확실성이 없으면 0

- [ ] **Step 1: Write the failing test**

```python
# tests/test_going_concern.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.going_concern import extract_going_concern

def test_material_uncertainty_is_one() -> None:
    html = "<p>계속기업 가정에 중요한 불확실성이 존재합니다.</p>"
    item = extract_going_concern(ExtractionContext(html=html, sections={"going_concern": html}))
    assert item.value == 1


def test_emphasis_of_liquidation_is_zero() -> None:
    html = "<p>청산기준에 따라 재무제표를 작성하였음을 강조합니다.</p>"
    assert extract_going_concern(ExtractionContext(html=html, sections={"going_concern": html})).value == 0


def test_prior_year_quote_is_zero() -> None:
    html = "<p>전기 감사보고서는 계속기업 불확실성을 언급하였습니다.</p>"
    assert extract_going_concern(ExtractionContext(html=html, sections={"going_concern": html})).value == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_going_concern.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

정규화 텍스트에서 `중요한 불확실성` + `계속기업`이 있고, `전기`만 가리키거나 `청산`만 있으면 0. 의견 근거 문장(`한정의 근거`/`부적정의 근거`/`거절의 근거`) 안의 언급도 0.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_going_concern.py -v && python -m ruff check src/dart_parser/parser/extractors/going_concern.py tests/test_going_concern.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/going_concern.py tests/test_going_concern.py
git commit -m "feat: classify going-concern material uncertainty as 0 or 1"
```

---

### Task 10: Subsidiary count

**Files:**
- Create: `src/dart_parser/parser/extractors/subsidiary.py`
- Create: `tests/test_subsidiary.py`

**Interfaces:**
- Consumes: `ctx.fs_scope`, `ctx.sections["subsidiaries"]` 또는 종속기업 표, `Subsidiary`
- Produces:
  - `extract_subsidiary(ctx: ExtractionContext) -> Subsidiary`
  - `fs_scope=="separate"` → `subsidiary_status=not_applicable`, `subsidiary_count=None` (표를 찾지 않음)
  - 연결: 종속기업 표에서 데이터 행 수. 헤더·합계 제외. 행 라벨/구분 열이 `관계기업` 또는 `공동기업`이면 제외
  - 연결인데 표를 못 찾으면 `missing`, count `None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subsidiary.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.subsidiary import extract_subsidiary

TABLE = """
<p>종속기업</p>
<table>
  <tr><th>기업명</th><th>구분</th></tr>
  <tr><td>A주식회사</td><td>종속기업</td></tr>
  <tr><td>B주식회사</td><td>종속기업</td></tr>
  <tr><td>C주식회사</td><td>관계기업</td></tr>
  <tr><td>D주식회사</td><td>공동기업</td></tr>
</table>
"""

def test_separate_is_not_applicable() -> None:
    out = extract_subsidiary(ExtractionContext(html="<p>감사보고서</p>", fs_scope="separate"))
    assert out.subsidiary_status is ExtractionStatus.not_applicable
    assert out.subsidiary_count is None


def test_consolidated_counts_only_subsidiaries() -> None:
    ctx = ExtractionContext(
        html=TABLE, fs_scope="consolidated", tables=extract_tables(TABLE)
    )
    out = extract_subsidiary(ctx)
    assert out.subsidiary_status is ExtractionStatus.found
    assert out.subsidiary_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subsidiary.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

별도 가드 후, 캡션/선행문에 `종속기업`이 있는 표를 평탄화. 구분 열이 없으면 모든 데이터 행을 종속기업으로 센다. 있으면 `관계`/`공동` 제외.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_subsidiary.py -v && python -m ruff check src/dart_parser/parser/extractors/subsidiary.py tests/test_subsidiary.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/subsidiary.py tests/test_subsidiary.py
git commit -m "feat: count consolidated subsidiaries and mark separate as not_applicable"
```

---

### Task 11: Notes TOC

**Files:**
- Create: `src/dart_parser/parser/extractors/notes_toc.py`
- Create: `tests/test_notes_toc.py`

**Interfaces:**
- Consumes: `ctx.sections["notes_toc"]` 또는 `주석` 목차 창
- Produces:
  - `extract_notes_toc(ctx: ExtractionContext) -> Item[NotesToc]`
  - `NotesToc(count: int, titles: list[str])`. `count == len(titles)`
  - 제목만. 주석 본문 문단을 이어붙이지 않음
  - 창이 없으면 `item_missing()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notes_toc.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.notes_toc import extract_notes_toc

HTML = """
<h2>주석</h2>
<p>1. 회사의 개요</p>
<p>2. 중요한 회계정책</p>
<p>3. 매출채권</p>
<h3>1. 회사의 개요</h3>
<p>당사는 1988년에 설립되었으며 본문은 길다.</p>
"""

def test_notes_toc_titles_exclude_body() -> None:
    item = extract_notes_toc(ExtractionContext(html=HTML, sections={"notes_toc": HTML}))
    assert item.value.titles == ["회사의 개요", "중요한 회계정책", "매출채권"]
    assert item.value.count == 3
    assert "1988" not in " ".join(item.value.titles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_notes_toc.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`주석` 헤딩 이후, 본문 헤딩(`h3` 또는 `1. 제목`이 본문에서 반복되기 전)까지의 번호 목록만 수집. `^\s*(\d+)\s*[\.．]\s*(.+)$` 줄. 같은 번호가 본문에서 다시 나오면 목차 구간을 종료.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_notes_toc.py -v && python -m ruff check src/dart_parser/parser/extractors/notes_toc.py tests/test_notes_toc.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/parser/extractors/notes_toc.py tests/test_notes_toc.py
git commit -m "feat: extract notes table of contents titles only"
```

---

### Task 12: Pipeline assembly

**Files:**
- Modify: `src/dart_parser/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Create: `tests/sample_htmls/mock_standard_min.html` (표지 + 의견서 + BS + IS + 별지 2·3·4절을 한 파일에)

**Interfaces:**
- Consumes: Task 1–11의 `extract_*` 함수와 `ExtractionContext`
- Produces:
  - `Pipeline.run_from_html(html, *, rcept_no=None, use_fallback=None, corp_form=None) -> PipelineResult`
  - 순서: `extract_tables` → `locate_sections` → `extract_identification`로 `ctx.fs_scope`/`fiscal_year` 설정 → 나머지 추출기를 `StandardExtraction`에 대입 → `validate_accounts` (+ 있으면 `validate_hours`) → 실패하고 `use_fallback`이면 실패한 창만 SLM
  - 기존 `tests/test_pipeline.py`의 accounts mock는 그대로 통과
  - 새 스모크: min HTML에서 `fs_scope`, `accounts`(필요 시 `revenue`), `opinion`, `hours` 중 존재하는 필드가 `missing`이 아님

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py 에 추가
def test_run_from_html_fills_identification_before_accounts(mock_bs_html: str) -> None:
    html = "<p>주식회사 예시</p><p>감사보고서</p><p>제5기 2024.01.01부터 2024.12.31까지</p>" + mock_bs_html
    result = Pipeline().run_from_html(html, rcept_no="demo", use_fallback=False)
    assert result.extraction.fs_scope == "separate"
    assert result.extraction.company_name.value == "주식회사 예시"
    assert result.extraction.accounts.status.value == "found"
    assert result.extraction.subsidiary.subsidiary_status.value == "not_applicable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py::test_run_from_html_fills_identification_before_accounts -v`
Expected: FAIL (`fs_scope` still None 또는 `company_name` missing)

- [ ] **Step 3: Write minimal implementation**

`run_from_html` 본문을 추출기 호출 목록으로 교체. `_extract_accounts` 인라인 로직 삭제. fallback은 `validation.ok`가 아닐 때 `accounts` 표 마크다운만 전달 (문서 전체 금지).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest && python -m ruff check .`
Expected: 전 테스트 PASS, ruff clean

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/pipeline.py tests/test_pipeline.py tests/sample_htmls/mock_standard_min.html
git commit -m "feat: wire standard extractors into the pipeline in dependency order"
```

---

## Self-review

**Spec coverage**

| Spec item | Task |
| --- | --- |
| 회사명, 문서 제목, 기수, 보고기간=`current_period` | 2 |
| `auditor`, `opinion`, `gaap`, `audit_report_date` | 4 |
| `hours` 역할×지표×기간, `unmapped` | 5 |
| `activities` 절차 7개, 실사/조회 하위필드, 3절≠4절 | 6 |
| `communications` 위원회·회차, 옛 4절 `not_in_regime` | 7 |
| `accounts` 13계정(FS 10 + 매출·영업이익·순손익), Amount 4필드, 제N기 열, 손실 음수, 거부 과목 | 3 |
| `icfr` 같은 문서 leaf, 운영보고서 제외, F001/F002 게이트, 감사/검토 코드 | 8 |
| `going_concern` 1/0 + 제외 규칙 | 9 |
| `subsidiary` 연결 수, 관계·공동 제외, 별도 `not_applicable` | 10 |
| 주석 목차 제목만 | 11 |
| 파이프라인 조립, 상태 혼동 금지 | 1, 12 |
| 주석 본문·계정 전량·사업보고서·별지 5절·운영보고서 비추출 | 8, 11, Global Constraints |

**Out of this plan:** Open DART XBRL로 `accounts`를 채우는 클라이언트 연결. `extract_accounts` 시그니처는 Task 3에서 고정했으므로 별도 후속 작업으로 `source="xbrl"` 분기를 추가한다.
