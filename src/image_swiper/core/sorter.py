"""Session state: which image is next and how to move or restore it.

Responsibility
    Coordinate the folder manager and the image loader into the small state
    machine the UI drives: a queue of images, a cursor for skipped files, one
    move per category and a bounded undo stack. Pure Python with no signals, so
    it is unit-testable without Qt and can be wrapped by the UI later.

Public API
    SorterError                      base class
    NoCurrentImageError              queue exhausted
    MissingImageError                the current file vanished mid-session
    UndoError                        nothing restorable, or the file is gone
    MoveRecord(source, destination, category, index, moved_at)
    Sorter(source_folder, *, folder_manager=None, image_loader=None,
           undo_limit=50, on_record=None, dry_run=False):
        current_image(), advance(), categorize(category), undo(),
        images, remaining, remaining_count, index, total, counts, history,
        finished, dry_run, reload(), reset()

Semantics
    * ``current_image()`` returns ``None`` once the queue is exhausted.
    * ``advance()`` skips the current image without moving it; the cursor moves
      on and a skipped image is not revisited in this session.
    * ``categorize()`` moves the current image, removes it from the queue and
      returns the :class:`MoveRecord`. The next image then occupies the same
      index, so callers never adjust the cursor themselves.
    * ``undo()`` restores the most recent move to its original path (or a
      ``_N`` variant if that path is now occupied) and puts the image back at
      the position it was taken from. Returns ``None`` for an empty history.
    * The undo stack keeps at most ``undo_limit`` records; ``0`` disables undo.
    * ``dry_run=True`` walks the exact same state machine — counters, cursor and
      undo history all move — but no file is touched: ``categorize`` logs
      ``dry run: would move …`` and ``undo`` logs ``dry run: would restore …``.
      It is what ``--dry-run`` uses, so the whole UI can be exercised safely.
    * Nothing here imports Qt: the window subscribes via ``on_record`` and
      re-renders, which keeps the core layer headless.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.file_ops import reverse_move, unique_path
from ..utils.logging_setup import get_logger
from .folder_manager import Category, FolderManager, normalize_category
from .image_loader import ImageLoader

LOGGER = get_logger(__name__)

DEFAULT_UNDO_LIMIT = 50


class SorterError(Exception):
    """Base class for sorter state errors."""


class NoCurrentImageError(SorterError):
    """Raised when an action needs an image but the queue is exhausted."""


class MissingImageError(SorterError):
    """Raised when the current image vanished from disk mid-session.

    The offending path is removed from the queue before this is raised, so a
    caller may catch it, tell the user and call again to continue.
    """


class UndoError(SorterError):
    """Raised when the last move cannot be reversed."""


@dataclass(frozen=True, slots=True)
class MoveRecord:
    """One completed move, carrying everything needed to reverse it."""

    source: Path
    destination: Path
    category: Category
    index: int
    moved_at: float = field(default_factory=time.time)

    @property
    def filename(self) -> str:
        """Name of the file in its new location."""
        return self.destination.name


class Sorter:
    """Sort the images of one folder, one category decision at a time.

    Args:
        source_folder: Folder that holds the images and receives the category
            folders. Used only when the collaborators are not injected.
        folder_manager: Pre-built :class:`FolderManager` (tests, custom layout).
        image_loader: Pre-built :class:`ImageLoader` (tests, custom extensions).
        undo_limit: Maximum number of moves kept on the undo stack.
        on_record: Optional callback invoked with every new :class:`MoveRecord`;
            the UI uses it to refresh its counters.
        dry_run: Log the moves instead of performing them. Everything else —
            cursor, counters and undo history — behaves exactly as it does in a
            real session, so ``--dry-run`` can rehearse a sort safely.

    Raises:
        ValueError: ``undo_limit`` is negative.
        SourceFolderError: the source folder is missing.
        ImageLoaderError: the source folder is unusable.
    """

    def __init__(
        self,
        source_folder: str | Path,
        *,
        folder_manager: FolderManager | None = None,
        image_loader: ImageLoader | None = None,
        undo_limit: int = DEFAULT_UNDO_LIMIT,
        on_record: Callable[[MoveRecord], None] | None = None,
        dry_run: bool = False,
    ) -> None:
        if undo_limit < 0:
            raise ValueError(f"undo_limit must be zero or positive, got {undo_limit}")

        self._folders = (
            folder_manager if folder_manager is not None else FolderManager(source_folder)
        )
        self._loader = image_loader if image_loader is not None else ImageLoader(source_folder)
        self._remaining: list[Path] = self._loader.load()
        self._index = 0
        self._processed = 0
        self._undo_limit = undo_limit
        self._history: deque[MoveRecord] = deque()
        self._counts: Counter[Category] = Counter()
        self._on_record = on_record
        self._dry_run = bool(dry_run)
        LOGGER.info(
            "sorter ready for %s with %d image(s)%s",
            self._folders.source_folder,
            len(self._remaining),
            " (dry run)" if self._dry_run else "",
        )

    def __repr__(self) -> str:
        """Return a debug-friendly summary of cursor position and history size."""
        return (
            f"Sorter(source_folder={str(self._folders.source_folder)!r}, "
            f"index={self._index}, total={self.total}, undo={len(self._history)})"
        )

    @property
    def source_folder(self) -> Path:
        """Absolute path of the folder being sorted."""
        return self._folders.source_folder

    @property
    def folder_manager(self) -> FolderManager:
        """The folder manager this sorter moves files through."""
        return self._folders

    @property
    def image_loader(self) -> ImageLoader:
        """The loader that produced and can refresh the queue."""
        return self._loader

    @property
    def index(self) -> int:
        """Cursor into :attr:`images`; equals the number of skipped images."""
        return self._index

    @property
    def total(self) -> int:
        """Images seen this session: still queued plus already categorised."""
        return len(self._remaining) + self._processed

    @property
    def images(self) -> tuple[Path, ...]:
        """Every image still in the queue, including the current one."""
        return tuple(self._remaining)

    @property
    def remaining(self) -> tuple[Path, ...]:
        """Images from the cursor to the end of the queue."""
        return tuple(self._remaining[self._index :])

    @property
    def remaining_count(self) -> int:
        """How many images the user has still to decide on."""
        return len(self._remaining) - min(self._index, len(self._remaining))

    @property
    def finished(self) -> bool:
        """``True`` when the cursor has moved past the last image."""
        return self._index >= len(self._remaining)

    @property
    def counts(self) -> dict[Category, int]:
        """Number of images moved into each category this session."""
        return dict(self._counts)

    @property
    def history(self) -> tuple[MoveRecord, ...]:
        """Moves available for undo, oldest first."""
        return tuple(self._history)

    @property
    def dry_run(self) -> bool:
        """``True`` when moves are only logged, never performed."""
        return self._dry_run

    def current_image(self) -> Path | None:
        """Return the image at the cursor, or ``None`` when finished."""
        if self._index >= len(self._remaining):
            return None
        return self._remaining[self._index]

    def advance(self) -> Path | None:
        """Skip the current image without moving it and return the next one.

        Returns ``None`` when the queue was already exhausted; skipping never
        raises, because ``Space`` on the last image should feel like finishing.
        """
        current = self.current_image()
        if current is None:
            LOGGER.debug("advance() with an empty queue; nothing to skip")
            return None
        LOGGER.debug("skipping %s", current.name)
        self._index += 1
        return self.current_image()

    def categorize(self, category: Category | str) -> MoveRecord:
        """Move the current image into ``category`` and return its record.

        In a dry run (``dry_run=True``) nothing is moved: the planned name is
        resolved with the same collision rules as a real move, the intent is
        logged at INFO, and the state machine advances exactly as usual.

        Args:
            category: One of ``"Good"``, ``"Bad"``, ``"Great"``, ``"OK"``;
                matched case-insensitively.

        Raises:
            NoCurrentImageError: the queue is exhausted.
            CategoryError: ``category`` is not a known category.
            MissingImageError: the current file disappeared; it is dropped from
                the queue before this is raised.
            FileOperationError: the move failed; nothing is recorded or counted.
        """
        current = self.current_image()
        if current is None:
            raise NoCurrentImageError("no image left to categorise")

        canonical = normalize_category(category)
        if not current.exists():
            LOGGER.error("queued image disappeared, dropping it: %s", current)
            self._remaining.pop(self._index)
            raise MissingImageError(f"image disappeared: {current}")

        destination = (
            unique_path(self._folders.destination_for(canonical), current.name)
            if self._dry_run
            else self._folders.move_image(current, canonical)
        )
        record = MoveRecord(
            source=current,
            destination=destination,
            category=canonical,
            index=self._index,
        )
        self._remaining.pop(self._index)
        self._processed += 1
        self._counts[canonical] += 1
        self._push_history(record)
        if self._dry_run:
            LOGGER.info("dry run: would move %s -> %s [%s]", current.name, destination, canonical)
        else:
            LOGGER.info("categorised %s as %s", current.name, canonical)
        if self._on_record is not None:
            self._on_record(record)
        return record

    def undo(self) -> MoveRecord | None:
        """Restore the most recent move and make that image current again.

        Returns:
            The record that was undone, or ``None`` when the history is empty.

        Raises:
            UndoError: the file is no longer at its destination, so restoring
                would mean guessing; the record is put back for a later attempt.
        """
        if not self._history:
            LOGGER.debug("undo() with an empty history")
            return None

        record = self._history.pop()
        if self._dry_run:
            restored = record.source
            LOGGER.info("dry run: would restore %s from %s/", record.filename, record.category)
        else:
            if not record.destination.exists():
                self._history.append(record)
                LOGGER.error("cannot undo, %s no longer exists", record.destination)
                raise UndoError(f"cannot undo: {record.destination} no longer exists")

            restored = reverse_move(record.source, record.destination)
            if restored != record.source:
                LOGGER.warning("original name was taken; restored as %s", restored)

        insert_at = min(record.index, len(self._remaining))
        self._remaining.insert(insert_at, restored)
        self._index = insert_at
        self._processed = max(self._processed - 1, 0)
        remaining_for_category = self._counts[record.category] - 1
        if remaining_for_category > 0:
            self._counts[record.category] = remaining_for_category
        else:
            self._counts.pop(record.category, None)
        if not self._dry_run:
            LOGGER.info("undid move of %s from %s", record.filename, record.category)
        return record

    def reload(self) -> list[Path]:
        """Rescan the source folder and restart the queue from the top.

        History and counters are kept, so ``undo`` still works after a refresh.
        Files already moved live in a category folder and are therefore not
        picked up again by the non-recursive scan.
        """
        self._remaining = self._loader.reload()
        self._index = 0
        LOGGER.info("reloaded queue with %d image(s)", len(self._remaining))
        return list(self._remaining)

    def reset(self) -> None:
        """Rescan the folder and clear the cursor, counters and undo history."""
        self._remaining = self._loader.reload()
        self._index = 0
        self._processed = 0
        self._history.clear()
        self._counts.clear()
        LOGGER.info("sorter reset with %d image(s)", len(self._remaining))

    def _push_history(self, record: MoveRecord) -> None:
        """Append ``record`` and trim the stack to ``undo_limit`` entries."""
        if self._undo_limit == 0:
            return
        self._history.append(record)
        while len(self._history) > self._undo_limit:
            self._history.popleft()
