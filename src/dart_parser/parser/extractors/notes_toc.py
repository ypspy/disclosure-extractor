"""Notes table of contents: titles only, no note bodies."""

from __future__ import annotations

import re

from dart_parser.fallback.schemas import Item, NotesToc, found, item_missing
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.context import ExtractionContext

_NOTE_RE = re.compile(r"^\s*(\d+)\s*[.．]\s*(.+)$")
_BAD_TITLE_RE = re.compile(r"^[\d.%]+$")


def extract_notes_toc(ctx: ExtractionContext) -> Item[NotesToc]:
    window = ctx.sections.get("notes_toc", "")
    if not window.strip():
        return item_missing()

    titles: list[str] = []
    expected = 1
    for raw_line in html_to_text(window).splitlines():
        line = normalize_text(raw_line)
        match = _NOTE_RE.match(line)
        if match is None:
            continue
        number = int(match.group(1))
        title = normalize_text(match.group(2)).rstrip(" :：")
        if number != expected:
            continue
        if len(title) < 2 or len(title) > 80 or _BAD_TITLE_RE.match(title):
            continue
        titles.append(title)
        expected += 1
    return found(NotesToc(count=len(titles), titles=titles), source="rule", evidence="notes_toc")
