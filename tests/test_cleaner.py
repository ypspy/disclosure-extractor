from dart_parser.normalizer.cleaner import clean_html, html_to_text, normalize_text


def test_normalize_text_collapses_nbsp_and_fullwidth_space() -> None:
    assert normalize_text("감사\u00a0의견\u3000적정") == "감사 의견 적정"


def test_normalize_text_nfkc_fullwidth_digits() -> None:
    assert normalize_text("제５７기") == "제57기"


def test_clean_html_unwraps_font_and_drops_styles() -> None:
    html = (
        '<p style="margin:0"><font color="red"><span class="x">감사의견</span></font></p>'
        '<table width="100%"><tr><td align="right">1,000</td></tr></table>'
    )
    cleaned = clean_html(html)
    assert "font" not in cleaned.lower()
    assert "span" not in cleaned.lower()
    assert "style=" not in cleaned
    assert "class=" not in cleaned
    assert "감사의견" in cleaned
    assert 'colspan' not in cleaned or "1,000" in cleaned


def test_clean_html_keeps_colspan_and_rowspan() -> None:
    html = '<table><tr><th colspan="2" rowspan="1" style="color:red">당기</th></tr></table>'
    cleaned = clean_html(html)
    assert "colspan" in cleaned
    assert "당기" in cleaned
    assert "style" not in cleaned


def test_html_to_text_uses_block_boundaries() -> None:
    text = html_to_text("<p>회사명</p><p>감사보고서</p>")
    assert "회사명" in text
    assert "감사보고서" in text
