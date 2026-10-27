from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.activities import extract_activities
from dart_parser.parser.sections import locate_sections

HTML = """
<h3>3. 주요 감사 실시 내용</h3>
<table>
  <tr><td>전반감사계획</td><td>위험평가 및 계획 수립</td></tr>
  <tr><td>현장감사</td><td>2024.11.01~2024.11.15</td></tr>
  <tr><td>재고자산 실사</td><td>시기 2024.12.31 / 장소 본사창고 / 대상 제품</td></tr>
  <tr><td>외부조회</td><td>금융거래 실시 / 채권채무 실시 / 변호사 미실시 / 기타 없음</td></tr>
  <tr><td>지배기구와의 커뮤니케이션</td><td>감사 계획 및 결과 보고</td></tr>
  <tr><td>외부전문가</td><td>해당없음</td></tr>
</table>
"""


def test_activities_seven_procedures() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    item = extract_activities(ctx)
    acts = item.value
    assert acts.planning == "위험평가 및 계획 수립"
    assert acts.inventory_observation is not None
    assert acts.inventory_observation.place == "본사창고"
    assert acts.external_confirmations.legal == "미실시"
    assert acts.tcwg_communication == "감사 계획 및 결과 보고"
    assert "제1회" not in (acts.tcwg_communication or "")


def test_empty_window_is_missing() -> None:
    ctx = ExtractionContext(html=HTML, sections={"exhibit4_activities": ""})
    assert extract_activities(ctx).value is None
