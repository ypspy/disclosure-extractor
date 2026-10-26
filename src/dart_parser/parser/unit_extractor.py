"""Extract a disclosure unit phrase and apply its scale to a numeric value."""

from __future__ import annotations

import re
from dataclasses import dataclass

from dart_parser.normalizer.cleaner import normalize_text

_UNIT_SCALES: tuple[tuple[str, int], ...] = (
    ("백만원", 1_000_000),
    ("천원", 1_000),
    ("억원", 100_000_000),
    ("원", 1),
)
_UNIT_FIND_RE = re.compile(r"(백만원|천원|억원|원)")


@dataclass(frozen=True)
class UnitInfo:
    raw: str
    label: str
    scale: int


def extract_unit(text: str | None) -> UnitInfo:
    """Return the first recognized KRW unit in ``text``.

    When no unit word is present the scale defaults to 1 (원). Never raises.
    """
    raw = normalize_text(text)
    match = _UNIT_FIND_RE.search(raw)
    if match is None:
        return UnitInfo(raw=raw, label="원", scale=1)
    label = match.group(1)
    scale = next(scale for name, scale in _UNIT_SCALES if name == label)
    return UnitInfo(raw=raw, label=label, scale=scale)


def apply_scale(value: float | None, unit: UnitInfo | int) -> float | None:
    """Multiply ``value`` by the unit scale. ``None`` stays ``None``."""
    if value is None:
        return None
    scale = unit.scale if isinstance(unit, UnitInfo) else int(unit)
    return value * scale
