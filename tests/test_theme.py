"""Tests for the palette switcher (``ui/theme.py``).

Coverage
    * the dark palette uses the documented window/text colours and dims text in
      the disabled group;
    * ``apply_theme`` installs the palette on the running application and
      reports the effective theme;
    * ``system`` resolves through the platform colour scheme, and an unknown
      name falls back to it instead of raising.

Every test that changes the application palette restores it afterwards, so the
look of later widget tests does not depend on the order they run in.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

from swipey_photos.ui.theme import (
    DARK_TEXT,
    DARK_WINDOW,
    apply_theme,
    build_dark_palette,
    build_light_palette,
    system_theme,
)
from swipey_photos.utils.config import THEME_DARK, THEME_LIGHT, THEME_SYSTEM

pytestmark = pytest.mark.gui


@pytest.fixture
def restore_palette(qapp: QApplication) -> Iterator[None]:
    """Put the original application palette back when the test ends."""
    original = qapp.palette()
    yield
    qapp.setPalette(original)


def test_dark_palette_uses_the_marker_colours() -> None:
    """The palette is dark, and disabled text is dimmer than enabled text."""
    palette = build_dark_palette()

    assert palette.color(QPalette.ColorRole.Window) == DARK_WINDOW
    assert palette.color(QPalette.ColorRole.WindowText) == DARK_TEXT
    assert palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text) != DARK_TEXT


def test_apply_theme_dark_installs_the_dark_palette(
    qapp: QApplication, restore_palette: None
) -> None:
    """``dark`` reaches the application palette that every widget reads."""
    assert apply_theme(THEME_DARK) == THEME_DARK

    assert qapp.palette().color(QPalette.ColorRole.Window) == DARK_WINDOW


def test_apply_theme_light_leaves_the_dark_palette_behind(
    qapp: QApplication, restore_palette: None
) -> None:
    """Switching back to light restores the platform's own palette."""
    apply_theme(THEME_DARK)

    assert apply_theme(THEME_LIGHT) == THEME_LIGHT

    assert qapp.palette().color(QPalette.ColorRole.Window) != DARK_WINDOW


def test_apply_theme_system_resolves_the_platform_preference(
    qapp: QApplication, restore_palette: None
) -> None:
    """``system`` reports the theme it resolved to, never the word "system"."""
    assert apply_theme(THEME_SYSTEM) == system_theme()


def test_unknown_theme_falls_back_to_system(qapp: QApplication, restore_palette: None) -> None:
    """A hand-edited config cannot stop the window from opening."""
    assert apply_theme("midnight") == system_theme()


def test_system_theme_is_one_of_two_values() -> None:
    """The platform answer is always usable as a theme name."""
    assert system_theme() in {THEME_DARK, THEME_LIGHT}


def test_light_palette_differs_from_the_dark_one() -> None:
    """The light palette is the style default, not a copy of the dark one."""
    assert build_light_palette().color(QPalette.ColorRole.Window) != DARK_WINDOW
