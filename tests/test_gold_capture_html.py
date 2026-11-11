"""공시 HTML은 보이되 스크립트는 실행되지 않게 정리한다."""

from dart_parser.gold.capture_html import prepare_disclosure_html
from dart_parser.gold.capture_page import render_capture_page


def test_prepare_disclosure_html_strips_script_iframe_and_handlers() -> None:
    page = (
        "<style>td{text-align:right}</style>"
        "<table><tr><td onclick=\"alert(1)\" align=\"right\">19,506</td></tr></table>"
        "<script>alert(1)</script>"
        "<iframe src=\"https://example.test\"></iframe>"
    )
    cleaned = prepare_disclosure_html(page)
    assert "19,506" in cleaned
    assert "<style>" in cleaned
    assert "alert(1)" not in cleaned
    assert "<iframe" not in cleaned.lower()
    assert "onclick" not in cleaned.lower()
    assert "align=" in cleaned


def test_prepare_disclosure_html_drops_javascript_urls() -> None:
    page = (
        '<a href="javascript:alert(1)">note</a>'
        '<button formaction="JavaScript:alert(2)">go</button>'
        '<a href="https://example.test/note">web</a>'
        '<a href="http://example.test/note">web</a>'
        '<a href="#note">frag</a>'
    )
    cleaned = prepare_disclosure_html(page)
    assert "javascript:" not in cleaned.lower()
    assert 'href="https://example.test/note"' in cleaned
    assert 'href="http://example.test/note"' in cleaned
    assert 'href="#note"' in cleaned


def test_selected_row_click_cancels_the_default_action() -> None:
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
    handler = page.split("root.addEventListener('click'", 1)[1]
    assert handler.index("if (!chosen) return;") < handler.index("event.preventDefault()")
    assert handler.index("event.preventDefault()") < handler.index("fetch(")
