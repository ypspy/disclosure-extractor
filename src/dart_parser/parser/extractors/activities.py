"""Exhibit 4 section 3: seven audit activity procedures."""

from __future__ import annotations

import re

from dart_parser.fallback.schemas import (
    Activities,
    ExternalConfirmations,
    Item,
    Observation,
    found,
    item_missing,
)
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.anchor_matcher import match_anchor
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.lexicon import ACTIVITY_ALIASES


def extract_activities(ctx: ExtractionContext) -> Item[Activities]:
    window = ctx.sections.get("exhibit4_activities", "")
    if not window.strip():
        return item_missing()
    acts = Activities()
    for table in extract_tables(window):
        for row in table.grid:
            if not row:
                continue
            label = row[0]
            body = normalize_text(" ".join(cell for cell in row[1:] if cell))
            key = _activity_key(label)
            if key is None:
                continue
            _assign(acts, key, body or normalize_text(label))
    return found(acts, source="rule", evidence="exhibit4_activities")


def _activity_key(label: str) -> str | None:
    best: str | None = None
    best_score = -1.0
    for key, aliases in ACTIVITY_ALIASES.items():
        hit = match_anchor(label, aliases)
        if hit is not None and hit.score > best_score:
            best = key
            best_score = hit.score
    return best


def _assign(acts: Activities, key: str, body: str) -> None:
    if key in {"planning", "fieldwork", "tcwg_communication", "expert"}:
        setattr(acts, key, body)
        return
    if key in {"inventory_observation", "financial_asset_observation"}:
        setattr(acts, key, _observation(body))
        return
    if key == "external_confirmations":
        acts.external_confirmations = _confirmations(body)


def _observation(text: str) -> Observation:
    return Observation(
        content=text,
        date=_labeled(text, "시기"),
        place=_labeled(text, "장소"),
        target=_labeled(text, "대상"),
    )


def _confirmations(text: str) -> ExternalConfirmations:
    return ExternalConfirmations(
        financial=_labeled(text, "금융거래"),
        receivables_payables=_labeled(text, "채권채무"),
        legal=_labeled(text, "변호사"),
        other=_labeled(text, "기타"),
    )


def _labeled(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*[:：]?\s*([^/]+)", text)
    if match is None:
        return None
    return normalize_text(match.group(1))
