from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.icfr import extract_icfr
from dart_parser.parser.sections import locate_sections

LEAF = """
<h2>독립된 감사인의 내부회계관리제도 감사의견</h2>
<p>중요성의 관점에서 효과적으로 설계 및 운영되고 있습니다. 적정</p>
"""


def test_f001_without_leaf_is_not_in_regime() -> None:
    ctx = ExtractionContext(html="<p>감사보고서</p>", corp_form="F001", sections={})
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.not_in_regime
    assert out.icfr_opinion_code is None


def test_f002_fy2022_without_leaf_is_not_in_regime() -> None:
    ctx = ExtractionContext(
        html="<p>연결감사보고서</p>", corp_form="F002", fiscal_year=2022,
        fs_scope="consolidated", sections={},
    )
    assert extract_icfr(ctx).icfr_status is ExtractionStatus.not_in_regime


def test_in_regime_without_leaf_is_missing() -> None:
    ctx = ExtractionContext(
        html="<p>감사보고서</p>", corp_form="F002", fiscal_year=2024, sections={}
    )
    assert extract_icfr(ctx).icfr_status is ExtractionStatus.missing


def test_audit_opinion_from_same_document_leaf() -> None:
    ctx = ExtractionContext(html=LEAF, fiscal_year=2024, sections=locate_sections(LEAF))
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.found
    assert out.icfr_engagement == "audit"
    assert out.icfr_opinion_code == "적정"


def test_audit_report_heading_is_audit_even_if_toc_says_or_review() -> None:
    html = """
    <p class="section-1">내부회계관리제도 감사 또는 검토의견</p>
    <p>독립된 감사인의 내부회계관리제도 감사보고서</p>
    <p>중요성의 관점에서 효과적으로 설계 및 운영되고 있습니다. 적정</p>
    """
    ctx = ExtractionContext(html=html, fiscal_year=2023, sections=locate_sections(html))
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.found
    assert out.icfr_engagement == "audit"
    assert out.icfr_opinion_code == "적정"


def test_boilerplate_material_weakness_is_not_adverse() -> None:
    html = """
    <p class="section-1">내부회계관리제도 감사 또는 검토의견</p>
    <p>독립된 감사인의 내부회계관리제도 감사보고서</p>
    <p>우리의 의견으로는 회사의 내부회계관리제도는 중요성의 관점에서 효과적으로
    설계 및 운영되고 있습니다.</p>
    <p>내부회계관리제도 감사는 중요한 취약점이 존재하는지에 대한 감사증거를
    입수하기 위한 절차의 수행을 포함합니다.</p>
    """
    ctx = ExtractionContext(html=html, fiscal_year=2023, sections=locate_sections(html))
    out = extract_icfr(ctx)
    assert out.icfr_status is ExtractionStatus.found
    assert out.icfr_engagement == "audit"
    assert out.icfr_opinion_code == "적정"


def test_operating_report_is_not_icfr_leaf() -> None:
    html = "<h2>내부회계관리제도 운영보고서</h2><p>이사회 보고</p>"
    ctx = ExtractionContext(html=html, fiscal_year=2024, sections=locate_sections(html))
    assert extract_icfr(ctx).icfr_status is not ExtractionStatus.found
