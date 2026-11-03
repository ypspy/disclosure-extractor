"""서식 기간 판정."""

from __future__ import annotations

import pytest

from dart_parser.gold.periods import assign_period


@pytest.mark.parametrize(
    ("rcept", "fye", "dtd", "expected"),
    [
        ("20010315", "2000.12", "dart2.dtd", ("P1", "P1a")),
        ("20050315", "2004.12", "dart2.dtd", ("P1", "P1b")),
        ("20080315", "2007.12", "dart2.dtd", ("P2", None)),
        ("20100315", "2009.12", "dart3.xsd", ("P3", None)),
        ("20120315", "2011.12", "dart3.xsd", ("P4", "P4a")),
        ("20140315", "2013.12", "dart3.xsd", ("P4", "P4b")),
        ("20190320", "2018.11", "dart3.xsd", ("P5", None)),
        ("20190320", "2018.12", "dart3.xsd", ("P6", None)),
        ("20240228", "2023.12", "dart3.xsd", ("P6", None)),
        ("20240229", "2023.12", "dart4.xsd", ("P7", None)),
        ("20240423", "2017.12", "dart4.xsd", ("P7", None)),
        ("19990601", "1998.12", "dart.dtd", ("OUT", None)),
    ],
)
def test_assign_period(
    rcept: str,
    fye: str,
    dtd: str,
    expected: tuple[str, str | None],
) -> None:
    assert assign_period(rcept, fye, dtd) == expected


def test_correction_by_filing_date() -> None:
    """정정은 접수일 기준으로 기간을 배정한다."""
    assert assign_period("20200410", "2017.12", "dart3.xsd", is_correction=True) == (
        "P6",
        None,
    )
    assert assign_period("20200410", "2017.12", "dart3.xsd") == ("P5", None)
