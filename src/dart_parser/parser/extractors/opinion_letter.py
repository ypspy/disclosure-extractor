"""Financial-statement opinion letter: auditor, opinion, GAAP, and report date.

The source is ``ctx.sections["opinion_letter"]``. When that window is empty,
auditor, opinion, and GAAP fall back to the full document. The report date
stays missing when the window is empty; it is not inferred from the rest of
the filing. Internal-control opinions are a different section and are not read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dart_parser.fallback.schemas import ExtractionStatus, Gaap, Item, found, item_missing
from dart_parser.normalizer.cleaner import html_to_text, normalize_text
from dart_parser.parser.anchor_matcher import canonical, match_anchor
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.lexicon import GAAP_ALIASES, OPINION_ALIASES

_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_FIRM_MARK_RE = re.compile(r"공인회계사감사반|회계법인|감사반")
_CPA_BAN_RE = re.compile(r"([가-힣]{2,8})(?:제\d+호)?공인회계사감사반(?:제\d+호)?$")
_PRIOR_CITE_RE = re.compile(r"적정의견이\s*표명|감사보고서에는\s*적정의견")
_OPINION_STOPS = (
    "감사의견근거",
    "재무제표에 대한 경영진",
    "내부회계관리제도에 대한",
    "강조사항",
    "기타사항",
)


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
    cover = html_to_text(ctx.sections.get("cover") or "")
    return OpinionLetter(
        auditor=_auditor(text, cover),
        opinion=_opinion(text),
        gaap=_gaap(text),
        audit_report_date=_report_date(text) if window_present else item_missing(),
    )


def _opinion(text: str) -> Item[str]:
    hit = _classify_opinion(_current_opinion_span(text))
    if hit.status is ExtractionStatus.found:
        return hit
    return _classify_opinion(_without_prior_citations(text))


def _current_opinion_span(text: str) -> str:
    starts = [text.find(marker) for marker in ("의견으로는", "의견거절") if marker in text]
    body = text if not starts else text[min(starts) :]
    for stop in _OPINION_STOPS:
        index = body.find(stop)
        if 0 < index < 800:
            return body[:index]
    return body[:800] if starts else body


def _without_prior_citations(text: str) -> str:
    parts = re.split(r"(?<=다\.)", text)
    return "".join(part for part in parts if not _PRIOR_CITE_RE.search(part))


def _classify_opinion(text: str) -> Item[str]:
    compact = canonical(text)
    if not compact:
        return item_missing()
    if "부적정" in compact:
        return found("부적정", evidence="부적정")
    if "의견거절" in compact:
        return found("거절", evidence="의견거절")
    if "공정하게표시" in compact:
        return found("적정", evidence="공정하게 표시")
    if "적정하게표시" in compact:
        return found("적정", evidence="적정하게 표시")
    if "적정" in compact and "적정의견이표명" not in compact:
        hit = _best_alias(text, OPINION_ALIASES)
        if hit is None or hit[0] != "적정":
            return item_missing()
        if _PRIOR_CITE_RE.search(text):
            return item_missing()
        return found("적정", evidence=hit[1])
    return item_missing()


def _gaap(text: str) -> Item[Gaap]:
    hit = _best_alias(text, GAAP_ALIASES)
    if hit is None:
        return item_missing()
    code, raw = hit
    return found(Gaap(raw=raw, code=code), evidence=raw)


def _auditor(text: str, cover: str = "") -> Item[str]:
    name = _firm_from_compact(canonical(text)) or _firm_from_cover(cover)
    if not name:
        return item_missing()
    return found(name, evidence=name)


def _firm_from_cover(cover: str) -> str | None:
    """The auditor is the last firm-like line on the cover, not a glued 까지…법인."""
    lines = [normalize_text(line) for line in cover.splitlines() if normalize_text(line)]
    for line in reversed(lines[-8:]):
        hit = _match_firm_at_end(canonical(line))
        if hit:
            return hit
    return None


def _firm_from_compact(compact: str) -> str | None:
    """Read ``한영회계법인``, ``참회계법인``, or the inverted ``회계법인세진``."""
    if "대표이사" in compact:
        hit = _match_firm_at_end(compact.rsplit("대표이사", 1)[0])
        if hit:
            return hit
    marks = list(_FIRM_MARK_RE.finditer(compact))
    if not marks:
        return None
    last = marks[-1]
    after = compact[last.end() :]
    if last.group(0) == "회계법인":
        prefix = re.match(r"([가-힣]{1,8})(?=대표이사|$)", after)
        if prefix:
            return "회계법인" + prefix.group(1)
    return _match_firm_at_end(compact[: last.end()])


def _match_firm_at_end(left: str) -> str | None:
    snippet = re.sub(r".*(?:습니다|입니다|합니다)", "", left[-80:])
    prefix = re.search(r"회계법인([가-힣]{1,8})$", snippet)
    if prefix:
        return "회계법인" + prefix.group(1)
    cpa_ban = _CPA_BAN_RE.search(snippet)
    if cpa_ban:
        return cpa_ban.group(1) + "공인회계사감사반"
    for length in (2, 3, 4, 1, 5, 6):
        match = re.search(rf"([가-힣]{{{length}}}(?:회계법인|감사반))$", snippet)
        if match:
            return match.group(1)
    return None


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
