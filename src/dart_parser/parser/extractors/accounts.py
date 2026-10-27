"""13 research accounts from balance-sheet and income-statement grids.

HTML only. Open DART XBRL is a later step and must keep this signature,
filling the same ``Item[Accounts]`` with ``source="xbrl"``.
"""

from __future__ import annotations

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
from dart_parser.normalizer.table_grid import Table
from dart_parser.parser.anchor_matcher import canonical, find_rows
from dart_parser.parser.context import ExtractionContext, FsScope
from dart_parser.parser.lexicon import ACCOUNT_ALIASES, account_label_rejected
from dart_parser.parser.rule_engine import (
    RuleEngine,
    TableSpec,
    detect_period_columns,
    infer_header_row_count,
    stacked_header_labels,
)

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
    _fill(accounts, _candidate_tables(ctx.tables, "bs", ctx.fs_scope), _BS_KEYS, evidence)
    _fill(accounts, _candidate_tables(ctx.tables, "is", ctx.fs_scope), _IS_KEYS, evidence)
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
            if getattr(accounts, key) is not None:
                continue
            setattr(accounts, key, line)
            wrote = True
        if not wrote:
            continue
        hint = table.unit_text or table.context_before or table.caption
        if hint and hint not in evidence:
            evidence.append(hint)


def _candidate_tables(
    tables: list[Table],
    kind: str,
    fs_scope: FsScope | None,
) -> list[Table]:
    typed = [table for table in tables if _statement_kind(table) == kind]
    pool = typed if typed else [table for table in tables if _statement_kind(table) == "other"]
    return _prefer_consolidated(pool, fs_scope)


def _title_text(table: Table) -> str:
    """Caption and preceding text, compared the same way as row labels."""
    return canonical(f"{table.caption}\n{table.context_before}")


def _title_contains(table: Table, *needles: str) -> bool:
    text = _title_text(table)
    return any(token and canonical(token) in text for token in needles)


def _statement_kind(table: Table) -> str:
    has_is = _title_contains(table, "손익")
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
    periods = detect_period_columns(header_labels)
    if "current" not in periods:
        return {}
    column_anchors = {
        period: [header_labels[idx]]
        for period, idx in periods.items()
        if idx < len(header_labels)
    }
    engine = RuleEngine()
    used_rows: set[int] = set()
    lines: dict[str, AccountLine] = {}
    for key in keys:
        aliases = ACCOUNT_ALIASES.get(key)
        if not aliases:
            continue
        grid = _grid_without_rejected_labels(table.grid, key, header_n, used_rows)
        filtered = replace(table, grid=grid)
        matrix = engine.extract(
            filtered,
            TableSpec(
                name="accounts",
                column_anchors=column_anchors,
                row_anchors={key: aliases},
                header_row_count=header_n,
            ),
        )
        cells = matrix.get(key)
        row_idx = find_rows(grid, {key: aliases}, start_row=header_n).get(key)
        if not cells or row_idx is None:
            continue
        used_rows.add(row_idx)
        label = table.grid[row_idx][0]
        current = cells.get("current")
        prior = cells.get("prior")
        if _is_loss_label(label):
            current = _negate_if_positive(current)
            prior = _negate_if_positive(prior)
        lines[key] = AccountLine(current=current, prior=prior)
    return lines


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


def _is_loss_label(label: str) -> bool:
    text = canonical(label)
    return any(marker in text for marker in _LOSS_MARKERS)


def _negate_if_positive(amount: Amount | None) -> Amount | None:
    if amount is None or amount.value is None or amount.value <= 0:
        return amount
    won = None if amount.value_won is None else -amount.value_won
    return amount.model_copy(update={"value": -amount.value, "value_won": won})
