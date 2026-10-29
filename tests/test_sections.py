from dart_parser.fallback.schemas import (
    ExtractionStatus,
    item_missing,
    item_not_applicable,
    item_not_in_regime,
)
from dart_parser.parser import ExtractionContext
from dart_parser.parser import locate_sections as exported_locate_sections
from dart_parser.parser.sections import locate_sections

COVER_AND_EXHIBIT = """
<h1>감사보고서</h1>
<p>제5기 2024.01.01부터 2024.12.31까지</p>
<h2>독립된 감사인의 감사보고서</h2>
<p>의견 적정</p>
<h2>별지 제4호</h2>
<h3>2. 감사 투입 인력 및 시간</h3>
<table><tr><td>품질관리검토자</td></tr></table>
<h3>3. 주요 감사 실시 내용</h3>
<p>전반감사계획</p>
<h3>4. 감사위원회와의 커뮤니케이션</h3>
<p>제1회</p>
"""


def test_status_helper_is_not_failure() -> None:
    item = item_not_in_regime()
    assert item.status is ExtractionStatus.not_in_regime
    assert item.value is None


def test_locate_sections_splits_exhibit4() -> None:
    sections = locate_sections(COVER_AND_EXHIBIT)
    assert "품질관리검토자" in sections["exhibit4_hours"]
    assert "전반감사계획" in sections["exhibit4_activities"]
    assert "제1회" in sections["exhibit4_communications"]
    assert "적정" in sections["opinion_letter"]
    assert "제5기" in sections["cover"]
    assert "전반감사계획" not in sections["exhibit4_hours"]
    assert "제1회" not in sections["exhibit4_activities"]
    assert "품질관리검토자" not in sections["opinion_letter"]
    assert "적정" not in sections["cover"]
    assert "제5기" not in sections["opinion_letter"]
    for key in (
        "bs",
        "is_",
        "icfr_opinion",
        "going_concern",
        "subsidiaries",
        "notes_toc",
    ):
        assert sections[key] == ""


def test_other_status_helpers_keep_value_empty() -> None:
    missing = item_missing()
    skipped = item_not_applicable()
    assert missing.status is ExtractionStatus.missing
    assert missing.value is None
    assert skipped.status is ExtractionStatus.not_applicable
    assert skipped.value is None


def test_numbered_anchors_stop_at_higher_heading() -> None:
    html = """
    <h3 style="color:red">2.&nbsp;투입 시간</h3>
    <p>시간표</p>
    <h4>세부</h4>
    <p>세부본문</p>
    <h2>재무상태표</h2>
    <p>자산총계</p>
    <h3>3. 절차</h3>
    <p>절차본문</p>
    <h3>4. 위원회</h3>
    <p>회차</p>
    """
    sections = locate_sections(html)
    assert "시간표" in sections["exhibit4_hours"]
    assert "세부본문" in sections["exhibit4_hours"]
    assert "자산총계" not in sections["exhibit4_hours"]
    assert "절차본문" in sections["exhibit4_activities"]
    assert "회차" not in sections["exhibit4_activities"]
    assert "회차" in sections["exhibit4_communications"]
    assert sections["cover"] == ""
    assert sections["is_"] == ""


DART_P_SECTIONS = """
<p>삼성전자주식회사</p>
<p>감 사 보 고 서</p>
<p>제 55 기</p>
<p>2023년 01월 01일부터 2023년 12월 31일까지</p>
<p class="section-1"><a name="toc1">독립된 감사인의 감사보고서</a></p>
<p>의견은 적정입니다. 2024년 2월 19일</p>
<p>우리는 지배기구와 커뮤니케이션합니다.</p>
<p class="section-1"><a name="toc1">내부회계관리제도 감사 또는 검토의견</a></p>
<p>내부회계관리제도 감사보고서 적정</p>
<p class="section-2">2. 감사참여자 구분별 인원수 및 감사시간</p>
<p>품질관리검토자</p>
<p class="section-2">3. 주요 감사실시내용</p>
<p>전반감사계획</p>
<p class="section-2">4. 감사(감사위원회)와의 커뮤니케이션</p>
<p>제1회</p>
<p class="section-1"><a name="toc2">주석</a></p>
<p>1. 회사의 개요</p>
"""


def test_dart_paragraph_toc_splits_windows() -> None:
    sections = locate_sections(DART_P_SECTIONS)
    assert "제 55 기" in sections["cover"]
    assert "적정" in sections["opinion_letter"]
    assert "품질관리검토자" in sections["exhibit4_hours"]
    assert "전반감사계획" in sections["exhibit4_activities"]
    assert "제1회" in sections["exhibit4_communications"]
    assert "내부회계관리제도 감사보고서" in sections["icfr_opinion"]
    assert "회사의 개요" in sections["notes_toc"]
    assert "제1회" not in sections["exhibit4_activities"]
    assert "전반감사계획" not in sections["exhibit4_hours"]
    assert "품질관리검토자" not in sections["opinion_letter"]


def test_long_paragraph_mentioning_communication_is_not_a_heading() -> None:
    html = """
    <p class="section-1">독립된 감사인의 감사보고서</p>
    <p>우리는 여러 가지 사항들 중에서 계획된 감사범위와 시기 그리고 감사 중 식별된
    유의적 내부통제 미비점 등 유의적인 감사의 발견사항에 대하여 지배기구와 커뮤니케이션합니다.</p>
    <p>적정 의견</p>
    """
    sections = locate_sections(html)
    assert "커뮤니케이션합니다" in sections["opinion_letter"]
    assert sections["exhibit4_communications"] == ""


def test_context_defaults_are_not_shared() -> None:
    first = ExtractionContext(html="a")
    second = ExtractionContext(html="b")
    first.sections["cover"] = "표지"
    assert second.sections == {}
    assert first.tables == []
    assert second.tables == []
    assert first.rcept_no is None
    assert first.fs_scope is None
    assert first.fiscal_year is None
    assert first.corp_form is None
    assert exported_locate_sections is locate_sections
    assert set(locate_sections("")) == {
        "cover",
        "opinion_letter",
        "exhibit4_hours",
        "exhibit4_activities",
        "exhibit4_communications",
        "bs",
        "is_",
        "icfr_opinion",
        "going_concern",
        "subsidiaries",
        "notes_toc",
    }
