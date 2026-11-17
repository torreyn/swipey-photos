"""Welcome page: pick a folder, or reopen one of the last five.

Responsibility
    Give the application a friendly entry point before a session exists. The
    widget shows the brand mark, a one-line explanation and a single primary
    action ("Select Folder…"), then a list of recently opened folders that
    starts a session with one click. It performs no scanning and no file I/O:
    it only asks for a directory through ``QFileDialog`` and reports the choice
    as a signal, so the window decides what happens next.

Public API
    class WelcomeScreen(QWidget):
        folder_selected: pyqtSignal(str)        # absolute path of a directory
        set_recent_folders(folders) -> None
        recent_folders() -> tuple[Path, ...]
        choose_folder() -> None                 # open the directory dialog
        select_button -> QPushButton
        recent_buttons -> tuple[QPushButton, ...]

Behaviour
    * ``folder_selected`` carries ``str(Path)`` so the signal needs no Qt type
      registration and tests can compare it directly with ``str(tmp_path)``.
    * The recent list is newest-first, de-duplicated and capped at
      :data:`swipey_photos.utils.config.MAX_RECENT_FOLDERS`; entries are elided
      in the middle so long paths stay readable and the full path is a tooltip.
    * Cancelling the dialog emits nothing, so the window can stay where it is.
    * The primary button is the default button: Enter opens the picker, which is
      what a keyboard-only user expects on a page with one purpose.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from ..utils.config import MAX_RECENT_FOLDERS
from ..utils.logging_setup import get_logger
from .branding import APP_DISPLAY_NAME, TAGLINE, logo_pixmap

LOGGER = get_logger(__name__)

LOGO_SIZE = 96
"""Edge length of the welcome logo in logical pixels."""

RECENT_BUTTON_WIDTH = 420
"""Width budget for eliding a recent folder path, in logical pixels."""

_MUTED_STYLE = "color: palette(mid);"
"""Stylesheet for secondary text, resolved from the active colour scheme."""


class WelcomeScreen(QWidget):
    """Empty state with a folder picker and the most recent folders.

    Signals:
        folder_selected: Emitted with the absolute path of the chosen folder,
            either from the picker or from a recent-folder button.
    """

    folder_selected = pyqtSignal(str, arguments=["folder"])

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        recent_folders: Sequence[Path] = (),
    ) -> None:
        """Build the page and populate the recent list.

        Args:
            parent: Optional Qt parent.
            recent_folders: Newest-first folders offered as shortcuts; the list
                is trimmed to :data:`MAX_RECENT_FOLDERS` entries.
        """
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self.setObjectName("welcome_screen")
        self._recent: tuple[Path, ...] = ()
        self._recent_buttons: list[QPushButton] = []

        self._logo = QLabel(self)
        self._logo.setObjectName("welcome_logo")
        self._logo.setPixmap(logo_pixmap(LOGO_SIZE))
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title = QLabel(APP_DISPLAY_NAME, self)
        self._title.setObjectName("welcome_title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont(self._title.font())
        title_font.setPointSize(max(title_font.pointSize(), 12) + 14)
        title_font.setBold(True)
        self._title.setFont(title_font)

        self._tagline = QLabel(TAGLINE, self)
        self._tagline.setObjectName("welcome_tagline")
        self._tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tagline.setStyleSheet(_MUTED_STYLE)

        self._select_button = QPushButton("Select Folder…", self)
        self._select_button.setObjectName("welcome_select_folder")
        self._select_button.setMinimumSize(260, 48)
        self._select_button.setDefault(True)
        self._select_button.setToolTip("Choose the folder that holds the photos to sort (Ctrl+O)")
        self._select_button.clicked.connect(self.choose_folder)

        self._recent_header = QLabel("Recent folders", self)
        self._recent_header.setObjectName("welcome_recent_header")
        self._recent_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_header.setStyleSheet(_MUTED_STYLE)

        self._recent_container = QWidget(self)
        self._recent_container.setObjectName("welcome_recent_list")
        self._recent_layout = QVBoxLayout(self._recent_container)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(4)
        self._recent_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(12)
        layout.addStretch(1)
        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title)
        layout.addWidget(self._tagline)
        layout.addSpacing(20)
        layout.addWidget(self._select_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(20)
        layout.addWidget(self._recent_header)
        layout.addWidget(self._recent_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)

        self.set_recent_folders(recent_folders)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def select_button(self) -> QPushButton:
        """The primary "Select Folder…" button, exposed for shortcuts and tests."""
        return self._select_button

    @property
    def recent_buttons(self) -> tuple[QPushButton, ...]:
        """Shortcut buttons for the recent folders, newest first."""
        return tuple(self._recent_buttons)

    def recent_folders(self) -> tuple[Path, ...]:
        """Return the folders currently offered as shortcuts, newest first."""
        return self._recent

    def set_recent_folders(self, folders: Sequence[Path]) -> None:
        """Rebuild the recent-folder list from *folders*.

        Args:
            folders: Candidate folders, newest first. Duplicates and entries
                beyond :data:`MAX_RECENT_FOLDERS` are dropped; an empty sequence
                hides the list and its heading.
        """
        unique: list[Path] = []
        for folder in folders:
            path = Path(folder)
            if path not in unique:
                unique.append(path)
        self._recent = tuple(unique[:MAX_RECENT_FOLDERS])

        while self._recent_buttons:
            button = self._recent_buttons.pop()
            self._recent_layout.removeWidget(button)
            button.hide()
            button.deleteLater()

        metrics = QFontMetrics(self.font())
        for folder in self._recent:
            caption = metrics.elidedText(
                str(folder),
                Qt.TextElideMode.ElideMiddle,
                RECENT_BUTTON_WIDTH,
            )
            button = QPushButton(caption, self._recent_container)
            button.setObjectName("welcome_recent_folder")
            button.setFlat(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"Reopen {folder}")
            button.setMinimumWidth(RECENT_BUTTON_WIDTH)
            button.clicked.connect(lambda _checked=False, path=folder: self._emit(path))
            self._recent_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._recent_buttons.append(button)

        has_recent = bool(self._recent)
        self._recent_header.setVisible(has_recent)
        self._recent_container.setVisible(has_recent)

    def choose_folder(self) -> None:
        """Ask for a directory with ``QFileDialog`` and emit ``folder_selected``.

        Nothing is emitted when the user cancels the dialog.
        """
        start = str(self._recent[0]) if self._recent else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose a folder of photos",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if chosen:
            self._emit(Path(chosen))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit(self, folder: Path) -> None:
        """Log *folder* and emit it through :attr:`folder_selected`."""
        LOGGER.debug("welcome screen chose folder %s", folder)
        self.folder_selected.emit(str(folder))
