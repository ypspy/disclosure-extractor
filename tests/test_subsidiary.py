from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.subsidiary import extract_subsidiary

TABLE = """
<p>종속기업</p>
<table>
  <tr><th>기업명</th><th>구분</th></tr>
  <tr><td>A주식회사</td><td>종속기업</td></tr>
  <tr><td>B주식회사</td><td>종속기업</td></tr>
  <tr><td>C주식회사</td><td>관계기업</td></tr>
  <tr><td>D주식회사</td><td>공동기업</td></tr>
</table>
"""


def test_separate_is_not_applicable() -> None:
    out = extract_subsidiary(ExtractionContext(html="<p>감사보고서</p>", fs_scope="separate"))
    assert out.subsidiary_status is ExtractionStatus.not_applicable
    assert out.subsidiary_count is None


def test_consolidated_counts_only_subsidiaries() -> None:
    ctx = ExtractionContext(
        html=TABLE, fs_scope="consolidated", tables=extract_tables(TABLE)
    )
    out = extract_subsidiary(ctx)
    assert out.subsidiary_status is ExtractionStatus.found
    assert out.subsidiary_count == 2
