"""Notes table of contents: titles only, no note bodies."""

from __future__ import annotations

import re

from dart_parser.fallback.schemas import Item, NotesToc, found, item_missing
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.context import ExtractionContext

_NOTE_RE = re.compile(r"^\s*(\d+)\s*[.．]\s*(.+)$")


def extract_notes_toc(ctx: ExtractionContext) -> Item[NotesToc]:
    window = ctx.sections.get("notes_toc", "")
    if not window.strip():
        return item_missing()

    titles: list[str] = []
    seen: set[int] = set()
    for raw_line in html_to_text(window).splitlines():
        line = normalize_text(raw_line)
        match = _NOTE_RE.match(line)
        if match is None:
            continue
        number = int(match.group(1))
        title = normalize_text(match.group(2))
        if number in seen:
            break
        seen.add(number)
        titles.append(title)
    return found(NotesToc(count=len(titles), titles=titles), source="rule", evidence="notes_toc")
