"""Discovering the images in a folder and decoding them safely.

Responsibility
    Turn a folder into a deterministic, sorted list of supported image paths,
    skipping everything the user cannot actually view: wrong extension, a
    subfolder, an unreadable file, or bytes that Pillow rejects. It is also the
    single place that decodes a file for display, with EXIF orientation applied
    and a bounded size so a 100 MP photo cannot exhaust memory.

Public API
    SUPPORTED_EXTENSIONS: frozenset[str]
    ImageLoaderError                source folder missing or unreadable
    natural_key(path)               case-insensitive, numeric-aware sort key
    ImageLoader(source_folder, *, extensions=None, validate=True):
        source_folder, extensions, images, load(), reload(),
        validate_image(path), load_preview(path, max_edge), next_candidates()

Behaviour
    * Scanning is non-recursive, so the Good/Bad/Great/OK folders created by
      :class:`~image_swiper.core.folder_manager.FolderManager` never reappear
      in the queue.
    * Order is alphabetical but numeric-aware: ``IMG_2`` sorts before
      ``IMG_10`` and ``photo.jpg`` before ``photo_1.jpg``.
    * ``validate=True`` opens each candidate and calls ``verify()``; corrupt
      files are logged at WARNING and skipped. That costs one I/O pass, so a
      caller scanning a huge folder may pass ``validate=False`` and rely on
      :meth:`ImageLoader.validate_image` before display.
    * Hidden files are ignored. Symlinks to files are followed, symlinked
      directories are never descended into.
    * ``reload()`` rescans from scratch and is the only way to pick up images
      the user drops into the folder mid-session.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..utils.file_ops import expand_path
from ..utils.logging_setup import get_logger

LOGGER = get_logger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
)
DEFAULT_PREVIEW_EDGE = 1600

_SPLIT_DIGITS = re.compile(r"(\d+)")


class ImageLoaderError(Exception):
    """Raised when the source folder is missing, unusable or undecodable."""


def natural_key(path: Path) -> tuple[tuple[int, object], ...]:
    """Return a case-insensitive, numeric-aware sort key for ``path.name``."""
    parts: list[tuple[int, object]] = []
    for chunk in _SPLIT_DIGITS.split(path.name.casefold()):
        if not chunk:
            continue
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, chunk))
    return tuple(parts)


class ImageLoader:
    """Scan one folder for supported, readable image files.

    Args:
        source_folder: Folder to scan; must exist and be a directory.
        extensions: Override for :data:`SUPPORTED_EXTENSIONS`; entries may be
            given with or without the leading dot.
        validate: Open each candidate with Pillow and skip corrupt files.

    Raises:
        ImageLoaderError: ``source_folder`` is missing or not a directory.
    """

    def __init__(
        self,
        source_folder: str | Path,
        *,
        extensions: Iterable[str] | None = None,
        validate: bool = True,
    ) -> None:
        root = expand_path(source_folder)
        if not root.exists():
            raise ImageLoaderError(f"source folder does not exist: {root}")
        if not root.is_dir():
            raise ImageLoaderError(f"source path is not a folder: {root}")
        self._source_folder = root
        if extensions is None:
            self._extensions = SUPPORTED_EXTENSIONS
        else:
            self._extensions = frozenset(
                (ext if ext.startswith(".") else f".{ext}").casefold() for ext in extensions
            )
        self._validate = validate
        self._images: tuple[Path, ...] = ()
        self._loaded = False

    def __repr__(self) -> str:
        """Return a debug-friendly representation naming the scanned folder."""
        return f"ImageLoader(source_folder={str(self._source_folder)!r})"

    @property
    def source_folder(self) -> Path:
        """Absolute path of the folder being scanned."""
        return self._source_folder

    @property
    def extensions(self) -> frozenset[str]:
        """Lower-case extensions, including the leading dot, that are accepted."""
        return self._extensions

    @property
    def images(self) -> tuple[Path, ...]:
        """Images found by the last scan; empty until :meth:`load` runs."""
        return self._images

    def load(self) -> list[Path]:
        """Scan the folder and return the sorted list of usable image paths.

        The result is cached until :meth:`reload` is called, so repeated calls
        are free and always return the same list.

        Raises:
            ImageLoaderError: the folder cannot be listed.
        """
        if self._loaded:
            return list(self._images)

        try:
            entries = sorted(self._source_folder.iterdir())
        except OSError as exc:
            raise ImageLoaderError(f"could not read {self._source_folder}: {exc.strerror}") from exc

        candidates: list[Path] = []
        for entry in entries:
            if entry.name.startswith("."):
                LOGGER.debug("skipping hidden entry %s", entry.name)
                continue
            try:
                if not entry.is_file():
                    continue
            except OSError as exc:
                LOGGER.warning("skipping unstatable entry %s: %s", entry.name, exc)
                continue
            if entry.suffix.casefold() not in self._extensions:
                LOGGER.debug("skipping unsupported file %s", entry.name)
                continue
            if not os.access(entry, os.R_OK):
                LOGGER.warning("skipping unreadable file %s", entry)
                continue
            if self._validate and not self.validate_image(entry):
                continue
            candidates.append(entry)

        candidates.sort(key=natural_key)
        self._images = tuple(candidates)
        self._loaded = True
        LOGGER.info("found %d sortable image(s) in %s", len(candidates), self._source_folder)
        return list(candidates)

    def reload(self) -> list[Path]:
        """Rescan the folder, picking up images added during this session."""
        LOGGER.debug("reloading %s", self._source_folder)
        self._loaded = False
        self._images = ()
        return self.load()

    def validate_image(self, path: str | Path) -> bool:
        """Return ``True`` when Pillow can decode ``path`` without error."""
        image_path = Path(path)
        try:
            with Image.open(image_path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            LOGGER.warning("skipping invalid image %s: %s", image_path, exc)
            return False
        return True

    def load_preview(
        self, path: str | Path, *, max_edge: int = DEFAULT_PREVIEW_EDGE
    ) -> tuple[Image.Image, tuple[int, int]]:
        """Decode ``path`` for display and downscale its longest edge.

        Returns the RGB(A) image plus the orientation-corrected original size,
        so the UI can print ``"4000 x 3000"`` while drawing at screen size.

        Raises:
            ImageLoaderError: the file cannot be decoded.
            ValueError: ``max_edge`` is not positive.
        """
        if max_edge <= 0:
            raise ValueError(f"max_edge must be positive, got {max_edge}")
        image_path = Path(path)
        try:
            with Image.open(image_path) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise ImageLoaderError(f"could not decode {image_path}: {exc}") from exc

        original_size = image.size
        if image.mode not in {"RGB", "RGBA"}:
            has_alpha = "A" in image.getbands()
            image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        return image, original_size

    def next_candidates(self, index: int, lookahead: int = 2) -> list[Path]:
        """Return up to ``lookahead`` images after ``index`` for preloading."""
        images = self.load()
        start = max(index + 1, 0)
        return images[start : start + max(lookahead, 0)]
