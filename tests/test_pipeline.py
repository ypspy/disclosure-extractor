from pathlib import Path

from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.pipeline import Pipeline

SAMPLE_DIR = Path(__file__).parent / "sample_htmls"


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


def test_run_from_html_fills_identification_before_accounts(mock_bs_html: str) -> None:
    html = (
        "<p>주식회사 예시</p><p>감사보고서</p>"
        "<p>제5기 2024.01.01부터 2024.12.31까지</p>" + mock_bs_html
    )
    result = Pipeline().run_from_html(html, rcept_no="demo", use_fallback=False)
    assert result.extraction.fs_scope == "separate"
    assert result.extraction.company_name.value == "주식회사 예시"
    assert result.extraction.accounts.status.value == "found"
    assert result.extraction.subsidiary.subsidiary_status.value == "not_applicable"


def test_missing_accounts_is_a_validation_failure() -> None:
    html = "<p>주식회사 예시</p><p>감사보고서</p><p>제5기 2024.01.01부터 2024.12.31까지</p>"
    result = Pipeline().run_from_html(html, use_fallback=False)
    assert result.extraction.accounts.status is ExtractionStatus.missing
    assert result.validation.ok is False
    assert any(issue.code == "accounts_missing" for issue in result.validation.issues)


def test_run_from_html_smoke_on_standard_min() -> None:
    html = (SAMPLE_DIR / "mock_standard_min.html").read_text(encoding="utf-8")
    result = Pipeline().run_from_html(html, rcept_no="min", use_fallback=False)
    ext = result.extraction
    assert ext.fs_scope == "separate"
    assert ext.accounts.status is not ExtractionStatus.missing
    assert ext.opinion.status is not ExtractionStatus.missing
    assert ext.hours.status is not ExtractionStatus.missing
    assert ext.activities.status is ExtractionStatus.found
    assert ext.communications.status is ExtractionStatus.found
    assert result.validation.ok is True
