"""Exhibit 4 section 2: role × metric × period hours grid."""

from __future__ import annotations

from typing import Literal, NamedTuple

from dart_parser.fallback.schemas import HoursCell, HoursTable, Item, found, item_missing
from dart_parser.normalizer.numeric import to_number
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.anchor_matcher import match_anchor, stack_headers
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.lexicon import (
    HOUR_METRIC_ALIASES,
    HOUR_PERIOD_ALIASES,
    HOUR_ROLE_ALIASES,
)
from dart_parser.validator.math_validator import ValidationIssue, ValidationResult, sums_to

_HOURS_METRICS = frozenset({"headcount", "audit_hours", "interim_review"})
_EXCLUDED_ROLES = frozenset({"total", "other"})
_STUB_LABELS = frozenset({"구분", "직위", "성명"})
_TOLERANCE = 1.0
_Period = Literal["current", "prior"]


def extract_hours(ctx: ExtractionContext) -> Item[HoursTable]:
    """Read section 2 of exhibit 4 into one cell per role, metric, and period.

    An empty ``exhibit4_hours`` window is ``missing``. Tables are taken from that
    window. When the window has no hours grid, the full document is searched.
    An axis label outside the lexicon clears ``role_key``, ``metric_key``, and
    ``period`` on that cell and sets ``unmapped``.
    """
    window = ctx.sections.get("exhibit4_hours", "")
    if not window or not window.strip():
        return item_missing()

    cells = _cells_from_html(window)
    if not cells and ctx.html and ctx.html != window:
        cells = _cells_from_html(ctx.html, first_only=True)
    if not cells:
        return item_missing()
    return found(HoursTable(cells=cells), source="rule", evidence="exhibit4_hours")


def validate_hours(table: HoursTable) -> ValidationResult:
    """Check 합계 감사시간 당기 against the other mapped roles.

    Component roles exclude ``total`` and ``other``. Blank cells are omitted.
    Tolerance is 1.0. With no numeric total cell the table is unchecked.
    """
    current = [
        cell
        for cell in table.cells
        if not cell.unmapped
        and cell.metric_key == "audit_hours"
        and cell.period == "current"
        and cell.value is not None
        and cell.role_key is not None
    ]
    totals = [cell.value for cell in current if cell.role_key == "total"]
    if not totals:
        return ValidationResult(ok=True)
    total = totals[-1]
    parts = [
        cell.value
        for cell in current
        if cell.role_key not in _EXCLUDED_ROLES and cell.value is not None
    ]
    if sums_to(parts, total, tolerance=_TOLERANCE):
        return ValidationResult(ok=True)
    return ValidationResult(
        ok=False,
        issues=[
            ValidationIssue(
                code="hours_role_sum",
                message="합계 감사시간 당기 != 구성 역할 합",
                expected=total,
                actual=sum(float(part) for part in parts),
            )
        ],
    )


def _cells_from_html(html: str, *, first_only: bool = False) -> list[HoursCell]:
    cells: list[HoursCell] = []
    for table in extract_tables(html):
        parsed = _cells_from_grid(table.grid)
        if not parsed:
            continue
        cells.extend(parsed)
        if first_only:
            break
    return cells


def _cells_from_grid(grid: list[list[str]]) -> list[HoursCell] | None:
    header_n = _header_row_count(grid)
    if header_n <= 0 or header_n >= len(grid):
        return None
    if _looks_transposed(grid, header_n):
        return _cells_from_transposed(grid, header_n)

    header_rows = grid[:header_n]
    stacked = stack_headers(header_rows)
    width = max(len(row) for row in grid)
    axes: list[_Axis | None] = []
    recognized = False
    for col in range(width):
        axis = None if col == 0 else _column_axis(header_rows, stacked, col)
        axes.append(axis)
        if axis is not None and axis.metric_key in _HOURS_METRICS:
            recognized = True
    if not recognized:
        return None

    cells: list[HoursCell] = []
    for row in grid[header_n:]:
        cells.extend(_row_cells(row, axes))
    return cells


def _looks_transposed(grid: list[list[str]], header_n: int) -> bool:
    """Roles sit in columns when the first data-row label is a metric, not a role."""
    first = grid[header_n]
    metric_key = _row_metric(first)[1]
    role_key = _best_key(first[0] if first else "", HOUR_ROLE_ALIASES)
    return metric_key in _HOURS_METRICS and role_key is None


def _cells_from_transposed(grid: list[list[str]], header_n: int) -> list[HoursCell] | None:
    header_rows = grid[:header_n]
    stacked = stack_headers(header_rows)
    width = max(len(row) for row in grid)
    roles: list[tuple[str | None, _Period | None, str] | None] = []
    role_hits = 0
    for col in range(width):
        axis = _column_role(header_rows, stacked, col)
        roles.append(axis)
        if axis is not None and axis[0] is not None:
            role_hits += 1
    if role_hits < 2:
        return None

    cells: list[HoursCell] = []
    for row in grid[header_n:]:
        metric_text, metric_key = _row_metric(row)
        if not metric_text:
            continue
        for col, axis in enumerate(roles):
            if axis is None:
                continue
            role_key, period, role_text = axis
            raw = row[col] if col < len(row) else ""
            mapped = (
                role_key is not None
                and metric_key is not None
                and period in ("current", "prior")
            )
            cells.append(
                HoursCell(
                    role=role_text,
                    role_key=role_key if mapped else None,
                    metric=metric_text,
                    metric_key=metric_key if mapped else None,
                    period=period if mapped else None,
                    value=to_number(raw),
                    unmapped=not mapped,
                )
            )
    return cells or None


def _column_role(
    header_rows: list[list[str]],
    stacked: list[str],
    col: int,
) -> tuple[str | None, _Period | None, str] | None:
    header_cells = [row[col] if col < len(row) else "" for row in header_rows]
    stacked_label = stacked[col] if col < len(stacked) else ""
    period = None
    for cell in reversed(header_cells):
        if cell:
            period = _period_of(cell)
            if period is not None:
                break
    if period is None:
        period = _period_of(stacked_label, threshold=92.0)

    role_key: str | None = None
    role_text = ""
    for cell in reversed(header_cells):
        if not cell or _period_of(cell) is not None:
            continue
        found = _best_key(cell, HOUR_ROLE_ALIASES)
        if found is not None:
            role_key = found
            role_text = cell
            break
    if role_key is None:
        role_key = _best_key(stacked_label, HOUR_ROLE_ALIASES, threshold=92.0)
        role_text = stacked_label
    if not role_text or role_text in _STUB_LABELS:
        return None
    return role_key, period, role_text


def _row_metric(row: list[str]) -> tuple[str, str | None]:
    last_text = ""
    last_key: str | None = None
    for cell in row[:2]:
        if not cell:
            continue
        key = _best_key(cell, HOUR_METRIC_ALIASES)
        if key is not None:
            last_text = cell
            last_key = key
    if last_key is not None:
        return last_text, last_key
    label = next((cell for cell in row[:2] if cell), "")
    return label, None


class _Axis(NamedTuple):
    metric_key: str | None
    period: _Period | None
    metric: str


def _column_axis(
    header_rows: list[list[str]],
    stacked: list[str],
    col: int,
) -> _Axis | None:
    header_cells = [row[col] if col < len(row) else "" for row in header_rows]
    stacked_label = stacked[col] if col < len(stacked) else ""
    if not any(header_cells) and not stacked_label:
        return None

    metric_key: str | None = None
    period: _Period | None = None
    metric_text = ""
    # Lower header bands are the specific axis (분·반기검토 under 감사시간).
    for cell in reversed(header_cells):
        if not cell:
            continue
        if period is None:
            period = _period_of(cell)
        if metric_key is None:
            found_metric = _best_key(cell, HOUR_METRIC_ALIASES)
            if found_metric is not None:
                metric_key = found_metric
                metric_text = cell

    if metric_key is None:
        found_metric = _best_key(stacked_label, HOUR_METRIC_ALIASES, threshold=92.0)
        if found_metric is not None:
            metric_key = found_metric
            metric_text = stacked_label
    if period is None:
        period = _period_of(stacked_label, threshold=92.0)
    if not metric_text:
        parts = [cell for cell in header_cells if cell and _period_of(cell) is None]
        metric_text = " ".join(parts) if parts else stacked_label
    if not metric_text or metric_text in _STUB_LABELS:
        return None
    return _Axis(metric_key, period, metric_text)


def _row_cells(row: list[str], axes: list[_Axis | None]) -> list[HoursCell]:
    role_text = row[0] if row else ""
    if not role_text or role_text in _STUB_LABELS:
        return []
    role_key = _best_key(role_text, HOUR_ROLE_ALIASES)
    indexed = [
        (axis, row[col] if col < len(row) else "")
        for col, axis in enumerate(axes)
        if axis is not None
    ]
    has_number = any(to_number(raw) is not None for _, raw in indexed)
    if role_key is None and not has_number:
        return []

    cells: list[HoursCell] = []
    for axis, raw in indexed:
        period = axis.period if axis.period in ("current", "prior") else None
        mapped = role_key is not None and axis.metric_key is not None and period is not None
        cells.append(
            HoursCell(
                role=role_text,
                role_key=role_key if mapped else None,
                metric=axis.metric,
                metric_key=axis.metric_key if mapped else None,
                period=period if mapped else None,
                value=to_number(raw),
                unmapped=not mapped,
            )
        )
    return cells


def _header_row_count(grid: list[list[str]]) -> int:
    count = 0
    for row in grid:
        if _is_data_row(row):
            break
        count += 1
    return count


def _is_data_row(row: list[str]) -> bool:
    if not row:
        return False
    if any(to_number(cell) is not None for cell in row[1:]):
        return True
    return _best_key(row[0], HOUR_ROLE_ALIASES) is not None


def _period_of(text: str, *, threshold: float = 80.0) -> _Period | None:
    key = _best_key(text, HOUR_PERIOD_ALIASES, threshold=threshold)
    if key == "current" or key == "prior":
        return key
    return None


def _best_key(
    text: str,
    aliases: dict[str, list[str]],
    *,
    threshold: float = 80.0,
) -> str | None:
    if not text or not text.strip():
        return None
    best_key: str | None = None
    best_score = -1.0
    best_len = -1
    for key, names in aliases.items():
        hit = match_anchor(text, names, threshold=threshold)
        if hit is None:
            continue
        alias_len = len(hit.matched)
        if hit.score > best_score or (hit.score == best_score and alias_len > best_len):
            best_key = key
            best_score = hit.score
            best_len = alias_len
    return best_key
