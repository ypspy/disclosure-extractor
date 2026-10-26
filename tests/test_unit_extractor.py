from dart_parser.parser.unit_extractor import apply_scale, extract_unit


def test_extract_unit_million_won() -> None:
    info = extract_unit("(단위 : 백만원)")
    assert info.label == "백만원"
    assert info.scale == 1_000_000
    assert "백만원" in info.raw


def test_extract_unit_cheon_and_eok() -> None:
    assert extract_unit("단위: 천원").scale == 1_000
    assert extract_unit("단위 억원").scale == 100_000_000


def test_extract_unit_defaults_to_won() -> None:
    info = extract_unit("감사시간 명세")
    assert info.scale == 1
    assert info.label == "원"


def test_apply_scale_multiplies_value() -> None:
    info = extract_unit("단위 : 백만원")
    assert apply_scale(1_200.0, info) == 1_200_000_000.0
    assert apply_scale(None, info) is None
    assert apply_scale(5.0, 1_000) == 5_000.0
