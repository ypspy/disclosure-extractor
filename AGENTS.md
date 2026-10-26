# AGENTS.md - DART Hybrid Parser Project Guidelines

## Project Mission
Extract structured data from irregular DART disclosure documents using a multi-tiered pipeline:
`API Fetch (TOC/XBRL) -> HTML & Table Normalization -> Anchor-based Rule Engine -> Validation -> Fallback to SLM (Small Language Model)`.

The first extraction task is `standard` (see `docs/standard-extraction-items.md`): identification fields,
the 12 bundles (`auditor`, `opinion`, `gaap`, `audit_report_date`, `current_period`, `hours`, `activities`,
`communications`, `accounts` (13 lines including revenue and operating income), `icfr`, `going_concern`,
`subsidiary`) plus the notes TOC.

## Role & Engineering Principles
1. **Never parse styles:** Ignore font, color, margin, and layout tags. Treat HTML strictly as semantic structures.
2. **Flatten first, then parse:** Never attempt regex or selector navigation on unflattened `colspan` or `rowspan`. Expand them into a 2D coordinate grid first (`normalizer/table_grid.py`).
3. **XBRL Priority:** For financial statements, prioritize Open DART XBRL API before falling back to HTML parsing.
4. **Deterministic over Stochastic:** Maximize rule-based parsing accuracy. Small LLM fallback should only be invoked when validation fails or table shapes break heuristics.
5. **Strict Schema Output:** LLM outputs and rule engine outputs must both strictly conform to the Pydantic schemas in `fallback/schemas.py`.
6. **Missing is not failure-by-default:** Distinguish `missing` (item exists in the regime but was not found: counts as a failure), `not_applicable`, and `not_in_regime` (older disclosures without the section). Never silently coerce one into another.

## Tech Stack & Dependencies
- **Language:** Python 3.11+ (package lives in `src/dart_parser/`, src-layout)
- **Parsing/HTML:** `lxml`, `beautifulsoup4`, `html5lib`
- **Data & Numeric:** `pandas`, `pydantic>=2.0`, `rapidfuzz` (for anchor matching)
- **LLM/Fallback:** `instructor`, `openai` SDK pointed at an OpenAI-compatible endpoint (Ollama / vLLM)
- **Config:** `pydantic-settings`, values from `.env` (see `.env.example`)
- **Testing:** `pytest` (`python -m pytest`)

## Code Conventions
- Use type hints on all function signatures.
- Write defensive parsers: all cell conversions must go through `to_number()` (`normalizer/numeric.py`), which handles commas, dashes, `△`/`▲`/parentheses negatives, non-breaking and full-width spaces.
- Normalize text with `normalize_text()` before any keyword/anchor comparison.
- Unit tests must be written alongside parser implementations using mock HTML snippets in `tests/`. Real DART snapshots go in `tests/sample_htmls/`.
- Amounts are stored as `Amount(raw, value, unit_scale, value_won)`. Never store a scaled number without its scale.
- Keep modules side-effect free at import time; no network calls or LLM calls outside `fetcher/` and `fallback/`.
- Run `python -m pytest` and `ruff check .` before finishing a change.
