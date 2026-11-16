"""Crash-safe, collision-free filesystem primitives.

Responsibility
    The only module allowed to move, copy or create files on the user's behalf.
    It offers small primitives with explicit semantics so that the folder
    manager and the sorter stay readable: no Qt, no image knowledge and no
    user-facing prose, only typed exceptions that carry both paths.

Public API
    ``FileOperationError``, ``SourceNotFoundError``, ``SameFileError`` and
    ``DestinationUnwritableError`` - typed failures, each carrying the paths.
    ``unique_path``, ``move_file``, ``copy_file``, ``remove_file``,
    ``reverse_move``, ``expand_path`` and ``is_writable_directory``.

Collision policy
    ``photo.jpg`` becomes ``photo_1.jpg``, then ``photo_2.jpg``; nothing is
    ever overwritten. Undo restores use the same scheme, so a file that the
    user put back manually is preserved instead of being clobbered.

Cross-device behaviour
    ``os.rename`` is attempted first, so a same-filesystem move is atomic. On
    ``EXDEV`` the file is copied, the byte count is verified, and only then is
    the source unlinked. No ``fsync``: the fallback is best-effort, not
    transactional.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path


class FileOperationError(Exception):
    """Base class for filesystem failures, carrying both involved paths."""

    def __init__(
        self,
        message: str,
        *,
        source: Path | None = None,
        destination: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.destination = destination


class SourceNotFoundError(FileOperationError):
    """The file to operate on does not exist or is not a regular file."""


class SameFileError(FileOperationError):
    """The source already lives in the requested destination directory."""


class DestinationUnwritableError(FileOperationError):
    """The destination directory is missing, not a directory, or read-only."""


def unique_path(directory: Path, filename: str) -> Path:
    """Return the first free path for ``filename`` inside ``directory``.

    The suffix scheme is ``photo.jpg`` -> ``photo_1.jpg`` -> ``photo_2.jpg``.
    Only existence is checked, which is all that is needed to avoid
    overwriting anything.
    """
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def expand_path(raw: str | Path) -> Path:
    """Expand ``~`` and resolve ``raw`` to an absolute path."""
    return Path(raw).expanduser().resolve()


def is_writable_directory(path: Path) -> bool:
    """Return ``True`` when ``path`` is a directory we may write into."""
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def _ensure_source_file(source: Path) -> None:
    """Raise :class:`SourceNotFoundError` unless ``source`` is a regular file."""
    if not source.exists():
        raise SourceNotFoundError(f"source does not exist: {source}", source=source)
    if not source.is_file():
        raise SourceNotFoundError(f"source is not a regular file: {source}", source=source)


def _ensure_destination_dir(destination_dir: Path) -> None:
    """Raise :class:`DestinationUnwritableError` unless we may write there."""
    if not destination_dir.exists():
        raise DestinationUnwritableError(
            f"destination directory does not exist: {destination_dir}",
            destination=destination_dir,
        )
    if not destination_dir.is_dir():
        raise DestinationUnwritableError(
            f"destination is not a directory: {destination_dir}",
            destination=destination_dir,
        )
    if not is_writable_directory(destination_dir):
        raise DestinationUnwritableError(
            f"destination directory is not writable: {destination_dir}",
            destination=destination_dir,
        )


def _verify_sizes(source: Path, target: Path) -> None:
    """Raise unless ``target`` has the same byte count as ``source``."""
    if source.stat().st_size != target.stat().st_size:
        target.unlink(missing_ok=True)
        raise FileOperationError(
            f"size verification failed for {target}",
            source=source,
            destination=target,
        )


def _copy_then_unlink(source: Path, target: Path) -> None:
    """Cross-device fallback: copy, verify, then remove the source."""
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise FileOperationError(
            f"cross-device copy failed for {source}: {exc.strerror}",
            source=source,
            destination=target,
        ) from exc
    _verify_sizes(source, target)
    try:
        source.unlink()
    except OSError as exc:
        raise FileOperationError(
            f"copied {source} but could not remove the source: {exc.strerror}",
            source=source,
            destination=target,
        ) from exc


def _relocate(source: Path, target: Path) -> None:
    """Move ``source`` to ``target``, falling back to copy+unlink on ``EXDEV``."""
    try:
        os.rename(source, target)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise FileOperationError(
                f"could not move {source} to {target}: {exc.strerror}",
                source=source,
                destination=target,
            ) from exc
        _copy_then_unlink(source, target)


def move_file(source: Path, destination_dir: Path) -> Path:
    """Move ``source`` into ``destination_dir`` and return the final path.

    Raises:
        SourceNotFoundError: ``source`` is missing or not a file.
        DestinationUnwritableError: the destination is missing or read-only.
        SameFileError: ``source`` already sits in ``destination_dir``.
        FileOperationError: any other filesystem failure.
    """
    source = Path(source)
    destination_dir = Path(destination_dir)
    _ensure_source_file(source)
    _ensure_destination_dir(destination_dir)
    if source.parent.resolve() == destination_dir.resolve():
        raise SameFileError(
            f"{source} is already inside {destination_dir}",
            source=source,
            destination=destination_dir,
        )

    target = unique_path(destination_dir, source.name)
    _relocate(source, target)
    return target


def copy_file(source: Path, destination_dir: Path) -> Path:
    """Copy ``source`` into ``destination_dir`` and return the new path.

    Uses the same collision handling as :func:`move_file` and leaves the
    source untouched.
    """
    source = Path(source)
    destination_dir = Path(destination_dir)
    _ensure_source_file(source)
    _ensure_destination_dir(destination_dir)

    target = unique_path(destination_dir, source.name)
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise FileOperationError(
            f"could not copy {source} to {target}: {exc.strerror}",
            source=source,
            destination=target,
        ) from exc
    _verify_sizes(source, target)
    return target


def remove_file(path: Path) -> None:
    """Remove exactly ``path``; used only to undo a copy this session made.

    Callers must pass a path this application created. The function refuses to
    guess and never removes a directory.
    """
    path = Path(path)
    _ensure_source_file(path)
    try:
        path.unlink()
    except OSError as exc:
        raise FileOperationError(
            f"could not remove {path}: {exc.strerror}",
            source=path,
        ) from exc


def reverse_move(source: Path, destination: Path) -> Path:
    """Move ``destination`` back to ``source``, recreating parent directories.

    ``source`` is the path recorded before the original move. If something now
    occupies it, the restored file receives a fresh ``_N`` name instead of
    overwriting the stranger. Returns the path the file actually ended up at.
    """
    source = Path(source)
    destination = Path(destination)
    _ensure_source_file(destination)

    parent = source.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DestinationUnwritableError(
            f"could not recreate {parent}: {exc.strerror}",
            destination=parent,
        ) from exc
    if not is_writable_directory(parent):
        raise DestinationUnwritableError(
            f"restore directory is not writable: {parent}",
            destination=parent,
        )

    target = unique_path(parent, source.name)
    _relocate(destination, target)
    return target
