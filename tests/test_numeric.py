from dart_parser.normalizer.numeric import to_int, to_number


def test_to_number_strips_commas() -> None:
    assert to_number("1,234,567") == 1_234_567.0


def test_to_number_parenthesis_negative() -> None:
    assert to_number("(1,234)") == -1234.0


def test_to_number_triangle_negative() -> None:
    assert to_number("△1,234") == -1234.0
    assert to_number("▲ 500") == -500.0


def test_to_number_dash_and_empty_are_none() -> None:
    assert to_number("-") is None
    assert to_number("—") is None
    assert to_number("해당없음") is None
    assert to_number("") is None
    assert to_number(None) is None


def test_to_number_ignores_trailing_unit() -> None:
    assert to_number("1,000원") == 1000.0


def test_to_int_rejects_fraction() -> None:
    assert to_int("12") == 12
    assert to_int("12.5") is None
