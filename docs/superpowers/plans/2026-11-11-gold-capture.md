# Gold Capture Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 루프백 문서 화면에서 고른 공시 태그 글자를 골드 칸의 값으로 저장한다.

**Architecture:** 클릭 글자의 변환은 `capture.py` 한 곳에 둔다. 저장은 `gold_captures`와 `gold_capture_units`만 쓰고 `gold_labels`는 호출하지 않는다. 문서 페이지는 캐시 HTML을 왼쪽 shadow root에 넣고, 오른쪽은 입수 단위별 빈 행이다. 검수 판정 라우트는 제거한다.

**Tech Stack:** Python 3.11+, SQLite, pytest, ruff, `html.parser`. 숫자는 `to_number`와 `Amount.from_cell`, 글자는 `normalize_text`.

## Global Constraints

- 명세: `docs/superpowers/specs/2026-11-11-gold-capture-design.md`
- 행이 없으면 입수 전이다. 상태는 `found`, `not_applicable`, `not_in_regime`만이다.
- 태그 글자가 비어 있거나, 선택된 행이 없거나, 값으로 읽을 수 없으면 저장하지 않는다.
- 금액 단위를 고르기 전에는 금액 클릭을 저장하지 않는다. 허용 배수는 `1`, `1000`, `1000000`, `100000000`이다.
- 단위를 바꾸면 그 묶음에 이미 있는 금액의 `value`는 그대로 두고 `unit_scale`과 `value_won`만 다시 계산한다.
- 재무상태표 계정은 `total_asset`, `current_asset`, `inventory`, `receivable`, `long_term_receivable`, `contract_asset`, `unbilled`, `total_liability`, `current_liability`, `total_equity`이다. 손익계산서는 `revenue`, `operating_income`, `net_income`이다.
- 감사시간 subject는 `{role_key}|{metric_key}|current` 또는 `prior`다. 키는 `lexicon.py`의 `HOUR_ROLE_ALIASES`, `HOUR_METRIC_ALIASES`다. 격자에 없는 행은 만들지 않는다.
- 서버는 루프백에서만 받는다. 네트워크와 LLM 호출을 넣지 않는다.
- 작업 트리에 커밋되지 않은 검수 화면 수정이 있다. 구현에 넣지 않는다.
- 작업 끝에 `python -m pytest`와 `ruff check .`를 통과시킨다.

---

### Task 1: 클릭 글자 변환

**Files:**
- Create: `src/dart_parser/gold/capture.py`
- Test: `tests/test_gold_capture_parse.py`

**Interfaces:**
- Consumes: `Amount.from_cell`, `to_number`, `normalize_text`, `going_concern_value`, `HOUR_ROLE_ALIASES`, `HOUR_METRIC_ALIASES`, `ACCOUNT_KEYS`
- Produces:
  - `parse_click(bundle: str, subject: str, text: str, *, unit_scale: int | None = None, icfr_engagement: str | None = None) -> Any | None`
  - `money_group(bundle: str, subject: str) -> Literal["bs", "is"] | None`
  - `capture_rows() -> tuple[CaptureRow, ...]`
  - `CaptureRow` fields: `group: str`, `bundle: str`, `subject: str`, `label: str`
  - `known_subject(bundle: str, subject: str) -> bool`

`parse_click`이 `None`이면 저장하지 않는다. 반환값은 JSON으로 넣을 값이다.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_capture_parse.py`를 만든다.

```python
"""클릭한 글자가 골드 값으로 바뀌는지."""

from __future__ import annotations

from dart_parser.gold.capture import capture_rows, known_subject, money_group, parse_click
from dart_parser.parser.lexicon import HOUR_METRIC_ALIASES, HOUR_ROLE_ALIASES


def test_amount_uses_the_chosen_scale_and_to_number() -> None:
    parsed = parse_click(
        "accounts", "total_asset@current", "19,506", unit_scale=1_000_000
    )
    assert parsed == {
        "raw": "19,506",
        "value": 19506.0,
        "unit_scale": 1_000_000,
        "value_won": 19_506_000_000.0,
    }
    assert parse_click("accounts", "operating_income@current", "△1,234", unit_scale=1)["value"] == -1234.0
    assert parse_click("accounts", "revenue@current", "19,506", unit_scale=None) is None
    assert parse_click("accounts", "revenue@current", "없음", unit_scale=1) is None
    assert parse_click("accounts", "revenue@current", "  ", unit_scale=1) is None


def test_money_groups_follow_the_statement() -> None:
    assert money_group("accounts", "total_equity@prior") == "bs"
    assert money_group("accounts", "net_income@current") == "is"
    assert money_group("hours", "eqcr|headcount|current") is None


def test_opinion_gaap_and_title_take_one_phrase() -> None:
    assert parse_click("opinion", "value", "한정의견을 표명한다") == "한정"
    assert parse_click("opinion", "value", "부적정의견") == "부적정"
    assert parse_click("opinion", "value", "적정 또는 한정") is None
    assert parse_click("gaap", "value", "K-IFRS를 적용") == "K-IFRS"
    assert parse_click("gaap", "value", "K-IFRS와 K-GAAP") is None
    assert parse_click("document_title", "value", "연결감사보고서") == "연결감사보고서"
    assert parse_click("document_title", "value", "감사보고서") == "감사보고서"


def test_dates_period_and_counts() -> None:
    assert parse_click("audit_report_date", "value", "2017년 3월 31일") == "2017-03-31"
    assert parse_click("audit_report_date", "value", "2017-03-31 및 2016-03-31") is None
    assert parse_click("current_period", "value", "2016.1.1부터 2016.12.31까지") == {
        "start": "2016-01-01",
        "end": "2016-12-31",
    }
    assert parse_click("hours", "eqcr|headcount|current", "1 명") == 1.0
    assert parse_click("subsidiary", "value", "12") == 12.0
    assert parse_click("hours", "nope|headcount|current", "1") is None


def test_icfr_needs_one_engagement_before_an_opinion() -> None:
    assert parse_click("icfr", "engagement", "내부회계관리제도 감사") == "audit"
    assert parse_click("icfr", "engagement", "감사 및 검토") is None
    assert parse_click("icfr", "opinion", "중요한 취약점", icfr_engagement="review") == "중요한 취약점"
    assert parse_click("icfr", "opinion", "한정", icfr_engagement="audit") is None
    assert parse_click("icfr", "opinion", "적정", icfr_engagement=None) is None


def test_text_notes_communications_and_going_concern() -> None:
    assert parse_click("company_name", "value", " 케이에스피 ") == "케이에스피"
    assert parse_click("notes_toc", "value", "1. 일반사항") == "1. 일반사항"
    assert parse_click("communications", "has_audit_committee", "감사위원회가 있음") is True
    assert parse_click("communications", "has_audit_committee", "있음과 없음") is None
    item = parse_click("communications", "items", "2017년 3월 2일 1회차")
    assert item["raw"] == "2017년 3월 2일 1회차"
    assert item["date"] == "2017-03-02"
    assert parse_click("going_concern", "value", "계속기업의 중요한 불확실성이 있다") == 1
    assert parse_click("going_concern", "value", "전기 감사보고서를 인용한다") == 0
    assert parse_click("activities", "inventory_observation.place", "본사 창고") == "본사 창고"


def test_rows_cover_each_capture_cell_once() -> None:
    rows = capture_rows()
    pairs = [(row.bundle, row.subject) for row in rows]
    assert len(pairs) == len(set(pairs))
    assert ("accounts", "total_asset@current") in pairs
    assert ("accounts", "revenue@prior") in pairs
    assert sum(1 for bundle, _subject in pairs if bundle == "hours") == (
        len(HOUR_ROLE_ALIASES) * len(HOUR_METRIC_ALIASES) * 2
    )
    assert known_subject("accounts", "total_asset@current")
    assert not known_subject("accounts", "table")
    assert {row.group for row in rows if row.bundle == "accounts"} == {"재무상태표", "손익계산서"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_capture_parse.py -q`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `dart_parser.gold.capture`.

- [ ] **Step 3: Write minimal implementation**

`src/dart_parser/gold/capture.py`를 만든다. 구문은 긴 것부터 차지하고, `부적정` 안의 `적정`은 두 번째 값으로 세지 않는다.

```python
"""클릭한 공시 글자를 골드 칸 값으로 바꾼다."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Literal

from dart_parser.fallback.schemas import ACCOUNT_KEYS, Amount
from dart_parser.gold.subjects import going_concern_value
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.numeric import to_number
from dart_parser.parser.lexicon import HOUR_METRIC_ALIASES, HOUR_ROLE_ALIASES

BS_ACCOUNTS: tuple[str, ...] = ACCOUNT_KEYS[:10]
IS_ACCOUNTS: tuple[str, ...] = ACCOUNT_KEYS[10:]
SCALES = frozenset({1, 1000, 1_000_000, 100_000_000})
_OPINIONS = ("부적정", "한정", "거절", "적정")
_GAAP = ("K-IFRS", "K-GAAP")
_DATE_RE = re.compile(r"(\d{4})\s*(?:년|[.\-])\s*(\d{1,2})\s*(?:월|[.\-])\s*(\d{1,2})\s*일?")
_ACTIVITY_SUBJECTS = (
    "planning",
    "fieldwork",
    "tcwg_communication",
    "expert",
    "inventory_observation.date",
    "inventory_observation.place",
    "inventory_observation.target",
    "financial_asset_observation.date",
    "financial_asset_observation.place",
    "financial_asset_observation.target",
    "external_confirmations.financial",
    "external_confirmations.receivables_payables",
    "external_confirmations.legal",
    "external_confirmations.other",
)
_ACTIVITY_LABELS = {
    "planning": "전반감사계획",
    "fieldwork": "현장감사",
    "tcwg_communication": "지배기구와의 커뮤니케이션",
    "expert": "외부전문가",
    "inventory_observation.date": "재고자산 실사 · 시기",
    "inventory_observation.place": "재고자산 실사 · 장소",
    "inventory_observation.target": "재고자산 실사 · 대상",
    "financial_asset_observation.date": "금융자산 실사 · 시기",
    "financial_asset_observation.place": "금융자산 실사 · 장소",
    "financial_asset_observation.target": "금융자산 실사 · 대상",
    "external_confirmations.financial": "외부조회 · 금융거래",
    "external_confirmations.receivables_payables": "외부조회 · 채권채무",
    "external_confirmations.legal": "외부조회 · 변호사",
    "external_confirmations.other": "외부조회 · 기타",
}
_ACCOUNT_LABELS = {
    "total_asset": "자산총계",
    "current_asset": "유동자산",
    "inventory": "재고",
    "receivable": "매출채권",
    "long_term_receivable": "장기매출채권",
    "contract_asset": "계약자산",
    "unbilled": "미청구공사",
    "total_liability": "부채총계",
    "current_liability": "유동부채",
    "total_equity": "자본총계",
    "revenue": "매출액",
    "operating_income": "영업이익",
    "net_income": "당기순손익",
}
_COVER = (
    ("company_name", "회사명"),
    ("document_title", "문서 제목"),
    ("fiscal_term", "기수"),
    ("auditor", "감사인"),
    ("opinion", "감사의견"),
    ("gaap", "회계기준"),
    ("audit_report_date", "감사보고서일"),
    ("current_period", "보고기간"),
)


@dataclass(frozen=True)
class CaptureRow:
    group: str
    bundle: str
    subject: str
    label: str


def money_group(bundle: str, subject: str) -> Literal["bs", "is"] | None:
    account, separator, period = subject.partition("@")
    if bundle != "accounts" or separator != "@" or period not in {"current", "prior"}:
        return None
    if account in BS_ACCOUNTS:
        return "bs"
    if account in IS_ACCOUNTS:
        return "is"
    return None


def known_subject(bundle: str, subject: str) -> bool:
    return any(row.bundle == bundle and row.subject == subject for row in capture_rows())


def capture_rows() -> tuple[CaptureRow, ...]:
    rows: list[CaptureRow] = [
        CaptureRow("표지", bundle, "value", label) for bundle, label in _COVER
    ]
    for account in BS_ACCOUNTS:
        for period, when in (("current", "당기"), ("prior", "전기")):
            rows.append(
                CaptureRow(
                    "재무상태표",
                    "accounts",
                    f"{account}@{period}",
                    f"{_ACCOUNT_LABELS[account]} · {when}",
                )
            )
    for account in IS_ACCOUNTS:
        for period, when in (("current", "당기"), ("prior", "전기")):
            rows.append(
                CaptureRow(
                    "손익계산서",
                    "accounts",
                    f"{account}@{period}",
                    f"{_ACCOUNT_LABELS[account]} · {when}",
                )
            )
    for role, role_names in HOUR_ROLE_ALIASES.items():
        for metric, metric_names in HOUR_METRIC_ALIASES.items():
            for period, when in (("current", "당기"), ("prior", "전기")):
                rows.append(
                    CaptureRow(
                        "감사시간",
                        "hours",
                        f"{role}|{metric}|{period}",
                        f"{role_names[0]} · {metric_names[0]} · {when}",
                    )
                )
    rows.extend(
        CaptureRow("실시내용", "activities", subject, label)
        for subject, label in _ACTIVITY_LABELS.items()
    )
    rows.append(CaptureRow("커뮤니케이션", "communications", "has_audit_committee", "감사위원회"))
    rows.append(CaptureRow("커뮤니케이션", "communications", "items", "회차"))
    rows.append(CaptureRow("나머지", "icfr", "engagement", "내부회계 업무"))
    rows.append(CaptureRow("나머지", "icfr", "opinion", "내부회계 의견"))
    rows.append(CaptureRow("나머지", "going_concern", "value", "계속기업"))
    rows.append(CaptureRow("나머지", "subsidiary", "value", "종속기업 수"))
    rows.append(CaptureRow("나머지", "notes_toc", "value", "주석 목차"))
    return tuple(rows)


def parse_click(
    bundle: str,
    subject: str,
    text: str,
    *,
    unit_scale: int | None = None,
    icfr_engagement: str | None = None,
) -> Any | None:
    cleaned = normalize_text(text)
    if not cleaned or not known_subject(bundle, subject):
        return None
    if bundle == "accounts":
        return _amount(text, unit_scale)
    if bundle in {"hours", "subsidiary"}:
        return to_number(text)
    if bundle == "opinion":
        return _one(_hits(cleaned, _OPINIONS))
    if bundle == "gaap":
        return _one(_hits(cleaned, _GAAP))
    if bundle == "document_title":
        if "연결감사보고서" in cleaned:
            return "연결감사보고서"
        if "감사보고서" in cleaned:
            return "감사보고서"
        return None
    if bundle == "audit_report_date":
        return _one(_dates(cleaned))
    if bundle == "current_period":
        found = _dates(cleaned)
        if len(found) != 2:
            return None
        return {"start": found[0], "end": found[1]}
    if bundle == "icfr" and subject == "engagement":
        found = _hits(cleaned, ("검토", "감사"))
        chosen = _one(found)
        return {"감사": "audit", "검토": "review"}.get(chosen or "")
    if bundle == "icfr" and subject == "opinion":
        allowed = {
            "audit": ("부적정", "거절", "적정"),
            "review": ("중요한 취약점", "한정", "거절", "적정"),
        }.get(icfr_engagement or "")
        if allowed is None:
            return None
        return _one(_hits(cleaned, allowed))
    if bundle == "communications" and subject == "has_audit_committee":
        chosen = _one(_hits(cleaned, ("있음", "없음")))
        if chosen == "있음":
            return True
        if chosen == "없음":
            return False
        return None
    if bundle == "communications" and subject == "items":
        found = _dates(cleaned)
        item: dict[str, Any] = {"raw": cleaned}
        if len(found) == 1:
            item["date"] = found[0]
        return item
    if bundle == "going_concern":
        return going_concern_value(text)
    if bundle == "notes_toc" or bundle in {"company_name", "fiscal_term", "auditor", "activities"}:
        return cleaned
    return None


def _amount(text: str, unit_scale: int | None) -> dict[str, Any] | None:
    if unit_scale not in SCALES:
        return None
    amount = Amount.from_cell(text, unit_scale)
    if amount.value is None:
        return None
    return {
        "raw": amount.raw,
        "value": amount.value,
        "unit_scale": amount.unit_scale,
        "value_won": amount.value_won,
    }


def _dates(text: str) -> list[str]:
    found: list[str] = []
    for year, month, day in _DATE_RE.findall(text):
        try:
            parsed = dt.date(int(year), int(month), int(day))
        except ValueError:
            continue
        found.append(parsed.isoformat())
    return found


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    occupied = [False] * len(text)
    hits: list[str] = []
    for phrase in sorted(phrases, key=len, reverse=True):
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            span = range(index, index + len(phrase))
            if not any(occupied[pos] for pos in span):
                for pos in span:
                    occupied[pos] = True
                hits.append(phrase)
            start = index + len(phrase)
    return hits


def _one(found: list[str]) -> str | None:
    if len(found) != 1:
        return None
    return found[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_capture_parse.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/gold/capture.py tests/test_gold_capture_parse.py
git commit -m "feat: parse a clicked disclosure tag into a gold value"
```

---

### Task 2: 입수 저장

**Files:**
- Modify: `src/dart_parser/gold/schema.py` (네 번째 마이그레이션을 `MIGRATIONS` 끝에 추가)
- Modify: `tests/test_gold_db.py` (`test_migrate_creates_tables`의 테이블 집합에 두 테이블 추가)
- Create: `src/dart_parser/gold/capture_store.py`
- Test: `tests/test_gold_capture_store.py`

**Interfaces:**
- Consumes: `parse_click`, `money_group`, `known_subject` from Task 1. `migrate`, `open_gold`.
- Produces:
  - `save_capture(conn, rcept_no: str, dcm_no: str, bundle: str, subject: str, text: str) -> bool`
  - `set_capture_status(conn, rcept_no: str, dcm_no: str, bundle: str, subject: str, status: str) -> bool` — `not_applicable` 또는 `not_in_regime`
  - `clear_capture(conn, rcept_no: str, dcm_no: str, bundle: str, subject: str) -> None`
  - `set_unit(conn, rcept_no: str, dcm_no: str, unit_group: str, unit_scale: int) -> bool`
  - `load_captures(conn, rcept_no: str, dcm_no: str) -> dict[tuple[str, str], sqlite3.Row]`
  - `load_units(conn, rcept_no: str, dcm_no: str) -> dict[str, int]`

`save_capture`는 `parse_click`이 `None`이면 `False`이고 행을 만들지 않는다. 성공하면 `True`. `notes_toc`/`value`와 `communications`/`items`는 덮어쓰지 않고 배열에 붙인다. 회차 `round`는 1부터다.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_capture_store.py`를 만든다.

```python
"""입수 행은 gold_captures에만 쌓인다."""

from __future__ import annotations

import json

from dart_parser.gold.capture_store import (
    clear_capture,
    load_captures,
    load_units,
    save_capture,
    set_capture_status,
    set_unit,
)
from dart_parser.gold.db import migrate, open_gold


def _conn(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    return conn


def test_click_stores_an_amount_and_ignores_an_unreadable_cell(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert set_unit(conn, "R", "D", "bs", 1_000_000)
    assert save_capture(conn, "R", "D", "accounts", "total_asset@current", "19,506")
    assert not save_capture(conn, "R", "D", "accounts", "current_asset@current", "없음")
    row = load_captures(conn, "R", "D")[("accounts", "total_asset@current")]
    assert row["status"] == "found"
    assert json.loads(row["value"])["value_won"] == 19_506_000_000.0
    assert row["evidence"] == "19,506"
    assert ("accounts", "current_asset@current") not in load_captures(conn, "R", "D")
    assert conn.execute("SELECT count(*) FROM gold_labels").fetchone()[0] == 0


def test_amount_click_before_a_unit_does_not_insert(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert not save_capture(conn, "R", "D", "accounts", "revenue@current", "10")
    assert load_captures(conn, "R", "D") == {}


def test_changing_the_unit_recomputes_only_scale_and_won(tmp_path) -> None:
    conn = _conn(tmp_path)
    set_unit(conn, "R", "D", "is", 1_000)
    save_capture(conn, "R", "D", "accounts", "revenue@current", "10")
    set_unit(conn, "R", "D", "bs", 1)
    save_capture(conn, "R", "D", "accounts", "total_asset@current", "5")
    assert set_unit(conn, "R", "D", "is", 1_000_000)
    revenue = json.loads(load_captures(conn, "R", "D")[("accounts", "revenue@current")]["value"])
    asset = json.loads(load_captures(conn, "R", "D")[("accounts", "total_asset@current")]["value"])
    assert revenue["value"] == 10.0
    assert revenue["unit_scale"] == 1_000_000
    assert revenue["value_won"] == 10_000_000.0
    assert asset["unit_scale"] == 1
    assert load_units(conn, "R", "D") == {"is": 1_000_000, "bs": 1}


def test_absent_status_and_clear(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert set_capture_status(conn, "R", "D", "subsidiary", "value", "not_applicable")
    row = load_captures(conn, "R", "D")[("subsidiary", "value")]
    assert row["status"] == "not_applicable"
    assert row["value"] is None
    clear_capture(conn, "R", "D", "subsidiary", "value")
    assert load_captures(conn, "R", "D") == {}
    assert not set_capture_status(conn, "R", "D", "subsidiary", "value", "found")


def test_notes_and_rounds_append(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "notes_toc", "value", "일반사항")
    save_capture(conn, "R", "D", "notes_toc", "value", "재고자산")
    notes = json.loads(load_captures(conn, "R", "D")[("notes_toc", "value")]["value"])
    assert notes == {"count": 2, "titles": ["일반사항", "재고자산"]}
    save_capture(conn, "R", "D", "communications", "items", "2017년 3월 2일 회의")
    save_capture(conn, "R", "D", "communications", "items", "둘째 회의")
    items = json.loads(load_captures(conn, "R", "D")[("communications", "items")]["value"])
    assert [item["round"] for item in items] == [1, 2]
    assert items[0]["date"] == "2017-03-02"
```

`tests/test_gold_db.py`의 기대 테이블 집합에 `"gold_captures"`와 `"gold_capture_units"`를 넣는다.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_capture_store.py -q`

Expected: FAIL with `ImportError` for `dart_parser.gold.capture_store`.

- [ ] **Step 3: Write minimal implementation**

`schema.py`의 `MIGRATIONS` 끝에 이 DDL 문자열을 추가한다.

```python
"""
CREATE TABLE gold_captures (
    rcept_no VARCHAR(32) NOT NULL,
    dcm_no VARCHAR(32) NOT NULL,
    bundle VARCHAR(32) NOT NULL,
    subject VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    value TEXT,
    evidence TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (rcept_no, dcm_no, bundle, subject)
);

CREATE TABLE gold_capture_units (
    rcept_no VARCHAR(32) NOT NULL,
    dcm_no VARCHAR(32) NOT NULL,
    unit_group VARCHAR(8) NOT NULL,
    unit_scale INTEGER NOT NULL,
    PRIMARY KEY (rcept_no, dcm_no, unit_group)
);
""",
```

`src/dart_parser/gold/capture_store.py`:

```python
"""gold_captures 읽기·쓰기. gold_labels는 쓰지 않는다."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
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
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_capture_store.py tests/test_gold_db.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/gold/schema.py src/dart_parser/gold/capture_store.py tests/test_gold_capture_store.py tests/test_gold_db.py
git commit -m "feat: store gold capture cells apart from review labels"
```

---

### Task 3: 공시 HTML에서 스크립트 제거

**Files:**
- Create: `src/dart_parser/gold/capture_html.py`
- Test: `tests/test_gold_capture_html.py`

**Interfaces:**
- Consumes: 없음
- Produces: `prepare_disclosure_html(page: str) -> str`

스크립트 태그와 그 내용, `iframe`, `on`으로 시작하는 속성을 뺀다. `style`과 표 태그는 남긴다.

- [ ] **Step 1: Write the failing test**

```python
"""공시 HTML은 보이되 스크립트는 실행되지 않게 정리한다."""

from dart_parser.gold.capture_html import prepare_disclosure_html


def test_prepare_disclosure_html_strips_script_iframe_and_handlers() -> None:
    page = (
        "<style>td{text-align:right}</style>"
        "<table><tr><td onclick=\"alert(1)\" align=\"right\">19,506</td></tr></table>"
        "<script>alert(1)</script>"
        "<iframe src=\"https://example.test\"></iframe>"
    )
    cleaned = prepare_disclosure_html(page)
    assert "19,506" in cleaned
    assert "<style>" in cleaned
    assert "alert(1)" not in cleaned
    assert "<iframe" not in cleaned.lower()
    assert "onclick" not in cleaned.lower()
    assert "align=" in cleaned
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_capture_html.py -q`

Expected: FAIL with `ImportError` for `dart_parser.gold.capture_html`.

- [ ] **Step 3: Write minimal implementation**

```python
"""공시 HTML을 왼쪽 영역에 넣기 전에 실행 요소를 뺀다."""

from __future__ import annotations

import html
from html.parser import HTMLParser

_DROP = frozenset({"script", "iframe"})


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=True)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _DROP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&#{name};")

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> None:
        name = tag.lower()
        if name in _DROP:
            if not close:
                self._skip += 1
            return
        if self._skip:
            return
        chunks = [f"<{tag}"]
        for key, value in attrs:
            if key.lower().startswith("on"):
                continue
            if value is None:
                chunks.append(f" {key}")
            else:
                chunks.append(f' {key}="{html.escape(value, quote=True)}"')
        chunks.append(" />" if close else ">")
        self.parts.append("".join(chunks))


def prepare_disclosure_html(page: str) -> str:
    parser = _Clean()
    parser.feed(page)
    parser.close()
    return "".join(parser.parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_capture_html.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/gold/capture_html.py tests/test_gold_capture_html.py
git commit -m "feat: strip scripts from disclosure HTML before display"
```

---

### Task 4: 입수 화면으로 교체

**Files:**
- Create: `src/dart_parser/gold/capture_page.py`
- Create: `tests/test_gold_capture_app.py`
- Modify: `src/dart_parser/gold/app.py` (HEAD 버전. 커밋되지 않은 검수 화면 diff는 먼저 버린다)
- Modify: `tests/test_gold_app.py` (HEAD 버전에서 문서 페이지가 판정 폼과 iframe을 기대하는 테스트를 입수 화면 기준으로 고친다)
- Delete: `tests/test_gold_review_judge.py`

**Interfaces:**
- Consumes: Task 1의 `capture_rows`, Task 2의 저장 함수, Task 3의 `prepare_disclosure_html`, 기존 `ReviewStore.load_source`의 섹션 읽기, `_host_allowed`, `_origin_allowed`, `_token_ok`, `_form_body`, `_safe_id`
- Produces: `GET /doc/{rcept_no}/{dcm_no}` 입수 페이지. `POST /doc/{rcept_no}/{dcm_no}/capture`. `POST /doc/{rcept_no}/{dcm_no}/unit`. `/source`와 `/label`은 404다.

시작 전에 검수 화면의 미커밋 수정을 버린다.

```bash
git checkout -- src/dart_parser/gold/app.py src/dart_parser/gold/evidence.py src/dart_parser/gold/subjects.py tests/test_gold_app.py tests/test_gold_standard_subjects.py
```

`docs/cursor-prompt-sanction-agenda.md`는 이 작업 파일이 아니므로 그대로 둔다.

- [ ] **Step 1: Write the failing test**

`tests/test_gold_capture_app.py`를 만든다. `_build`는 `tests/test_gold_app.py`의 표본 삽입을 따라 `ReviewApplication`을 만들고, 캐시에 아래 HTML을 쓴다.

```python
def test_document_page_is_capture_without_an_iframe(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _write_cache(
        tmp_path,
        "<script>alert(1)</script><iframe src=\"x\"></iframe><td id=\"n\">19,506</td>",
    )
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "<iframe" not in page.lower()
    assert "alert(1)" not in page
    assert "19,506" in page
    assert "자산총계 · 당기" in page
    assert "R100" in page and "D100" in page
    assert 'name="verdict"' not in page
    app.close()


def test_click_saves_when_a_row_and_unit_are_chosen(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(app, "/doc/R100/D100/unit", {"unit_group": "bs", "unit_scale": "1000000"})
    status, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "accounts",
            "subject": "total_asset@current",
            "text": "19,506",
        },
    )
    assert status.startswith("303")
    row = _capture(tmp_path, "accounts", "total_asset@current")
    assert json.loads(row["value"])["unit_scale"] == 1_000_000
    missed, headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "accounts", "subject": "current_asset@current", "text": "없음"},
    )
    assert missed.startswith("303")
    assert "miss_subject=current_asset%40current" in headers["Location"]
    assert _capture(tmp_path, "accounts", "current_asset@current") is None
    location = headers["Location"]
    path, _, query = location.partition("?")
    _status, _headers, again = _request(app, "GET", path, query)
    assert "읽을 수 없습니다" in again.decode()
    app.close()


def test_absent_clear_and_rejected_requests(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "subsidiary", "subject": "value", "status": "not_applicable"},
    )
    assert _capture(tmp_path, "subsidiary", "value")["status"] == "not_applicable"
    _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "subsidiary", "subject": "value", "status": "clear"},
    )
    assert _capture(tmp_path, "subsidiary", "value") is None
    host, _headers, host_body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "company_name", "subject": "value", "text": "가나다"},
        host="evil.test:80",
    )
    assert host.startswith("403")
    assert app.token not in host_body.decode()
    bad, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "accounts", "subject": "table", "text": "1"},
    )
    assert bad.startswith("400")
    missing, _headers, _body = _request(app, "GET", "/doc/R100/D100/source")
    assert missing.startswith("404")
    app.close()
```

`_post`는 페이지에서 읽은 `token` hidden 값을 폼에 넣고, `Content-Type`은 `application/x-www-form-urlencoded`로 한다. 호스트 기본값은 `localhost:80`이다. `_capture`는 `gold_captures`에서 `R100`/`D100`과 subject를 읽는다. 성공한 POST는 `303`과 `Location: /doc/R100/D100`이다.

`tests/test_gold_app.py`에서 판정 폼, `/label`, `/source` iframe을 기대하는 테스트는 지운다. 목록, 루프백 바인딩, CLI 인자 테스트는 남긴다.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gold_capture_app.py -q`

Expected: FAIL. `/unit`과 `/capture`가 없고, 문서 페이지에 자산총계 행이 없다.

- [ ] **Step 3: Write minimal implementation**

`capture_page.py`의 `render_capture_page(rcept_no, dcm_no, token, filing_html, rows, saved, units, company, report, filed) -> str`는 다음을 만든다.

- 위: 목록 링크, 회사명·보고서명, 제출일, 접수번호, 문서번호, `표시 {len(saved)}건`
- 왼쪽: `<div id="filing"></div>`. 공시 HTML은 `json.dumps(prepare_disclosure_html(filing_html))`로 스크립트에 넣고 shadow root의 `innerHTML`로만 넣는다.
- 그 스크립트는 shadow root의 클릭에서 `event.target`의 `textContent`를, 선택된 `form.row`의 `bundle`·`subject`와 함께 `POST /doc/{rcept}/{dcm}/capture`로 보낸다. 선택된 행이 없으면 보내지 않는다. 응답이 오면 페이지를 다시 연다.
- 오른쪽: `capture_rows()` 순서. 재무상태표 헤더의 단위 폼은 `unit_group=bs`, 손익계산서는 `is`. 저장된 배수가 있으면 그 옵션을 선택한다. 각 행은 버튼 세 개로 `status=not_applicable`, `not_in_regime`, `clear`를 같은 capture URL에 보낸다.
- 금액 행의 표시는 저장된 `value`와 단위 이름(1 원, 1000 천원, 1000000 백만원, 100000000 억원)이다. 주석 목차는 제목을 줄로 보여 준다. 회차는 `round`와 `raw`를 보여 준다.
- 페이지 문자열에 `<iframe`를 넣지 않는다.

`ReviewStore`에 `load_disclosure(rcept_no, dcm_no)`를 추가한다. 본문은 HEAD의 `load_source`와 같이 섹션 HTML을 이어 붙이되, `needles`와 `_anchor_text`는 호출하지 않고 이어 붙인 문자열을 `SourceDocument.html`에 넣는다.

`ReviewApplication.__call__`에서 `/label`과 `/source` 분기를 삭제한다. 같은 자리의 규칙은 이렇다.

- `POST /doc/{rcept}/{dcm}/capture`: 호스트·오리진·토큰이 실패하면 403이고 `gold_captures`에 쓰지 않는다. `status`가 `not_applicable` 또는 `not_in_regime`이면 `set_capture_status`. `clear`면 `clear_capture`. 아니면 `text`로 `save_capture`. 알 수 없는 subject는 400. 저장되면 303으로 문서 페이지. `save_capture`가 `False`이면 행을 만들지 않고 303으로 `/doc/{rcept}/{dcm}?miss_bundle={bundle}&miss_subject={subject}`에 간다. 페이지는 그 한 행에만 `읽을 수 없습니다`를 보여 준다.
- `POST /doc/{rcept}/{dcm}/unit`: 같은 검사 뒤 `set_unit`. 실패는 400, 성공은 303.
- `GET /doc/{rcept}/{dcm}`: 표본이 없으면 404. 있으면 `render_capture_page`.

카탈로그에서 회사명·보고서명·제출일을 읽는 쿼리는 `cat.disclosures`와 `cat.corps`다. 쿼리가 실패하거나 행이 없으면 세 문자열은 빈 문자열이고, 제목은 `{rcept_no}/{dcm_no}`다.

HEAD의 `_forms`, `_subject_form`, `_answer_inputs`, `_field_table`, `_save`, `_gold_value`, `_write_label`, `_source`, `_anchor_text`, `_TextAnchor`는 삭제한다. `_host_allowed`, `_origin_allowed`, `_token_ok`, `_form_body`, `_list_page`는 남긴다.

`tests/test_gold_review_judge.py`는 삭제한다. 호스트·토큰·없는 subject 거부는 `test_gold_capture_app.py`가 대신한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gold_capture_app.py tests/test_gold_app.py -q`

Expected: PASS

그다음 전체다.

Run: `python -m pytest -q`

Expected: PASS

Run: `ruff check .`

Expected: 진단 없음

- [ ] **Step 5: Commit**

```bash
git add src/dart_parser/gold/app.py src/dart_parser/gold/capture_page.py tests/test_gold_capture_app.py tests/test_gold_app.py
git add -u tests/test_gold_review_judge.py
git commit -m "feat: replace the gold review page with click capture"
```

`evidence.py`와 `subjects.py`는 이 태스크에서 고치지 않는다. checkout으로 되돌린 뒤 변경이 없으면 커밋에 넣지 않는다.
