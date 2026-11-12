"""공시 HTML은 보이되 스크립트는 실행되지 않게 정리한다."""

from pathlib import Path

from dart_parser.gold.capture_html import heading_toc, prepare_disclosure_html
from dart_parser.gold.capture_page import html_json, render_capture_page

_JS = Path(__file__).parents[1] / "src" / "dart_parser" / "gold" / "static" / "capture.js"


def test_prepare_disclosure_html_strips_script_iframe_and_handlers() -> None:
    page = (
        "<style>td{text-align:right}</style>"
        '<table><tr><td onclick="alert(1)" align="right">19,506</td></tr></table>'
        "<script>alert(1)</script>"
        '<iframe src="https://example.test"></iframe>'
    )
    cleaned = prepare_disclosure_html(page)
    assert "19,506" in cleaned
    assert "<style>" in cleaned
    assert "alert(1)" not in cleaned
    assert "<iframe" not in cleaned.lower()
    assert "onclick" not in cleaned.lower()
    assert "align=" in cleaned


def test_prepare_disclosure_html_keeps_dart_fields_as_elements() -> None:
    page = (
        "<head><title>문서제목</title></head>"
        "<COMPANY-NAME>주식회사 한일진공</COMPANY-NAME>"
        "<TITLE>연결감사보고서</TITLE>"
        "<TE>2,393,113</TE>"
        "<P>본문</P>"
    )
    cleaned = prepare_disclosure_html(page)
    assert "문서제목" not in cleaned
    assert "<span>주식회사 한일진공</span>" in cleaned
    assert "<span>연결감사보고서</span>" in cleaned
    assert "<span>2,393,113</span>" in cleaned
    assert "<p>본문</p>" in cleaned


def test_self_closing_unknown_tags_emit_a_closed_span() -> None:
    cleaned = prepare_disclosure_html("<p>앞</p><PGBRK/><p>뒤</p>")
    assert "<span />" not in cleaned
    assert "<span/>" not in cleaned
    assert "<span></span>" in cleaned
    assert cleaned.index("<span></span>") < cleaned.index("<p>뒤</p>")
    assert "</span><p>뒤</p>" in cleaned


def test_self_closing_break_does_not_wrap_the_next_heading() -> None:
    cleaned = prepare_disclosure_html("<h1>감사의견</h1><PGBRK/><h2>재무상태표</h2>")
    assert "<span />" not in cleaned
    assert "<span></span><h2>재무상태표</h2>" in cleaned
    _html, toc = heading_toc(cleaned)
    assert toc[0][1] == "감사의견"
    assert toc[1][1] == "재무상태표"
    assert f'id="{toc[0][0]}"' in _html
    assert f'id="{toc[1][0]}"' in _html


def test_self_closing_break_does_not_swallow_following_text() -> None:
    cleaned = prepare_disclosure_html("<SPAN>앞</SPAN><PGBRK/>뒤")
    assert cleaned == "<span>앞</span><span></span>뒤"


def test_html_and_body_tags_are_not_emitted() -> None:
    cleaned = prepare_disclosure_html(
        "<html><head><title>문서제목</title></head><body><p>본문</p></body></html>"
    )
    assert "문서제목" not in cleaned
    assert "<p>본문</p>" in cleaned
    assert "<span>" not in cleaned
    assert "<html" not in cleaned.lower()
    assert "<body" not in cleaned.lower()


def test_body_title_without_a_head_stays_visible() -> None:
    cleaned = prepare_disclosure_html("<title>문서제목</title><p>본문</p>")
    assert "문서제목" in cleaned
    assert "<p>본문</p>" in cleaned
    assert "<head>" not in cleaned


def test_dropped_plugin_and_rawtext_tags_leave_no_payload() -> None:
    cleaned = prepare_disclosure_html(
        "<xmp><script>alert(1)</script></xmp>"
        '<applet code="Evil.class" archive="https://evil.example/e.jar">대체</applet>'
    )
    lowered = cleaned.lower()
    assert "<script" not in lowered
    assert "alert(1)" not in cleaned
    assert "evil.class" not in lowered
    assert "archive=" not in lowered
    assert "https://evil.example" not in lowered


def test_self_closing_unit_in_a_row_does_not_swallow_the_next_cell() -> None:
    cleaned = prepare_disclosure_html(
        '<TABLE><TR><TD>매출액</TD><TU AUNIT="원"/></TR><TR><TD>10,000</TD></TR></TABLE>'
    )
    assert "<span />" not in cleaned
    assert "<td>매출액</td>" in cleaned
    assert "<td>10,000</td>" in cleaned
    assert "<span></span>" in cleaned


def test_prepare_disclosure_html_drops_active_content() -> None:
    page = (
        '<object data="https://example.test/x"></object>'
        '<embed src="https://example.test/y">'
        "<svg><animate>move</animate>그림</svg>"
        '<base href="https://example.test/">'
        '<meta http-equiv="refresh" content="0;url=https://example.test">'
        '<link rel="stylesheet" href="https://example.test/a.css">'
        '<form action="https://example.test"><input value="go"></form>'
        '<img src="https://example.test/a.png" alt="outside">'
        '<img src="data:image/png;base64,aaaa">'
        '<a href="https://example.test/note">web</a>'
        '<a href="javascript:alert(1)">note</a>'
    )
    cleaned = prepare_disclosure_html(page).lower()
    assert "<object" not in cleaned
    assert "<embed" not in cleaned
    assert "<svg" not in cleaned
    assert "<animate" not in cleaned
    assert "move" not in cleaned
    assert "<base" not in cleaned
    assert "<meta" not in cleaned
    assert "<link" not in cleaned
    assert "<form" not in cleaned
    assert "https://example.test" not in cleaned
    assert "javascript:" not in cleaned
    assert "<img" in cleaned
    assert "data:image/png;base64,aaaa" in cleaned
    assert "<span" in cleaned
    assert "web" in cleaned
    assert "href=" not in cleaned


def test_capture_data_escapes_html_breaks() -> None:
    raw = html_json("a<b>&\u2028\u2029")
    assert "<" not in raw
    assert ">" not in raw
    assert "&" not in raw
    assert "\\u003c" in raw
    assert "\\u003e" in raw
    assert "\\u0026" in raw
    assert "\\u2028" in raw
    assert "\\u2029" in raw


def test_page_has_no_inline_script_and_clicks_do_not_navigate() -> None:
    page = render_capture_page(
        "R",
        "D",
        "token",
        '<a href="https://example.test/note">19,506</a>',
        (),
        {},
        {},
        "",
        "",
        "",
    )
    assert '<script src="/static/capture.js">' in page
    assert 'id="capture-data"' in page
    assert "function" not in page.split('id="capture-data"', 1)[0]
    data = page.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    assert "<a" not in data
    assert "\\u003c" in data
    script = _JS.read_text(encoding="utf-8")
    click = script.split('root.addEventListener("click"', 1)[1]
    assert click.index("event.preventDefault()") < click.index("selectedRow()")
    assert 'root.addEventListener("submit"' in script
    submit = script.split('root.addEventListener("submit"', 1)[1]
    assert "event.preventDefault()" in submit
    assert "if (!response.ok)" in script
    assert "textContent" in script
    assert "response.url" in script
