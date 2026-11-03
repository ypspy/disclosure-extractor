"""표준 항목 채점 단위. 스냅샷은 StandardExtraction JSON이다."""

from __future__ import annotations

from dart_parser.gold.subjects import BUNDLE_KEYS, extract_predicted, subjects_for


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
