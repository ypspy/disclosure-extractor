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
