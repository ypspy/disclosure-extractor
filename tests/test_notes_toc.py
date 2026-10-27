from dart_parser.parser.context import ExtractionContext
from dart_parser.parser.extractors.notes_toc import extract_notes_toc

HTML = """
<h2>주석</h2>
<p>1. 회사의 개요</p>
<p>2. 중요한 회계정책</p>
<p>3. 매출채권</p>
<h3>1. 회사의 개요</h3>
<p>당사는 1988년에 설립되었으며 본문은 길다.</p>
"""


def test_notes_toc_titles_exclude_body() -> None:
    item = extract_notes_toc(ExtractionContext(html=HTML, sections={"notes_toc": HTML}))
    assert item.value.titles == ["회사의 개요", "중요한 회계정책", "매출채권"]
    assert item.value.count == 3
    assert "1988" not in " ".join(item.value.titles)
