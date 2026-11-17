"""Destination folders and collision-free file moves for one source folder.

Responsibility
    Own the physical layout of a sort session: make sure the Good, Bad, Great
    and OK subfolders exist inside the source folder, validate the category a
    caller asks for, and move exactly one image into the matching folder. Every
    move is logged at INFO so a user can reconstruct a session from the log.

Public API
    CATEGORIES: tuple[str, ...]      # ("Good", "Bad", "Great", "OK")
    Category: Literal["Good", "Bad", "Great", "OK"]
    FolderManagerError               base class for layout problems
    SourceFolderError                missing, unusable source folder
    CategoryError                    unknown category name
    normalize_category(value)        canonical spelling or CategoryError
    FolderManager(source_folder, *, create=True):
        source_folder, category_folders, ensure_folders(), destination_for(),
        move_image(image_path, category), is_inside(candidate, parent)

Behaviour
    * The source folder must already exist and be a directory; the four
      category folders are created on construction unless ``create=False``.
    * Category names are matched case-insensitively but stored canonically, so
      ``"ok"`` and ``"OK"`` both land in ``OK``.
    * Collisions never overwrite: ``photo.jpg`` becomes ``photo_1.jpg``.
    * ``move_image`` returns the final path and logs source, category and
      result. Filesystem failures propagate as ``FileOperationError`` after
      being logged once, so the UI can show a message without guessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..utils.file_ops import (
    FileOperationError,
    SourceNotFoundError,
    expand_path,
    move_file,
)
from ..utils.logging_setup import get_logger

LOGGER = get_logger(__name__)

Category = Literal["Good", "Bad", "Great", "OK"]
CATEGORIES: tuple[Category, ...] = ("Good", "Bad", "Great", "OK")
_CANONICAL: dict[str, Category] = {name.casefold(): name for name in CATEGORIES}


class FolderManagerError(Exception):
    """Base class for folder layout problems."""


class SourceFolderError(FolderManagerError):
    """The source folder is missing, not a directory, or unusable."""


class CategoryError(FolderManagerError, ValueError):
    """The requested category is not one of :data:`CATEGORIES`."""


def normalize_category(value: str) -> Category:
    """Return the canonical spelling of ``value`` or raise :class:`CategoryError`."""
    canonical = _CANONICAL.get(value.strip().casefold())
    if canonical is None:
        allowed = ", ".join(CATEGORIES)
        raise CategoryError(f"unknown category {value!r}; expected one of: {allowed}")
    return canonical


class FolderManager:
    """Create and manage the per-category destination folders.

    Args:
        source_folder: Folder that holds the images to sort.
        create: When ``True`` (the default) the four category folders are
            created immediately if they are missing.

    Raises:
        SourceFolderError: ``source_folder`` is missing or not a folder.
        FolderManagerError: a category folder could not be created.
    """

    def __init__(self, source_folder: str | Path, *, create: bool = True) -> None:
        root = expand_path(source_folder)
        if not root.exists():
            raise SourceFolderError(f"source folder does not exist: {root}")
        if not root.is_dir():
            raise SourceFolderError(f"source path is not a folder: {root}")
        self._source_folder = root
        self._folders: dict[Category, Path] = {name: root / name for name in CATEGORIES}
        if create:
            self.ensure_folders()

    def __repr__(self) -> str:
        """Return a debug-friendly representation naming the source folder."""
        return f"FolderManager(source_folder={str(self._source_folder)!r})"

    @property
    def source_folder(self) -> Path:
        """Absolute path of the folder being sorted."""
        return self._source_folder

    @property
    def category_folders(self) -> dict[Category, Path]:
        """Mapping of canonical category name to its destination folder."""
        return dict(self._folders)

    def ensure_folders(self) -> dict[Category, Path]:
        """Create any missing category folder and return the full mapping."""
        for folder in self._folders.values():
            try:
                folder.mkdir(exist_ok=True)
            except OSError as exc:
                raise FolderManagerError(
                    f"could not create category folder {folder}: {exc.strerror}"
                ) from exc
        LOGGER.debug(
            "destination folders ready under %s: %s",
            self._source_folder,
            ", ".join(sorted(self._folders)),
        )
        return dict(self._folders)

    def destination_for(self, category: Category | str) -> Path:
        """Return the destination folder for ``category`` without creating it."""
        return self._folders[normalize_category(category)]

    def move_image(self, image_path: str | Path, category: Category | str) -> Path:
        """Move ``image_path`` into the folder for ``category``.

        Returns the path the file actually ended up at; collisions are resolved
        with a numeric suffix rather than overwriting. Every attempt is logged.

        Raises:
            CategoryError: ``category`` is not one of :data:`CATEGORIES`.
            SourceNotFoundError: the image path does not exist.
            FolderManagerError: the destination folder cannot be created.
            FileOperationError: the move itself failed.
        """
        canonical = normalize_category(category)
        source = Path(image_path).expanduser()
        destination = self._folders[canonical]
        if not source.exists():
            LOGGER.error("cannot move missing image %s (%s)", source, canonical)
            raise SourceNotFoundError(f"image does not exist: {source}", source=source)

        try:
            destination.mkdir(exist_ok=True)
        except OSError as exc:
            LOGGER.error("cannot create %s: %s", destination, exc.strerror)
            raise FolderManagerError(
                f"could not create category folder {destination}: {exc.strerror}"
            ) from exc

        LOGGER.debug("moving %s to category %s", source.name, canonical)
        try:
            final_path = move_file(source, destination)
        except FileOperationError as exc:
            LOGGER.error("move failed for %s (%s): %s", source, canonical, exc)
            raise
        if final_path.name != source.name:
            LOGGER.info("collision avoided: %s renamed to %s", source.name, final_path.name)
        LOGGER.info("moved %s -> %s [%s]", source.name, final_path, canonical)
        return final_path

    @staticmethod
    def is_inside(candidate: Path, parent: Path) -> bool:
        """Return ``True`` when ``candidate`` is ``parent`` or below it."""
        candidate_resolved = Path(candidate).resolve()
        parent_resolved = Path(parent).resolve()
        return (
            candidate_resolved == parent_resolved or parent_resolved in candidate_resolved.parents
        )
