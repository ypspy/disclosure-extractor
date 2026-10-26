"""First-pass deterministic extractor: map a flattened table through a spec."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from dart_parser.fallback.schemas import Amount
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.table_grid import Table
from dart_parser.parser.anchor_matcher import find_rows, map_columns, stack_headers
from dart_parser.parser.unit_extractor import extract_unit

_TERM_RE = re.compile(r"제\s*(\d+)\s*기")


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


def detect_period_columns(labels: Sequence[str]) -> dict[str, int]:
    """Map ``current`` / ``prior`` to column indexes.

    Prefers 당기/전기 labels; otherwise 제N기 columns (larger term = current).
    When several columns share a period, prefer the one whose label contains 금액
    and skip 비고.
    """
    term_cols: dict[int, list[int]] = {}
    current_cands: list[int] = []
    prior_cands: list[int] = []
    for i, label in enumerate(labels):
        text = normalize_text(label)
        compact = text.replace(" ", "")
        match = _TERM_RE.search(text)
        if match:
            term_cols.setdefault(int(match.group(1)), []).append(i)
        if "당기" in compact and "전기" not in compact:
            current_cands.append(i)
        elif "전기" in compact:
            prior_cands.append(i)

    def pick(cands: list[int]) -> int | None:
        if not cands:
            return None
        for i in cands:
            if "금액" in labels[i]:
                return i
        for i in cands:
            if "비고" not in labels[i]:
                return i
        return cands[0]

    out: dict[str, int] = {}
    if current_cands or prior_cands:
        current = pick(current_cands)
        prior = pick(prior_cands)
        if current is not None:
            out["current"] = current
        if prior is not None:
            out["prior"] = prior
        return out

    if len(term_cols) >= 2:
        terms = sorted(term_cols)
        current = pick(term_cols[terms[-1]])
        prior = pick(term_cols[terms[0]])
        if current is not None:
            out["current"] = current
        if prior is not None:
            out["prior"] = prior
        return out

    if len(term_cols) == 1:
        current = pick(next(iter(term_cols.values())))
        if current is not None:
            out["current"] = current
    return out


def stacked_header_labels(grid: Sequence[Sequence[str]], header_row_count: int) -> list[str]:
    n = min(max(header_row_count, 1), len(grid))
    if n == 1:
        return list(grid[0]) if grid else []
    return stack_headers(grid[:n])
