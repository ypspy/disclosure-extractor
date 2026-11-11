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
