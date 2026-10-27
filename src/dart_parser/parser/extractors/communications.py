"""Exhibit 4 section 4: TCWG communications and old-form regime."""

from __future__ import annotations

import re

from dart_parser.fallback.schemas import (
    CommunicationItem,
    Communications,
    Item,
    found,
    item_missing,
    item_not_in_regime,
)
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.context import ExtractionContext

_ROUND_RE = re.compile(r"제?\s*(\d+)\s*회")
_DATE_RE = re.compile(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})")


def extract_communications(ctx: ExtractionContext) -> Item[Communications]:
    sections = ctx.sections
    has_s2 = bool(sections.get("exhibit4_hours", "").strip())
    has_s3 = bool(sections.get("exhibit4_activities", "").strip())
    window = sections.get("exhibit4_communications", "")
    has_s4 = bool(window.strip())
    if not has_s4 and (has_s2 or has_s3):
        return item_not_in_regime()
    if not has_s4:
        return item_missing()

    text = html_to_text(window)
    compact = normalize_text(text)
    has_committee = "감사위원회" in compact
    items = _rounds(window)
    return found(
        Communications(has_audit_committee=has_committee, items=items),
        source="rule",
        evidence="exhibit4_communications",
    )


def _rounds(html: str) -> list[CommunicationItem]:
    items: list[CommunicationItem] = []
    for table in extract_tables(html):
        for row in table.grid:
            if not row:
                continue
            joined = " ".join(row)
            if "회차" in joined and "일자" in joined:
                continue
            round_match = _ROUND_RE.search(joined)
            if round_match is None:
                continue
            date_match = _DATE_RE.search(joined)
            date = None
            if date_match is not None:
                year, month, day = date_match.groups()
                date = f"{int(year):04d}.{int(month):02d}.{int(day):02d}"
            items.append(
                CommunicationItem(
                    round=int(round_match.group(1)),
                    date=date,
                    raw=normalize_text(joined),
                )
            )
    return items
