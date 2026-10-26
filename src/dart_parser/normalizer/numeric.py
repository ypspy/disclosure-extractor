"""Defensive numeric conversion for DART table cells.

Handles the conventions seen in Korean financial disclosures:

- thousands separators `1,234,567`
- negatives written as `(1,234)`, `△1,234`, `▲1,234`, `-1,234`, `−1,234` (unicode minus)
- empty / dash cells (`-`, `–`, `—`, `―`, `ㅡ`, `해당없음`) -> ``None``
- trailing unit words (`원`, `주`, `%`, `명`, `시간`) are ignored
- full-width digits and NBSP are normalized first
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from dart_parser.normalizer.cleaner import normalize_text

_DASHES = {"-", "–", "—", "―", "ㅡ", "−", "‒", "ー"}
_EMPTY_WORDS = {"", "해당없음", "해당사항없음", "없음", "n/a", "na", "nan", "null"}
_NEG_PREFIX = ("△", "▲", "-", "−", "‒")
_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_STRIP_RE = re.compile(r"[,\s]")


def _strip_units(s: str) -> str:
    s = s.strip()
    # Drop a trailing unit word or percent sign; keep the numeric core only.
    s = re.sub(r"(원|주|%|명|시간|건|회|배|개|천원|백만원|억원)$", "", s).strip()
    return s


def to_number(cell: str | int | float | None) -> float | None:
    """Convert a table cell to ``float``.

    Returns ``None`` when the cell is empty, a dash, or not a number. Never raises.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, int | float):
        return float(cell)

    s = normalize_text(str(cell))
    if s.lower() in _EMPTY_WORDS or s in _DASHES:
        return None

    negative = False
    # Parenthesised negatives: "(1,234)"
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    # Triangle / leading-minus negatives: "△1,234", "-1,234"
    while s and s[0] in _NEG_PREFIX:
        negative = True
        s = s[1:].strip()
    if s.startswith("+"):
        s = s[1:].strip()

    s = _strip_units(s)
    s = _STRIP_RE.sub("", s)
    if not s or s in _DASHES:
        return None

    m = _NUMBER_RE.fullmatch(s)
    if not m:
        return None
    try:
        value = float(Decimal(s))
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def to_int(cell: str | int | float | None) -> int | None:
    """Like :func:`to_number` but returns ``int`` (``None`` when not integral)."""
    v = to_number(cell)
    if v is None or v != int(v):
        return None
    return int(v)
