"""13 research accounts from balance-sheet and income-statement grids.

HTML only. Open DART XBRL is a later step and must keep this signature,
filling the same ``Item[Accounts]`` with ``source="xbrl"``.
"""

from __future__ import annotations

import re
from dataclasses import replace

from dart_parser.fallback.schemas import (
    ACCOUNT_KEYS,
    AccountLine,
    Accounts,
    Amount,
    Item,
    found,
    item_missing,
)
from dart_parser.normalizer.numeric import to_number
from dart_parser.normalizer.table_grid import Table
from dart_parser.parser.anchor_matcher import canonical, find_rows
from dart_parser.parser.context import ExtractionContext, FsScope
from dart_parser.parser.lexicon import ACCOUNT_ALIASES, account_label_rejected
from dart_parser.parser.rule_engine import (
    infer_header_row_count,
    period_column_groups,
    stacked_header_labels,
)
from dart_parser.parser.unit_extractor import extract_unit

_BS_KEYS = ACCOUNT_KEYS[:10]
_IS_KEYS = ACCOUNT_KEYS[10:]
_LOSS_MARKERS = ("당기순손실", "영업손실")


def extract_accounts(ctx: ExtractionContext) -> Item[Accounts]:
    """Read FS lines from balance-sheet tables and IS lines from income-statement tables.

    A table with neither statement title is a candidate for both. When ``fs_scope``
    is consolidated, a table whose caption or preceding text contains ``연결`` wins.
    Title checks use ``canonical``, so spaced headings such as ``재 무 상 태 표`` match.
    """
    if not ctx.tables:
        return item_missing()

    accounts = Accounts()
    evidence: list[str] = []
    labeled = _label_tables(ctx.tables)
    _fill(accounts, _candidate_tables(labeled, "bs", ctx.fs_scope), _BS_KEYS, evidence)
    _fill(accounts, _candidate_tables(labeled, "is", ctx.fs_scope), _IS_KEYS, evidence)
    if not any(getattr(accounts, key) is not None for key in ACCOUNT_KEYS):
        return item_missing()
    return found(accounts, source="rule", evidence=" | ".join(evidence) or None)


def _fill(
    accounts: Accounts,
    tables: list[Table],
    keys: tuple[str, ...],
    evidence: list[str],
) -> None:
    for table in tables:
        wrote = False
        for key, line in _lines_from_table(table, keys).items():
            existing = getattr(accounts, key)
            if existing is not None and _has_current_amount(existing):
                continue
            if existing is not None and not _has_current_amount(line):
                continue
            setattr(accounts, key, line)
            wrote = True
        if not wrote:
            continue
        hint = table.unit_text or table.context_before or table.caption
        if hint and hint not in evidence:
            evidence.append(hint)


def _label_tables(tables: list[Table]) -> list[tuple[Table, str]]:
    """Pair a title-only banner with the next amount grid of the same statement."""
    labeled: list[tuple[Table, str]] = []
    pending: str | None = None
    previous: Table | None = None
    for table in tables:
        kind = _statement_kind(table)
        if kind != "other":
            pending = kind
            labeled.append((_with_unit(table, previous), kind))
            previous = table
            continue
        if pending is not None and _looks_like_amount_grid(table):
            labeled.append((_with_unit(table, previous), pending))
            pending = None
        else:
            labeled.append((_with_unit(table, previous), "other"))
        previous = table
    return labeled


def _candidate_tables(
    labeled: list[tuple[Table, str]],
    kind: str,
    fs_scope: FsScope | None,
) -> list[Table]:
    typed = [table for table, label in labeled if label == kind]
    pool = typed if typed else [table for table, label in labeled if label == "other"]
    return _prefer_consolidated(pool, fs_scope)


def _title_text(table: Table) -> str:
    """Caption, preceding text, and the first grid rows — DART puts the title in its own table."""
    head = " ".join(cell for row in table.grid[:2] for cell in row)
    return canonical(f"{table.caption}\n{table.context_before}\n{head}")


def _looks_like_amount_grid(table: Table) -> bool:
    if table.n_rows < 2 or table.n_cols < 3:
        return False
    header = canonical(" ".join(table.grid[0]))
    return "당기" in header or "전기" in header or bool(re.search(r"제\d+기", header))


def _with_unit(table: Table, previous: Table | None) -> Table:
    if table.unit_text:
        return table
    hint = _unit_hint(table) or (None if previous is None else _unit_hint(previous))
    if not hint:
        return table
    return replace(table, unit_text=hint)


def _unit_hint(table: Table) -> str:
    for blob in (table.unit_text, table.context_before, table.caption):
        if blob and "단위" in blob:
            return blob
    for row in table.grid[:4]:
        joined = " ".join(row)
        if "단위" in joined:
            return joined
    return ""


def _title_contains(table: Table, *needles: str) -> bool:
    text = _title_text(table)
    return any(token and canonical(token) in text for token in needles)


def _statement_kind(table: Table) -> str:
    has_is = _title_contains(table, "손익계산서")
    has_bs = _title_contains(table, "재무상태표", "대차대조표")
    if has_is and not has_bs:
        return "is"
    if has_bs and not has_is:
        return "bs"
    return "other"


def _prefer_consolidated(tables: list[Table], fs_scope: FsScope | None) -> list[Table]:
    if fs_scope != "consolidated":
        return tables
    linked = [table for table in tables if _title_contains(table, "연결")]
    return linked or tables


def _lines_from_table(table: Table, keys: tuple[str, ...]) -> dict[str, AccountLine]:
    if table.n_rows < 2:
        return {}
    header_n = infer_header_row_count(table.grid)
    header_labels = stacked_header_labels(table.grid, header_n)
    periods = period_column_groups(header_labels)
    if "current" not in periods:
        return {}
    unit = extract_unit(table.unit_text or table.context_before or table.caption)
    used_rows: set[int] = set()
    lines: dict[str, AccountLine] = {}
    for key in keys:
        aliases = ACCOUNT_ALIASES.get(key)
        if not aliases:
            continue
        grid = _grid_without_rejected_labels(table.grid, key, header_n, used_rows)
        row_idx = find_rows(grid, {key: aliases}, start_row=header_n).get(key)
        if row_idx is None:
            continue
        used_rows.add(row_idx)
        row = table.grid[row_idx]
        label = row[0] if row else ""
        current = _amount_in_cols(row, periods.get("current"), unit.scale)
        prior = _amount_in_cols(row, periods.get("prior"), unit.scale)
        if current is None and prior is None:
            continue
        if _is_loss_label(label):
            current = _negate_if_positive(current)
            prior = _negate_if_positive(prior)
        lines[key] = AccountLine(current=current, prior=prior)
    return lines


def _amount_in_cols(
    row: list[str],
    cols: list[int] | None,
    unit_scale: int,
) -> Amount | None:
    """First numeric cell among flattened duplicate period columns."""
    if not cols:
        return None
    for col in cols:
        if col >= len(row):
            continue
        if to_number(row[col]) is None:
            continue
        return Amount.from_cell(row[col], unit_scale=unit_scale)
    return None


def _grid_without_rejected_labels(
    grid: list[list[str]],
    key: str,
    header_n: int,
    used_rows: set[int],
) -> list[list[str]]:
    """Blank labels that must not match ``key``, before anchor matching runs."""
    filtered = [list(row) for row in grid]
    for i in range(header_n, len(filtered)):
        if not filtered[i]:
            continue
        if i in used_rows or account_label_rejected(key, filtered[i][0]):
            filtered[i][0] = ""
    return filtered


def _has_current_amount(line: AccountLine) -> bool:
    return line.current is not None and line.current.value is not None


def _is_loss_label(label: str) -> bool:
    text = canonical(label)
    return any(marker in text for marker in _LOSS_MARKERS)


def _negate_if_positive(amount: Amount | None) -> Amount | None:
    if amount is None or amount.value is None or amount.value <= 0:
        return amount
    won = None if amount.value_won is None else -amount.value_won
    return amount.model_copy(update={"value": -amount.value, "value_won": won})
