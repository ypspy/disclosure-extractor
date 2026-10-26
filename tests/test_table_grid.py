from dart_parser.normalizer.table_grid import (
    extract_tables,
    flatten_table_to_grid,
    grid_to_markdown,
)

SPAN_HTML = """
<table>
  <tr><th rowspan="2">과목</th><th colspan="2">당기</th></tr>
  <tr><th>3개월</th><th>누적</th></tr>
  <tr><td>매출액</td><td>100</td><td>400</td></tr>
</table>
"""


def test_flatten_expands_rowspan_and_colspan() -> None:
    grid = flatten_table_to_grid(SPAN_HTML)
    assert grid == [
        ["과목", "당기", "당기"],
        ["과목", "3개월", "누적"],
        ["매출액", "100", "400"],
    ]


def test_extract_tables_reads_unit_hint(mock_bs_html: str) -> None:
    tables = extract_tables(mock_bs_html)
    assert len(tables) == 1
    table = tables[0]
    assert table.n_rows == 5
    assert table.n_cols == 5
    assert table.grid[2][0] == "자산총계"
    assert table.grid[2][1] == "1,200"
    assert "백만원" in table.unit_text or "백만원" in table.context_before


def test_grid_to_markdown_renders_header_separator() -> None:
    md = grid_to_markdown([["과목", "당기"], ["매출액", "100"]])
    assert md.splitlines()[0].startswith("|")
    assert "---" in md.splitlines()[1]
    assert "매출액" in md
