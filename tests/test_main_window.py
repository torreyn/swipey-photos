"""Tests for the main window (``ui/main_window.py``).

Coverage
    * the three-page flow: welcome → stage → summary, and back via undo/restart;
    * opening folders: rejected (missing, empty), remembered, recent list
      updated, configuration persisted;
    * every decision path: footer buttons, keyboard actions, the card's
      ``swipe_committed``, skip, and the guard against a second decision while a
      move is in flight;
    * error paths: an undecodable image is reported and skipped, a failed move
      keeps the image queued, a vanished image is dropped with a warning;
    * the live progress label and the status-bar counters;
    * the shortcut surface: rescan (F5/Ctrl+R), full screen (F11), the F1/`?`
      reference overlay, and that every bound key is documented in it;
    * the About box: product name, version, and the *Buy me a coffee* button that
      hands ``SUPPORT_URL`` to the desktop service.

Conventions
    * The window is always built with an explicit ``config_path`` under
      ``tmp_path`` and the ``xdg_dirs`` fixture, so no real config is touched.
    * Modal dialogs never open: the ``dialogs`` fixture replaces the three
      ``_report_*`` helpers and records what the user would have seen.
    * Tests wait with ``qtbot.waitUntil`` on observable state (sorter counters,
      recorded dialogs) instead of sleeping through the 250 ms fly-out.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QLabel, QWidget

from helpers import FakeFileDialog
from swipey_photos import __version__
from swipey_photos.core.folder_manager import CATEGORIES
from swipey_photos.core.sorter import Sorter
from swipey_photos.ui import main_window as main_window_module
from swipey_photos.ui.branding import APP_DISPLAY_NAME, SUPPORT_URL
from swipey_photos.ui.main_window import MainWindow, default_sorter_factory, qimage_from_pil
from swipey_photos.utils.config import Config, WindowConfig, load_config
from swipey_photos.utils.file_ops import FileOperationError

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, xdg_dirs: dict[str, Path]) -> Callable[..., MainWindow]:
    """Return a factory that builds a shown window persisting into ``tmp_path``."""

    def factory(config: Config | None = None, *, dry_run: bool = False) -> MainWindow:
        created = MainWindow(
            config=Config() if config is None else config,
            config_path=tmp_path / "config.json",
            dry_run=dry_run,
        )
        qtbot.addWidget(created)
        created.show()
        return created

    return factory


def commit(qtbot: QtBot, window: MainWindow, category: str) -> None:
    """Trigger *category* and wait until the move or the summary completed."""
    sorter = window.sorter
    assert sorter is not None, "open a folder before committing"
    before = sum(sorter.counts.values())
    window.category_actions[category].trigger()
    qtbot.waitUntil(
        lambda: sorter.finished or sum(sorter.counts.values()) > before,
        timeout=5000,
    )


def wait_for_dialog(qtbot: QtBot, dialogs: list[tuple[str, str, str]]) -> None:
    """Wait until the window reported something to the user."""
    qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)


# ----------------------------------------------------------------------
# Startup, folders and persistence
# ----------------------------------------------------------------------


def test_starts_on_the_welcome_page(window: Callable[..., MainWindow]) -> None:
    """With no folder configured the app waits on the select-folder page."""
    created = window()

    assert created.current_page == "welcome"
    assert created.sorter is None
    assert created.progress_label.text() == ""
    for action in created.category_actions.values():
        assert not action.isEnabled()
    assert not created.findChild(QAction, "action_undo").isEnabled()  # type: ignore[union-attr]
    for button in created.category_buttons.values():
        assert not button.isEnabled()


def test_restore_last_session_opens_the_remembered_folder(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path, tmp_path: Path
) -> None:
    """A remembered folder is reopened straight into the stage."""
    created = window(Config(last_folder=sample_folder))

    assert created.restore_last_session()
    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 3"
    assert created.sorter is not None
    assert created.sorter.total == 3
    assert sample_folder.name in created.windowTitle()
    assert created.swipe_widget.card.scaled_pixmap() is not None


def test_restore_without_a_folder_keeps_the_welcome_page(
    window: Callable[..., MainWindow],
) -> None:
    """No remembered folder means no session to restore."""
    created = window()

    assert not created.restore_last_session()
    assert created.current_page == "welcome"


def test_restore_with_a_missing_folder_stays_on_welcome(
    window: Callable[..., MainWindow], tmp_path: Path
) -> None:
    """A deleted folder is reported in the status bar, not as a modal error."""
    created = window(Config(last_folder=tmp_path / "gone"))

    assert not created.restore_last_session()
    assert created.current_page == "welcome"
    assert "no longer available" in created.statusBar().currentMessage()


def test_open_folder_rejects_a_missing_folder(
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    tmp_path: Path,
) -> None:
    """An unusable folder is reported and nothing changes."""
    created = window()

    assert not created.open_folder(tmp_path / "nope")
    assert created.current_page == "welcome"
    assert [kind for kind, _title, _message in dialogs] == ["error"]
    assert "Could not open folder" in dialogs[0][1]


def test_open_folder_reports_a_folder_without_images(
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    tmp_path: Path,
) -> None:
    """An empty folder explains the supported formats instead of showing a blank card."""
    empty = tmp_path / "empty"
    empty.mkdir()
    created = window()

    assert not created.open_folder(empty)
    assert created.current_page == "welcome"
    assert dialogs[0][0] == "info"
    assert dialogs[0][1] == "No images found"


def test_open_folder_starts_a_session(
    window: Callable[..., MainWindow], sample_folder: Path, tmp_path: Path
) -> None:
    """Opening a folder shows the first image, remembers it and persists that."""
    created = window()

    assert created.open_folder(sample_folder)

    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 3"
    assert f"{sample_folder.name}" in created.windowTitle()
    assert "Good 0" in created.status_counts_label.text()
    assert "3 left" in created.status_counts_label.text()
    assert created.config.last_folder == sample_folder
    assert created.welcome_screen.recent_folders()[0] == sample_folder
    assert load_config(tmp_path / "config.json").last_folder == sample_folder
    assert created.category_actions["Good"].isEnabled()
    assert created.category_buttons["Good"].isEnabled()


def test_recent_folders_from_config_are_offered(
    window: Callable[..., MainWindow], tmp_path: Path
) -> None:
    """The welcome page starts with the recents stored in the config file."""
    recents = (tmp_path / "one", tmp_path / "two")
    created = window(Config(recent_folders=recents))

    assert created.welcome_screen.recent_folders() == recents


def test_opening_a_folder_promotes_it_in_the_recents(
    window: Callable[..., MainWindow], sample_folder: Path, tmp_path: Path
) -> None:
    """The most recently opened folder moves to the front of the list."""
    older = tmp_path / "older"
    created = window(Config(recent_folders=(older,)))

    created.open_folder(sample_folder)

    assert created.welcome_screen.recent_folders() == (sample_folder, older)


def test_save_state_persists_the_window_geometry(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path, tmp_path: Path
) -> None:
    """Closing remembers the size so the next launch looks the same."""
    created = window()
    created.open_folder(sample_folder)
    created.resize(700, 560)

    created.save_state()

    saved = load_config(tmp_path / "config.json")
    assert saved.window == WindowConfig(width=700, height=560)
    assert saved.last_folder == sample_folder


def test_closing_the_window_saves_the_session(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path, tmp_path: Path
) -> None:
    """``closeEvent`` writes the configuration without being asked."""
    created = window()
    created.open_folder(sample_folder)

    created.close()

    assert load_config(tmp_path / "config.json").last_folder == sample_folder


def test_switch_to_another_folder_through_the_picker(
    window: Callable[..., MainWindow],
    fake_file_dialog: type[FakeFileDialog],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """File → Open Folder uses the dialog and starts a new session."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_images(first, count=1)
    make_images(second, count=2, prefix="SECOND_", fmt="PNG")
    created = window()
    created.open_folder(first)

    fake_file_dialog.result = str(second)
    created.findChild(QAction, "action_open_folder").trigger()  # type: ignore[union-attr]

    assert created.sorter is not None
    assert created.sorter.source_folder.name == "second"
    assert created.progress_label.text() == "Image 1 of 2"
    assert created.sorter.total == 2


# ----------------------------------------------------------------------
# Committing decisions
# ----------------------------------------------------------------------


def test_footer_button_moves_the_image(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """A click on the footer is an alternative to a drag."""
    created = window()
    created.open_folder(sample_folder)

    qtbot.mouseClick(created.category_buttons["Bad"], Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: (sample_folder / "Bad" / "IMG_1.jpg").exists(), timeout=5000)

    assert not (sample_folder / "IMG_1.jpg").exists()
    assert created.progress_label.text() == "Image 2 of 3"
    assert "Bad 1" in created.status_counts_label.text()
    assert "2 left" in created.status_counts_label.text()
    assert created.swipe_widget.card.scaled_pixmap() is not None


def test_keyboard_action_moves_the_image(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """The arrow/WASD action for a category commits it."""
    created = window()
    created.open_folder(sample_folder)

    commit(qtbot, created, "Great")

    assert (sample_folder / "Great" / "IMG_1.jpg").exists()
    assert "Great 1" in created.status_counts_label.text()


def test_each_category_lands_in_its_own_folder(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """All four decisions map to the folders the sorter manages."""
    folder = tmp_path / "four"
    make_images(folder, count=4)
    created = window()
    created.open_folder(folder)

    for category in CATEGORIES:
        commit(qtbot, created, category)

    for index, category in enumerate(CATEGORIES, start=1):
        assert (folder / category / f"IMG_{index}.jpg").exists()
    assert created.current_page == "completion"


def test_finishing_the_deck_shows_the_summary(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """The last decision swaps in the completion page with the session counts."""
    created = window()
    created.open_folder(sample_folder)

    commit(qtbot, created, "Good")
    commit(qtbot, created, "Good")
    commit(qtbot, created, "OK")

    assert created.current_page == "completion"
    assert created.completion_screen.headline.text() == "All done! 3 images sorted"
    assert created.completion_screen.buttons["open"].isEnabled()
    assert created.progress_label.text() == ""
    assert "0 left" in created.status_counts_label.text()
    for action in created.category_actions.values():
        assert not action.isEnabled()
    for button in created.category_buttons.values():
        assert not button.isEnabled()


def test_second_decision_is_ignored_while_the_card_flies(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """A rapid double press must not move two files for one image."""
    created = window()
    created.open_folder(sample_folder)

    created.category_actions["Good"].trigger()
    created.category_actions["Bad"].trigger()
    qtbot.waitUntil(
        lambda: created.sorter is not None and sum(created.sorter.counts.values()) == 1,
        timeout=5000,
    )

    assert created.sorter is not None
    assert created.sorter.counts == {"Good": 1}
    assert (sample_folder / "Good" / "IMG_1.jpg").exists()
    assert not list((sample_folder / "Bad").iterdir())


def test_skip_keeps_the_file_and_advances(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """Space leaves the image in place and shows the next one."""
    created = window()
    created.open_folder(sample_folder)
    skip = created.findChild(QAction, "action_skip")
    assert skip is not None and skip.isEnabled()

    skip.trigger()

    assert (sample_folder / "IMG_1.jpg").exists()
    assert created.progress_label.text() == "Image 2 of 3"
    assert "3 left" in created.status_counts_label.text()
    assert created.sorter is not None and created.sorter.counts == {}


def test_skipping_the_last_image_finishes_the_session(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """Skipping everything ends on the summary with zero moves."""
    folder = tmp_path / "skipall"
    make_images(folder, count=2)
    created = window()
    created.open_folder(folder)
    skip = created.findChild(QAction, "action_skip")
    assert skip is not None

    skip.trigger()
    skip.trigger()

    assert created.current_page == "completion"
    assert created.completion_screen.headline.text() == "All done! 0 images sorted"
    assert len(list(folder.glob("*.jpg"))) == 2


# ----------------------------------------------------------------------
# Undo
# ----------------------------------------------------------------------


def test_undo_restores_the_last_image(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """Undo moves the file back, shows it again and clears the counter."""
    created = window()
    created.open_folder(sample_folder)
    commit(qtbot, created, "Good")
    undo = created.findChild(QAction, "action_undo")
    assert undo is not None and undo.isEnabled()

    undo.trigger()

    assert (sample_folder / "IMG_1.jpg").exists()
    assert not (sample_folder / "Good" / "IMG_1.jpg").exists()
    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 3"
    assert "Good 0" in created.status_counts_label.text()
    assert not undo.isEnabled()


def test_undo_paints_the_restored_card(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """The restored card is actually on screen, not merely queued again.

    Regression guard: a stage-wide opacity effect sitting above the card's own
    drop-shadow effect made Qt paint an empty stage after undo, while all the
    state assertions above still passed. ``IMG_1.jpg`` is a flat image, so the
    stage centre must show its colour.
    """
    created = window()
    created.open_folder(sample_folder)
    commit(qtbot, created, "Good")
    undo = created.findChild(QAction, "action_undo")
    assert undo is not None
    undo.trigger()
    qtbot.waitUntil(lambda: created.swipe_widget.card.fade == pytest.approx(1.0), timeout=5000)

    stage = created.swipe_widget
    grabbed = stage.grab().toImage()
    painted = grabbed.pixelColor(grabbed.width() // 2, grabbed.height() // 2)
    assert abs(painted.red() - 37) <= 8  # make_images(): (IMG_1 * 37 % 256, 80, 160)
    assert abs(painted.green() - 80) <= 8
    assert abs(painted.blue() - 160) <= 8


def test_undo_from_the_summary_returns_to_the_stage(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """Finishing the deck is not a one-way trip: the last move can be undone."""
    folder = tmp_path / "one"
    make_images(folder, count=1)
    created = window()
    created.open_folder(folder)
    commit(qtbot, created, "OK")
    assert created.current_page == "completion"

    undo = created.findChild(QAction, "action_undo")
    assert undo is not None and undo.isEnabled()
    undo.trigger()

    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 1"
    assert (folder / "IMG_1.jpg").exists()


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------


def test_unreadable_image_is_skipped_with_a_toast(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """A corrupt file is announced in the status bar and left in place."""
    folder = tmp_path / "corrupt"
    make_images(folder, count=1)
    make_images(folder, count=1, start=2, corrupt=True)
    created = window()
    created.open_folder(folder)
    assert created.progress_label.text() == "Image 1 of 2"

    commit(qtbot, created, "Good")
    qtbot.waitUntil(lambda: "unreadable" in created.statusBar().currentMessage(), timeout=3000)

    assert dialogs == []
    assert "IMG_2.jpg" in created.statusBar().currentMessage()
    assert (folder / "IMG_2.jpg").exists()
    assert created.current_page == "completion"
    note = created.completion_screen.findChild(QWidget, "completion_skipped")
    assert note is not None and note.isVisible()


def test_folder_of_only_corrupt_images_finishes_immediately(
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """Nothing decodable means the session ends with an explanation, not a crash."""
    folder = tmp_path / "broken"
    make_images(folder, count=2, corrupt=True)
    created = window()

    assert created.open_folder(folder)

    assert created.current_page == "completion"
    assert dialogs == []
    assert "2 unreadable image(s)" in created.statusBar().currentMessage()
    assert created.completion_screen.headline.text() == "All done! 0 images sorted"


def test_failed_move_keeps_the_image_queued(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    monkeypatch: pytest.MonkeyPatch,
    sample_folder: Path,
) -> None:
    """A permission error leaves the session usable and the file untouched."""

    def refuse(_self: Sorter, _category: str) -> None:
        raise FileOperationError("permission denied", source=sample_folder / "IMG_1.jpg")

    monkeypatch.setattr(Sorter, "categorize", refuse)
    created = window()
    created.open_folder(sample_folder)

    created.category_actions["Good"].trigger()
    wait_for_dialog(qtbot, dialogs)

    assert dialogs[0][0] == "error"
    assert dialogs[0][1] == "Could not move image"
    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 3"
    assert (sample_folder / "IMG_1.jpg").exists()
    assert created.sorter is not None and created.sorter.counts == {}
    assert created.swipe_widget.is_interactive()
    assert created.swipe_widget.card.scaled_pixmap() is not None


def test_vanished_image_is_dropped_with_a_warning(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    sample_folder: Path,
) -> None:
    """A file deleted behind the app's back is reported and skipped."""
    created = window()
    created.open_folder(sample_folder)
    (sample_folder / "IMG_1.jpg").unlink()

    created.category_actions["Good"].trigger()
    wait_for_dialog(qtbot, dialogs)

    assert dialogs[0][0] == "warning"
    assert dialogs[0][1] == "Image disappeared"
    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 2"
    assert created.sorter is not None and created.sorter.counts == {}


def test_undo_reports_a_destination_that_vanished(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    sample_folder: Path,
) -> None:
    """Undo cannot guess where the file went, so it says so."""
    created = window()
    created.open_folder(sample_folder)
    commit(qtbot, created, "Good")
    (sample_folder / "Good" / "IMG_1.jpg").unlink()
    undo = created.findChild(QAction, "action_undo")
    assert undo is not None

    undo.trigger()

    assert dialogs[0][0] == "warning"
    assert dialogs[0][1] == "Could not undo"
    assert created.current_page == "stage"


# ----------------------------------------------------------------------
# Restarting and helpers
# ----------------------------------------------------------------------


def test_open_source_folder_rescans_after_finishing(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    sample_folder: Path,
) -> None:
    """The summary's first button starts a new session on the same folder."""
    created = window()
    created.open_folder(sample_folder)
    for _ in range(3):
        commit(qtbot, created, "Good")
    assert created.current_page == "completion"
    make_images(sample_folder, count=1, prefix="LATE_", start=9)

    qtbot.mouseClick(created.completion_screen.buttons["open"], Qt.MouseButton.LeftButton)

    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 1"
    assert created.sorter is not None and created.sorter.counts == {}


def test_category_actions_expose_the_documented_keys(
    window: Callable[..., MainWindow],
) -> None:
    """Arrows and WASD are both bound, window-wide."""
    created = window()

    expected = {
        "Good": ["Right", "D"],
        "Bad": ["Left", "A"],
        "Great": ["Up", "W"],
        "OK": ["Down", "S"],
    }
    for category, keys in expected.items():
        action = created.category_actions[category]
        assert [sequence.toString() for sequence in action.shortcuts()] == keys
        assert action.shortcutContext() == Qt.ShortcutContext.WindowShortcut


def test_pil_images_are_converted_without_losing_alpha() -> None:
    """The GUI boundary keeps RGBA pixels intact for transparent previews."""
    image = Image.new("RGBA", (4, 3), (10, 20, 30, 40))

    converted = qimage_from_pil(image)

    assert (converted.width(), converted.height()) == (4, 3)
    colour = converted.pixelColor(1, 1)
    assert (colour.red(), colour.green(), colour.blue(), colour.alpha()) == (10, 20, 30, 40)


def test_default_sorter_factory_scans_without_decoding(
    make_images: Callable[..., list[Path]], tmp_path: Path
) -> None:
    """Opening a folder is a stat-only pass; decoding happens per image."""
    make_images(tmp_path, count=1)
    make_images(tmp_path, count=1, prefix="broken_", corrupt=True)

    sorter = default_sorter_factory(tmp_path)

    assert sorter.total == 2


# ----------------------------------------------------------------------
# Shortcuts: rescan, full screen and the reference overlay
# ----------------------------------------------------------------------


def test_rescan_picks_up_images_added_mid_session(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    sample_folder: Path,
    make_images: Callable[..., list[Path]],
) -> None:
    """F5/Ctrl+R rescans without losing counters or the undo history."""
    created = window()
    created.open_folder(sample_folder)
    commit(qtbot, created, "Good")
    make_images(sample_folder, count=1, prefix="LATE_", start=9)
    rescan = created.findChild(QAction, "action_rescan")
    assert rescan is not None and rescan.isEnabled()

    rescan.trigger()

    sorter = created.sorter
    assert sorter is not None
    assert created.current_page == "stage"
    assert sorter.remaining_count == 3
    assert sorter.total == 4
    assert sorter.counts == {"Good": 1}
    assert created.progress_label.text() == "Image 2 of 4"
    assert "Good 1" in created.status_counts_label.text()
    assert "3 left" in created.status_counts_label.text()
    assert "Rescanned: 3 image(s) left" in created.statusBar().currentMessage()
    undo = created.findChild(QAction, "action_undo")
    assert undo is not None and undo.isEnabled()


def test_rescan_with_nothing_left_shows_the_summary(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """Rescanning a drained folder keeps the summary instead of a blank stage."""
    folder = tmp_path / "drained"
    make_images(folder, count=1)
    created = window()
    created.open_folder(folder)
    commit(qtbot, created, "OK")
    assert created.current_page == "completion"

    rescan = created.findChild(QAction, "action_rescan")
    assert rescan is not None
    rescan.trigger()

    assert created.current_page == "completion"
    assert created.completion_screen.headline.text() == "All done! 1 image sorted"
    assert "No images left" in created.statusBar().currentMessage()


def test_rescan_does_not_double_count_unreadable_images(
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """A file that cannot be decoded stays one skipped image after a rescan."""
    folder = tmp_path / "corrupt"
    make_images(folder, count=1, corrupt=True)
    created = window()
    created.open_folder(folder)
    note = created.completion_screen.findChild(QWidget, "completion_skipped")
    assert note is not None and note.text().startswith("1 image")

    rescan = created.findChild(QAction, "action_rescan")
    assert rescan is not None
    rescan.trigger()

    assert note.text().startswith("1 image")


def test_rescan_is_disabled_without_a_session(window: Callable[..., MainWindow]) -> None:
    """There is nothing to rescan on the welcome page, so the action is off."""
    created = window()

    rescan = created.findChild(QAction, "action_rescan")

    assert rescan is not None and not rescan.isEnabled()


def test_fullscreen_action_toggles_the_window_state(
    qtbot: QtBot, window: Callable[..., MainWindow]
) -> None:
    """F11 hides the chrome and comes back on the second press."""
    created = window()
    fullscreen = created.findChild(QAction, "action_fullscreen")
    assert fullscreen is not None and fullscreen.isCheckable()

    fullscreen.trigger()
    qtbot.waitUntil(created.isFullScreen, timeout=2000)

    assert fullscreen.isChecked()

    fullscreen.trigger()
    qtbot.waitUntil(lambda: not created.isFullScreen(), timeout=2000)

    assert not fullscreen.isChecked()


def test_save_state_remembers_the_normal_size_in_full_screen(
    window: Callable[..., MainWindow], tmp_path: Path
) -> None:
    """Closing in full screen must not persist a screen-sized window."""
    created = window()
    created.resize(700, 560)
    created.showFullScreen()

    created.save_state()

    saved = load_config(tmp_path / "config.json")
    assert saved.window == WindowConfig(width=700, height=560)


def test_documented_shortcuts_match_the_actions(window: Callable[..., MainWindow]) -> None:
    """Every documented key is bound, and the overlay documents it back."""
    created = window()
    expected = {
        "action_open_folder": ["Ctrl+O"],
        "action_rescan": ["F5", "Ctrl+R"],
        "action_undo": ["Ctrl+Z"],
        "action_quit": ["Ctrl+Q"],
        "action_fullscreen": ["F11"],
        "action_shortcut_help": ["F1", "?"],
    }
    for name, keys in expected.items():
        action = created.findChild(QAction, name)
        assert action is not None, name
        assert [sequence.toString() for sequence in action.shortcuts()] == keys

    created.findChild(QAction, "action_shortcut_help").trigger()  # type: ignore[union-attr]
    overlay = created.shortcut_overlay
    assert overlay is not None
    documented = overlay.keys_text()
    for keys in expected.values():
        for key in keys:
            assert key in documented, f"{key} is bound but not documented"
    assert "Space" in documented


def test_quit_is_bound_on_linux(window: Callable[..., MainWindow]) -> None:
    """``StandardKey.Quit`` is empty on Linux, so Ctrl+Q must be spelled out."""
    created = window()

    quit_action = created.findChild(QAction, "action_quit")

    assert quit_action is not None
    assert [sequence.toString() for sequence in quit_action.shortcuts()] == ["Ctrl+Q"]


def test_about_box_names_the_app_version_and_support_button(
    window: Callable[..., MainWindow],
) -> None:
    """The About box names the product, the version and the coffee button."""
    created = window()

    box, coffee = created._build_about_box()

    assert box.objectName() == "about_box"
    assert box.windowTitle() == f"About {APP_DISPLAY_NAME}"
    assert APP_DISPLAY_NAME in box.text()
    assert __version__ in box.text()
    assert coffee.text() == "Buy me a coffee"
    assert coffee.objectName() == "button_buy_me_a_coffee"
    assert SUPPORT_URL in coffee.toolTip()


def test_coffee_button_opens_the_support_page(
    window: Callable[..., MainWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clicking the button hands the donation URL to the desktop service."""
    opened: list[QUrl] = []

    # Stands in for QDesktopServices so the test never launches a browser.
    class RecordingDesktopServices:
        @staticmethod
        def openUrl(url: QUrl) -> bool:
            opened.append(url)
            return True

    monkeypatch.setattr(main_window_module, "QDesktopServices", RecordingDesktopServices)
    created = window()

    _box, coffee = created._build_about_box()
    coffee.click()

    assert [url.toString() for url in opened] == [SUPPORT_URL]


def test_about_action_sits_in_the_help_menu(window: Callable[..., MainWindow]) -> None:
    """*Help → About* exists and names the app rather than the action."""
    created = window()

    action = created.findChild(QAction, "action_about")

    assert action is not None
    assert APP_DISPLAY_NAME in action.text()


def test_shortcut_help_reuses_one_overlay(qtbot: QtBot, window: Callable[..., MainWindow]) -> None:
    """The window builds the overlay once and keeps it for the whole session."""
    created = window()
    action = created.findChild(QAction, "action_shortcut_help")
    assert action is not None
    assert created.shortcut_overlay is None

    action.trigger()
    first = created.shortcut_overlay
    assert first is not None
    qtbot.waitUntil(first.isVisible, timeout=2000)

    action.trigger()

    assert created.shortcut_overlay is first
    assert first.isVisible()


# ----------------------------------------------------------------------
# Polish: theme, footer labels, summary bar, prefetching and dry run
# ----------------------------------------------------------------------


def test_footer_buttons_show_their_swipe_arrows(window: Callable[..., MainWindow]) -> None:
    """Each caption repeats its gesture; nothing else hints at the keys."""
    created = window()

    labels = {category: button.text() for category, button in created.category_buttons.items()}

    assert labels == {
        "Bad": "← Bad",
        "OK": "↓ OK",
        "Great": "↑ Great",
        "Good": "Good →",
    }
    assert created.swipe_widget.findChild(QLabel, "swipe_legend") is None


def test_summary_bar_uses_the_category_colours(
    window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """The live counts are coloured per category, like the buttons."""
    created = window()
    created.open_folder(sample_folder)

    text = created.status_counts_label.text()

    assert "Good 0" in text
    for colour in ("#3ddc84", "#ff5b5b", "#f2c14e", "#4aa3ff"):
        assert colour in text


def test_opening_a_folder_starts_prefetching(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """The next previews are decoded in the background, not on demand."""
    created = window()

    created.open_folder(sample_folder)

    prefetcher = created.prefetcher
    assert prefetcher is not None
    qtbot.waitUntil(lambda: len(prefetcher.cached_paths()) >= 2, timeout=5000)
    assert str(sample_folder / "IMG_1.jpg") not in prefetcher.cached_paths()


def test_dark_mode_toggle_switches_and_persists(
    qtbot: QtBot, window: Callable[..., MainWindow], tmp_path: Path
) -> None:
    """View → Dark Mode applies the palette and remembers the choice."""
    created = window(Config(theme="light"))
    dark = created.findChild(QAction, "action_dark_mode")
    assert dark is not None
    assert not dark.isChecked()

    dark.trigger()

    assert dark.isChecked()
    assert created.config.theme == "dark"
    saved = load_config(tmp_path / "config.json")
    assert saved.theme == "dark"
    assert "Dark theme" in created.statusBar().currentMessage()

    dark.trigger()

    assert not dark.isChecked()
    assert created.config.theme == "light"


def test_dark_config_checks_the_menu_item(window: Callable[..., MainWindow]) -> None:
    """A remembered dark theme shows up as a ticked menu item."""
    created = window(Config(theme="dark"))

    dark = created.findChild(QAction, "action_dark_mode")

    assert dark is not None and dark.isChecked()


def test_dry_run_never_moves_a_file(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """``--dry-run`` walks the session but leaves every image where it was."""
    created = window(dry_run=True)
    assert created.dry_run
    assert "(dry run)" in created.windowTitle()
    assert created.open_folder(sample_folder)
    assert "Dry run" in created.statusBar().currentMessage()

    commit(qtbot, created, "Good")

    assert (sample_folder / "IMG_1.jpg").exists()
    assert not (sample_folder / "Good" / "IMG_1.jpg").exists()
    sorter = created.sorter
    assert sorter is not None and sorter.counts == {"Good": 1}
    assert created.progress_label.text() == "Image 2 of 3"
    assert "would move IMG_1.jpg" in created.statusBar().currentMessage()


def test_dry_run_undo_returns_to_the_stage(
    qtbot: QtBot, window: Callable[..., MainWindow], sample_folder: Path
) -> None:
    """Undo in a dry run is rehearsed too, and cannot fail on a missing file."""
    created = window(dry_run=True)
    created.open_folder(sample_folder)
    commit(qtbot, created, "Bad")

    undo = created.findChild(QAction, "action_undo")
    assert undo is not None
    undo.trigger()

    assert created.current_page == "stage"
    assert created.progress_label.text() == "Image 1 of 3"
    assert (sample_folder / "IMG_1.jpg").exists()


def test_empty_folder_message_suggests_adding_photos(
    window: Callable[..., MainWindow], dialogs: list[tuple[str, str, str]], tmp_path: Path
) -> None:
    """An empty folder is explained, with the supported formats."""
    folder = tmp_path / "empty"
    folder.mkdir()
    created = window()

    assert not created.open_folder(folder)

    assert dialogs[0][0] == "info"
    assert dialogs[0][1] == "No images found"
    assert "does not contain any supported image files" in dialogs[0][2]
    assert "Add some photos" in dialogs[0][2]


def test_folder_of_only_subfolders_names_them(
    window: Callable[..., MainWindow],
    dialogs: list[tuple[str, str, str]],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """Photos one level down are pointed out instead of silently missing."""
    folder = tmp_path / "trip"
    make_images(folder / "day_1", count=1)
    make_images(folder / "day_2", count=1)
    (folder / "notes").mkdir()
    created = window()

    assert not created.open_folder(folder)

    message = dialogs[0][2]
    assert "The images are in subfolders: day_1, day_2" in message
    assert "Open one of them to sort it." in message


def test_folder_of_empty_subfolders_says_so(
    window: Callable[..., MainWindow], dialogs: list[tuple[str, str, str]], tmp_path: Path
) -> None:
    """Subfolders without images are still named, with the right advice."""
    folder = tmp_path / "albums"
    (folder / "misc").mkdir(parents=True)
    (folder / "old").mkdir()
    created = window()

    assert not created.open_folder(folder)

    message = dialogs[0][2]
    assert "It only contains subfolders: misc, old." in message
    assert "Open one of them to sort its images." in message


def test_large_image_is_downscaled_for_display_and_moved_unchanged(
    qtbot: QtBot,
    window: Callable[..., MainWindow],
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
) -> None:
    """A 12 MP photo is previewed at screen size while the original moves as-is."""
    folder = tmp_path / "huge"
    source = make_images(folder, count=1, size=(4000, 3000))[0]
    original = source.read_bytes()
    created = window()

    assert created.open_folder(folder)
    preview = created.swipe_widget.card.pixmap
    assert preview is not None
    assert max(preview.width(), preview.height()) <= 1600

    commit(qtbot, created, "Great")

    moved = folder / "Great" / source.name
    assert moved.exists()
    assert moved.read_bytes() == original
