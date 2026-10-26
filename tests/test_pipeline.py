from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.pipeline import Pipeline


def test_run_from_html_returns_schema_and_tables(mock_bs_html: str) -> None:
    result = Pipeline().run_from_html(mock_bs_html, rcept_no="demo", use_fallback=False)
    assert result.extraction.rcept_no == "demo"
    assert result.extraction.auditor.status is ExtractionStatus.missing
    assert len(result.tables) == 1
    assert result.tables[0].grid[2][0] == "자산총계"
    assert result.used_fallback is False
    assert result.validation.ok is True


def test_run_from_html_extracts_accounts_when_spec_matches(mock_bs_html: str) -> None:
    result = Pipeline().run_from_html(mock_bs_html, use_fallback=False)
    accounts = result.extraction.accounts
    assert accounts.status is ExtractionStatus.found
    assert accounts.value is not None
    assert accounts.value.total_asset is not None
    assert accounts.value.total_asset.current is not None
    assert accounts.value.total_asset.current.value == 1200.0
    assert accounts.value.total_asset.current.unit_scale == 1_000_000
    assert accounts.value.total_asset.current.value_won == 1_200_000_000.0
