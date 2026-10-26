# tests/test_identification.py
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.identification import extract_identification
from dart_parser.parser.sections import locate_sections

HTML = """
<p>주식회사 예시</p>
<p>감사보고서</p>
<p>제5기 2024.01.01부터 2024.12.31까지</p>
"""


def test_extracts_cover_fields_and_separate_scope() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    result = extract_identification(ctx)
    assert result.company_name.value == "주식회사 예시"
    assert result.document_title.value == "감사보고서"
    assert result.fiscal_term.value == "제5기"
    assert result.current_period.value is not None
    assert result.current_period.value.start == "2024-01-01"
    assert result.current_period.value.end == "2024-12-31"
    assert result.fs_scope == "separate"


def test_consolidated_title_sets_scope() -> None:
    html = "<p>연결감사보고서</p><p>제3기 2023.01.01부터 2023.12.31까지</p>"
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_identification(ctx).fs_scope == "consolidated"
