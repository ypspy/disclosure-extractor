from dart_parser.fallback.schemas import ExtractionStatus
from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.communications import extract_communications
from dart_parser.parser.sections import locate_sections

OLD = """
<h3>2. 감사 투입 인력 및 시간</h3><p>표</p>
<h3>3. 주요 감사 실시 내용</h3><p>계획</p>
"""

NEW = """
<h3>2. 감사 투입 인력 및 시간</h3><p>표</p>
<h3>3. 주요 감사 실시 내용</h3><p>계획</p>
<h3>4. 감사위원회와의 커뮤니케이션</h3>
<table>
  <tr><th>회차</th><th>일자</th></tr>
  <tr><td>제1회</td><td>2024.03.05</td></tr>
  <tr><td>제2회</td><td>2024.11.20</td></tr>
</table>
"""


def test_old_form_without_section4_is_not_in_regime() -> None:
    ctx = ExtractionContext(html=OLD, sections=locate_sections(OLD))
    item = extract_communications(ctx)
    assert item.status is ExtractionStatus.not_in_regime
    assert item.value is None


def test_committee_rounds() -> None:
    ctx = ExtractionContext(html=NEW, sections=locate_sections(NEW))
    item = extract_communications(ctx)
    assert item.value.has_audit_committee is True
    assert [i.round for i in item.value.items] == [1, 2]
