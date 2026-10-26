"""Numeric integrity checks on extracted amounts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from dart_parser.fallback.schemas import AccountLine, Accounts


@dataclass
class ValidationIssue:
    code: str
    message: str
    expected: float | None = None
    actual: float | None = None


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def _close(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def sums_to(
    parts: Sequence[float | None],
    total: float | None,
    *,
    tolerance: float = 1.0,
) -> bool:
    if total is None or any(part is None for part in parts):
        return False
    return _close(sum(float(part) for part in parts if part is not None), total, tolerance)


def accounting_equation(
    assets: float | None,
    liabilities: float | None,
    equity: float | None,
    *,
    tolerance: float = 1.0,
) -> bool:
    if assets is None or liabilities is None or equity is None:
        return False
    return _close(assets, liabilities + equity, tolerance)


def _line_value(line: AccountLine | None) -> float | None:
    if line is None or line.current is None:
        return None
    amount = line.current
    if amount.value_won is not None:
        return amount.value_won
    return amount.value


def validate_accounts(accounts: Accounts | None, *, tolerance: float = 1.0) -> ValidationResult:
    """Check 자산총계 = 부채총계 + 자본총계 when all three current values exist."""
    if accounts is None:
        return ValidationResult(ok=True)
    assets = _line_value(accounts.total_asset)
    liabilities = _line_value(accounts.total_liability)
    equity = _line_value(accounts.total_equity)
    if assets is None or liabilities is None or equity is None:
        return ValidationResult(ok=True)
    if accounting_equation(assets, liabilities, equity, tolerance=tolerance):
        return ValidationResult(ok=True)
    return ValidationResult(
        ok=False,
        issues=[
            ValidationIssue(
                code="accounting_equation",
                message="자산총계 != 부채총계 + 자본총계",
                expected=assets,
                actual=liabilities + equity,
            )
        ],
    )
