"""Fuzzy header / row-label matching against a flattened 2D grid."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from dart_parser.normalizer.cleaner import normalize_text

_PUNCT_RE = re.compile(r"[\s\-_/·.,:;()\[\]{}'\"`~!@#$%^&*+=|\\<>?]+")


@dataclass(frozen=True)
class AnchorMatch:
    query: str
    matched: str
    score: float
    index: int | None = None
    row: int | None = None
    col: int | None = None


def canonical(text: str | None) -> str:
    """Normalize then drop spaces and light punctuation for comparison."""
    return _PUNCT_RE.sub("", normalize_text(text))


def score_anchor(text: str, anchor: str) -> float:
    """Score ``text`` against one alias. Containment beats raw Levenshtein."""
    query = canonical(text)
    target = canonical(anchor)
    if not query or not target:
        return 0.0
    if query == target:
        return 100.0
    if target in query:
        return 92.0 + 8.0 * (len(target) / len(query))
    if query in target:
        return 88.0 + 8.0 * (len(query) / len(target))
    return float(fuzz.ratio(query, target))


def match_anchor(
    text: str,
    anchors: Sequence[str],
    *,
    threshold: float = 80.0,
) -> AnchorMatch | None:
    """Return the best alias at or above ``threshold``, or ``None``."""
    best: AnchorMatch | None = None
    for i, anchor in enumerate(anchors):
        score = score_anchor(text, anchor)
        if score < threshold:
            continue
        if best is None or score > best.score:
            best = AnchorMatch(query=text, matched=anchor, score=score, index=i)
    return best


def stack_headers(rows: Sequence[Sequence[str]]) -> list[str]:
    """Join vertically stacked header cells, dropping duplicate repeats from rowspan."""
    if not rows:
        return []
    width = max((len(r) for r in rows), default=0)
    labels: list[str] = []
    for col in range(width):
        parts: list[str] = []
        for row in rows:
            if col < len(row) and row[col] and row[col] not in parts:
                parts.append(row[col])
        labels.append(" ".join(parts))
    return labels


def _as_header_labels(header_cells: Sequence[str] | Sequence[Sequence[str]]) -> list[str]:
    if header_cells and isinstance(header_cells[0], (list, tuple)):
        return stack_headers(header_cells)  # type: ignore[arg-type]
    return [str(c) for c in header_cells]


def find_header_row(
    grid: Sequence[Sequence[str]],
    anchors: Sequence[str],
    *,
    threshold: float = 80.0,
    max_rows: int = 5,
    min_hits: int = 1,
) -> int | None:
    """Index of the row that matches the most anchors (ties: earlier row)."""
    best_i: int | None = None
    best_hits = 0
    for i, row in enumerate(grid[:max_rows]):
        hits = sum(1 for cell in row if match_anchor(cell, anchors, threshold=threshold))
        if hits > best_hits:
            best_hits = hits
            best_i = i
    return best_i if best_hits >= min_hits else None


def map_columns(
    header_cells: Sequence[str] | Sequence[Sequence[str]],
    column_anchors: Mapping[str, Sequence[str]],
    *,
    threshold: float = 80.0,
) -> dict[str, int]:
    """Map each column key to the best unused header index."""
    labels = _as_header_labels(header_cells)
    used: set[int] = set()
    out: dict[str, int] = {}
    for key, anchors in column_anchors.items():
        best_i: int | None = None
        best_score = -1.0
        for i, label in enumerate(labels):
            if i in used:
                continue
            hit = match_anchor(label, list(anchors), threshold=threshold)
            if hit is not None and hit.score > best_score:
                best_score = hit.score
                best_i = i
        if best_i is not None:
            used.add(best_i)
            out[key] = best_i
    return out


def find_rows(
    grid: Sequence[Sequence[str]],
    row_anchors: Mapping[str, Sequence[str]],
    *,
    start_row: int = 0,
    label_col: int = 0,
    threshold: float = 80.0,
) -> dict[str, int]:
    """Map each row key to the best unused label-column index."""
    used: set[int] = set()
    out: dict[str, int] = {}
    for key, anchors in row_anchors.items():
        best_i: int | None = None
        best_score = -1.0
        for i in range(start_row, len(grid)):
            if i in used or label_col >= len(grid[i]):
                continue
            hit = match_anchor(grid[i][label_col], list(anchors), threshold=threshold)
            if hit is not None and hit.score > best_score:
                best_score = hit.score
                best_i = i
        if best_i is not None:
            used.add(best_i)
            out[key] = best_i
    return out
