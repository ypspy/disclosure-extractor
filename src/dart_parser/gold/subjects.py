"""12개 필드 묶음의 채점 단위와 리뷰 subject 매핑."""

from __future__ import annotations

import json
from typing import Any

ACCOUNTS: tuple[str, ...] = (
    "total_asset",
    "total_equity",
    "net_income",
    "inventory",
    "receivable",
    "long_term_receivable",
    "contract_asset",
    "unbilled",
    "current_asset",
    "total_liability",
    "current_liability",
)

TABLE_BUNDLES = frozenset({"hours", "activities", "communications"})

_SCALAR_COLUMNS: dict[str, str] = {
    "auditor": "auditor_resolved",
    "opinion": "opinion_resolved",
    "gaap": "gaap_resolved",
    "audit_report_date": "audit_report_date",
    "current_period": "current_period_resolved",
    "going_concern": "going_concern",
    "subsidiary": "subsidiary_count",
}

_ICFR_COLUMNS = {"engagement": "icfr_engagement", "opinion": "icfr_opinion_code"}


def subjects_for(bundle: str) -> list[str]:
    """묶음 하나의 채점 subject 목록."""
    if bundle == "icfr":
        return ["engagement", "opinion"]
    if bundle in TABLE_BUNDLES:
        return ["table"]
    if bundle == "accounts":
        return [
            f"{account}@{period}"
            for account in ACCOUNTS
            for period in ("current", "prior")
        ]
    if bundle not in _SCALAR_COLUMNS:
        raise KeyError(bundle)
    return ["value"]


def _parse_json(value: Any) -> Any:
    """문자열이 JSON이면 풀고, 아니면 그대로 둔다."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _blank_to_none(value: Any) -> Any:
    """비어 있는 문자열은 값이 없는 것으로 본다."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def extract_predicted(fact_row: dict[str, Any], bundle: str, subject: str) -> Any:
    """스냅샷 또는 facts 행에서 채점할 예측값을 꺼낸다."""
    if bundle == "accounts":
        account, _, period = subject.partition("@")
        rows = _parse_json(fact_row.get("accounts")) or []
        if not isinstance(rows, list):
            return None
        for item in rows:
            if not isinstance(item, dict):
                continue
            if item.get("account") == account and item.get("period") == period:
                return {
                    "raw": item.get("raw"),
                    "unit_raw": item.get("unit_raw"),
                    "value": item.get("value"),
                }
        return None
    if bundle in TABLE_BUNDLES and subject == "table":
        return _parse_json(fact_row.get(bundle))
    if bundle == "icfr":
        column = _ICFR_COLUMNS.get(subject)
        if column is None:
            return None
        return _blank_to_none(fact_row.get(column))
    column = _SCALAR_COLUMNS.get(bundle)
    if column is None or subject != "value":
        return None
    value = _blank_to_none(fact_row.get(column))
    if value is None:
        return None
    if bundle in {"going_concern", "subsidiary"} and isinstance(value, str):
        token = value.strip()
        if token.lstrip("-").isdigit():
            return int(token)
    return value


def _review_map() -> dict[tuple[str, str], str]:
    """extraction_reviews.subject를 골드 subject로 옮기는 표."""
    mapping: dict[tuple[str, str], str] = {
        ("hours", "audit_current_total"): "table",
        ("activities", "audit_current_total"): "table",
        ("communications", "audit_current_total"): "table",
        ("subsidiary", "subsidiary_count"): "value",
        ("audit_report_date", "lag_days"): "value",
    }
    for account in ACCOUNTS:
        mapping[("accounts", account)] = f"{account}@current"
    return mapping


REVIEW_SUBJECT_MAP: dict[tuple[str, str], str] = _review_map()
