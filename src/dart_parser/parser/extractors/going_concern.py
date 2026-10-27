"""Current-period going-concern material uncertainty as 0 or 1."""

from __future__ import annotations

from dart_parser.fallback.schemas import Item, found
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.context import ExtractionContext

_BASIS_MARKERS = ("한정의 근거", "부적정의 근거", "거절의 근거")


def extract_going_concern(ctx: ExtractionContext) -> Item[int]:
    window = ctx.sections.get("going_concern") or ctx.html
    text = normalize_text(html_to_text(window) if "<" in window else window)
    flag = _is_current_uncertainty(text)
    return found(1 if flag else 0, source="rule", evidence="going_concern")


def _is_current_uncertainty(text: str) -> bool:
    if not text:
        return False
    if any(marker in text for marker in _BASIS_MARKERS):
        return False
    if "청산" in text:
        return False
    if "전기" in text and "당기" not in text:
        return False
    return "계속기업" in text and "중요한 불확실성" in text
