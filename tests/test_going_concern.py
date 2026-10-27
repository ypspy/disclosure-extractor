from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.going_concern import extract_going_concern


def test_material_uncertainty_is_one() -> None:
    html = "<p>계속기업 가정에 중요한 불확실성이 존재합니다.</p>"
    item = extract_going_concern(ExtractionContext(html=html, sections={"going_concern": html}))
    assert item.value == 1


def test_emphasis_of_liquidation_is_zero() -> None:
    html = "<p>청산기준에 따라 재무제표를 작성하였음을 강조합니다.</p>"
    ctx = ExtractionContext(html=html, sections={"going_concern": html})
    assert extract_going_concern(ctx).value == 0


def test_prior_year_quote_is_zero() -> None:
    html = "<p>전기 감사보고서는 계속기업 불확실성을 언급하였습니다.</p>"
    ctx = ExtractionContext(html=html, sections={"going_concern": html})
    assert extract_going_concern(ctx).value == 0
