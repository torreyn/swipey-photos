"""Tests for the completion page (``ui/completion_screen.py``).

Coverage
    * the headline is derived from the counts and handles the singular case;
    * one row per category in canonical order, including zero counts, with the
      category colour on the swatch;
    * the three buttons emit their intent signals and the "open source folder"
      action is disabled when no folder is known;
    * the skipped note appears only when images were actually skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from image_swiper.core.folder_manager import CATEGORIES
from image_swiper.ui.completion_screen import CompletionScreen
from image_swiper.ui.swipe_card import CATEGORY_COLORS

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


def _count_label(screen: CompletionScreen, category: str) -> QLabel:
    """Return the count label for *category*, failing when it is missing."""
    label = screen.findChild(QLabel, f"completion_count_{category}")
    assert label is not None, f"missing count label for {category}"
    return label


def test_headline_counts_every_category(qtbot: QtBot, tmp_path: Path) -> None:
    """The summary states how many images were sorted in total."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)

    screen.set_summary({"Good": 4, "Bad": 2, "Great": 1, "OK": 3}, source_folder=tmp_path)

    assert screen.headline.text() == "All done! 10 images sorted"


def test_headline_uses_the_singular_for_one_image(qtbot: QtBot) -> None:
    """One image must not read "1 images"."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)

    screen.set_summary({"Good": 1})

    assert screen.headline.text() == "All done! 1 image sorted"


def test_every_category_gets_a_row_with_its_colour(qtbot: QtBot) -> None:
    """Rows are stable across sessions so the layout does not jump."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)

    screen.set_summary({"Good": 2, "OK": 5})

    for category in CATEGORIES:
        name = screen.findChild(QLabel, f"completion_name_{category}")
        swatch = screen.findChild(QLabel, f"completion_swatch_{category}")
        assert name is not None and name.text() == category
        assert swatch is not None
        assert CATEGORY_COLORS[category] in swatch.styleSheet()
    assert _count_label(screen, "Good").text() == "2"
    assert _count_label(screen, "OK").text() == "5"
    assert _count_label(screen, "Bad").text() == "0"


def test_unknown_categories_are_ignored(qtbot: QtBot) -> None:
    """Counts keyed by something else cannot break the summary."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)

    screen.set_summary({"Good": 1, "Elsewhere": 99})

    assert screen.headline.text() == "All done! 1 image sorted"


def test_buttons_report_their_intent(qtbot: QtBot, tmp_path: Path) -> None:
    """All three actions are wired to their signals."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)
    screen.show()
    screen.set_summary({"Good": 1}, source_folder=tmp_path)
    emitted: list[str] = []
    screen.open_source_requested.connect(lambda: emitted.append("open"))
    screen.pick_folder_requested.connect(lambda: emitted.append("pick"))
    screen.quit_requested.connect(lambda: emitted.append("quit"))

    for name in ("open", "pick", "quit"):
        qtbot.mouseClick(screen.buttons[name], Qt.MouseButton.LeftButton)

    assert emitted == ["open", "pick", "quit"]


def test_open_source_is_disabled_without_a_folder(qtbot: QtBot, tmp_path: Path) -> None:
    """Without a known folder there is nothing to rescan."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)

    screen.set_summary({"Good": 1})
    assert not screen.buttons["open"].isEnabled()

    screen.set_summary({"Good": 1}, source_folder=tmp_path)
    assert screen.buttons["open"].isEnabled()
    folder_label = screen.findChild(QLabel, "completion_folder")
    assert folder_label is not None and folder_label.text() == str(tmp_path)


def test_skipped_note_only_appears_when_needed(qtbot: QtBot) -> None:
    """The note explains images that could not be decoded."""
    screen = CompletionScreen()
    qtbot.addWidget(screen)
    screen.show()
    note = screen.findChild(QLabel, "completion_skipped")
    assert note is not None

    screen.set_summary({"Good": 1})
    assert not note.isVisible()

    screen.set_summary({"Good": 1}, skipped=2)
    assert note.isVisible()
    assert "2 images" in note.text()
