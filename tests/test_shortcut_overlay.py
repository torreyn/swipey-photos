"""Tests for the keyboard reference overlay (``ui/shortcut_overlay.py``).

Coverage
    * the table is well-formed: unique key caps, non-empty descriptions and the
      three group headings the README talks about;
    * the widget renders one key cap and one description per row, plus a Close
      button, and is not modal;
    * ``show_overlay()`` is reuse-safe: repeated calls keep one dialog, and a
      dismissed overlay can be shown again;
    * the documented keys cover the bindings the window really installs (the
      window side of that comparison lives in ``test_main_window.py``).

Conventions
    * GUI tests are marked ``gui`` and need no display: run with
      ``QT_QPA_PLATFORM=offscreen``.
    * The overlay is owned by ``qtbot`` and never opened modally, so no test
      blocks on an event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from swipey_photos.ui.shortcut_overlay import SHORTCUT_GROUPS, ShortcutOverlay

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui

DOCUMENTED_KEYS: tuple[str, ...] = (
    "Ctrl+O",
    "F5",
    "Ctrl+R",
    "Ctrl+Z",
    "Space",
    "F11",
    "F1",
    "?",
    "Ctrl+Q",
)
"""Keys the README shortcut table promises, independent of the overlay's own table."""


@pytest.fixture
def overlay(qtbot: QtBot) -> ShortcutOverlay:
    """Return a built overlay owned by ``qtbot``."""
    created = ShortcutOverlay()
    qtbot.addWidget(created)
    return created


def test_rows_are_unique_and_described(overlay: ShortcutOverlay) -> None:
    """Every binding appears exactly once and explains itself."""
    pairs = overlay.shortcut_pairs()

    assert len(pairs) == sum(len(rows) for _group, rows in SHORTCUT_GROUPS)
    keys = [keys for keys, _description in pairs]
    descriptions = [description for _keys, description in pairs]
    assert len(keys) == len(set(keys))
    assert len(descriptions) == len(set(descriptions))
    assert all(keys.strip() and description.strip() for keys, description in pairs)


def test_headings_group_the_bindings(overlay: ShortcutOverlay) -> None:
    """Sorting, session and window-wide bindings are separate blocks."""
    assert overlay.headings() == ("Sorting", "Session", "Window")
    for group, rows in SHORTCUT_GROUPS:
        assert rows, f"{group} must not be empty"


def test_keys_text_mentions_every_documented_binding(overlay: ShortcutOverlay) -> None:
    """The overlay is the table the README points at, so it lists every key."""
    text = overlay.keys_text()

    for keys in DOCUMENTED_KEYS:
        assert keys in text, f"{keys} is missing from the overlay"


def test_widget_renders_a_cap_and_a_description_per_row(overlay: ShortcutOverlay) -> None:
    """The grid, the title and the dismiss button are all there."""
    pairs = overlay.shortcut_pairs()

    caps = [
        child for child in overlay.findChildren(QLabel) if child.objectName() == "shortcut_keys"
    ]
    descriptions = [
        child
        for child in overlay.findChildren(QLabel)
        if child.objectName() == "shortcut_description"
    ]
    assert len(caps) == len(pairs)
    assert len(descriptions) == len(pairs)
    assert [cap.text() for cap in caps] == [keys for keys, _description in pairs]
    assert overlay.objectName() == "shortcut_overlay"
    assert "Swipey Photos" in overlay.windowTitle()
    assert overlay.close_button.text() == "Close"
    assert not overlay.isModal()


def test_show_overlay_is_reuse_safe(qtbot: QtBot, overlay: ShortcutOverlay) -> None:
    """Showing it twice keeps the same dialog instead of stacking copies."""
    overlay.show_overlay()
    qtbot.waitUntil(overlay.isVisible, timeout=2000)

    overlay.show_overlay()

    assert overlay.isVisible()


def test_close_button_dismisses_the_overlay(qtbot: QtBot, overlay: ShortcutOverlay) -> None:
    """The Close button hides the dialog, which can then be shown again."""
    overlay.show_overlay()
    qtbot.waitUntil(overlay.isVisible, timeout=2000)

    qtbot.mouseClick(overlay.close_button, Qt.MouseButton.LeftButton)

    assert not overlay.isVisible()
    overlay.show_overlay()
    assert overlay.isVisible()


def test_escape_dismisses_the_overlay(qtbot: QtBot, overlay: ShortcutOverlay) -> None:
    """Esc works like Close, so the overlay never traps the user."""
    overlay.show_overlay()
    qtbot.waitUntil(overlay.isVisible, timeout=2000)
    overlay.setFocus()

    qtbot.keyClick(overlay, Qt.Key.Key_Escape)

    assert not overlay.isVisible()
