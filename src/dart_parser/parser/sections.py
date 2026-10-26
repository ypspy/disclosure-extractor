"""Cut a disclosure into heading-anchored HTML windows.

Heading text is compared only after ``normalize_text``. A window runs from a
matching heading up to the next heading of the same or higher rank. Keys with
no match are present as empty strings. Styles are ignored.
"""

from __future__ import annotations

import re
from html import unescape

from dart_parser.normalizer.cleaner import normalize_text

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
_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_NO = {
    "2": re.compile(r"2\s*\."),
    "3": re.compile(r"3\s*\."),
    "4": re.compile(r"4\s*\."),
}


def locate_sections(html: str) -> dict[str, str]:
    """Return the standard section windows. Missing windows are ``""``."""
    sections = {key: "" for key in SECTION_KEYS}
    if not html:
        return sections

    headings = list(_OPEN_HEADING_RE.finditer(html))
    windows: dict[str, list[str]] = {key: [] for key in SECTION_KEYS}
    opinion_at: int | None = None

    for index, match in enumerate(headings):
        level = int(match.group(1))
        text = _heading_text(html, match.end(), level)
        key = _section_key(text)
        end = _window_end(headings, index, level, len(html))
        if key == "opinion_letter" and opinion_at is None:
            opinion_at = match.start()
        if key is not None:
            windows[key].append(html[match.start() : end])

    if opinion_at is not None:
        sections["cover"] = html[:opinion_at]
    for key, parts in windows.items():
        if parts:
            sections[key] = "\n".join(parts)
    return sections


def _heading_text(html: str, content_start: int, level: int) -> str:
    close = re.search(rf"</h{level}\s*>", html[content_start:], re.IGNORECASE)
    next_open = _OPEN_HEADING_RE.search(html, content_start)
    ends = [len(html)]
    if close is not None:
        ends.append(content_start + close.start())
    if next_open is not None:
        ends.append(next_open.start())
    inner = html[content_start : min(ends)]
    return normalize_text(unescape(_TAG_RE.sub(" ", inner)))


def _window_end(
    headings: list[re.Match[str]],
    index: int,
    level: int,
    document_end: int,
) -> int:
    """Stop at the next heading of equal or higher rank (smaller level number)."""
    for later in headings[index + 1 :]:
        if int(later.group(1)) <= level:
            return later.start()
    return document_end


def _section_key(text: str) -> str | None:
    if "독립된 감사인의 감사보고서" in text:
        return "opinion_letter"
    if "감사 투입" in text or (_LEADING_NO["2"].match(text) and "시간" in text):
        return "exhibit4_hours"
    if "실시 내용" in text or _LEADING_NO["3"].match(text):
        return "exhibit4_activities"
    if "커뮤니케이션" in text or _LEADING_NO["4"].match(text):
        return "exhibit4_communications"
    return None
