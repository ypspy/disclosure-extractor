"""Smoke test that the package imports as a src-layout install."""

from dart_parser import __version__
from dart_parser.pipeline import Pipeline


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_pipeline_is_importable() -> None:
    assert Pipeline is not None
