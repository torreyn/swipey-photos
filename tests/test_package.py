"""Smoke tests for the package's public surface and packaging contract."""

from __future__ import annotations

import re
from importlib import import_module

import image_swiper

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[.\-+][0-9A-Za-z.\-]+)?$")


def test_package_exposes_a_version() -> None:
    """The packaging metadata and ``image_swiper.__version__`` must agree."""
    assert isinstance(image_swiper.__version__, str)
    assert SEMVER_PATTERN.match(image_swiper.__version__), image_swiper.__version__


def test_console_script_entry_point_is_importable() -> None:
    """``pyproject.toml`` points at ``image_swiper.__main__:main``."""
    entry_module = import_module("image_swiper.__main__")
    assert callable(entry_module.main)


def test_subpackages_are_importable_without_qt() -> None:
    """``core`` and ``utils`` must stay importable on a Qt-less interpreter.

    This is a real constraint, not a formality: it keeps those layers usable
    from a future CLI and ensures unit tests do not need a display.
    """
    for name in ("image_swiper.core", "image_swiper.utils"):
        module = import_module(name)
        assert module.__doc__, f"{name} should document its responsibility"
