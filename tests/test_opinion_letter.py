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


def test_fairly_presents_in_opinion_paragraph_is_unqualified() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 별첨된 회사의 재무제표는 일반기업회계기준에 따라
    중요성의 관점에서 공정하게 표시하고 있습니다.</p>
    <p>감사의견근거 우리는 대한민국의 회계감사기준에 따라 감사를 수행하였습니다.</p>
    <p>2025년 12월 30일</p>
    <p>정 명 회 계 법 인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.value == "적정"
    assert out.auditor.value == "정명회계법인"


def test_prior_year_unqualified_citation_is_not_current_opinion() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리는 재무제표를 감사하였습니다.</p>
    <p>이 감사인의 2024년 3월 10일자 감사보고서에는 적정의견이 표명되었습니다.</p>
    <p>2025년 3월 10일</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.opinion.status is ExtractionStatus.missing
    assert out.opinion.value is None


def test_auditor_before_closing_boilerplate_is_kept() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>한영회계법인</p>
    <p>이 감사보고서는 감사보고서일 후 이 보고서를 열람하는 시점 사이에
    첨부된 회사의 재무제표에 중요한 영향을 미칠 수 있는 사건이나 상황이
    발생할 수도 있으며 이로 인하여 이 감사보고서가 수정될 수도 있습니다.</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "한영회계법인"


def test_firm_name_after_hoegyebeobin_is_the_auditor() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>서울특별시 송파구 백제고분로 364</p>
    <p>회 계 법 인 세 진</p>
    <p>대표이사 박 영 웅</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "회계법인세진"


def test_single_syllable_firm_before_hoegyebeobin_is_the_auditor() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>참 회 계 법 인</p>
    <p>대 표 이 사 김 성 균</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "참회계법인"


def test_spaced_signature_firm_with_address_is_the_auditor() -> None:
    html = """
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>서울특별시 금천구 벚꽃로 36길 30, 1515호</p>
    <p>태 림 회 계 법 인</p>
    <p>대 표 이 사 김 병 욱</p>
    <p>2026년 2월 6일</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    out = extract_opinion_letter(ctx)
    assert out.auditor.value == "태림회계법인"


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


def test_cover_firm_is_used_when_letter_has_no_firm() -> None:
    html = """
    <p>주식회사 리야드</p>
    <p>재 무 제 표 에 대 한</p>
    <p>감 사 보 고 서</p>
    <p>제19 기</p>
    <p>2025년 12월 31일까지</p>
    <p>일 우 회 계 법 인</p>
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>이 감사보고서는 감사보고서일 후 수정될 수도 있습니다.</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "일우회계법인"


def test_letter_firm_wins_over_cover_firm() -> None:
    html = """
    <p>일 우 회 계 법 인</p>
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    <p>한영회계법인</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "한영회계법인"


def test_cover_cpa_audit_ban_drops_registration_number() -> None:
    html = """
    <p>주식회사 대일씨에프티</p>
    <p>감 사 보 고 서</p>
    <p>2025년 12월 31일까지</p>
    <p>다 일(제 375 호) 공인회계사 감 사 반</p>
    <h2>독립된 감사인의 감사보고서</h2>
    <p>우리의 의견으로는 재무제표는 공정하게 표시하고 있습니다.</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    assert extract_opinion_letter(ctx).auditor.value == "다일공인회계사감사반"
