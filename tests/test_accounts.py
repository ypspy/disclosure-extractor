from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.accounts import extract_accounts

REJECT_HTML = """
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>1,200</td><td>1,000</td></tr>
  <tr><td>부채와자본총계</td><td>1,200</td><td>1,000</td></tr>
  <tr><td>비유동자산</td><td>100</td><td>80</td></tr>
  <tr><td>재고자산충당금</td><td>3</td><td>2</td></tr>
  <tr><td>지배주주당기순이익</td><td>50</td><td>40</td></tr>
  <tr><td>당기순손실</td><td>20</td><td>10</td></tr>
</table>
"""

IS_HTML = """
<p>손익계산서</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>매출액</td><td>3,000</td><td>2,500</td></tr>
  <tr><td>매출원가</td><td>1,800</td><td>1,500</td></tr>
  <tr><td>영업손실</td><td>100</td><td>40</td></tr>
  <tr><td>당기순이익</td><td>80</td><td>50</td></tr>
</table>
"""

CONSOLIDATED_HTML = """
<p>재무상태표</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>100</td><td>90</td></tr>
</table>
<p>연결재무상태표</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>9,000</td><td>8,000</td></tr>
</table>
"""


def test_rejects_out_of_scope_account_labels() -> None:
    ctx = ExtractionContext(html=REJECT_HTML, tables=extract_tables(REJECT_HTML))
    item = extract_accounts(ctx)
    assert item.status is ExtractionStatus.found
    assert item.value is not None
    assert item.value.total_asset.current.value == 1200.0
    assert item.value.current_asset is None
    assert item.value.inventory is None
    assert item.value.total_equity is None
    assert item.value.net_income.current.value == -20.0


def test_revenue_from_merged_current_cols_when_term_omits_gi() -> None:
    html = """
    <p>손익계산서</p>
    <table>
      <tr>
        <th>과 목</th><th>제21(당)</th><th>제21(당)</th>
        <th>제20(전)기</th><th>제20(전)기</th>
      </tr>
      <tr>
        <td>I.매출액(주2)</td><td></td><td>28,564,006,752</td>
        <td></td><td>28,822,560,259</td>
      </tr>
      <tr><td>당기순이익</td><td></td><td>80</td><td></td><td>50</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, tables=extract_tables(html), fs_scope="separate")
    item = extract_accounts(ctx)
    assert item.value is not None
    assert item.value.revenue.current.value == 28564006752.0


def test_total_revenue_line_wins_over_other_sales() -> None:
    html = """
    <p>손익계산서</p>
    <p>(단위 : 원)</p>
    <table>
      <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
      <tr><td>I. 매출액(주석12)</td><td>9,000</td><td>8,000</td></tr>
      <tr><td>기타매출</td><td>100</td><td>90</td></tr>
      <tr><td>당기순이익</td><td>80</td><td>50</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, tables=extract_tables(html), fs_scope="separate")
    item = extract_accounts(ctx)
    assert item.value is not None
    assert item.value.revenue.current.value == 9000.0


def test_operating_revenue_alias_is_read_as_revenue() -> None:
    html = """
    <p>손익계산서</p>
    <p>(단위 : 원)</p>
    <table>
      <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
      <tr><td>영업수익</td><td>9,000</td><td>8,000</td></tr>
      <tr><td>영업외수익</td><td>50</td><td>40</td></tr>
      <tr><td>당기순이익</td><td>80</td><td>50</td></tr>
    </table>
    """
    ctx = ExtractionContext(html=html, tables=extract_tables(html), fs_scope="separate")
    item = extract_accounts(ctx)
    assert item.value is not None
    assert item.value.revenue is not None
    assert item.value.revenue.current.value == 9000.0
    assert item.value.net_income.current.value == 80.0


def test_income_statement_lines_join_accounts() -> None:
    ctx = ExtractionContext(
        html=IS_HTML, tables=extract_tables(IS_HTML), fs_scope="separate"
    )
    item = extract_accounts(ctx)
    assert item.value.revenue.current.value == 3000.0
    assert item.value.revenue.current.unit_scale == 1_000_000
    assert item.value.revenue.prior.value == 2500.0
    assert item.value.operating_income.current.value == -100.0
    assert item.value.net_income.current.value == 80.0


def test_balance_sheet_fixture_amounts(mock_bs_html: str) -> None:
    ctx = ExtractionContext(html=mock_bs_html, tables=extract_tables(mock_bs_html))
    item = extract_accounts(ctx)
    assert item.status is ExtractionStatus.found
    assert item.value is not None
    assert item.value.total_asset is not None
    assert item.value.total_asset.current is not None
    assert item.value.total_asset.current.value == 1200.0
    assert item.value.total_asset.current.unit_scale == 1_000_000
    assert item.value.total_asset.current.value_won == 1_200_000_000.0
    assert item.value.total_liability is not None
    assert item.value.total_liability.current is not None
    assert item.value.total_liability.current.value == 700.0
    assert item.value.total_equity is not None
    assert item.value.total_equity.current is not None
    assert item.value.total_equity.current.value == 500.0
    assert item.value.total_equity.prior is not None
    assert item.value.total_equity.prior.value == 400.0


# Spaced titles stay spaced after extract_tables. The income-statement grid also
# has 자산총계, so only a balance-sheet classification keeps that 111 out of total_asset.
SPACED_HTML = """
<p>재 무 상 태 표</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>100</td><td>90</td></tr>
</table>
<p>(단위 : 백만원)</p>
<table>
  <caption>연 결 재 무 상 태 표</caption>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>9,000</td><td>8,000</td></tr>
</table>
<p>손 익 계 산 서</p>
<p>(단위 : 백만원)</p>
<table>
  <tr><th>과목</th><th>제5기</th><th>제4기</th></tr>
  <tr><td>자산총계</td><td>111</td><td>110</td></tr>
  <tr><td>매출액</td><td>3,000</td><td>2,500</td></tr>
</table>
"""


def test_spaced_titles_classify_balance_sheet_and_prefer_consolidated() -> None:
    tables = extract_tables(SPACED_HTML)
    separate, consolidated, income = tables
    assert "재 무 상 태 표" in separate.context_before
    assert "재무상태표" not in separate.context_before
    assert consolidated.caption == "연 결 재 무 상 태 표"
    assert "연결" not in consolidated.caption
    assert "손 익 계 산 서" in income.context_before
    assert "손익" not in income.context_before

    ctx = ExtractionContext(
        html=SPACED_HTML,
        tables=tables,
        fs_scope="consolidated",
    )
    item = extract_accounts(ctx)
    assert item.value is not None
    assert item.value.total_asset is not None
    assert item.value.total_asset.current is not None
    assert item.value.total_asset.current.value == 9000.0
    assert item.value.revenue is not None
    assert item.value.revenue.current is not None
    assert item.value.revenue.current.value == 3000.0


TITLE_THEN_GRID = """
<table>
  <tr><td>재 무 상 태 표</td><td>재 무 상 태 표</td></tr>
  <tr><td>제 55 기 : 2023년 12월 31일 현재</td><td>제 55 기 : 2023년 12월 31일 현재</td></tr>
  <tr><td>삼성전자주식회사</td><td>(단위 : 백만원)</td></tr>
</table>
<table>
  <tr>
    <th>과 목</th><th>주석</th>
    <th>제 55 (당) 기</th><th>제 55 (당) 기</th>
    <th>제 54 (전) 기</th><th>제 54 (전) 기</th>
  </tr>
  <tr>
    <td>6. 재 고 자 산</td><td>8</td>
    <td>29,338,151</td><td></td><td>27,990,007</td><td></td>
  </tr>
  <tr>
    <td>자 산 총 계</td><td></td><td></td>
    <td>296,857,289</td><td></td><td>260,083,750</td>
  </tr>
  <tr>
    <td>부 채 총 계</td><td></td><td></td>
    <td>72,069,515</td><td></td><td>50,667,559</td>
  </tr>
  <tr>
    <td>자 본 총 계</td><td></td><td></td>
    <td>224,787,774</td><td></td><td>209,416,191</td>
  </tr>
</table>
<table>
  <tr><td>손 익 계 산 서</td><td>손 익 계 산 서</td></tr>
</table>
<table>
  <tr>
    <th>과 목</th><th>주 석</th>
    <th>제 55 (당) 기</th><th>제 55 (당) 기</th>
    <th>제 54 (전) 기</th><th>제 54 (전) 기</th>
  </tr>
  <tr>
    <td>I. 매 출 액</td><td>29</td><td></td>
    <td>170,374,090</td><td></td><td>211,867,483</td>
  </tr>
  <tr>
    <td>IV. 영 업 이 익 (손 실)</td><td></td><td></td>
    <td>(11,526,297)</td><td></td><td>25,319,329</td>
  </tr>
  <tr>
    <td>VI. 당 기 순 이 익</td><td></td><td></td>
    <td>25,397,099</td><td></td><td>25,418,778</td>
  </tr>
</table>
"""


def test_title_table_then_data_table_reads_spaced_lines() -> None:
    ctx = ExtractionContext(
        html=TITLE_THEN_GRID,
        tables=extract_tables(TITLE_THEN_GRID),
        fs_scope="separate",
    )
    item = extract_accounts(ctx)
    assert item.status is ExtractionStatus.found
    assert item.value is not None
    assert item.value.total_asset.current.value == 296_857_289.0
    assert item.value.total_asset.current.unit_scale == 1_000_000
    assert item.value.inventory.current.value == 29_338_151.0
    assert item.value.total_liability.current.value == 72_069_515.0
    assert item.value.total_equity.current.value == 224_787_774.0
    assert item.value.revenue.current.value == 170_374_090.0
    assert item.value.operating_income.current.value == -11_526_297.0
    assert item.value.net_income.current.value == 25_397_099.0


def test_consolidated_scope_prefers_consolidated_caption() -> None:
    ctx = ExtractionContext(
        html=CONSOLIDATED_HTML,
        tables=extract_tables(CONSOLIDATED_HTML),
        fs_scope="consolidated",
    )
    item = extract_accounts(ctx)
    assert item.value is not None
    assert item.value.total_asset is not None
    assert item.value.total_asset.current is not None
    assert item.value.total_asset.current.value == 9000.0
