"""Financial-statement opinion letter: auditor, opinion, GAAP, and report date.

The source is ``ctx.sections["opinion_letter"]``. When that window is empty,
auditor, opinion, and GAAP fall back to the full document. The report date
stays missing when the window is empty; it is not inferred from the rest of
the filing. Internal-control opinions are a different section and are not read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dart_parser.fallback.schemas import Gaap, Item, found, item_missing
from dart_parser.normalizer.cleaner import html_to_text
from dart_parser.parser.anchor_matcher import match_anchor
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.lexicon import GAAP_ALIASES, OPINION_ALIASES

_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_AUDITOR_RE = re.compile(r"(?:\S+회계법인|\S+감사반)")


@dataclass
class OpinionLetter:
    auditor: Item[str]
    opinion: Item[str]
    gaap: Item[Gaap]
    audit_report_date: Item[str]


def extract_opinion_letter(ctx: ExtractionContext) -> OpinionLetter:
    """Read the opinion-letter window, or the whole document when that window is empty."""
    window = ctx.sections.get("opinion_letter") or ""
    window_present = bool(window.strip())
    text = html_to_text(window if window_present else ctx.html)
    return OpinionLetter(
        auditor=_auditor(text),
        opinion=_opinion(text),
        gaap=_gaap(text),
        audit_report_date=_report_date(text) if window_present else item_missing(),
    )


def _opinion(text: str) -> Item[str]:
    hit = _best_alias(text, OPINION_ALIASES)
    if hit is None:
        return item_missing()
    code, raw = hit
    return found(code, evidence=raw)


def _gaap(text: str) -> Item[Gaap]:
    hit = _best_alias(text, GAAP_ALIASES)
    if hit is None:
        return item_missing()
    code, raw = hit
    return found(Gaap(raw=raw, code=code), evidence=raw)


def _auditor(text: str) -> Item[str]:
    names = _AUDITOR_RE.findall(text)
    if not names:
        return item_missing()
    # The firm that signs the letter is the last name in the window.
    name = names[-1]
    return found(name, evidence=name)


def _report_date(text: str) -> Item[str]:
    matches = list(_DATE_RE.finditer(text))
    if not matches:
        return item_missing()
    last = matches[-1]
    year = int(last.group(1))
    month = int(last.group(2))
    day = int(last.group(3))
    iso = f"{year:04d}-{month:02d}-{day:02d}"
    return found(iso, evidence=last.group(0))


def _best_alias(text: str, aliases: dict[str, list[str]]) -> tuple[str, str] | None:
    """Return ``(code, raw)`` for the strongest alias in ``text``.

    Rank is match score, then alias length. ``부적정`` contains ``적정``, so a
    shorter hit must not replace the longer one.
    """
    if not text:
        return None
    best_rank: tuple[float, int] | None = None
    chosen: tuple[str, str] | None = None
    for code, names in aliases.items():
        hit = match_anchor(text, names)
        if hit is None:
            continue
        rank = (hit.score, len(hit.matched))
        if best_rank is not None and rank <= best_rank:
            continue
        best_rank = rank
        chosen = (code, _surface(text, hit.matched))
    return chosen


def _surface(text: str, matched: str) -> str:
    if matched in text:
        return matched
    for line in text.split("\n"):
        if line and match_anchor(line, [matched]) is not None:
            return line
    return matched
