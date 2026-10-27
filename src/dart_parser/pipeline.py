"""Orchestrate normalize -> rule engine -> validation -> optional SLM fallback."""

from __future__ import annotations

from dataclasses import dataclass

from dart_parser.config.settings import Settings, get_settings
from dart_parser.fallback.llm_client import extract_with_slm
from dart_parser.fallback.schemas import StandardExtraction, empty_standard
from dart_parser.normalizer.table_grid import Table, extract_tables
from dart_parser.parser.context import CorpForm, ExtractionContext
from dart_parser.parser.extractors.accounts import extract_accounts
from dart_parser.parser.extractors.activities import extract_activities
from dart_parser.parser.extractors.communications import extract_communications
from dart_parser.parser.extractors.going_concern import extract_going_concern
from dart_parser.parser.extractors.hours import extract_hours, validate_hours
from dart_parser.parser.extractors.icfr import extract_icfr
from dart_parser.parser.extractors.identification import extract_identification
from dart_parser.parser.extractors.notes_toc import extract_notes_toc
from dart_parser.parser.extractors.opinion_letter import extract_opinion_letter
from dart_parser.parser.extractors.subsidiary import extract_subsidiary
from dart_parser.parser.sections import locate_sections
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
        corp_form: CorpForm | None = None,
    ) -> PipelineResult:
        cfg = self.settings or get_settings()
        tables = extract_tables(html)
        sections = locate_sections(html)
        ctx = ExtractionContext(
            html=html,
            rcept_no=rcept_no,
            corp_form=corp_form,
            tables=tables,
            sections=sections,
        )

        extraction = empty_standard(rcept_no=rcept_no)
        extraction.source = "rule"
        _apply_identification(ctx, extraction)
        _apply_opinion(ctx, extraction)
        extraction.accounts = extract_accounts(ctx)
        extraction.hours = extract_hours(ctx)
        extraction.activities = extract_activities(ctx)
        extraction.communications = extract_communications(ctx)
        extraction.icfr = extract_icfr(ctx)
        extraction.going_concern = extract_going_concern(ctx)
        extraction.subsidiary = extract_subsidiary(ctx)
        extraction.notes_toc = extract_notes_toc(ctx)

        validation = _validate(extraction)
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


def _apply_identification(ctx: ExtractionContext, extraction: StandardExtraction) -> None:
    ident = extract_identification(ctx)
    ctx.fs_scope = ident.fs_scope
    period = ident.current_period.value
    if period is not None and period.end:
        ctx.fiscal_year = int(period.end[:4])
    extraction.fs_scope = ident.fs_scope
    extraction.company_name = ident.company_name
    extraction.document_title = ident.document_title
    extraction.fiscal_term = ident.fiscal_term
    extraction.current_period = ident.current_period


def _apply_opinion(ctx: ExtractionContext, extraction: StandardExtraction) -> None:
    letter = extract_opinion_letter(ctx)
    extraction.auditor = letter.auditor
    extraction.opinion = letter.opinion
    extraction.gaap = letter.gaap
    extraction.audit_report_date = letter.audit_report_date


def _validate(extraction: StandardExtraction) -> ValidationResult:
    accounts = validate_accounts(extraction.accounts.value)
    hours = (
        validate_hours(extraction.hours.value)
        if extraction.hours.value is not None
        else ValidationResult(ok=True)
    )
    if accounts.ok and hours.ok:
        return ValidationResult(ok=True)
    return ValidationResult(ok=False, issues=[*accounts.issues, *hours.issues])
