"""Completion page: the session summary once every image has been sorted.

Responsibility
    Close the loop. When the deck is empty the window swaps this page in and
    shows how many images went into each destination, plus the three things a
    user actually wants next: start over in the same folder, choose another
    folder, or quit. The widget renders numbers it is given and emits intent as
    signals; it never asks the sorter or the filesystem anything itself.

Public API
    class CompletionScreen(QWidget):
        open_source_requested: pyqtSignal()     # rescan the same folder
        pick_folder_requested: pyqtSignal()     # show the folder picker
        quit_requested: pyqtSignal()
        set_summary(counts, *, source_folder=None, skipped=0) -> None

Behaviour
    * The headline is built from the counts, so it stays correct when a move
      failed and was retried: ``"All done! 47 images sorted"``.
    * One row per category, in :data:`CATEGORIES` order, each with the category
      colour and the session count; categories with zero images are still shown
      so the layout does not jump around between sessions.
    * ``skipped`` reports images that could not be decoded; the line only
      appears when it is greater than zero.
    * All counts come from :attr:`image_swiper.core.sorter.Sorter.counts`, which
      counts *this session*, not what happens to be on disk.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.folder_manager import CATEGORIES
from .swipe_card import CATEGORY_COLORS

_MUTED_STYLE = "color: palette(mid);"
"""Stylesheet for secondary text, resolved from the active colour scheme."""


class CompletionScreen(QWidget):
    """Summary page for a finished session.

    Signals:
        open_source_requested: The user wants to rescan the same folder.
        pick_folder_requested: The user wants to choose a different folder.
        quit_requested: The user wants to close the application.
    """

    open_source_requested = pyqtSignal(arguments=[])
    pick_folder_requested = pyqtSignal(arguments=[])
    quit_requested = pyqtSignal(arguments=[])

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the page with an empty summary."""
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self.setObjectName("completion_screen")

        self._headline = QLabel("All done!", self)
        self._headline.setObjectName("completion_headline")
        self._headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline_font = QFont(self._headline.font())
        headline_font.setPointSize(max(headline_font.pointSize(), 12) + 12)
        headline_font.setBold(True)
        self._headline.setFont(headline_font)

        self._folder_label = QLabel("", self)
        self._folder_label.setObjectName("completion_folder")
        self._folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._folder_label.setStyleSheet(_MUTED_STYLE)
        self._folder_label.setWordWrap(True)

        self._rows = QWidget(self)
        self._rows.setObjectName("completion_rows")
        self._rows_layout = QGridLayout(self._rows)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setHorizontalSpacing(18)
        self._rows_layout.setVerticalSpacing(6)
        self._count_labels: dict[str, QLabel] = {}
        self._build_rows()

        self._skipped_label = QLabel("", self)
        self._skipped_label.setObjectName("completion_skipped")
        self._skipped_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._skipped_label.setStyleSheet(_MUTED_STYLE)
        self._skipped_label.setVisible(False)

        self._open_button = QPushButton("Open source folder", self)
        self._open_button.setObjectName("completion_open_source")
        self._open_button.setMinimumHeight(40)
        self._open_button.setToolTip("Scan the same folder again for new images")
        self._open_button.clicked.connect(self.open_source_requested)

        self._pick_button = QPushButton("Pick another folder", self)
        self._pick_button.setObjectName("completion_pick_folder")
        self._pick_button.setMinimumHeight(40)
        self._pick_button.clicked.connect(self.pick_folder_requested)

        self._quit_button = QPushButton("Quit", self)
        self._quit_button.setObjectName("completion_quit")
        self._quit_button.setMinimumHeight(40)
        self._quit_button.clicked.connect(self.quit_requested)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)
        buttons.addWidget(self._open_button)
        buttons.addWidget(self._pick_button)
        buttons.addWidget(self._quit_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(14)
        layout.addStretch(1)
        layout.addWidget(self._headline)
        layout.addWidget(self._folder_label)
        layout.addSpacing(16)
        layout.addWidget(self._rows, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._skipped_label)
        layout.addSpacing(24)
        layout.addLayout(buttons)
        layout.addStretch(2)

        self.set_summary({})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def headline(self) -> QLabel:
        """The "All done! N images sorted" label, exposed for tests and themes."""
        return self._headline

    @property
    def buttons(self) -> dict[str, QPushButton]:
        """The three actions keyed by name: ``open``, ``pick`` and ``quit``."""
        return {"open": self._open_button, "pick": self._pick_button, "quit": self._quit_button}

    def set_summary(
        self,
        counts: Mapping[str, int],
        *,
        source_folder: Path | None = None,
        skipped: int = 0,
    ) -> None:
        """Render the session result.

        Args:
            counts: Images moved per category, as returned by
                :attr:`image_swiper.core.sorter.Sorter.counts`. Unknown keys are
                ignored and missing categories count as zero.
            source_folder: Folder that was sorted, shown under the headline and
                used by the "Open source folder" button.
            skipped: Number of images that could not be decoded; ``0`` hides
                the note.
        """
        total = sum(counts.get(category, 0) for category in CATEGORIES)
        noun = "image" if total == 1 else "images"
        self._headline.setText(f"All done! {total} {noun} sorted")
        self._folder_label.setText(str(source_folder) if source_folder is not None else "")
        self._folder_label.setVisible(source_folder is not None)
        self._open_button.setEnabled(source_folder is not None)
        for category in CATEGORIES:
            self._count_labels[category].setText(str(counts.get(category, 0)))

        if skipped > 0:
            images = "image" if skipped == 1 else "images"
            self._skipped_label.setText(f"{skipped} {images} could not be read and were skipped.")
        self._skipped_label.setVisible(skipped > 0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_rows(self) -> None:
        """Create one permanent row per category, in canonical order."""
        for row, category in enumerate(CATEGORIES):
            colour = QLabel(self._rows)
            colour.setObjectName(f"completion_swatch_{category}")
            colour.setFixedSize(14, 14)
            colour.setStyleSheet(
                f"background-color: {CATEGORY_COLORS[category]}; border-radius: 7px;"
            )

            name = QLabel(category, self._rows)
            name.setObjectName(f"completion_name_{category}")

            count = QLabel("0", self._rows)
            count.setObjectName(f"completion_count_{category}")
            count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_font = QFont(count.font())
            count_font.setBold(True)
            count.setFont(count_font)

            self._rows_layout.addWidget(colour, row, 0, Qt.AlignmentFlag.AlignVCenter)
            self._rows_layout.addWidget(name, row, 1)
            self._rows_layout.addWidget(count, row, 2)
            self._count_labels[category] = count
