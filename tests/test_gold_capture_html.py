"""공시 HTML은 보이되 스크립트는 실행되지 않게 정리한다."""

from dart_parser.gold.capture_html import prepare_disclosure_html


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
