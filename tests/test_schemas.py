from dart_parser.fallback.schemas import (
    ACCOUNT_KEYS,
    ACTIVITY_KEYS,
    Amount,
    ExtractionStatus,
    Item,
    StandardExtraction,
    empty_standard,
)


def test_amount_from_cell_keeps_scale() -> None:
    amt = Amount.from_cell("1,200", unit_scale=1_000_000)
    assert amt.value == 1200.0
    assert amt.unit_scale == 1_000_000
    assert amt.value_won == 1_200_000_000.0
    assert amt.raw == "1,200"


def test_item_defaults_to_missing() -> None:
    item: Item[str] = Item()
    assert item.status is ExtractionStatus.missing
    assert item.value is None


def test_empty_standard_has_all_twelve_bundles() -> None:
    result = empty_standard(rcept_no="20240312000000")
    assert result.rcept_no == "20240312000000"
    assert result.auditor.status is ExtractionStatus.missing
    assert result.opinion.status is ExtractionStatus.missing
    assert result.gaap.status is ExtractionStatus.missing
    assert result.audit_report_date.status is ExtractionStatus.missing
    assert result.current_period.status is ExtractionStatus.missing
    assert result.hours.status is ExtractionStatus.missing
    assert result.activities.status is ExtractionStatus.missing
    assert result.communications.status is ExtractionStatus.missing
    assert result.accounts.status is ExtractionStatus.missing
    assert result.icfr.icfr_status is ExtractionStatus.missing
    assert result.going_concern.status is ExtractionStatus.missing
    assert result.subsidiary.subsidiary_status is ExtractionStatus.missing
    assert result.notes_toc.status is ExtractionStatus.missing


def test_standard_key_sets_match_docs() -> None:
    assert ACCOUNT_KEYS == (
        "total_asset",
        "current_asset",
        "inventory",
        "receivable",
        "long_term_receivable",
        "contract_asset",
        "unbilled",
        "total_liability",
        "current_liability",
        "total_equity",
        "revenue",
        "operating_income",
        "net_income",
    )
    assert ACTIVITY_KEYS == (
        "planning",
        "fieldwork",
        "inventory_observation",
        "financial_asset_observation",
        "external_confirmations",
        "tcwg_communication",
        "expert",
    )


def test_standard_extraction_roundtrip() -> None:
    payload = empty_standard().model_dump()
    again = StandardExtraction.model_validate(payload)
    assert again.company_name.status is ExtractionStatus.missing
