"""Light and dark palettes for the whole application.

Responsibility
    Own the two palettes and decide which one is in force. The window only says
    *which* theme the user configured (``system``, ``light`` or ``dark``); this
    module resolves that against the platform's colour scheme and installs the
    result on the ``QApplication``, so every widget follows without a single
    hard-coded colour of its own.

Public API
    DARK_WINDOW, DARK_TEXT        the two reference colours, for tests and docs
    build_dark_palette() -> QPalette
    build_light_palette() -> QPalette
    system_theme() -> str         ``"dark"`` or ``"light"`` for the platform
    apply_theme(theme) -> str     install a theme, return the effective name

Behaviour
    * Widgets use semantic palette roles (``palette(mid)``, ``palette(text)``)
      in their stylesheets, so switching palettes restyles the whole UI live.
    * The card plate keeps its own dark colour in both themes: it is an image
      mat, not chrome, and a white plate would glare around every photo.
    * An unknown theme name falls back to ``system`` instead of raising, because
      a hand-edited config file must never stop the app from opening.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from ..utils.config import THEME_DARK, THEME_LIGHT, THEME_SYSTEM, THEMES
from ..utils.logging_setup import get_logger

LOGGER = get_logger(__name__)

DARK_WINDOW = QColor(30, 32, 38)
"""Background colour of the dark theme; also what the tests assert against."""

DARK_TEXT = QColor(232, 234, 238)
"""Foreground colour of the dark theme."""


def _application() -> QApplication | None:
    """Return the running ``QApplication``, or ``None`` outside a GUI process."""
    instance: QCoreApplication | None = QApplication.instance()
    return instance if isinstance(instance, QApplication) else None


def build_dark_palette() -> QPalette:
    """Return the dark palette used by the whole application."""
    palette = QPalette()
    window = DARK_WINDOW
    text = DARK_TEXT
    base = QColor(24, 26, 31)
    alternate = QColor(38, 41, 48)
    disabled = QColor(128, 132, 142)
    highlight = QColor(74, 163, 255)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
    palette.setColor(QPalette.ColorRole.ToolTipBase, alternate)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 92, 92))
    palette.setColor(QPalette.ColorRole.Light, QColor(58, 62, 72))
    palette.setColor(QPalette.ColorRole.Midlight, QColor(48, 52, 60))
    palette.setColor(QPalette.ColorRole.Mid, QColor(120, 126, 138))
    palette.setColor(QPalette.ColorRole.Dark, QColor(18, 20, 24))
    palette.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(16, 18, 22))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(180, 140, 255))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 156, 168))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)

    return palette


def build_light_palette() -> QPalette:
    """Return the platform's standard palette, i.e. the light theme."""
    app = _application()
    if app is None:
        return QPalette()
    style = app.style()
    if style is None:  # pragma: no cover - QApplication always installs a style
        return QPalette()
    return style.standardPalette()


def system_theme() -> str:
    """Return ``"dark"`` or ``"light"`` depending on the desktop's preference."""
    app = _application()
    if app is None:
        return THEME_LIGHT
    hints = app.styleHints()
    if hints is None:  # pragma: no cover - every supported Qt build has it
        return THEME_LIGHT
    return THEME_DARK if hints.colorScheme() == Qt.ColorScheme.Dark else THEME_LIGHT


def apply_theme(theme: str) -> str:
    """Install *theme* on the application and return the name that took effect.

    Args:
        theme: ``"system"``, ``"light"`` or ``"dark"``; anything else is treated
            as ``"system"`` after a warning.

    Returns:
        The effective theme: ``"light"`` or ``"dark"``.
    """
    requested = theme if theme in THEMES else THEME_SYSTEM
    if requested != theme:
        LOGGER.warning("unknown theme %r; falling back to %s", theme, THEME_SYSTEM)
    effective = system_theme() if requested == THEME_SYSTEM else requested
    palette = build_dark_palette() if effective == THEME_DARK else build_light_palette()

    app = _application()
    if app is not None:
        app.setPalette(palette)
    LOGGER.debug("applied %s theme (requested %s)", effective, requested)
    return effective
