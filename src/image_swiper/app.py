"""Application bootstrap and object wiring.

Responsibility
    Own the process-level lifecycle: create the ``QApplication``, apply the
    application name/version/icon and the high-DPI policy, load the
    configuration, install the Qt-to-logging bridge, build
    :class:`image_swiper.ui.main_window.MainWindow`, show it and run the event
    loop. This module is the *composition root*: it is the only place where the
    process-wide objects are created, which keeps widgets testable with fakes
    and ``core``/``utils`` free of Qt.

Public API
    ORGANIZATION_NAME, ORGANIZATION_DOMAIN   identity reported by ``QApplication``
    run(argv=None, *, config=None, config_path=None, folder=None) -> int
        Configure the process, show the main window, return the Qt exit code.
        Called by :func:`image_swiper.__main__.main`.
    build_main_window(app, config=None, *, config_path=None) -> MainWindow
        Construct the window without entering the event loop, for tests.

Rules
    * All ``QApplication`` construction and exit-code handling lives here; no
      other module calls ``exec()`` or ``sys.exit``.
    * No filesystem scanning, decoding or file moves happen in this module.
    * Importing this module must not create widgets and must not read
      ``sys.argv``: Qt is imported lazily inside the functions, so
      ``python -m image_swiper --version`` works even where Qt cannot start.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .utils.config import Config, ConfigError, default_config, load_config
from .utils.logging_setup import get_logger

if TYPE_CHECKING:
    from PyQt6.QtCore import QCoreApplication, QMessageLogContext, QtMsgType
    from PyQt6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

LOGGER = get_logger(__name__)

ORGANIZATION_NAME = "ImageSwiper"
"""Value of ``QApplication.organizationName``; also used by Qt for app data."""

ORGANIZATION_DOMAIN = "github.com"
"""Value of ``QApplication.organizationDomain``."""

DESKTOP_FILE_NAME = "image-swiper"
"""Wayland/X11 application id Qt reports to the desktop environment."""

_QT_HANDLER_INSTALLED = False
"""Guard so repeated ``run()`` calls in tests cannot stack message handlers."""


def _enable_high_dpi() -> None:
    """Ask Qt 6 to keep fractional scale factors instead of rounding them.

    Qt 6 scales automatically; the Qt 5 attributes ``AA_EnableHighDpiScaling``
    and ``AA_UseHighDpiPixmaps`` no longer exist. The rounding policy is the one
    knob left, and it must be set before the ``QApplication`` is constructed.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def _configure_application(app: QApplication) -> None:
    """Apply the application name, version, identity and window icon."""
    from .ui.branding import APP_DISPLAY_NAME, app_icon

    app.setApplicationName("image-swiper")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain(ORGANIZATION_DOMAIN)
    app.setDesktopFileName(DESKTOP_FILE_NAME)
    app.setWindowIcon(app_icon())


def _install_qt_message_handler() -> None:
    """Route Qt's own diagnostic messages into the ``image_swiper`` log.

    Qt reports platform-plugin and font problems through its own handler, which
    writes to stderr and is lost in a desktop launch. Forwarding them keeps a
    single, greppable log file. Installing twice is a no-op.
    """
    global _QT_HANDLER_INSTALLED
    if _QT_HANDLER_INSTALLED:
        return

    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qt_logger = get_logger("qt")

    def handler(mode: QtMsgType, _context: QMessageLogContext, message: str | None) -> None:
        """Log one Qt message at the matching Python level."""
        qt_logger.log(levels.get(mode, logging.INFO), "%s", message or "")

    qInstallMessageHandler(handler)
    _QT_HANDLER_INSTALLED = True


def build_main_window(
    app: QApplication,
    config: Config | None = None,
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> MainWindow:
    """Construct the main window and its dependencies without an event loop.

    Args:
        app: The live ``QApplication``; its window icon is copied to the window
            so screen readers and window managers see the same brand mark.
        config: Configuration to use. When ``None`` it is read from
            *config_path* (or the XDG default).
        config_path: Explicit configuration file, used by ``--config`` and tests.
        dry_run: Rehearse the session instead of moving files, for ``--dry-run``.

    Returns:
        A :class:`~image_swiper.ui.main_window.MainWindow` that is not shown yet.

    Raises:
        ConfigError: The configuration file exists but cannot be used.
    """
    from .ui.main_window import MainWindow

    resolved = config if config is not None else load_config(config_path)
    window = MainWindow(config=resolved, config_path=config_path, dry_run=dry_run)
    window.setWindowIcon(app.windowIcon())
    return window


def run(
    argv: list[str] | None = None,
    *,
    config: Config | None = None,
    config_path: Path | None = None,
    folder: Path | str | None = None,
    dry_run: bool = False,
) -> int:
    """Create the application, show the main window and run the event loop.

    Args:
        argv: Argument vector handed to ``QApplication``; defaults to the
            sanitised ``sys.argv``. The CLI parses its own flags, so this
            normally carries only the program name.
        config: Pre-loaded configuration; when ``None`` the file is read and a
            broken file falls back to defaults with a visible warning.
        config_path: Alternative configuration file.
        folder: Folder to open immediately, skipping the welcome page.
        dry_run: Log what would be moved instead of moving anything.

    Returns:
        The Qt exit code (``0`` for a clean quit) or ``1`` when the window could
        not be created at all, for example because no Qt platform plugin loads.
    """
    from PyQt6.QtWidgets import QApplication

    try:
        _enable_high_dpi()
    except Exception:  # pragma: no cover - depends on the Qt build
        LOGGER.debug("high-DPI rounding policy unavailable", exc_info=True)

    existing: QCoreApplication | None = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else None
    if app is None:
        app = QApplication([sys.argv[0]] if argv is None else list(argv))

    _configure_application(app)
    _install_qt_message_handler()

    startup_warning = ""
    if config is None:
        try:
            config = load_config(config_path)
        except ConfigError as exc:
            LOGGER.error("configuration could not be read: %s", exc)
            startup_warning = f"Settings could not be read ({exc}); using defaults."
            config = default_config()

    try:
        window = build_main_window(app, config, config_path=config_path, dry_run=dry_run)
    except Exception:
        LOGGER.exception("could not create the main window")
        print(
            "ImageSwiper could not start. See the log for details; on a minimal "
            "system make sure the Qt platform plugin's system libraries "
            "(for example libxcb-cursor0) are installed.",
            file=sys.stderr,
        )
        return 1

    app.aboutToQuit.connect(window.save_state)
    window.show()
    if startup_warning:
        window.show_status_message(startup_warning, 10000)
    if folder is not None:
        window.open_folder(folder)
    elif not window.restore_last_session():
        LOGGER.info("no session restored; waiting on the welcome page")
    return app.exec()
