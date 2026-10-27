# tests/test_opinion_letter.py
from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.opinion_letter import extract_opinion_letter
from dart_parser.parser.sections import locate_sections

HTML = """
<h2>독립된 감사인의 감사보고서</h2>
<p>우리는 한국채택국제회계기준에 따라 작성된 재무제표를 감사하였습니다.</p>
<p>우리의 의견으로는 재무제표는 적정하게 표시하고 있습니다.</p>
<p>2025년 3월 10일</p>
<p>한영회계법인</p>
"""


def test_opinion_letter_fields() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    out = extract_opinion_letter(ctx)
    assert out.auditor.value == "한영회계법인"
    assert out.opinion.value == "적정"
    assert out.gaap.value is not None
    assert out.gaap.value.code == "K-IFRS"
    assert "한국채택국제회계기준" in out.gaap.value.raw
    assert out.audit_report_date.value == "2025-03-10"


def test_audit_report_date_missing_without_date_sentence() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리는 한국채택국제회계기준에 따라 작성된 재무제표를 감사하였습니다.</p>
    <p>우리의 의견으로는 재무제표는 적정하게 표시하고 있습니다.</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.audit_report_date.status is ExtractionStatus.missing
    assert out.audit_report_date.value is None


def test_audit_report_date_is_the_last_date_in_the_window() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>2024년 1월 2일 현재의 재무상태표를 감사하였습니다.</p>
    <p>적정하게 표시하고 있습니다.</p>
    <p>2025년 3월 5일</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.audit_report_date.value == "2025-03-05"


def test_empty_opinion_window_does_not_guess_report_date() -> None:
    html = """
    <p>우리는 한국채택국제회계기준에 따라 감사하였습니다.</p>
    <p>적정하게 표시하고 있습니다.</p>
    <p>2025년 3월 10일</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert ctx.sections["opinion_letter"] == ""
    out = extract_opinion_letter(ctx)
    assert out.audit_report_date.status is ExtractionStatus.missing
    assert out.audit_report_date.value is None
    assert out.opinion.value == "적정"
    assert out.auditor.value == "한영회계법인"
    assert out.gaap.value is not None
    assert out.gaap.value.code == "K-IFRS"


def test_adverse_opinion_is_not_read_as_unqualified() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>재무제표가 부적정하게 표시되어 있습니다.</p>
    <p>2025년 3월 10일</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.value == "부적정"
    assert out.opinion.status is ExtractionStatus.found


def test_disclaimer_alias_maps_to_rejection_code() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리는 의견거절을 표명합니다.</p>
    <p>2025년 3월 10일</p>
    <p>한영감사반</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.value == "거절"
    assert out.auditor.value == "한영감사반"


def test_qualified_wording_is_not_a_financial_statement_opinion() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리는 한정의견을 표명합니다.</p>
    <p>2025년 3월 10일</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.status is ExtractionStatus.missing
    assert out.opinion.value is None


def test_opinion_window_ignores_a_later_heading() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리는 일반기업회계기준에 따라 작성된 재무제표를 감사하였습니다.</p>
    <p>재무제표는 적정하게 표시하고 있습니다.</p>
    <p>2025년 3월 10일</p>
    <p>삼일회계법인</p>
    <h2>내부회계관리제도에 대한 감사의견</h2>
    <p>내부회계관리제도는 부적정합니다.</p>
    <p>2025년 3월 18일</p>
    <p>다른회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.value == "적정"
    assert out.auditor.value == "삼일회계법인"
    assert out.gaap.value is not None
    assert out.gaap.value.code == "K-GAAP"
    assert "일반기업회계기준" in out.gaap.value.raw
    assert out.audit_report_date.value == "2025-03-10"
