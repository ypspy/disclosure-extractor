"""Orchestrate normalize -> rule engine -> validation -> optional SLM fallback."""

from __future__ import annotations

from dataclasses import dataclass

from dart_parser.config.settings import Settings, get_settings
from dart_parser.fallback.llm_client import extract_with_slm
from dart_parser.fallback.schemas import (
    AccountLine,
    Accounts,
    Amount,
    StandardExtraction,
    empty_standard,
    found,
)
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.table_grid import Table, extract_tables
from dart_parser.parser.anchor_matcher import find_rows
from dart_parser.parser.lexicon import ACCOUNT_ALIASES
from dart_parser.parser.rule_engine import (
    RuleEngine,
    TableSpec,
    detect_period_columns,
    infer_header_row_count,
    stacked_header_labels,
)
from dart_parser.validator.math_validator import ValidationResult, validate_accounts


@dataclass
class PipelineResult:
    extraction: StandardExtraction
    tables: list[Table]
    validation: ValidationResult
    used_fallback: bool = False


class Pipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self.engine = RuleEngine()

    def run_from_html(
        self,
        html: str,
        *,
        rcept_no: str | None = None,
        use_fallback: bool | None = None,
    ) -> PipelineResult:
        cfg = self.settings or get_settings()
        tables = extract_tables(html)
        extraction = empty_standard(rcept_no=rcept_no)
        extraction.source = "rule"

        for table in tables:
            accounts = self._extract_accounts(table)
            if accounts is None:
                continue
            extraction.accounts = found(
                accounts,
                source="rule",
                evidence=table.unit_text or table.context_before or table.caption,
            )
            break

        validation = validate_accounts(extraction.accounts.value)
        should_fallback = cfg.llm_enabled if use_fallback is None else use_fallback
        used_fallback = False
        if not validation.ok and should_fallback:
            used_fallback = self._run_fallback(tables, extraction)

        return PipelineResult(
            extraction=extraction,
            tables=tables,
            validation=validation,
            used_fallback=used_fallback,
        )

    def _extract_accounts(self, table: Table) -> Accounts | None:
        if table.n_rows < 2:
            return None
        header_n = infer_header_row_count(table.grid)
        labels = stacked_header_labels(table.grid, header_n)
        cols = detect_period_columns(labels)
        if "current" not in cols:
            return None
        spec = TableSpec(
            name="accounts",
            column_anchors={key: [labels[idx]] for key, idx in cols.items()},
            row_anchors=ACCOUNT_ALIASES,
            header_row_count=header_n,
        )
        matrix = self.engine.extract(table, spec)
        if not matrix:
            return None
        label_rows = find_rows(table.grid, ACCOUNT_ALIASES, start_row=header_n)
        accounts = Accounts()
        for key, cells in matrix.items():
            current = cells.get("current")
            prior = cells.get("prior")
            row_idx = label_rows.get(key)
            if row_idx is not None and "순손실" in normalize_text(table.grid[row_idx][0]):
                current = _negate_if_positive(current)
                prior = _negate_if_positive(prior)
            setattr(accounts, key, AccountLine(current=current, prior=prior))
        return accounts

    def _run_fallback(self, tables: list[Table], extraction: StandardExtraction) -> bool:
        if not tables:
            return False
        extract_with_slm(tables[0].to_markdown())
        extraction.source = "hybrid"
        return True


def _negate_if_positive(amount: Amount | None) -> Amount | None:
    if amount is None or amount.value is None or amount.value <= 0:
        return amount
    won = None if amount.value_won is None else -amount.value_won
    return amount.model_copy(update={"value": -amount.value, "value_won": won})
