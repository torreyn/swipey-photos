"""Tests for the application bootstrap (``app.py``) and the CLI entry point.

Coverage
    * ``run()`` really shows a ``MainWindow``, opens the requested folder and
      returns the Qt exit code (the window closes itself from a timer, so the
      test exercises the real event loop);
    * a malformed configuration falls back to defaults with a visible warning
      instead of blocking startup;
    * ``build_main_window`` applies the app identity and icon;
    * ``--version`` answers without importing Qt, and the parser accepts the
      documented flags.

The ``QApplication`` comes from pytest-qt; ``run()`` reuses it, which is exactly
what the guard in ``app.run`` is for.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QTimer

from image_swiper import __version__
from image_swiper import app as app_module
from image_swiper.__main__ import build_parser, main
from image_swiper.ui.main_window import MainWindow
from image_swiper.utils.config import Config

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

DIALOG_TIMEOUT_MS = 5000
"""Safety net: quit the loop if the window never closes itself."""


def test_version_flag_prints_and_exits(
    capsys: pytest.CaptureFixture[str], xdg_dirs: dict[str, Path]
) -> None:
    """``--version`` is answered before the GUI starts."""
    assert main(["--version"]) == 0

    captured = capsys.readouterr()
    assert "ImageSwiper" in captured.out
    assert __version__ in captured.out


def test_parser_documents_the_cli(tmp_path: Path) -> None:
    """The documented flags all parse and land on the namespace."""
    folder = tmp_path / "photos"

    args = build_parser().parse_args([str(folder), "--verbose", "--log-level", "DEBUG"])

    assert args.folder == folder
    assert args.verbose is True
    assert args.log_level == "DEBUG"
    assert args.version is False


@pytest.mark.gui
def test_build_main_window_applies_the_identity(
    qtbot: QtBot, qapp: object, tmp_path: Path, xdg_dirs: dict[str, Path]
) -> None:
    """The composition root sets the names and the icon before showing a window."""
    app_module._configure_application(qapp)  # type: ignore[arg-type]

    window = app_module.build_main_window(
        qapp,  # type: ignore[arg-type]
        Config(),
        config_path=tmp_path / "config.json",
    )
    qtbot.addWidget(window)

    assert isinstance(window, MainWindow)
    assert window.current_page == "welcome"
    assert not window.windowIcon().isNull()
    assert qapp.applicationName() == "image-swiper"  # type: ignore[attr-defined]
    assert qapp.applicationDisplayName() == "ImageSwiper"  # type: ignore[attr-defined]
    assert qapp.applicationVersion() == __version__  # type: ignore[attr-defined]


def _run_until_closed(
    qtbot: QtBot,
    qapp: object,
    *,
    folder: Path | None = None,
    config: Config | None = None,
    config_path: Path,
) -> tuple[int, MainWindow]:
    """Call ``run()`` and close the window from a timer to end the event loop."""
    seen: dict[str, MainWindow] = {}

    def inspect() -> None:
        for widget in qapp.topLevelWidgets():  # type: ignore[attr-defined]
            if isinstance(widget, MainWindow):
                seen["window"] = widget
                qtbot.addWidget(widget)
                widget.close()

    QTimer.singleShot(150, inspect)
    QTimer.singleShot(DIALOG_TIMEOUT_MS, qapp.quit)  # type: ignore[attr-defined]
    code = app_module.run(
        ["image-swiper"],
        config=config,
        config_path=config_path,
        folder=folder,
    )
    assert "window" in seen, "run() never showed a MainWindow"
    return code, seen["window"]


@pytest.mark.gui
def test_run_shows_the_window_and_opens_the_folder(
    qtbot: QtBot,
    qapp: object,
    make_images: Callable[..., list[Path]],
    tmp_path: Path,
    xdg_dirs: dict[str, Path],
) -> None:
    """``run()`` enters the event loop, shows a session and returns 0."""
    folder = tmp_path / "photos"
    make_images(folder, count=2)

    code, window = _run_until_closed(
        qtbot,
        qapp,
        folder=folder,
        config=Config(),
        config_path=tmp_path / "config.json",
    )

    assert code == 0
    assert window.current_page == "stage"
    assert window.progress_label.text() == "Image 1 of 2"


@pytest.mark.gui
def test_run_survives_a_broken_configuration(
    qtbot: QtBot, qapp: object, tmp_path: Path, xdg_dirs: dict[str, Path]
) -> None:
    """A corrupt config file falls back to defaults and warns in the status bar."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{not json", encoding="utf-8")

    code, window = _run_until_closed(
        qtbot,
        qapp,
        config_path=config_file,
    )

    assert code == 0
    assert window.current_page == "welcome"
    assert "Settings could not be read" in window.statusBar().currentMessage()


@pytest.mark.gui
def test_run_keeps_an_existing_application(
    qtbot: QtBot, qapp: object, tmp_path: Path, xdg_dirs: dict[str, Path]
) -> None:
    """A second launch inside one process reuses the ``QApplication``."""
    from PyQt6.QtWidgets import QApplication

    code, _window = _run_until_closed(
        qtbot,
        qapp,
        config=Config(),
        config_path=tmp_path / "config.json",
    )

    assert code == 0
    assert QApplication.instance() is qapp
