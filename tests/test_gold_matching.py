"""필드별 정답 일치 규칙."""

from __future__ import annotations

from dart_parser.gold.matching import matches, normalize_amount


def test_auditor_normalized() -> None:
    assert matches("auditor", "value", "삼일 회계법인", "삼일회계법인")


def test_amount_value_and_unit_scale() -> None:
    predicted = {"value": -1234, "unit_scale": 1000}
    assert matches(
        "accounts",
        "inventory@current",
        predicted,
        {"value": -1234, "unit_scale": 1000},
    )
    assert not matches(
        "accounts",
        "inventory@current",
        predicted,
        {"value": -1234, "unit_scale": 1},
    )
    assert not matches(
        "accounts",
        "inventory@current",
        predicted,
        {"value": -1235, "unit_scale": 1000},
    )


def test_opinion_qualified_matches() -> None:
    assert matches("opinion", "value", "한정", "한정")
    assert not matches("opinion", "value", "적정", "한정")


def test_negative_parentheses() -> None:
    assert normalize_amount("(1,234)") == -1234
    assert normalize_amount("△1,234") == -1234


def test_table_uses_verdict_only() -> None:
    assert matches("hours", "table", [{"x": 1}], {"verdict": "correct"})
