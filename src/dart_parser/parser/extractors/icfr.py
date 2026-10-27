"""Same-document ICFR opinion leaf, gated by corp form and fiscal year."""

from __future__ import annotations

from typing import Literal

from dart_parser.fallback.schemas import ExtractionStatus, Icfr
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.context import ExtractionContext

IcfrEngagement = Literal["audit", "review"]

_AUDIT_CODES = ("부적정", "거절", "적정")
_REVIEW_CODES = ("중요한 취약점", "한정", "거절", "적정")


def icfr_in_regime(ctx: ExtractionContext) -> bool:
    """True when this filing is expected to carry an ICFR opinion leaf."""
    if ctx.corp_form == "F001":
        return False
    if ctx.corp_form == "F002" and (ctx.fiscal_year is None or ctx.fiscal_year <= 2022):
        return False
    return ctx.corp_form == "F002" and ctx.fiscal_year is not None and ctx.fiscal_year > 2022


def extract_icfr(ctx: ExtractionContext) -> Icfr:
    window = ctx.sections.get("icfr_opinion", "")
    if _is_leaf(window):
        return _from_leaf(window)
    if not icfr_in_regime(ctx):
        return Icfr(icfr_status=ExtractionStatus.not_in_regime)
    return Icfr(icfr_status=ExtractionStatus.missing)


def _is_leaf(window: str) -> bool:
    if not window.strip():
        return False
    text = normalize_text(html_to_text(window))
    if "운영보고서" in text and "감사의견" not in text and "검토의견" not in text:
        return False
    return "내부회계관리제도" in text and ("감사의견" in text or "검토의견" in text)


def _from_leaf(window: str) -> Icfr:
    text = normalize_text(html_to_text(window))
    engagement: IcfrEngagement = (
        "review"
        if "검토의견" in text or ("검토" in text and "감사의견" not in text)
        else "audit"
    )
    return Icfr(
        icfr_engagement=engagement,
        icfr_opinion_code=_opinion_code(text, engagement),
        icfr_status=ExtractionStatus.found,
    )


def _opinion_code(text: str, engagement: str) -> str | None:
    if engagement == "audit" and "중요한 취약점" in text:
        return "부적정"
    codes = _REVIEW_CODES if engagement == "review" else _AUDIT_CODES
    for code in codes:
        if code in text:
            return code
    return None
