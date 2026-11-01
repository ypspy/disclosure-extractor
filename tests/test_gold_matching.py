"""필드별 정답 일치 규칙."""

from __future__ import annotations

from dart_parser.gold.matching import matches, normalize_amount


def test_auditor_normalized() -> None:
    assert matches("auditor", "value", "삼일 회계법인", "삼일회계법인")


def test_amount_display_unit_exact() -> None:
    predicted = {"raw": "(1,234)", "unit_raw": "천원", "value": -1234}
    assert matches(
        "accounts",
        "inventory@current",
        predicted,
        {"display": "-1234", "unit": "천원"},
    )
    assert not matches(
        "accounts",
        "inventory@current",
        predicted,
        {"display": "-1234", "unit": "원"},
    )
    assert not matches(
        "accounts",
        "inventory@current",
        predicted,
        {"display": "-1235", "unit": "천원"},
    )


def test_negative_parentheses() -> None:
    assert normalize_amount("(1,234)") == -1234
    assert normalize_amount("△1,234") == -1234


def test_table_uses_verdict_only() -> None:
    assert matches("hours", "table", [{"x": 1}], {"verdict": "correct"})
