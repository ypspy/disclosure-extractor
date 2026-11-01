"""사람 정답과 추출값의 일치 규칙."""

from __future__ import annotations

import re
from typing import Any

from dart_parser.gold.subjects import TABLE_BUNDLES

_AUDITOR_TOKENS = ("주식회사", "회계법인", "(주)", "㈜")


def normalize_auditor(value: str) -> str:
    """공백·괄호·법인 표기를 뺀 감사인 이름."""
    text = re.sub(r"\s+", "", (value or "").casefold())
    for token in _AUDITOR_TOKENS:
        text = text.replace(token.casefold(), "")
    return re.sub(r"[()（）\[\]\"']", "", text)


def normalize_amount(raw: str | None) -> int | None:
    """괄호·삼각 기호·쉼표를 반영한 표시 금액. 해석할 수 없으면 None."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    negative = False
    if len(text) >= 2 and text[0] in "(（" and text[-1] in ")）":
        negative = True
        text = text[1:-1]
    if text.startswith(("△", "▲", "-", "−")):
        negative = True
        text = text[1:]
    if not re.fullmatch(r"\d+", text):
        return None
    number = int(text)
    if negative:
        return -number
    return number


def matches(bundle: str, subject: str, predicted: Any, gold_value: Any) -> bool:
    """예측값이 골드 정답과 같은지. 계정은 표시값과 단위 배수가 둘 다 같아야 한다."""
    del subject
    if bundle in TABLE_BUNDLES:
        if not isinstance(gold_value, dict):
            return False
        return gold_value.get("verdict") == "correct"
    if bundle == "accounts":
        if not isinstance(predicted, dict) or not isinstance(gold_value, dict):
            return False
        return predicted.get("value") == gold_value.get("value") and predicted.get(
            "unit_scale"
        ) == gold_value.get("unit_scale")
    if bundle == "auditor":
        if predicted is None or gold_value is None:
            return False
        return normalize_auditor(str(predicted)) == normalize_auditor(str(gold_value))
    if bundle == "audit_report_date":
        if not predicted or not gold_value:
            return False
        return str(predicted)[:10] == str(gold_value)[:10]
    return predicted == gold_value
