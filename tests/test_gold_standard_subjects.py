"""표준 항목 채점 단위. 스냅샷은 StandardExtraction JSON이다."""

from __future__ import annotations

import pytest

from dart_parser.gold.subjects import (
    BUNDLE_KEYS,
    extract_predicted,
    going_concern_value,
    subjects_for,
)


def test_subject_count_matches_field_map() -> None:
    subjects = [(bundle, subject) for bundle in BUNDLE_KEYS for subject in subjects_for(bundle)]
    assert len(subjects) == 42
    assert ("company_name", "value") in subjects
    assert ("document_title", "value") in subjects
    assert ("fiscal_term", "value") in subjects
    assert ("notes_toc", "value") in subjects
    assert ("accounts", "revenue@current") in subjects
    assert ("accounts", "operating_income@prior") in subjects
    assert ("accounts", "revenue@prior") in subjects


def test_extract_account_keeps_display_value_and_scale() -> None:
    payload = {
        "extraction": {
            "accounts": {
                "status": "found",
                "value": {
                    "revenue": {
                        "current": {
                            "raw": "1,234",
                            "value": 1234,
                            "unit_scale": 1000,
                            "value_won": 1234000,
                        }
                    }
                },
            }
        }
    }
    assert extract_predicted(payload, "accounts", "revenue@current") == {
        "value": 1234,
        "unit_scale": 1000,
    }


def test_extract_notes_toc_is_the_whole_list() -> None:
    payload = {
        "notes_toc": {
            "status": "found",
            "value": {"count": 2, "titles": ["일반", "재고"]},
        }
    }
    assert extract_predicted(payload, "notes_toc", "value") == {
        "count": 2,
        "titles": ["일반", "재고"],
    }


def test_extract_opinion_and_icfr() -> None:
    payload = {
        "opinion": {"status": "found", "value": "한정"},
        "icfr": {
            "icfr_engagement": "review",
            "icfr_opinion_code": "한정",
            "icfr_status": "found",
        },
    }
    assert extract_predicted(payload, "opinion", "value") == "한정"
    assert extract_predicted(payload, "icfr", "opinion") == "한정"
    assert extract_predicted(payload, "icfr", "engagement") == "review"


def test_current_material_uncertainty_is_one() -> None:
    text = "강조사항 계속기업 가정에 중요한 불확실성이 존재합니다."
    assert going_concern_value(text) == 1


@pytest.mark.parametrize(
    "text",
    [
        "한정의 근거 계속기업 가정에 중요한 불확실성이 존재하나 공시하지 않았습니다.",
        "부적정의 근거 계속기업 가정에 중요한 불확실성이 존재하나 공시하지 않았습니다.",
        "거절의 근거 계속기업 가정에 중요한 불확실성이 존재하나 감사증거를 확보하지 못했습니다.",
    ],
)
def test_opinion_basis_only_is_zero(text: str) -> None:
    assert going_concern_value(text) == 0


def test_prior_period_citation_only_is_zero() -> None:
    text = "전기 감사보고서는 계속기업 가정에 중요한 불확실성이 있다고 기재하였습니다."
    assert going_concern_value(text) == 0


def test_current_uncertainty_that_mentions_prior_year_is_one() -> None:
    text = "계속기업 가정에 중요한 불확실성이 존재합니다. 이 상황은 전기부터 계속되었습니다."
    assert going_concern_value(text) == 1


def test_liquidation_emphasis_only_is_zero() -> None:
    text = "강조사항 청산기준에 따라 재무제표를 작성하였음을 강조합니다."
    assert going_concern_value(text) == 0


def test_current_uncertainty_outside_opinion_basis_is_one() -> None:
    text = (
        "강조사항 계속기업 가정에 중요한 불확실성이 존재합니다. "
        "한정의 근거 재고자산 실사가 제한되었습니다."
    )
    assert going_concern_value(text) == 1


def test_current_uncertainty_is_not_cleared_by_liquidation_word() -> None:
    text = (
        "강조사항 계속기업 가정에 중요한 불확실성이 존재합니다. "
        "청산기준은 적용하지 않았습니다."
    )
    assert going_concern_value(text) == 1
