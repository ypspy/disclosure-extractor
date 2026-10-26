"""Orchestrate normalize -> rule engine -> validation -> optional SLM fallback."""

from __future__ import annotations

from dataclasses import dataclass

from dart_parser.config.settings import Settings, get_settings
from dart_parser.fallback.llm_client import extract_with_slm
from dart_parser.fallback.schemas import StandardExtraction, empty_standard
from dart_parser.normalizer.table_grid import Table, extract_tables
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.accounts import extract_accounts
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
        ctx = ExtractionContext(html=html, rcept_no=rcept_no, tables=tables)
        extraction.accounts = extract_accounts(ctx)

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

    def _run_fallback(self, tables: list[Table], extraction: StandardExtraction) -> bool:
        if not tables:
            return False
        extract_with_slm(tables[0].to_markdown())
        extraction.source = "hybrid"
        return True
