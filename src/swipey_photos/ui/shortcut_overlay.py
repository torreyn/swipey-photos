"""Keyboard shortcut reference: a small non-modal overlay listing every binding.

Responsibility
    Answer "which key does what?" without leaving the session. The overlay is a
    read-only view: it renders :data:`SHORTCUT_GROUPS` as a two-column grid
    (keys, what they do) and offers one way out (the Close button or Esc). It
    talks to nothing else — no sorter, no configuration, no filesystem.

Public API
    ShortcutRow                         ``(keys, description)`` pair
    SHORTCUT_GROUPS                     the documented bindings, grouped
    class ShortcutOverlay(QDialog):
        show_overlay() -> None          # show and raise, reuse-safe
        shortcut_pairs() -> tuple[ShortcutRow, ...]
        headings() -> tuple[str, ...]
        keys_text() -> str              # every documented key, space-joined
        close_button -> QPushButton

Behaviour
    * Non-modal: the window underneath stays interactive, so the list can be
      read and the session continued. The window owns one instance and reuses
      it, so repeated presses raise the overlay instead of stacking copies.
    * Key caps and headings use palette roles, so the overlay follows the system
      colour scheme rather than hard-coding a look.
    * :data:`SHORTCUT_GROUPS` is the table the tests compare against the
      window's real ``QAction`` shortcuts, so the documentation cannot drift
      away from the bindings it describes.
    * Nothing here is stateful: the widget is built once, and showing or hiding
      it changes no application state.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.logging_setup import get_logger
from .branding import APP_DISPLAY_NAME

LOGGER = get_logger(__name__)

ShortcutRow = tuple[str, str]
"""One overlay row: the keys to press and what they do."""

SHORTCUT_GROUPS: tuple[tuple[str, tuple[ShortcutRow, ...]], ...] = (
    (
        "Sorting",
        (
            ("→  D", "Good — keep it"),
            ("←  A", "Bad — reject it"),
            ("↑  W", "Great — best of the set"),
            ("↓  S", "OK — undecided"),
        ),
    ),
    (
        "Session",
        (
            ("Ctrl+O", "Open another folder"),
            ("F5  Ctrl+R", "Rescan the folder for new images"),
            ("Ctrl+Z", "Undo the last move"),
            ("Space", "Skip for now; the file stays in the folder"),
        ),
    ),
    (
        "Window",
        (
            ("F11", "Toggle full screen"),
            ("F1  ?", "Show or hide this list"),
            ("Ctrl+Q", "Quit and save the window state"),
        ),
    ),
)
"""Every binding the application documents, in display order.

``F5  Ctrl+R`` means both sequences do the same thing; the two-key rows read
better than two separate lines in the grid.
"""

_KEY_CAP_STYLE = (
    "QLabel { background-color: palette(alternate-base);"
    " border: 1px solid palette(mid); border-radius: 5px;"
    " padding: 2px 8px; color: palette(window-text); }"
)
"""Stylesheet for a key cap, resolved from the active colour scheme."""

_MUTED_STYLE = "color: palette(mid);"
"""Stylesheet for secondary text, resolved from the active colour scheme."""


class ShortcutOverlay(QDialog):
    """Read-only reference of every keyboard binding, shown over the window.

    Args:
        parent: Optional Qt parent; the main window passes itself so the
            overlay stays above it and is destroyed with it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the overlay from :data:`SHORTCUT_GROUPS`."""
        super().__init__(parent)  # PyQt6 types the parent as Self
        self.setObjectName("shortcut_overlay")
        self.setWindowTitle(f"{APP_DISPLAY_NAME} keyboard shortcuts")
        self.setModal(False)
        self.setMinimumWidth(460)

        heading = QLabel("Keyboard shortcuts", self)
        heading.setObjectName("shortcut_overlay_heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        heading_font = QFont(heading.font())
        heading_font.setPointSize(max(heading_font.pointSize(), 12) + 4)
        heading_font.setBold(True)
        heading.setFont(heading_font)

        grid_holder = QWidget(self)
        grid_holder.setObjectName("shortcut_overlay_rows")
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        row = 0
        for group, rows in SHORTCUT_GROUPS:
            group_label = QLabel(group, grid_holder)
            group_label.setObjectName(f"shortcut_group_{group.lower()}")
            group_font = QFont(group_label.font())
            group_font.setBold(True)
            group_label.setFont(group_font)
            group_label.setStyleSheet(_MUTED_STYLE)
            grid.addWidget(group_label, row, 0, 1, 2)
            row += 1
            for keys, description in rows:
                grid.addWidget(self._key_cap(keys, grid_holder), row, 0)
                label = QLabel(description, grid_holder)
                label.setObjectName("shortcut_description")
                label.setTextFormat(Qt.TextFormat.PlainText)
                grid.addWidget(label, row, 1)
                row += 1
            grid.setRowMinimumHeight(row, 10)
            row += 1

        hint = QLabel("Press F1 or ? at any time to hide this list.", self)
        hint.setObjectName("shortcut_overlay_hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hint.setStyleSheet(_MUTED_STYLE)

        self._close_button = QPushButton("Close", self)
        self._close_button.setObjectName("shortcut_overlay_close")
        self._close_button.setMinimumHeight(36)
        self._close_button.setDefault(True)
        self._close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)
        buttons.addWidget(self._close_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(grid_holder)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def close_button(self) -> QPushButton:
        """The dismiss button, exposed for tests and themes."""
        return self._close_button

    def shortcut_pairs(self) -> tuple[ShortcutRow, ...]:
        """Return every row as ``(keys, description)``, in display order."""
        return tuple(pair for _group, rows in SHORTCUT_GROUPS for pair in rows)

    def headings(self) -> tuple[str, ...]:
        """Return the group headings in display order."""
        return tuple(group for group, _rows in SHORTCUT_GROUPS)

    def keys_text(self) -> str:
        """Return every documented key sequence, space-joined.

        The drift test compares this text with the window's real ``QAction``
        shortcuts, so a binding added to one side without the other fails.
        """
        return " ".join(keys for keys, _description in self.shortcut_pairs())

    def show_overlay(self) -> None:
        """Show the overlay and give it focus; safe to call repeatedly.

        An overlay that is already visible is raised instead of shown again, so
        the window can keep a single instance for its whole life.
        """
        self.show()
        self.raise_()
        self.activateWindow()
        LOGGER.debug("shortcut overlay shown")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _key_cap(self, keys: str, parent: QWidget) -> QLabel:
        """Return a styled label that looks like a physical key for *keys*."""
        cap = QLabel(keys, parent)
        cap.setObjectName("shortcut_keys")
        cap.setTextFormat(Qt.TextFormat.PlainText)
        cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cap.setStyleSheet(_KEY_CAP_STYLE)
        cap.setToolTip(f"Press {keys}")
        return cap
