from dart_parser.fallback.schemas import AccountLine, Accounts, Amount
from dart_parser.validator.math_validator import (
    accounting_equation,
    sums_to,
    validate_accounts,
)


def test_sums_to_within_tolerance() -> None:
    assert sums_to([100.0, 200.0], 300.0)
    assert not sums_to([100.0, 200.0], 310.0, tolerance=1.0)


def test_accounting_equation() -> None:
    assert accounting_equation(1_200, 700, 500)
    assert not accounting_equation(1_200, 700, 400)


def test_validate_accounts_flags_imbalance() -> None:
    accounts = Accounts(
        total_asset=AccountLine(current=Amount(raw="100", value=100, unit_scale=1, value_won=100)),
        total_liability=AccountLine(current=Amount(raw="40", value=40, unit_scale=1, value_won=40)),
        total_equity=AccountLine(current=Amount(raw="50", value=50, unit_scale=1, value_won=50)),
    )
    result = validate_accounts(accounts)
    assert result.ok is False
    assert any(issue.code == "accounting_equation" for issue in result.issues)


def test_validate_accounts_skips_when_incomplete() -> None:
    result = validate_accounts(None)
    assert result.ok is True
    assert result.issues == []
