"""Cover identification: company, title, fiscal term, current period, and fs_scope.

``current_period`` is the cover reporting period (one object, parsed once).
The year of ``Period.end`` is what a later step stores on ``ctx.fiscal_year``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dart_parser.fallback.schemas import Item, Period, found, item_missing
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.anchor_matcher import canonical
from dart_parser.parser.context import ExtractionContext, FsScope

_TITLE_CONSOLIDATED = "연결감사보고서"
_TITLE_SEPARATE = "감사보고서"
_FISCAL_TERM_RE = re.compile(r"제\s*(\d+)\s*(?:\(?\s*[당전]\s*\)?)?\s*기")
_COMPANY_MARKERS = ("주식회사", "(주)", "유한회사", "(유)", "투자회사", "株式會社")
_KO_PERIOD_RE = re.compile(
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
    r".{0,40}?"
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    re.DOTALL,
)
_PERIOD_RE = re.compile(
    r"(\d{4})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2})"
    r".*?"
    r"(\d{4})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2})"
)
# html_to_text NFKC-normalizes U+321C ㈜ to "(주)" before company matching.


@dataclass
class Identification:
    company_name: Item[str]
    document_title: Item[str]
    fiscal_term: Item[str]
    current_period: Item[Period]
    fs_scope: FsScope | None


def extract_identification(ctx: ExtractionContext) -> Identification:
    """Read the cover window, or the whole document when that window is empty."""
    cover = ctx.sections.get("cover") or ctx.html
    text = html_to_text(cover)
    title, scope = _document_title(text)
    return Identification(
        company_name=_company_name(text),
        document_title=title,
        fiscal_term=_fiscal_term(text),
        current_period=_current_period(text),
        fs_scope=scope,
    )


def _document_title(text: str) -> tuple[Item[str], FsScope | None]:
    # Spaced DART titles such as 감 사 보 고 서 collapse via canonical.
    # 연결감사보고서 contains 감사보고서, so the longer title is matched first.
    compact = canonical(text)
    if canonical(_TITLE_CONSOLIDATED) in compact:
        return found(_TITLE_CONSOLIDATED, evidence=_TITLE_CONSOLIDATED), "consolidated"
    if canonical(_TITLE_SEPARATE) in compact:
        return found(_TITLE_SEPARATE, evidence=_TITLE_SEPARATE), "separate"
    return item_missing(), None


def _fiscal_term(text: str) -> Item[str]:
    match = _FISCAL_TERM_RE.search(text)
    if match is None:
        return item_missing()
    return found(f"제{match.group(1)}기", evidence=match.group(0))


def _current_period(text: str) -> Item[Period]:
    # Cover uses 2023년 01월 01일부터 …까지. Dotted pairs later are exhibit dates.
    match = _KO_PERIOD_RE.search(text) or _PERIOD_RE.search(text)
    if match is None:
        return item_missing()
    start = _iso_date(*match.group(1, 2, 3))
    end = _iso_date(*match.group(4, 5, 6))
    period = Period(start=start, end=end, raw=match.group(0))
    return found(period, evidence=match.group(0))


def _iso_date(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _company_name(text: str) -> Item[str]:
    for raw_line in text.split("\n"):
        line = normalize_text(raw_line)
        if not line or _is_title_or_term_line(line):
            continue
        compact = canonical(line)
        if any(canonical(marker) in compact for marker in _COMPANY_MARKERS):
            return found(line, evidence=line)
    return item_missing()


def _is_title_or_term_line(line: str) -> bool:
    compact = canonical(line)
    if canonical(_TITLE_CONSOLIDATED) in compact or canonical(_TITLE_SEPARATE) in compact:
        return True
    return _FISCAL_TERM_RE.search(line) is not None
