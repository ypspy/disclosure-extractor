"""Cut a disclosure into heading-anchored HTML windows.

Heading text is compared after ``normalize_text`` / ``canonical``. A window
runs from a matching heading up to the next heading of the same or higher
rank. DART TOC uses ``p.section-N`` instead of ``h1``–``h6``; both count.
Keys with no match are present as empty strings. Styles are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.parser.anchor_matcher import canonical

SECTION_KEYS: tuple[str, ...] = (
    "cover",
    "opinion_letter",
    "exhibit4_hours",
    "exhibit4_activities",
    "exhibit4_communications",
    "bs",
    "is_",
    "icfr_opinion",
    "going_concern",
    "subsidiaries",
    "notes_toc",
)

_OPEN_HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>", re.IGNORECASE)
_OPEN_P_RE = re.compile(r"<p\b([^>]*)>", re.IGNORECASE)
_CLASS_RE = re.compile(r"""class\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_SECTION_CLASS_RE = re.compile(r"section-(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_NO = {
    "2": re.compile(r"2\s*\."),
    "3": re.compile(r"3\s*\."),
    "4": re.compile(r"4\s*\."),
}


@dataclass(frozen=True)
class _Mark:
    start: int
    level: int
    text: str


def locate_sections(html: str) -> dict[str, str]:
    """Return the standard section windows. Missing windows are ``""``."""
    sections = {key: "" for key in SECTION_KEYS}
    if not html:
        return sections

    headings = _collect_headings(html)
    windows: dict[str, list[str]] = {key: [] for key in SECTION_KEYS}
    opinion_at: int | None = None

    for index, mark in enumerate(headings):
        key = _section_key(mark.text)
        end = _window_end(headings, index, mark.level, len(html))
        if key == "opinion_letter" and opinion_at is None:
            opinion_at = mark.start
        if key is not None:
            windows[key].append(html[mark.start : end])

    if opinion_at is not None:
        sections["cover"] = html[:opinion_at]
    for key, parts in windows.items():
        if parts:
            sections[key] = "\n".join(parts)
    return sections


def _collect_headings(html: str) -> list[_Mark]:
    marks = [_h_mark(html, match) for match in _OPEN_HEADING_RE.finditer(html)]
    marks.extend(
        _p_mark(html, match)
        for match in _OPEN_P_RE.finditer(html)
        if _is_toc_paragraph(match.group(1))
    )
    marks.sort(key=lambda mark: mark.start)
    return marks


def _h_mark(html: str, match: re.Match[str]) -> _Mark:
    level = int(match.group(1))
    return _Mark(match.start(), level, _inner_text(html, match.end(), rf"</h{level}\s*>"))


def _p_mark(html: str, match: re.Match[str]) -> _Mark:
    # DART section-1/2 sit at the same rank so a later TOC item always closes the window.
    return _Mark(match.start(), 2, _inner_text(html, match.end(), r"</p\s*>"))


def _is_toc_paragraph(attrs: str) -> bool:
    cls = _CLASS_RE.search(attrs)
    if cls is None:
        return False
    return _SECTION_CLASS_RE.search(cls.group(1)) is not None


def _inner_text(html: str, content_start: int, close_pat: str) -> str:
    close = re.search(close_pat, html[content_start:], re.IGNORECASE)
    next_open = _OPEN_HEADING_RE.search(html, content_start)
    ends = [len(html)]
    if close is not None:
        ends.append(content_start + close.start())
    if next_open is not None:
        ends.append(next_open.start())
    inner = html[content_start : min(ends)]
    return normalize_text(unescape(_TAG_RE.sub(" ", inner)))


def _window_end(
    headings: list[_Mark],
    index: int,
    level: int,
    document_end: int,
) -> int:
    """Stop at the next heading of equal or higher rank (smaller level number)."""
    for later in headings[index + 1 :]:
        if later.level <= level:
            return later.start
    return document_end


def _section_key(text: str) -> str | None:
    compact = canonical(text)
    if "내부회계관리제도" in compact and (
        "감사의견" in compact or "검토의견" in compact or "감사보고서" in compact
    ):
        if "운영보고서" not in compact:
            return "icfr_opinion"
    if "독립된감사인의감사보고서" in compact:
        return "opinion_letter"
    if "감사투입" in compact or (_LEADING_NO["2"].match(text) and "시간" in compact):
        return "exhibit4_hours"
    if _LEADING_NO["3"].match(text) or "주요감사실시" in compact:
        return "exhibit4_activities"
    if "커뮤니케이션" in compact or _LEADING_NO["4"].match(text):
        return "exhibit4_communications"
    if "재무상태표" in compact:
        return "bs"
    if "손익계산서" in compact and "포괄" not in compact:
        return "is_"
    if "강조사항" in compact or "기타사항" in compact or "계속기업" in compact:
        return "going_concern"
    if "종속기업" in compact:
        return "subsidiaries"
    if compact == "주석" or compact.startswith("주석"):
        return "notes_toc"
    return None
