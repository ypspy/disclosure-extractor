"""공시 HTML은 보이되 스크립트는 실행되지 않게 정리한다."""

from pathlib import Path

from dart_parser.gold.capture_html import prepare_disclosure_html
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
    click = script.split("root.addEventListener(\"click\"", 1)[1]
    assert click.index("event.preventDefault()") < click.index("selectedRow()")
    assert 'root.addEventListener("submit"' in script
    submit = script.split('root.addEventListener("submit"', 1)[1]
    assert "event.preventDefault()" in submit
    assert "if (!response.ok)" in script
    assert "textContent" in script
    assert "response.url" in script
