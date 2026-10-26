from __future__ import annotations

from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).parent / "sample_htmls"


@pytest.fixture
def mock_bs_html() -> str:
    return (SAMPLE_DIR / "mock_bs_table.html").read_text(encoding="utf-8")
