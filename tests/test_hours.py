# tests/test_hours.py
from typing import Literal

from dart_parser.fallback.schemas import ExtractionStatus, HoursCell, HoursTable
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.hours import extract_hours, validate_hours
from dart_parser.parser.sections import locate_sections

HTML = """
<h3>2. 감사 투입 인력 및 시간</h3>
<table>
  <tr><th>구분</th><th colspan="2">투입인원수</th><th colspan="2">감사시간</th></tr>
  <tr><th></th><th>당기</th><th>전기</th><th>당기</th><th>전기</th></tr>
  <tr><td>업무수행이사</td><td>1</td><td>1</td><td>100</td><td>90</td></tr>
  <tr><td>등록공인회계사</td><td>3</td><td>2</td><td>400</td><td>350</td></tr>
  <tr><td>합계</td><td>4</td><td>3</td><td>500</td><td>440</td></tr>
</table>
"""


def test_hours_cells_are_role_metric_period() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.found
    partner = [
        c
        for c in item.value.cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    assert partner[0].value == 100.0
    assert not partner[0].unmapped


def test_prior_period_and_headcount_are_separate_cells() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    cells = extract_hours(ctx).value.cells
    prior = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "prior"
    ]
    headcount = [
        c
        for c in cells
        if c.role_key == "cpa" and c.metric_key == "headcount" and c.period == "current"
    ]
    assert prior[0].value == 90.0
    assert prior[0].unmapped is False
    assert headcount[0].value == 3.0
    assert headcount[0].role == "등록공인회계사"


def test_unknown_role_cells_are_unmapped() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr><th>구분</th><th colspan="2">투입인원수</th><th colspan="2">감사시간</th></tr>
      <tr><th></th><th>당기</th><th>전기</th><th>당기</th><th>전기</th></tr>
      <tr><td>파트너</td><td>1</td><td>1</td><td>80</td><td>70</td></tr>
      <tr><td>합계</td><td>1</td><td>1</td><td>80</td><td>70</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    cells = extract_hours(ctx).value.cells
    unknown = [c for c in cells if c.role == "파트너"]
    assert unknown
    assert all(c.unmapped for c in unknown)
    assert all(c.role_key is None and c.metric_key is None and c.period is None for c in unknown)
    assert any(c.value == 80.0 for c in unknown)
    total = [
        c
        for c in cells
        if c.role_key == "total" and c.metric_key == "audit_hours" and c.period == "current"
    ]
    assert total[0].value == 80.0
    assert total[0].unmapped is False


def test_unknown_metric_column_is_unmapped() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr><th>구분</th><th colspan="2">감사시간</th><th>검토시간</th></tr>
      <tr><th></th><th>당기</th><th>전기</th><th>당기</th></tr>
      <tr><td>업무수행이사</td><td>100</td><td>90</td><td>7</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    cells = extract_hours(ctx).value.cells
    unknown = [c for c in cells if c.value == 7.0]
    assert len(unknown) == 1
    assert unknown[0].unmapped is True
    assert unknown[0].role_key is None
    assert unknown[0].metric_key is None
    assert unknown[0].period is None
    mapped = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    assert mapped[0].value == 100.0


def test_unknown_period_column_is_unmapped() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr><th>구분</th><th colspan="2">감사시간</th></tr>
      <tr><th></th><th>당기</th><th>차기</th></tr>
      <tr><td>업무수행이사</td><td>100</td><td>15</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    cells = extract_hours(ctx).value.cells
    unknown = [c for c in cells if c.value == 15.0]
    assert len(unknown) == 1
    assert unknown[0].unmapped is True
    assert unknown[0].role_key is None
    assert unknown[0].metric_key is None
    assert unknown[0].period is None


def test_empty_window_is_missing_even_when_html_has_the_table() -> None:
    ctx = ExtractionContext(html=HTML, sections={"exhibit4_hours": ""})
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.missing
    assert item.value is None


def test_missing_section_key_is_missing() -> None:
    ctx = ExtractionContext(html=HTML, sections={})
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.missing
    assert item.value is None


def test_hours_ignore_a_later_section_table() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr><th>구분</th><th>감사시간</th></tr>
      <tr><th></th><th>당기</th></tr>
      <tr><td>업무수행이사</td><td>100</td></tr>
    </table>
    <h3>3. 주요 감사 실시 내용</h3>
    <table>
      <tr><th>구분</th><th>감사시간</th></tr>
      <tr><th></th><th>당기</th></tr>
      <tr><td>업무수행이사</td><td>999</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    values = [c.value for c in extract_hours(ctx).value.cells]
    assert 100.0 in values
    assert 999.0 not in values


def test_hours_use_full_html_when_the_window_has_no_table() -> None:
    ctx = ExtractionContext(
        html=HTML,
        sections={"exhibit4_hours": "<h3>2. 감사 투입 인력 및 시간</h3><p>본문만</p>"},
    )
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.found
    partner = [
        c
        for c in item.value.cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    assert partner[0].value == 100.0


def test_comma_separated_hours_go_through_to_number() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr><th>구분</th><th>감사시간</th></tr>
      <tr><th></th><th>당기</th></tr>
      <tr><td>업무 수행이사</td><td>1,234</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    cells = extract_hours(ctx).value.cells
    partner = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    assert partner[0].value == 1234.0


def test_nested_metric_headers_keep_the_lower_axis() -> None:
    html = """
    <h3>2. 감사 투입 인력 및 시간</h3>
    <table>
      <tr>
        <th rowspan="3">구분</th>
        <th colspan="2">투입인원수</th>
        <th colspan="6">감사시간</th>
      </tr>
      <tr>
        <th rowspan="2">당기</th>
        <th rowspan="2">전기</th>
        <th colspan="2">분·반기검토</th>
        <th colspan="2">감사</th>
        <th colspan="2">합계</th>
      </tr>
      <tr>
        <th>당기</th><th>전기</th><th>당기</th><th>전기</th><th>당기</th><th>전기</th>
      </tr>
      <tr>
        <td>업무수행이사</td><td>1</td><td>1</td><td>10</td><td>8</td><td>100</td><td>90</td><td>110</td><td>98</td>
      </tr>
      <tr>
        <td>기타</td><td>0</td><td>0</td><td>1</td><td>1</td><td>5</td><td>4</td><td>6</td><td>5</td>
      </tr>
      <tr>
        <td>합계</td><td>1</td><td>1</td><td>11</td><td>9</td><td>100</td><td>90</td><td>105</td><td>94</td>
      </tr>
    </table>
    """
    ctx = ExtractionContext(html=html, sections=locate_sections(html))
    item = extract_hours(ctx)
    cells = item.value.cells
    review = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "interim_review"
        and c.period == "current"
    ]
    audit = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    rolled = [
        c
        for c in cells
        if c.role_key == "engagement_partner" and c.metric_key == "total" and c.period == "current"
    ]
    other = [
        c
        for c in cells
        if c.role_key == "other" and c.metric_key == "audit_hours" and c.period == "current"
    ]
    assert review[0].value == 10.0
    assert review[0].unmapped is False
    assert audit[0].value == 100.0
    assert rolled[0].value == 110.0
    assert other[0].value == 5.0
    assert validate_hours(item.value).ok is True


TRANSPOSED_HTML = """
<h3>2. 감사참여자 구분별 인원수 및 감사시간</h3>
<table>
  <tr>
    <th>구분</th>
    <th colspan="2">품질관리 검토자 (심리실 등)</th>
    <th colspan="2">담당이사 (업무수행이사)</th>
    <th colspan="2">등록 공인회계사</th>
    <th colspan="2">수습 공인회계사</th>
    <th colspan="2">전산감사ᆞ 세무ᆞ가치평가 등 전문가</th>
    <th colspan="2">합계</th>
  </tr>
  <tr>
    <th></th>
    <th>당기</th><th>전기</th>
    <th>당기</th><th>전기</th>
    <th>당기</th><th>전기</th>
    <th>당기</th><th>전기</th>
    <th>당기</th><th>전기</th>
    <th>당기</th><th>전기</th>
  </tr>
  <tr>
    <td>투입 인원수</td>
    <td>10</td><td>11</td>
    <td>1</td><td>1</td>
    <td>45</td><td>33</td>
    <td>23</td><td>17</td>
    <td>45</td><td>64</td>
    <td>124</td><td>126</td>
  </tr>
  <tr>
    <td>분ᆞ반기검토</td>
    <td>59</td><td>156</td>
    <td>222</td><td>267</td>
    <td>22096</td><td>12787</td>
    <td>7149</td><td>3072</td>
    <td>4801</td><td>4327</td>
    <td>34327</td><td>20609</td>
  </tr>
  <tr>
    <td>감사</td>
    <td>412</td><td>308</td>
    <td>777</td><td>1004</td>
    <td>22142</td><td>29004</td>
    <td>7145</td><td>11145</td>
    <td>20233</td><td>16076</td>
    <td>50709</td><td>57537</td>
  </tr>
</table>
"""


def test_transposed_role_columns_read_samsung_shape() -> None:
    ctx = ExtractionContext(html=TRANSPOSED_HTML, sections=locate_sections(TRANSPOSED_HTML))
    item = extract_hours(ctx)
    assert item.status is ExtractionStatus.found
    cells = item.value.cells
    partner = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    specialist = [
        c
        for c in cells
        if c.role_key == "specialist"
        and c.metric_key == "audit_hours"
        and c.period == "current"
    ]
    review = [
        c
        for c in cells
        if c.role_key == "engagement_partner"
        and c.metric_key == "interim_review"
        and c.period == "current"
    ]
    assert partner[0].value == 777.0
    assert specialist[0].value == 20233.0
    assert review[0].value == 222.0
    assert validate_hours(item.value).ok is True


def test_extracted_brief_table_passes_hours_check() -> None:
    ctx = ExtractionContext(html=HTML, sections=locate_sections(HTML))
    assert validate_hours(extract_hours(ctx).value).ok is True


def _hours(
    role_key: str,
    value: float | None,
    *,
    metric_key: str = "audit_hours",
    period: Literal["current", "prior"] = "current",
) -> HoursCell:
    return HoursCell(
        role=role_key,
        role_key=role_key,
        metric="감사시간",
        metric_key=metric_key,
        period=period,
        value=value,
        unmapped=False,
    )


def test_validate_hours_excludes_other_from_the_sum() -> None:
    balanced = HoursTable(
        cells=[
            _hours("engagement_partner", 100),
            _hours("other", 50),
            _hours("total", 100),
        ]
    )
    assert validate_hours(balanced).ok is True
    over = HoursTable(
        cells=[
            _hours("engagement_partner", 100),
            _hours("other", 50),
            _hours("total", 150),
        ]
    )
    result = validate_hours(over)
    assert result.ok is False
    assert result.issues[0].code == "hours_role_sum"
    assert result.issues[0].expected == 150
    assert result.issues[0].actual == 100


def test_validate_hours_tolerance_is_one() -> None:
    within = HoursTable(
        cells=[
            _hours("engagement_partner", 100),
            _hours("cpa", 400),
            _hours("total", 501),
        ]
    )
    assert validate_hours(within).ok is True
    outside = HoursTable(
        cells=[
            _hours("engagement_partner", 100),
            _hours("cpa", 400),
            _hours("total", 502),
        ]
    )
    result = validate_hours(outside)
    assert result.ok is False
    assert result.issues[0].expected == 502.0
    assert result.issues[0].actual == 500.0


def test_validate_hours_checks_current_audit_hours_only() -> None:
    table = HoursTable(
        cells=[
            _hours("engagement_partner", 100),
            _hours("cpa", 400),
            _hours("total", 500),
            _hours("engagement_partner", 1, metric_key="headcount"),
            _hours("cpa", 1, metric_key="headcount"),
            _hours("total", 9, metric_key="headcount"),
            _hours("engagement_partner", 1, period="prior"),
            _hours("cpa", 1, period="prior"),
            _hours("total", 9, period="prior"),
        ]
    )
    assert validate_hours(table).ok is True


def test_validate_hours_skips_without_a_total_row() -> None:
    result = validate_hours(HoursTable(cells=[_hours("engagement_partner", 100)]))
    assert result.ok is True
    assert result.issues == []
