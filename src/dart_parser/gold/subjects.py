"""표준 과제 채점 단위.

스냅샷은 ``StandardExtraction`` JSON이다. 루트의 ``extraction`` 또는
필드 자체를 읽는다. 1단계 채점 테스트의 v19 facts 행도 그대로 읽는다.
"""

from __future__ import annotations

import json
from typing import Any

from dart_parser.fallback.schemas import ACCOUNT_KEYS

ACCOUNTS: tuple[str, ...] = ACCOUNT_KEYS

TABLE_BUNDLES = frozenset({"hours", "activities", "communications"})

BUNDLE_KEYS: tuple[str, ...] = (
    "company_name",
    "document_title",
    "fiscal_term",
    "auditor",
    "opinion",
    "gaap",
    "audit_report_date",
    "current_period",
    "hours",
    "activities",
    "communications",
    "accounts",
    "icfr",
    "going_concern",
    "subsidiary",
    "notes_toc",
)

OPINION_VALUES: tuple[str, ...] = ("적정", "한정", "부적정", "거절")

_LEGACY_COLUMNS: dict[str, str] = {
    "auditor": "auditor_resolved",
    "opinion": "opinion_resolved",
    "gaap": "gaap_resolved",
    "audit_report_date": "audit_report_date",
    "current_period": "current_period_resolved",
    "going_concern": "going_concern",
    "subsidiary": "subsidiary_count",
}

_LEGACY_ICFR = {"engagement": "icfr_engagement", "opinion": "icfr_opinion_code"}


def subjects_for(bundle: str) -> list[str]:
    """묶음 하나의 채점 subject 목록."""
    if bundle == "icfr":
        return ["engagement", "opinion"]
    if bundle in TABLE_BUNDLES:
        return ["table"]
    if bundle == "accounts":
        return [
            f"{account}@{period}" for account in ACCOUNTS for period in ("current", "prior")
        ]
    if bundle not in BUNDLE_KEYS:
        raise KeyError(bundle)
    return ["value"]


def extraction_status(row: dict[str, Any], bundle: str) -> str | None:
    """StandardExtraction 상태. v19 행이면 None."""
    body = _body(row)
    if bundle == "icfr":
        block = body.get("icfr")
        if isinstance(block, dict) and "icfr_status" in block:
            return str(block["icfr_status"])
        return None
    if bundle == "subsidiary":
        block = body.get("subsidiary")
        if isinstance(block, dict) and "subsidiary_status" in block:
            return str(block["subsidiary_status"])
        return None
    status, _value = _item(body, bundle)
    return status


def extract_predicted(row: dict[str, Any], bundle: str, subject: str) -> Any:
    """스냅샷에서 채점에 쓰는 예측값을 꺼낸다."""
    body = _body(row)
    if bundle == "accounts":
        return _account(body, subject)
    if bundle in TABLE_BUNDLES and subject == "table":
        return _table(body, bundle)
    if bundle == "icfr":
        return _icfr(body, subject)
    if bundle == "subsidiary" and subject == "value":
        return _subsidiary(body)
    if bundle == "gaap" and subject == "value":
        return _gaap(body)
    if subject != "value" or bundle not in BUNDLE_KEYS:
        return None
    status, value = _item(body, bundle)
    if status == "found":
        return value
    if status is not None:
        return None
    return _legacy_scalar(body, bundle)


def _body(row: dict[str, Any]) -> dict[str, Any]:
    extraction = row.get("extraction")
    if isinstance(extraction, dict):
        return extraction
    return row


def _item(body: dict[str, Any], key: str) -> tuple[str | None, Any]:
    raw = body.get(key)
    if isinstance(raw, dict) and "status" in raw:
        status = raw.get("status")
        return (str(status) if status is not None else None, raw.get("value"))
    return None, None


def _account(body: dict[str, Any], subject: str) -> dict[str, Any] | None:
    account, _, period = subject.partition("@")
    status, value = _item(body, "accounts")
    if status == "found" and isinstance(value, dict):
        line = value.get(account)
        if not isinstance(line, dict):
            return None
        amount = line.get(period)
        if not isinstance(amount, dict):
            return None
        return {"value": amount.get("value"), "unit_scale": amount.get("unit_scale")}
    if status is not None:
        return None
    rows = _parse_json(body.get("accounts")) or []
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


def _table(body: dict[str, Any], bundle: str) -> Any:
    status, value = _item(body, bundle)
    if status == "found":
        if bundle == "hours" and isinstance(value, dict):
            return value.get("cells")
        return value
    if status is not None:
        return None
    return _parse_json(body.get(bundle))


def _icfr(body: dict[str, Any], subject: str) -> Any:
    block = body.get("icfr")
    if isinstance(block, dict) and "icfr_status" in block:
        if block.get("icfr_status") != "found":
            return None
        if subject == "engagement":
            return _blank(block.get("icfr_engagement"))
        if subject == "opinion":
            return _blank(block.get("icfr_opinion_code"))
        return None
    column = _LEGACY_ICFR.get(subject)
    if column is None:
        return None
    return _blank(body.get(column))


def _subsidiary(body: dict[str, Any]) -> Any:
    block = body.get("subsidiary")
    if isinstance(block, dict) and "subsidiary_status" in block:
        if block.get("subsidiary_status") != "found":
            return None
        return block.get("subsidiary_count")
    value = _blank(body.get("subsidiary_count"))
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return value


def _gaap(body: dict[str, Any]) -> Any:
    status, value = _item(body, "gaap")
    if status == "found" and isinstance(value, dict):
        return value.get("code")
    if status is not None:
        return None
    return _blank(body.get("gaap_resolved"))


def _legacy_scalar(body: dict[str, Any], bundle: str) -> Any:
    column = _LEGACY_COLUMNS.get(bundle)
    if column is None:
        return None
    value = _blank(body.get(column))
    if value is None:
        return None
    if bundle in {"going_concern", "subsidiary"} and isinstance(value, str):
        token = value.strip()
        if token.lstrip("-").isdigit():
            return int(token)
    return value


def _blank(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value
