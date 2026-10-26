"""Flatten HTML tables (with ``rowspan``/``colspan``) into rectangular 2D grids.

Rule #2 of the project: never run selectors or regex on an unflattened table. Every
downstream component (anchor matcher, rule engine, LLM fallback) consumes the grid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from dart_parser.normalizer.cleaner import clean_soup, normalize_text

_UNIT_HINT_RE = re.compile(r"단\s*위")
_EMPTY = object()  # sentinel for "not yet filled" (distinct from an empty-string cell)


def _span(cell: Tag, name: str) -> int:
    raw = cell.get(name)
    if raw is None:
        return 1
    try:
        value = int(str(raw).strip() or 1)
    except ValueError:
        return 1
    return max(value, 1)


def _cell_text(cell: Tag) -> str:
    for br in cell.find_all("br"):
        br.replace_with(" ")
    return normalize_text(cell.get_text(" "))


def flatten_table_to_grid(table: str | Tag) -> list[list[str]]:
    """Return the table as a rectangular ``list[list[str]]``.

    Spanned cells are duplicated into every grid position they cover, so a header such
    as ``<th colspan=2>당기</th>`` yields ``["당기", "당기"]`` and can be matched per column.
    """
    if isinstance(table, str):
        soup = BeautifulSoup(table, "lxml")
        node = soup.find("table")
    else:
        node = table if table.name == "table" else table.find("table")
    if node is None:
        return []

    rows = [tr for tr in node.find_all("tr") if _closest_table(tr) is node]
    grid: list[list[object]] = []

    for r_idx, row in enumerate(rows):
        while len(grid) <= r_idx:
            grid.append([])
        c_idx = 0
        for cell in row.find_all(["th", "td"], recursive=False):
            rowspan = _span(cell, "rowspan")
            colspan = _span(cell, "colspan")
            text = _cell_text(cell)

            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not _EMPTY:
                c_idx += 1

            for r in range(rowspan):
                target_r = r_idx + r
                while len(grid) <= target_r:
                    grid.append([])
                target_row = grid[target_r]
                for c in range(colspan):
                    target_c = c_idx + c
                    while len(target_row) <= target_c:
                        target_row.append(_EMPTY)
                    target_row[target_c] = text
            c_idx += colspan

    # Trailing rows created solely by an over-long rowspan are dropped; the rest is padded.
    while grid and all(v is _EMPTY for v in grid[-1]):
        grid.pop()
    width = max((len(r) for r in grid), default=0)
    return [
        [("" if v is _EMPTY else str(v)) for v in row] + [""] * (width - len(row))
        for row in grid
    ]


def _closest_table(tag: Tag) -> Tag | None:
    parent = tag.parent
    while parent is not None and parent.name != "table":
        parent = parent.parent
    return parent


@dataclass
class Table:
    """A flattened table plus the context needed to interpret it."""

    index: int
    grid: list[list[str]]
    caption: str = ""
    context_before: str = ""  # nearby text preceding the table (title / unit hint)
    unit_text: str = ""  # raw unit phrase like "(단위 : 백만원)" if found nearby
    html: str = ""
    meta: dict[str, object] = field(default_factory=dict)

    @property
    def n_rows(self) -> int:
        return len(self.grid)

    @property
    def n_cols(self) -> int:
        return len(self.grid[0]) if self.grid else 0

    def to_markdown(self) -> str:
        return grid_to_markdown(self.grid)


def _preceding_text(table: Tag, max_blocks: int = 4) -> str:
    """Collect text from a few block elements before the table (titles, unit hints)."""
    chunks: list[str] = []
    node: Tag | None = table
    while node is not None and len(chunks) < max_blocks:
        prev = node.find_previous_sibling()
        if prev is None:
            parent = node.parent
            node = parent if parent is not None and parent.name != "[document]" else None
            continue
        if prev.name == "table":
            break
        text = normalize_text(prev.get_text(" "))
        if text:
            chunks.append(text)
        node = prev
    return " | ".join(reversed(chunks))


def extract_tables(html: str, *, min_rows: int = 1) -> list[Table]:
    """Clean the document and return every table flattened to a grid, in document order."""
    soup = clean_soup(BeautifulSoup(html, "lxml"))
    tables: list[Table] = []
    for i, node in enumerate(soup.find_all("table")):
        grid = flatten_table_to_grid(node)
        if len(grid) < min_rows:
            continue
        caption_tag = node.find("caption")
        caption = normalize_text(caption_tag.get_text(" ")) if caption_tag else ""
        context = _preceding_text(node)
        unit_text = ""
        for candidate in (caption, context, " ".join(grid[0]) if grid else ""):
            if _UNIT_HINT_RE.search(candidate):
                unit_text = candidate
                break
        tables.append(
            Table(
                index=i,
                grid=grid,
                caption=caption,
                context_before=context,
                unit_text=unit_text,
                html=str(node),
            )
        )
    return tables


def grid_to_markdown(grid: list[list[str]]) -> str:
    """Render a grid as a GitHub-flavoured markdown table (used for LLM prompts)."""
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    rows = [r + [""] * (width - len(r)) for r in grid]

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    header = "| " + " | ".join(esc(c) for c in rows[0]) + " |"
    sep = "|" + "|".join(" --- " for _ in range(width)) + "|"
    body = ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join([header, sep, *body])
