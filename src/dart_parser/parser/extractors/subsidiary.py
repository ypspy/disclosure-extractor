"""Consolidated subsidiary count; separate filings are not_applicable."""

from __future__ import annotations

from dart_parser.fallback.schemas import ExtractionStatus, Subsidiary
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.table_grid import Table, extract_tables
from dart_parser.parser.context import ExtractionContext

_SKIP_CLASSES = ("관계기업", "공동기업")
_HEADER_MARKERS = ("기업명", "회사명", "구분", "소재지")
_TOTAL_MARKERS = ("합계", "계")


def extract_subsidiary(ctx: ExtractionContext) -> Subsidiary:
    if ctx.fs_scope == "separate":
        return Subsidiary(
            subsidiary_status=ExtractionStatus.not_applicable,
            subsidiary_count=None,
        )

    tables = list(ctx.tables)
    window = ctx.sections.get("subsidiaries", "")
    if window.strip():
        tables = extract_tables(window) or tables
    if not tables and ctx.html:
        tables = extract_tables(ctx.html)

    for table in tables:
        if not _looks_like_subsidiary_table(table):
            continue
        count = _count_rows(table)
        return Subsidiary(
            subsidiary_status=ExtractionStatus.found,
            subsidiary_count=count,
        )
    return Subsidiary(
        subsidiary_status=ExtractionStatus.missing,
        subsidiary_count=None,
    )


def _looks_like_subsidiary_table(table: Table) -> bool:
    blob = normalize_text(" ".join((table.caption, table.context_before)))
    if "종속기업" in blob:
        return True
    for row in table.grid[:2]:
        if any("종속기업" in cell for cell in row):
            return True
    return False


def _count_rows(table: Table) -> int:
    grid = table.grid
    if not grid:
        return 0
    class_col = _class_column(grid[0])
    count = 0
    for row in grid[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        joined = normalize_text(" ".join(row))
        if any(marker in joined for marker in _TOTAL_MARKERS) and _is_total_row(row):
            continue
        if _is_header_row(row):
            continue
        klass = row[class_col] if class_col is not None and class_col < len(row) else joined
        if any(skip in klass for skip in _SKIP_CLASSES):
            continue
        count += 1
    return count


def _class_column(header: list[str]) -> int | None:
    for index, cell in enumerate(header):
        if "구분" in cell:
            return index
    return None


def _is_header_row(row: list[str]) -> bool:
    joined = normalize_text(" ".join(row))
    return any(marker in joined for marker in _HEADER_MARKERS) and not any(
        "주식회사" in cell or "㈜" in cell for cell in row
    )


def _is_total_row(row: list[str]) -> bool:
    first = normalize_text(row[0]) if row else ""
    return any(marker == first or first.endswith(marker) for marker in _TOTAL_MARKERS)
