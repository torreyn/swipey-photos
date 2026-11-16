"""Tests for the welcome page (``ui/welcome_screen.py``).

Coverage
    * the brand, the tagline and the primary "Select Folder…" button;
    * the recent-folder list: newest first, de-duplicated, capped at five,
      hidden when empty, and each entry emits its path when clicked;
    * ``QFileDialog`` integration: a picked directory is reported, a cancelled
      dialog emits nothing.

The dialog is replaced through the module global (``welcome_screen.QFileDialog``)
because PyQt6's ``QFileDialog`` class itself is a SIP type that cannot be
monkeypatched.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from helpers import FakeFileDialog
from image_swiper.ui.branding import APP_DISPLAY_NAME, TAGLINE
from image_swiper.ui.welcome_screen import WelcomeScreen
from image_swiper.utils.config import MAX_RECENT_FOLDERS

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


def _label(screen: WelcomeScreen, name: str) -> QLabel:
    """Return the label with the given object name, failing when it is missing."""
    label = screen.findChild(QLabel, name)
    assert label is not None, f"missing label {name!r}"
    return label


def _widget(screen: WelcomeScreen, name: str) -> QWidget:
    """Return the child widget with the given object name."""
    child = screen.findChild(QWidget, name)
    assert child is not None, f"missing widget {name!r}"
    return child


def test_shows_the_brand_and_one_primary_action(qtbot: QtBot) -> None:
    """The page states what the app is and offers exactly one primary action."""
    screen = WelcomeScreen()
    qtbot.addWidget(screen)
    screen.show()

    assert _label(screen, "welcome_title").text() == APP_DISPLAY_NAME
    assert _label(screen, "welcome_tagline").text() == TAGLINE
    assert screen.select_button.text() == "Select Folder…"
    assert screen.select_button.isDefault()
    assert screen.select_button.isVisible()


def test_recent_folders_are_listed_newest_first(qtbot: QtBot, tmp_path: Path) -> None:
    """Every stored folder becomes a shortcut button, in the stored order."""
    folders = [tmp_path / "newest", tmp_path / "older", tmp_path / "oldest"]
    screen = WelcomeScreen(recent_folders=folders)
    qtbot.addWidget(screen)
    screen.show()

    assert screen.recent_folders() == tuple(folders)
    assert len(screen.recent_buttons) == 3
    assert screen.recent_buttons[0].toolTip() == f"Reopen {folders[0]}"
    assert screen.recent_buttons[0].isVisible()


def test_recent_list_is_trimmed_and_de_duplicated(qtbot: QtBot, tmp_path: Path) -> None:
    """Only the five newest folders are kept and repeats collapse."""
    folders = [tmp_path / f"folder{index}" for index in range(7)]
    screen = WelcomeScreen(recent_folders=[*folders, folders[0]])
    qtbot.addWidget(screen)

    kept = screen.recent_folders()
    assert len(kept) == MAX_RECENT_FOLDERS
    assert kept == tuple(folders[:MAX_RECENT_FOLDERS])
    assert len(screen.recent_buttons) == MAX_RECENT_FOLDERS


def test_empty_recent_list_hides_the_section(qtbot: QtBot) -> None:
    """A first run shows no empty "Recent folders" heading."""
    screen = WelcomeScreen()
    qtbot.addWidget(screen)
    screen.show()

    assert screen.recent_buttons == ()
    assert not _label(screen, "welcome_recent_header").isVisible()
    assert not _widget(screen, "welcome_recent_list").isVisible()


def test_clicking_a_recent_folder_reports_it(qtbot: QtBot, tmp_path: Path) -> None:
    """A shortcut button emits the folder it stands for."""
    folders = [tmp_path / "first", tmp_path / "second"]
    screen = WelcomeScreen(recent_folders=folders)
    qtbot.addWidget(screen)
    screen.show()

    with qtbot.waitSignal(screen.folder_selected, timeout=1000) as blocker:
        qtbot.mouseClick(screen.recent_buttons[1], Qt.MouseButton.LeftButton)

    assert blocker.args == [str(folders[1])]


def test_picking_a_folder_reports_it(
    qtbot: QtBot, fake_file_dialog: type[FakeFileDialog], tmp_path: Path
) -> None:
    """The primary button opens the picker and forwards the choice."""
    fake_file_dialog.result = str(tmp_path / "picked")
    screen = WelcomeScreen()
    qtbot.addWidget(screen)
    screen.show()

    with qtbot.waitSignal(screen.folder_selected, timeout=1000) as blocker:
        qtbot.mouseClick(screen.select_button, Qt.MouseButton.LeftButton)

    assert blocker.args == [str(tmp_path / "picked")]
    assert len(fake_file_dialog.calls) == 1


def test_cancelling_the_picker_emits_nothing(
    qtbot: QtBot, fake_file_dialog: type[FakeFileDialog]
) -> None:
    """An empty dialog result means "stay where you are"."""
    emitted: list[str] = []
    screen = WelcomeScreen()
    qtbot.addWidget(screen)
    screen.folder_selected.connect(emitted.append)
    screen.show()

    qtbot.mouseClick(screen.select_button, Qt.MouseButton.LeftButton)

    assert fake_file_dialog.calls
    assert emitted == []


def test_picker_starts_in_the_most_recent_folder(
    qtbot: QtBot, fake_file_dialog: type[FakeFileDialog], tmp_path: Path
) -> None:
    """Reopening a known folder should not start from the home directory."""
    recent = tmp_path / "recent"
    screen = WelcomeScreen(recent_folders=[recent])
    qtbot.addWidget(screen)

    screen.choose_folder()

    assert fake_file_dialog.calls[0][2] == str(recent)
