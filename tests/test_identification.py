# tests/test_identification.py
from dart_parser.fallback.schemas import ExtractionStatus
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


def test_spaced_cover_title_and_korean_dates_win_over_exhibit_dots() -> None:
    html = """
    <p>삼성전자주식회사</p>
    <p>재 무 제 표 에 대 한</p>
    <p>감 사 보 고 서</p>
    <p>제 55 기</p>
    <p>2023년 01월 01일부터 2023년 12월 31일까지</p>
    <p class="section-1">독립된 감사인의 감사보고서</p>
    <p>적정</p>
    <p class="section-2">3. 주요 감사실시내용</p>
    <p>수행시기 2023.03.06 ~ 2023.09.30</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    result = extract_identification(ctx)
    assert result.document_title.value == "감사보고서"
    assert result.fs_scope == "separate"
    assert result.fiscal_term.value == "제55기"
    assert result.current_period.value is not None
    assert result.current_period.value.start == "2023-01-01"
    assert result.current_period.value.end == "2023-12-31"


def test_cover_term_with_parenthetical_dang_is_found() -> None:
    html = """
    <p>주식회사 성창에프앤지</p>
    <p>재 무 제 표 에 대 한 감 사 보 고 서</p>
    <p>제 26(당) 기 2024년 10월 01일부터 2025년 09월 30일까지</p>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    result = extract_identification(ctx)
    assert result.fiscal_term.value == "제26기"


def test_yuhan_and_spaced_jusik_company_lines_are_found() -> None:
    yuhan = "<p>하니웰유오피코리아 유한회사</p><p>감사보고서</p><p>제 10 기</p>"
    spaced = "<p>주 식 회 사 랜드파트너스</p><p>감사보고서</p><p>제 16(당)기</p>"
    yuhan_out = extract_identification(
        ExtractionContext(html=yuhan, sections=locate_sections(yuhan))
    )
    spaced_out = extract_identification(
        ExtractionContext(html=spaced, sections=locate_sections(spaced))
    )
    assert yuhan_out.company_name.value == "하니웰유오피코리아 유한회사"
    assert spaced_out.company_name.status is ExtractionStatus.found
    assert "랜드파트너스" in (spaced_out.company_name.value or "")


def test_investment_company_and_hanja_jusik_are_found() -> None:
    ship = "<p>지엠에프십칠호선박투자회사</p><p>감사보고서</p><p>제 2(당)기</p>"
    hanja = "<p>世旺商事 株式會社</p><p>감사보고서</p><p>제 48(당)기</p>"
    ship_out = extract_identification(
        ExtractionContext(html=ship, sections=locate_sections(ship))
    )
    hanja_out = extract_identification(
        ExtractionContext(html=hanja, sections=locate_sections(hanja))
    )
    assert ship_out.company_name.value == "지엠에프십칠호선박투자회사"
    assert hanja_out.company_name.status is ExtractionStatus.found
    assert "世旺" in (hanja_out.company_name.value or "")


def test_parenthesized_cieuc_company_prefix_is_found() -> None:
    """U+321C ㈜ is NFKC-normalized to (주) before the company regex runs."""
    html = "<p>㈜예시</p><p>감사보고서</p><p>제5기 2024.01.01부터 2024.12.31까지</p>"
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    result = extract_identification(ctx)
    assert result.company_name.status is ExtractionStatus.found
    assert result.company_name.value == "(주)예시"
