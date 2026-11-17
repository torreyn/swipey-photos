"""Main application window: the shell that ties the UI to the core layer.

Responsibility
    Present one sorting session and act as its *presenter*. ``MainWindow`` owns
    the session-level state (current folder, progress counters, images that were
    skipped) and translates user intent into core-layer calls. It contains
    layout and wiring only: no image decoding rules, no file moves and no
    animation maths of its own.

Composition
    * A ``QStackedWidget`` with three pages: :class:`WelcomeScreen`, the swipe
      stage (:class:`SwipeWidget`) and :class:`CompletionScreen`.
    * Header with ``"Image 3 of 47"`` and the folder path; footer with four
      buttons for users who prefer clicking to dragging. Each caption repeats
      the gesture it stands for (``← Bad``, ``↓ OK``, ``↑ Great``, ``Good →``),
      so the footer carries the key map that used to sit under the card.
    * Menus: *File* → Open Folder (Ctrl+O), Rescan Folder (F5, Ctrl+R), Undo
      Last (Ctrl+Z), Quit (Ctrl+Q); *View* → Dark Mode, Full Screen (F11);
      *Help* → Keyboard Shortcuts (F1, ?) and About; the About box carries the
      version, the tagline, the :data:`ui.branding.SUPPORT_URL` as selectable
      text and a *Buy me a coffee* button that hands the URL to
      :func:`utils.browser.open_in_browser`, reporting it in the status bar when
      the desktop has no browser to hand. The status bar shows the
      source folder on the left and a live per-category summary, with a coloured
      dot per category, plus the remaining images on the right.
    * Window-level ``QAction`` shortcuts for the four categories (arrows and
      WASD) and Space to skip, so they work no matter which child has focus.

Session flow
    ``open_folder()`` → ``Sorter`` (stat-only scan) → decode the current preview
    → ``SwipeWidget.show_image()`` → the card emits ``swipe_committed`` →
    ``Sorter.categorize()`` → next preview … → ``Sorter.finished`` →
    ``CompletionScreen``. Undo restores the file and returns to the stage, and
    ``rescan()`` picks up files added mid-session while keeping the counters and
    the undo history.

Error handling
    Every failure is logged and funnelled through :meth:`_report_info`,
    :meth:`_report_warning` and :meth:`_report_error` — the only methods that
    open a ``QMessageBox``, which is also what makes them replaceable in
    offscreen tests. A failed move leaves the image in the queue and the card
    usable. An undecodable image is skipped with a status-bar toast and a log
    line instead of a modal box per file, so a folder full of broken files does
    not turn into a click-a-thon.

Boundary rules
    * The window owns core objects but performs no file I/O itself: scanning,
      decoding and moving all go through :mod:`swipey_photos.core`.
    * The current preview is shown from the background prefetch cache when it is
      ready (:mod:`swipey_photos.ui.workers`); a cache miss falls back to a
      synchronous decode, so behaviour never depends on thread timing.
    * Window size, the last folder, the recent folders and the theme are
      persisted through :mod:`swipey_photos.utils.config` when a folder is opened
      and on close.
    * ``dry_run=True`` (``--dry-run``) uses the same wiring but builds sorters
      that only log their moves, so the whole flow can be rehearsed safely.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QFont,
    QKeySequence,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.folder_manager import (
    CATEGORIES,
    CategoryError,
    FolderManagerError,
    SourceFolderError,
)
from ..core.image_loader import ImageLoader, ImageLoaderError, subfolders
from ..core.sorter import MissingImageError, NoCurrentImageError, Sorter, UndoError
from ..utils.browser import open_in_browser
from ..utils.config import (
    THEME_DARK,
    THEME_LIGHT,
    Config,
    ConfigError,
    WindowConfig,
    default_config,
    save_config,
    with_recent_folder,
)
from ..utils.file_ops import FileOperationError
from ..utils.logging_setup import get_logger
from .branding import APP_DISPLAY_NAME, SUPPORT_URL, TAGLINE, app_icon
from .completion_screen import CompletionScreen
from .image_utils import pixmap_from_pil, qimage_from_pil
from .shortcut_overlay import ShortcutOverlay
from .swipe_card import CATEGORY_COLORS
from .swipe_widget import SwipeWidget
from .theme import apply_theme
from .welcome_screen import WelcomeScreen
from .workers import PreviewPrefetcher

LOGGER = get_logger(__name__)

__all__ = [
    "FOOTER_ORDER",
    "MainWindow",
    "SorterFactory",
    "default_sorter_factory",
    "pixmap_from_pil",
    "qimage_from_pil",
]
"""Public surface; the conversion helpers stay re-exported for the GUI tests."""

PAGE_WELCOME = 0
"""Stack index of the empty state / folder picker."""

PAGE_STAGE = 1
"""Stack index of the swipe stage."""

PAGE_COMPLETION = 2
"""Stack index of the session summary."""

_PAGE_NAMES: dict[int, str] = {
    PAGE_WELCOME: "welcome",
    PAGE_STAGE: "stage",
    PAGE_COMPLETION: "completion",
}

FOOTER_ORDER: tuple[str, ...] = ("Bad", "OK", "Good", "Great")
"""Button order in the footer: the two "cheap" decisions first, Great last."""

CATEGORY_SHORTCUTS: dict[str, tuple[QKeySequence, QKeySequence]] = {
    "Bad": (QKeySequence(Qt.Key.Key_Left), QKeySequence("A")),
    "OK": (QKeySequence(Qt.Key.Key_Down), QKeySequence("S")),
    "Good": (QKeySequence(Qt.Key.Key_Right), QKeySequence("D")),
    "Great": (QKeySequence(Qt.Key.Key_Up), QKeySequence("W")),
}
"""Keyboard equivalents per category, matching the README shortcut table."""

CATEGORY_HINTS: dict[str, str] = {
    "Bad": "← or A",
    "OK": "↓ or S",
    "Good": "→ or D",
    "Great": "↑ or W",
}
"""Short human hints reused in button tooltips."""

CATEGORY_BUTTON_LABELS: dict[str, str] = {
    "Bad": "← Bad",
    "OK": "↓ OK",
    "Great": "↑ Great",
    "Good": "Good →",
}
"""Footer captions: each button shows the gesture that triggers the same bucket.

The arrow leads the word on three of them; ``Good`` trails it (``Good →``), so
the right-swipe button reads the way the card moves. Kept as data rather than
built from :data:`CATEGORY_HINTS` because the placement is a layout choice, not
a string transform.
"""

RESCAN_SHORTCUTS: tuple[QKeySequence, ...] = (
    QKeySequence(Qt.Key.Key_F5),
    QKeySequence("Ctrl+R"),
)
"""Keys that rescan the current folder for files added mid-session."""

FULLSCREEN_SHORTCUTS: tuple[QKeySequence, ...] = (QKeySequence(Qt.Key.Key_F11),)
"""Key that toggles the distraction-free full-screen view."""

SHORTCUT_HELP_SHORTCUTS: tuple[QKeySequence, ...] = (
    QKeySequence(Qt.Key.Key_F1),
    QKeySequence("?"),
)
"""Keys that show the :class:`ShortcutOverlay` reference."""

QUIT_SHORTCUTS: tuple[QKeySequence, ...] = (QKeySequence("Ctrl+Q"),)
"""Key that closes the window.

``QKeySequence.StandardKey.Quit`` is empty outside macOS — Qt maps it to
``Cmd+Q`` only — so the Linux shortcut is spelled out instead of silently
binding nothing.
"""

SorterFactory = Callable[[Path], Sorter]
"""Builds a session sorter for a folder; injectable for tests and future modes."""


def default_sorter_factory(folder: Path, *, dry_run: bool = False) -> Sorter:
    """Return a :class:`Sorter` for *folder* with a stat-only scan.

    ``validate=False`` keeps folder opening fast on large directories: the
    expensive part of validation is decoding every file, which the window does
    lazily anyway when it shows a preview. A file that turns out to be corrupt
    is reported and skipped at that point, not during the scan.

    Args:
        folder: Source folder chosen by the user.
        dry_run: Build a sorter that logs moves instead of performing them.

    Returns:
        A sorter whose loader has not opened any image yet.

    Raises:
        SourceFolderError: The folder is missing or not a directory.
        ImageLoaderError: The folder cannot be read.
        FolderManagerError: The category folders cannot be created.
    """
    loader = ImageLoader(folder, validate=False)
    return Sorter(folder, image_loader=loader, dry_run=dry_run)


class MainWindow(QMainWindow):
    """Sorting-session shell around the swipe stage.

    Args:
        parent: Optional Qt parent.
        config: Configuration to start from; defaults are used when ``None``.
        config_path: File used to persist the configuration. ``None`` uses the
            XDG default; tests pass a ``tmp_path`` file instead.
        sorter_factory: Callable building a :class:`Sorter` per folder; inject a
            fake to exercise the wiring without touching the real core.
        dry_run: Rehearse the session: the default factory builds sorters that
            log ``would move`` instead of moving anything, and the window says so
            in its title and status bar.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: Config | None = None,
        config_path: Path | None = None,
        sorter_factory: SorterFactory = default_sorter_factory,
        dry_run: bool = False,
    ) -> None:
        """Build the window, its menus, its shortcuts and the welcome page."""
        super().__init__(parent)
        self._config = config if config is not None else default_config()
        self._config_path = config_path
        self._sorter_factory: SorterFactory = (
            partial(default_sorter_factory, dry_run=True) if dry_run else sorter_factory
        )
        self._sorter: Sorter | None = None
        self._prefetcher: PreviewPrefetcher | None = None
        self._dry_run = bool(dry_run)
        self._busy = False
        self._unreadable: set[Path] = set()
        self._last_category: str | None = None
        self._shortcut_overlay: ShortcutOverlay | None = None
        self._category_actions: dict[str, QAction] = {}
        self._category_buttons: dict[str, QPushButton] = {}

        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._apply_config()
        self._show_page(PAGE_WELCOME)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the page stack, the stage page and the status bar widgets."""
        self._pages = QStackedWidget(self)
        self._pages.setObjectName("main_pages")

        self._welcome = WelcomeScreen(self._pages, recent_folders=self._config.recent_folders)
        self._welcome.folder_selected.connect(self._on_folder_chosen)

        self._swipe = SwipeWidget(self._pages)
        self._swipe.swipe_committed.connect(self._on_swipe_committed)

        self._completion = CompletionScreen(self._pages)
        self._completion.open_source_requested.connect(self._on_open_source)
        self._completion.pick_folder_requested.connect(self._choose_folder)
        self._completion.quit_requested.connect(self.close)

        self._pages.addWidget(self._welcome)
        self._pages.addWidget(self._build_stage_page())
        self._pages.addWidget(self._completion)
        self.setCentralWidget(self._pages)

        self._status_folder = QLabel("", self)
        self._status_folder.setObjectName("status_folder")
        self._status_folder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._status_counts = QLabel("", self)
        self._status_counts.setObjectName("status_counts")
        self._status_counts.setTextFormat(Qt.TextFormat.RichText)
        self._status_counts.setStyleSheet("font-weight: 600;")
        self._status_counts.setToolTip("Images sorted so far, per category, and what is left")
        self._status_bar = QStatusBar(self)
        self._status_bar.setObjectName("main_status_bar")
        self.setStatusBar(self._status_bar)
        self._status_bar.addWidget(self._status_folder, 1)
        self._status_bar.addPermanentWidget(self._status_counts)

    def _build_stage_page(self) -> QWidget:
        """Return the page that composes the progress header, stage and footer."""
        page = QWidget(self._pages)
        page.setObjectName("stage_page")

        self._progress_label = QLabel("", page)
        self._progress_label.setObjectName("progress_label")
        progress_font = QFont(self._progress_label.font())
        progress_font.setBold(True)
        progress_font.setPointSize(max(progress_font.pointSize(), 10) + 2)
        self._progress_label.setFont(progress_font)

        self._folder_label = QLabel("", page)
        self._folder_label.setObjectName("stage_folder_label")
        self._folder_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._folder_label.setStyleSheet("color: palette(mid);")
        self._folder_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 0)
        header.addWidget(self._progress_label)
        header.addSpacing(12)
        header.addWidget(self._folder_label, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(16, 8, 16, 12)
        footer.setSpacing(8)
        footer.addStretch(1)
        for category in FOOTER_ORDER:
            button = self._build_category_button(category, page)
            self._category_buttons[category] = button
            footer.addWidget(button)
        footer.addStretch(1)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self._swipe, 1)
        layout.addLayout(footer)
        return page

    def _build_category_button(self, category: str, parent: QWidget) -> QPushButton:
        """Return a footer button that commits *category* when clicked."""
        colour = CATEGORY_COLORS[category]
        button = QPushButton(CATEGORY_BUTTON_LABELS[category], parent)
        button.setObjectName(f"category_button_{category}")
        button.setMinimumSize(120, 44)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(f"Move the current image to {category}/ ({CATEGORY_HINTS[category]})")
        button.setStyleSheet(
            "QPushButton {"
            f"background-color: {colour}; color: #101010; border: none;"
            " border-radius: 10px; padding: 10px 20px; font-weight: 600; }"
            "QPushButton:disabled { background-color: palette(mid); color: palette(dark); }"
            "QPushButton:pressed { background-color: palette(dark); }"
        )
        button.clicked.connect(lambda _checked=False, name=category: self._request_category(name))
        return button

    def _build_menus(self) -> None:
        """Create the File and Help menus with their standard shortcuts."""
        self._menu_bar = QMenuBar(self)
        self.setMenuBar(self._menu_bar)

        file_menu = QMenu("&File", self._menu_bar)
        self._menu_bar.addMenu(file_menu)

        self._open_action = QAction("&Open Folder…", self)
        self._open_action.setObjectName("action_open_folder")
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.setStatusTip("Choose the folder of photos to sort")
        self._open_action.triggered.connect(self._choose_folder)
        file_menu.addAction(self._open_action)

        self._rescan_action = QAction("&Rescan Folder", self)
        self._rescan_action.setObjectName("action_rescan")
        self._rescan_action.setShortcuts(list(RESCAN_SHORTCUTS))
        self._rescan_action.setStatusTip("Scan the current folder again for new images")
        self._rescan_action.setEnabled(False)
        self._rescan_action.triggered.connect(self._on_rescan)
        file_menu.addAction(self._rescan_action)

        self._undo_action = QAction("&Undo Last", self)
        self._undo_action.setObjectName("action_undo")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setStatusTip("Move the most recently sorted image back")
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._on_undo)
        file_menu.addAction(self._undo_action)

        file_menu.addSeparator()
        self._quit_action = QAction("&Quit", self)
        self._quit_action.setObjectName("action_quit")
        self._quit_action.setShortcuts(list(QUIT_SHORTCUTS))
        self._quit_action.setStatusTip("Close Swipey Photos (window state is saved)")
        self._quit_action.triggered.connect(self.close)
        file_menu.addAction(self._quit_action)

        view_menu = QMenu("&View", self._menu_bar)
        self._menu_bar.addMenu(view_menu)
        self._dark_action = QAction("&Dark Mode", self)
        self._dark_action.setObjectName("action_dark_mode")
        self._dark_action.setCheckable(True)
        self._dark_action.setStatusTip("Switch between the light and dark palette")
        self._dark_action.triggered.connect(self._on_toggle_dark_mode)
        view_menu.addAction(self._dark_action)
        view_menu.addSeparator()
        self._fullscreen_action = QAction("&Full Screen", self)
        self._fullscreen_action.setObjectName("action_fullscreen")
        self._fullscreen_action.setShortcuts(list(FULLSCREEN_SHORTCUTS))
        self._fullscreen_action.setCheckable(True)
        self._fullscreen_action.setStatusTip("Hide the window chrome and the menus")
        self._fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self._fullscreen_action)

        help_menu = QMenu("&Help", self._menu_bar)
        self._menu_bar.addMenu(help_menu)
        self._shortcuts_action = QAction("&Keyboard Shortcuts", self)
        self._shortcuts_action.setObjectName("action_shortcut_help")
        self._shortcuts_action.setShortcuts(list(SHORTCUT_HELP_SHORTCUTS))
        self._shortcuts_action.setStatusTip("Show every keyboard binding")
        self._shortcuts_action.triggered.connect(self._show_shortcut_help)
        help_menu.addAction(self._shortcuts_action)
        help_menu.addSeparator()
        self._about_action = QAction(f"&About {APP_DISPLAY_NAME}", self)
        self._about_action.setObjectName("action_about")
        self._about_action.setStatusTip("Version and a short description")
        self._about_action.triggered.connect(self._show_about)
        help_menu.addAction(self._about_action)

    def _build_shortcuts(self) -> None:
        """Install the category and skip actions so shortcuts work window-wide.

        The four category actions use ``WindowShortcut`` because they must work
        whichever child has focus. Space is bound on the card instead
        (``WidgetShortcut``): a window-wide Space would otherwise fire while a
        footer button has focus, and pressing Space on a focused button is
        supposed to press that button.
        """
        for category, sequences in CATEGORY_SHORTCUTS.items():
            action = QAction(category, self)
            action.setObjectName(f"action_category_{category}")
            action.setShortcuts(list(sequences))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.setStatusTip(f"Send the current image to {category}/")
            action.setEnabled(False)
            action.triggered.connect(
                lambda _checked=False, name=category: self._request_category(name)
            )
            self.addAction(action)
            self._category_actions[category] = action

        self._skip_action = QAction("Skip", self)
        self._skip_action.setObjectName("action_skip")
        self._skip_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self._skip_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self._skip_action.setStatusTip("Leave this image in the folder and show the next one")
        self._skip_action.setEnabled(False)
        self._skip_action.triggered.connect(self._on_skip)
        self._swipe.card.addAction(self._skip_action)

    def _apply_config(self) -> None:
        """Apply the remembered window size, the theme and the initial title."""
        self.setMinimumSize(QSize(640, 480))
        self.resize(self._config.window.width, self._config.window.height)
        self._apply_theme()
        self._apply_title()

    def _apply_theme(self) -> None:
        """Install the configured palette and keep the View menu tick in step."""
        effective = apply_theme(self._config.theme)
        self._dark_action.setChecked(effective == THEME_DARK)

    def _apply_title(self, folder_name: str | None = None) -> None:
        """Show the app name, the open folder (if any) and the dry-run marker."""
        parts = [APP_DISPLAY_NAME]
        if folder_name:
            parts.append(folder_name)
        title = " — ".join(parts)
        if self._dry_run:
            title = f"{title} (dry run)"
        self.setWindowTitle(title)

    def _on_toggle_dark_mode(self, checked: bool) -> None:
        """Switch palette between dark and light and remember the choice."""
        theme = THEME_DARK if checked else THEME_LIGHT
        self._config = replace(self._config, theme=theme)
        self._apply_theme()
        self._save_config()
        self.show_status_message(f"{theme.capitalize()} theme", 2000)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> Config:
        """The configuration currently in memory (updated as folders are used)."""
        return self._config

    @property
    def sorter(self) -> Sorter | None:
        """The active session sorter, or ``None`` before a folder was opened."""
        return self._sorter

    @property
    def welcome_screen(self) -> WelcomeScreen:
        """The page shown when no folder is open."""
        return self._welcome

    @property
    def completion_screen(self) -> CompletionScreen:
        """The page shown once the deck is empty."""
        return self._completion

    @property
    def swipe_widget(self) -> SwipeWidget:
        """The stage that hosts the swipe card."""
        return self._swipe

    @property
    def shortcut_overlay(self) -> ShortcutOverlay | None:
        """The keyboard reference overlay, or ``None`` until it is first shown."""
        return self._shortcut_overlay

    @property
    def category_actions(self) -> dict[str, QAction]:
        """The four keyboard actions, keyed by canonical category name."""
        return dict(self._category_actions)

    @property
    def category_buttons(self) -> dict[str, QPushButton]:
        """The four footer buttons, keyed by canonical category name."""
        return dict(self._category_buttons)

    @property
    def progress_label(self) -> QLabel:
        """The "Image 3 of 47" label in the stage header."""
        return self._progress_label

    @property
    def status_counts_label(self) -> QLabel:
        """The permanent status-bar label with the live per-category counts."""
        return self._status_counts

    @property
    def prefetcher(self) -> PreviewPrefetcher | None:
        """The background preview decoder, or ``None`` before a folder is open."""
        return self._prefetcher

    @property
    def dry_run(self) -> bool:
        """``True`` when moves are only logged, never performed."""
        return self._dry_run

    @property
    def current_page(self) -> str:
        """Name of the visible page: ``"welcome"``, ``"stage"`` or ``"completion"``."""
        return _PAGE_NAMES.get(self._pages.currentIndex(), "unknown")

    def open_folder(self, folder: str | Path) -> bool:
        """Start a sorting session for *folder*.

        Args:
            folder: Folder holding the images to sort. Missing, unreadable and
                image-less folders are reported to the user and rejected.

        Returns:
            ``True`` when the session started and the first preview is shown;
            ``False`` when the folder was rejected, in which case the window
            stays on the page it was showing.
        """
        target = Path(folder).expanduser()
        try:
            sorter = self._sorter_factory(target)
        except (SourceFolderError, ImageLoaderError, FolderManagerError, OSError) as exc:
            LOGGER.warning("cannot open %s: %s", target, exc)
            self._report_error("Could not open folder", f"{target}\n\n{exc}")
            return False

        if sorter.total == 0:
            LOGGER.info("no supported images in %s", target)
            self._report_info("No images found", self._no_images_message(target))
            return False

        self._sorter = sorter
        self._unreadable.clear()
        self._last_category = None
        self._busy = False
        self._reset_prefetcher(sorter.image_loader)
        self._remember_folder(sorter.source_folder)
        self._apply_title(sorter.source_folder.name)
        self._show_page(PAGE_STAGE)
        self._load_current_image()
        if self._dry_run:
            self.show_status_message("Dry run: no files will be moved", 8000)
        LOGGER.info("session started for %s with %d image(s)", sorter.source_folder, sorter.total)
        return True

    def _no_images_message(self, folder: Path) -> str:
        """Explain why *folder* yielded nothing and where its images may live.

        "No images found" alone is unhelpful when the photos are one level down,
        so the message names the subfolders that do contain images and, failing
        that, the subfolders that exist at all.
        """
        lines = [
            f"{folder} does not contain any supported image files at the top level.",
            "",
            "Supported formats: JPEG, PNG, GIF, BMP, WebP and TIFF.",
        ]
        with_images = subfolders(folder, require_images=True)
        if with_images:
            names = ", ".join(path.name for path in with_images)
            lines += ["", f"The images are in subfolders: {names}.", "Open one of them to sort it."]
            return "\n".join(lines)

        others = subfolders(folder)
        if others:
            names = ", ".join(path.name for path in others)
            lines += [
                "",
                f"It only contains subfolders: {names}.",
                "Open one of them to sort its images.",
            ]
        else:
            lines += ["", "Add some photos to it and open it again."]
        return "\n".join(lines)

    def _reset_prefetcher(self, loader: ImageLoader) -> None:
        """Replace the prefetcher so it only decodes files of the current session."""
        if self._prefetcher is not None:
            self._prefetcher.shutdown()
            self._prefetcher.deleteLater()
        self._prefetcher = PreviewPrefetcher(loader, parent=self)

    def restore_last_session(self) -> bool:
        """Reopen the folder remembered in the configuration, if it still exists.

        Returns:
            ``True`` when a session started, ``False`` when there is no
            remembered folder or it is no longer usable (the welcome page then
            stays visible).
        """
        folder = self._config.last_folder
        if folder is None:
            LOGGER.debug("no remembered folder; showing the welcome page")
            return False
        if not folder.is_dir():
            LOGGER.warning("remembered folder is gone: %s", folder)
            self.show_status_message(f"Last folder is no longer available: {folder}", 8000)
            return False
        return self.open_folder(folder)

    def save_state(self) -> None:
        """Persist window size, the current folder and the recents list.

        Configuration problems are logged and shown in the status bar instead of
        raising: a read-only home directory must not block closing the app.
        """
        size = self._saved_window_size()
        self._config = replace(
            self._config,
            window=WindowConfig(width=max(size.width(), 1), height=max(size.height(), 1)),
        )
        if self._sorter is not None:
            self._config = with_recent_folder(self._config, self._sorter.source_folder)
        self._save_config()

    def _saved_window_size(self) -> QSize:
        """Return the size worth remembering, never a full-screen one.

        Closing the app in full screen must not teach the next launch to open a
        screen-sized window, so the normal geometry wins whenever the window is
        full screen or maximised.
        """
        if self.isFullScreen() or self.isMaximized():
            normal = self.normalGeometry()
            if normal.isValid() and normal.width() > 0 and normal.height() > 0:
                return normal.size()
        return self.size()

    def show_status_message(self, message: str, timeout_ms: int = 5000) -> None:
        """Show *message* in the status bar for *timeout_ms* milliseconds."""
        self._status_bar.showMessage(message, timeout_ms)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Stop the prefetcher and save the state before the window closes."""
        if self._prefetcher is not None:
            self._prefetcher.shutdown()
        self.save_state()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Session flow
    # ------------------------------------------------------------------

    def _load_current_image(self) -> None:
        """Show the sorter's current image, skipping files that cannot be decoded.

        The preview comes from the background cache when it is ready and is
        decoded synchronously otherwise, so a slow disk never changes the
        behaviour, only the latency. A file Pillow rejects is skipped with a
        status-bar toast (never a modal box, which would turn a folder of broken
        files into a click-a-thon) and left where it is: the user can still deal
        with it outside the app. When no image is left the summary page replaces
        the stage.
        """
        sorter = self._sorter
        if sorter is None:
            self._show_page(PAGE_WELCOME)
            return

        skipped: list[str] = []
        while True:
            path = sorter.current_image()
            if path is None:
                if skipped:
                    self._report_skipped(skipped)
                self._show_completion()
                return
            pixmap, original_size = self._prefetched_preview(path)
            if pixmap is None:
                try:
                    image, original_size = sorter.image_loader.load_preview(path)
                except ImageLoaderError as exc:
                    LOGGER.warning("skipping undecodable image %s: %s", path, exc)
                    self._unreadable.add(path)
                    skipped.append(path.name)
                    sorter.advance()
                    continue
                pixmap = pixmap_from_pil(image)
            if skipped:
                self._report_skipped(skipped)
            caption = f"{path.name} - {original_size[0]} x {original_size[1]}"
            self._swipe.show_image(pixmap, caption=caption, from_direction=self._last_category)
            self._swipe.set_interactive(True)
            self._prefetch_upcoming()
            self._refresh_status()
            return

    def _prefetched_preview(self, path: Path) -> tuple[QPixmap | None, tuple[int, int]]:
        """Return a prefetched preview as ``(pixmap, original_size)``.

        ``(None, (0, 0))`` means the preview is not ready yet, in which case the
        caller decodes the file synchronously exactly as before.
        """
        if self._prefetcher is None:
            return None, (0, 0)
        preview = self._prefetcher.take(path)
        if preview is None:
            return None, (0, 0)
        image, size = preview
        return QPixmap.fromImage(image), size

    def _prefetch_upcoming(self) -> None:
        """Ask the worker pool to decode the images after the current one."""
        sorter = self._sorter
        if sorter is None or self._prefetcher is None:
            return
        upcoming = sorter.remaining[1:]
        if upcoming:
            self._prefetcher.prefetch(upcoming)

    def _report_skipped(self, names: list[str]) -> None:
        """Mention unreadable files in the status bar instead of a modal dialog."""
        shown = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
        LOGGER.warning("skipped %d unreadable image(s): %s", len(names), shown)
        self.show_status_message(f"Skipped {len(names)} unreadable image(s): {shown}", 8000)

    def _on_swipe_committed(self, category: str) -> None:
        """Move the current image into *category* and deal the next one.

        A failed move is reported and leaves the image queued and visible again,
        so the same file can be retried without anything having been mutated.
        """
        sorter = self._sorter
        if sorter is None or self._busy:
            return

        self._busy = True
        self._swipe.set_interactive(False)
        self._refresh_actions()
        try:
            record = sorter.categorize(category)
        except MissingImageError as exc:
            LOGGER.warning("current image vanished: %s", exc)
            self._report_warning(
                "Image disappeared",
                f"{exc}\n\nThe image was dropped from the queue.",
            )
        except (
            NoCurrentImageError,
            CategoryError,
            FolderManagerError,
            FileOperationError,
        ) as exc:
            LOGGER.error("could not move the current image to %s: %s", category, exc)
            self._report_error("Could not move image", f"{exc}\n\nThe image stays in the queue.")
        else:
            self._last_category = record.category
            if self._dry_run:
                self.show_status_message(
                    f"Dry run: would move {record.source.name} → {record.category}/", 4000
                )
            else:
                self.show_status_message(f"Moved {record.source.name} → {record.category}/", 3000)
        finally:
            self._busy = False
            self._load_current_image()

    def _on_undo(self) -> None:
        """Restore the most recently sorted image and show it again.

        The restored card arrives through the deck's normal entrance animation,
        which is enough of a cue that "this is the image you just put away" is
        obvious without a dialog; the stage itself never dims, because a
        stage-wide opacity effect would sit on top of the card's own drop-shadow
        effect and Qt stops compositing the card in that arrangement. Undo
        leaves the stage interactive again immediately.
        """
        sorter = self._sorter
        if sorter is None or self._busy:
            return
        try:
            record = sorter.undo()
        except UndoError as exc:
            LOGGER.warning("undo failed: %s", exc)
            self._report_warning("Could not undo", str(exc))
            return
        if record is None:
            self.show_status_message("Nothing to undo")
            return
        self.show_status_message(f"Restored {record.filename} from {record.category}/")
        self._show_page(PAGE_STAGE)
        self._load_current_image()

    def _on_skip(self) -> None:
        """Leave the current image in place and show the next one."""
        sorter = self._sorter
        if sorter is None or not self._can_decide():
            return
        current = sorter.current_image()
        if current is None:
            return
        sorter.advance()
        self.show_status_message(f"Skipped {current.name}; it stays in the folder", 3000)
        self._load_current_image()

    def _show_completion(self) -> None:
        """Swap in the summary page for the finished session."""
        sorter = self._sorter
        counts = {str(name): count for name, count in sorter.counts.items()} if sorter else {}
        source = sorter.source_folder if sorter is not None else None
        self._swipe.clear()
        self._completion.set_summary(counts, source_folder=source, skipped=len(self._unreadable))
        self._show_page(PAGE_COMPLETION)
        LOGGER.info("session finished: %s", counts)

    # ------------------------------------------------------------------
    # State refreshers
    # ------------------------------------------------------------------

    def _show_page(self, index: int) -> None:
        """Show the page at stack position *index* and refresh the chrome."""
        self._pages.setCurrentIndex(index)
        self._refresh_status()

    def _can_decide(self) -> bool:
        """Return ``True`` when a category decision may be started right now."""
        return (
            self._pages.currentIndex() == PAGE_STAGE
            and not self._busy
            and self._sorter is not None
            and not self._sorter.finished
        )

    def _refresh_status(self) -> None:
        """Update the header, status bar and the enabled state of all actions.

        ``"N left"`` is the number of images that are *not yet sorted*, so it
        does not drop when the user skips one: a skipped file stays in the
        folder and is offered again next session.
        """
        sorter = self._sorter
        counts = sorter.counts if sorter is not None else {}
        parts = [
            f'<span style="color:{CATEGORY_COLORS[category]}">●</span> '
            f"{category} {counts.get(category, 0)}"
            for category in CATEGORIES
        ]
        if sorter is not None:
            unsorted = sorter.total - sum(counts.values())
            parts.append(f"{unsorted} left")
        separator = "  ·  "
        self._status_counts.setText(separator.join(parts))
        self._status_folder.setText(str(sorter.source_folder) if sorter is not None else "")
        self._folder_label.setText(str(sorter.source_folder) if sorter is not None else "")
        self._refresh_progress()
        self._refresh_actions()

    def _refresh_progress(self) -> None:
        """Show ``"Image 3 of 47"`` for the current deck position."""
        sorter = self._sorter
        if sorter is None or sorter.finished or self._pages.currentIndex() != PAGE_STAGE:
            self._progress_label.setText("")
            return
        seen = sorter.total - sorter.remaining_count
        self._progress_label.setText(f"Image {seen + 1} of {sorter.total}")

    def _refresh_actions(self) -> None:
        """Enable the category/skip actions and footer buttons only when usable."""
        can_decide = self._can_decide()
        for action in self._category_actions.values():
            action.setEnabled(can_decide)
        self._skip_action.setEnabled(can_decide)
        for button in self._category_buttons.values():
            button.setEnabled(can_decide)
        self._undo_action.setEnabled(
            self._sorter is not None and bool(self._sorter.history) and not self._busy
        )
        self._rescan_action.setEnabled(self._sorter is not None and not self._busy)

    # ------------------------------------------------------------------
    # User intent
    # ------------------------------------------------------------------

    def _request_category(self, category: str) -> None:
        """Commit *category* through the card so it flies out like a drag."""
        if not self._can_decide():
            return
        self._swipe.trigger_swipe(category)

    def _on_folder_chosen(self, folder: str) -> None:
        """Open *folder* after the welcome screen reported a selection."""
        self.open_folder(folder)

    def _choose_folder(self) -> None:
        """Ask for a folder with ``QFileDialog`` and open it when chosen."""
        if self._sorter is not None:
            start = str(self._sorter.source_folder)
        elif self._config.last_folder is not None:
            start = str(self._config.last_folder)
        else:
            start = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose a folder of photos",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if chosen:
            self.open_folder(chosen)

    def _on_open_source(self) -> None:
        """Rescan the folder of the finished session."""
        sorter = self._sorter
        if sorter is None:
            self._show_page(PAGE_WELCOME)
            return
        self.open_folder(sorter.source_folder)

    def _on_rescan(self) -> None:
        """Scan the current folder again, keeping counts and undo history.

        ``Sorter.reload()`` re-reads the folder without touching the counters,
        so files added since the session started appear and files already moved
        (now inside a category folder) are not queued twice. When nothing is left
        the summary replaces the stage, which is what the user is about to see
        anyway.
        """
        sorter = self._sorter
        if sorter is None:
            self._choose_folder()
            return
        if self._busy:
            return
        try:
            remaining = sorter.reload()
        except (ImageLoaderError, OSError) as exc:
            LOGGER.warning("cannot rescan %s: %s", sorter.source_folder, exc)
            self._report_error("Could not rescan folder", f"{sorter.source_folder}\n\n{exc}")
            return

        LOGGER.info("rescanned %s: %d image(s) left", sorter.source_folder, len(remaining))
        if not remaining:
            self.show_status_message(f"No images left in {sorter.source_folder.name}", 5000)
            self._show_completion()
            return
        self._show_page(PAGE_STAGE)
        self._load_current_image()
        self.show_status_message(f"Rescanned: {len(remaining)} image(s) left", 4000)

    # ------------------------------------------------------------------
    # View and help
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        """Switch between full screen and the normal window frame."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        LOGGER.debug("full screen %s", "on" if self.isFullScreen() else "off")

    def _sync_fullscreen_action(self) -> None:
        """Keep the View menu tick in step with the actual window state."""
        self._fullscreen_action.setChecked(self.isFullScreen())

    def changeEvent(self, event: QEvent | None) -> None:
        """Keep the Full Screen tick correct when the window manager changes it."""
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.Type.WindowStateChange:
            self._sync_fullscreen_action()

    def _show_shortcut_help(self) -> None:
        """Show the keyboard reference overlay, creating it on first use."""
        if self._shortcut_overlay is None:
            self._shortcut_overlay = ShortcutOverlay(self)
        self._shortcut_overlay.show_overlay()

    def _remember_folder(self, folder: Path) -> None:
        """Record *folder* as the most recent one and persist the config."""
        self._config = with_recent_folder(self._config, folder)
        self._welcome.set_recent_folders(self._config.recent_folders)
        self._save_config()

    def _save_config(self) -> None:
        """Write the configuration, reporting failures without raising."""
        try:
            save_config(self._config, self._config_path)
        except ConfigError as exc:
            LOGGER.warning("could not save configuration: %s", exc)
            self.show_status_message(f"Could not save settings: {exc}", 8000)

    def _build_about_box(self) -> tuple[QMessageBox, QPushButton]:
        """Build the About box without showing it.

        Kept separate from :meth:`_show_about` so tests can inspect the text and
        the support button without going through a modal ``exec()`` loop.

        Returns:
            The dialog and its *Buy me a coffee* button, in that order.
        """
        box = QMessageBox(self)
        box.setObjectName("about_box")
        box.setWindowTitle(f"About {APP_DISPLAY_NAME}")
        box.setIconPixmap(app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<h3>{APP_DISPLAY_NAME} {__version__}</h3>"
            f"<p>{TAGLINE}</p>"
            "<p>Sort a folder of photos into Good, Bad, Great and OK subfolders by "
            "swiping or pressing a key. Files are moved, never overwritten and "
            "never deleted.</p>"
            f"<p><small>Support: {SUPPORT_URL}</small></p>"
        )
        # The URL is plain, selectable text on purpose: a Qt link would go
        # through the same desktop service the button cannot rely on, but text
        # can be copied into a browser by hand.
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        coffee = QPushButton("Buy me a coffee", box)
        coffee.setObjectName("button_buy_me_a_coffee")
        coffee.setToolTip(f"Opens {SUPPORT_URL} in your browser")
        coffee.clicked.connect(self._open_support_page)
        box.addButton(coffee, QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        return box, coffee

    def _show_about(self) -> None:
        """Show the About box with the version, description and support button."""
        box, _coffee = self._build_about_box()
        box.exec()

    def _open_support_page(self) -> None:
        """Open the donation page, or say where to find it; replaceable in tests."""
        LOGGER.info("opening the support page: %s", SUPPORT_URL)
        if open_in_browser(SUPPORT_URL):
            return
        LOGGER.warning("no browser accepted %s", SUPPORT_URL)
        # The About box is modal, so this stays readable in the status bar
        # behind it and after it closes.
        self.show_status_message(f"Could not open a browser — the page is {SUPPORT_URL}", 15000)

    # ------------------------------------------------------------------
    # Dialogs (replaceable in tests)
    # ------------------------------------------------------------------

    def _report_info(self, title: str, message: str) -> None:
        """Show an informational message box; tests replace this method."""
        QMessageBox.information(self, title, message)

    def _report_warning(self, title: str, message: str) -> None:
        """Show a warning message box; tests replace this method."""
        QMessageBox.warning(self, title, message)

    def _report_error(self, title: str, message: str) -> None:
        """Show a critical message box; tests replace this method."""
        QMessageBox.critical(self, title, message)
