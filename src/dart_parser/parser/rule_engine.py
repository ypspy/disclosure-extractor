"""First-pass deterministic extractor: map a flattened table through a spec."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from dart_parser.fallback.schemas import Amount
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.numeric import to_number
from dart_parser.normalizer.table_grid import Table
from dart_parser.parser.anchor_matcher import (
    canonical,
    find_rows,
    map_columns,
    stack_headers,
)
from dart_parser.parser.unit_extractor import extract_unit

# 제5기, 제 55 기, 제 55 (당) 기, 제55당기 after canonical.
_TERM_RE = re.compile(r"제\s*(\d+)\s*(?:\(?\s*[당전]\s*\)?)?\s*기")
_CURRENT_LABEL_RE = re.compile(r"당기|제\d+\(?당\)?")
_PRIOR_LABEL_RE = re.compile(r"전기|제\d+\(?전\)?")


def _is_current_period_label(compact: str) -> bool:
    return _CURRENT_LABEL_RE.search(compact) is not None


@dataclass
class TableSpec:
    name: str
    column_anchors: dict[str, list[str]]
    row_anchors: dict[str, list[str]]
    header_row_count: int = 1
    extra: dict[str, object] = field(default_factory=dict)


class RuleEngine:
    """Extract a ``{row_key: {col_key: Amount}}`` matrix from one table."""

    def extract(self, table: Table, spec: TableSpec) -> dict[str, dict[str, Amount | None]]:
        if not table.grid:
            return {}
        header_n = min(max(spec.header_row_count, 1), len(table.grid))
        headers: Sequence[Sequence[str]] = table.grid[:header_n]
        header_arg: Sequence[str] | Sequence[Sequence[str]] = (
            headers if header_n > 1 else table.grid[0]
        )
        cols = map_columns(header_arg, spec.column_anchors)
        rows = find_rows(table.grid, spec.row_anchors, start_row=header_n)
        unit = extract_unit(table.unit_text or table.context_before or table.caption)
        out: dict[str, dict[str, Amount | None]] = {}
        for row_key, r_idx in rows.items():
            row = table.grid[r_idx]
            out[row_key] = {}
            for col_key, c_idx in cols.items():
                raw = row[c_idx] if c_idx < len(row) else ""
                out[row_key][col_key] = Amount.from_cell(raw, unit_scale=unit.scale)
        return out


def infer_header_row_count(grid: Sequence[Sequence[str]]) -> int:
    """Heuristic: two header rows when the first label repeats or the second row is 금액/비고."""
    if len(grid) < 2:
        return 1
    first, second = grid[0], grid[1]
    if first and second and first[0] == second[0]:
        return 2
    if any("금액" in cell or "비고" in cell for cell in second):
        return 2
    return 1


def period_column_groups(labels: Sequence[str]) -> dict[str, list[int]]:
    """All ``current`` / ``prior`` column indexes (DART duplicates a 당기 header)."""
    term_cols: dict[int, list[int]] = {}
    current_cands: list[int] = []
    prior_cands: list[int] = []
    for i, label in enumerate(labels):
        compact = canonical(label)
        match = _TERM_RE.search(normalize_text(label)) or _TERM_RE.search(compact)
        if match:
            term_cols.setdefault(int(match.group(1)), []).append(i)
        if _is_current_period_label(compact) and "전기" not in compact:
            current_cands.append(i)
        elif _PRIOR_LABEL_RE.search(compact):
            prior_cands.append(i)
    if current_cands or prior_cands:
        return {
            key: cols
            for key, cols in (("current", current_cands), ("prior", prior_cands))
            if cols
        }
    if len(term_cols) >= 2:
        terms = sorted(term_cols)
        return {"current": term_cols[terms[-1]], "prior": term_cols[terms[0]]}
    if len(term_cols) == 1:
        return {"current": next(iter(term_cols.values()))}
    return {}


def detect_period_columns(
    labels: Sequence[str],
    grid: Sequence[Sequence[str]] | None = None,
    header_row_count: int = 1,
) -> dict[str, int]:
    """Map ``current`` / ``prior`` to column indexes.

    Prefers 당기/전기 labels (after ``canonical``, so ``제 55 (당) 기`` counts);
    otherwise 제N기 columns (larger term = current). When several columns share
    a period, prefer 금액, then the column with the most numeric body cells
    (DART flattens a 당기 header across an empty 주석 column and the amount).
    Skip 비고.
    """
    groups = period_column_groups(labels)

    def pick(cands: list[int]) -> int | None:
        if not cands:
            return None
        for i in cands:
            if "금액" in labels[i]:
                return i
        usable = [i for i in cands if "비고" not in labels[i]] or cands
        if grid is not None:
            scored = [(_numeric_hits(grid, i, header_row_count), i) for i in usable]
            best = max(n for n, _ in scored)
            return max((i for n, i in scored if n == best), default=usable[-1])
        return usable[-1]

    out: dict[str, int] = {}
    for key, cands in groups.items():
        chosen = pick(cands)
        if chosen is not None:
            out[key] = chosen
    return out


def _numeric_hits(
    grid: Sequence[Sequence[str]],
    col: int,
    header_row_count: int,
) -> int:
    start = min(max(header_row_count, 0), len(grid))
    return sum(
        1
        for row in grid[start:]
        if col < len(row) and to_number(row[col]) is not None
    )


def stacked_header_labels(grid: Sequence[Sequence[str]], header_row_count: int) -> list[str]:
    n = min(max(header_row_count, 1), len(grid))
    if n == 1:
        return list(grid[0]) if grid else []
    return stack_headers(grid[:n])
