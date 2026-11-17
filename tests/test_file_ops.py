"""Behavioural tests for the filesystem primitives in ``utils/file_ops.py``.

Every test works inside ``tmp_path``; nothing reads or writes outside the
sandbox. The cross-device path is simulated by making ``os.rename`` raise
``EXDEV``, and permission tests are skipped when the suite runs as root, where
``chmod`` does not restrict access.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from swipey_photos.utils import file_ops
from swipey_photos.utils.file_ops import (
    DestinationUnwritableError,
    FileOperationError,
    SameFileError,
    SourceNotFoundError,
    copy_file,
    expand_path,
    is_writable_directory,
    move_file,
    remove_file,
    reverse_move,
    unique_path,
)

NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permission checks",
)


def _write(path: Path, content: str = "data") -> Path:
    """Create ``path`` (and its parents) with ``content`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _raise_exdev(source: object, target: object) -> None:
    """Impersonate ``os.rename`` across filesystems."""
    raise OSError(errno.EXDEV, "Invalid cross-device link")


def test_unique_path_returns_original_when_free(tmp_path: Path) -> None:
    """An unused name is returned unchanged."""
    assert unique_path(tmp_path, "photo.jpg") == tmp_path / "photo.jpg"


def test_unique_path_uses_underscore_suffixes(tmp_path: Path) -> None:
    """Existing names push the candidate on to ``_1`` and then ``_2``."""
    _write(tmp_path / "photo.jpg")
    assert unique_path(tmp_path, "photo.jpg") == tmp_path / "photo_1.jpg"

    _write(tmp_path / "photo_1.jpg")
    assert unique_path(tmp_path, "photo.jpg") == tmp_path / "photo_2.jpg"


def test_unique_path_preserves_dotted_stem(tmp_path: Path) -> None:
    """Only the final suffix counts as the extension."""
    _write(tmp_path / "holiday.2024.jpg")
    assert unique_path(tmp_path, "holiday.2024.jpg").name == "holiday.2024_1.jpg"


def test_move_file_moves_and_returns_new_path(tmp_path: Path) -> None:
    """A move relocates the file and reports where it landed."""
    source = _write(tmp_path / "photo.jpg")
    destination = tmp_path / "Good"
    destination.mkdir()

    result = move_file(source, destination)

    assert result == destination / "photo.jpg"
    assert result.read_text(encoding="utf-8") == "data"
    assert not source.exists()


def test_move_file_never_overwrites(tmp_path: Path) -> None:
    """A same-named file in the destination is preserved."""
    source = _write(tmp_path / "photo.jpg", "incoming")
    destination = tmp_path / "Good"
    destination.mkdir()
    _write(destination / "photo.jpg", "resident")

    result = move_file(source, destination)

    assert result.name == "photo_1.jpg"
    assert (destination / "photo.jpg").read_text(encoding="utf-8") == "resident"
    assert result.read_text(encoding="utf-8") == "incoming"


def test_move_file_missing_source_raises(tmp_path: Path) -> None:
    """A missing source is reported with the offending path attached."""
    destination = tmp_path / "Good"
    destination.mkdir()

    with pytest.raises(SourceNotFoundError) as caught:
        move_file(tmp_path / "ghost.jpg", destination)

    assert caught.value.source == tmp_path / "ghost.jpg"


def test_move_file_directory_source_raises(tmp_path: Path) -> None:
    """Directories are not images and are refused."""
    source = tmp_path / "nested"
    source.mkdir()
    destination = tmp_path / "Good"
    destination.mkdir()

    with pytest.raises(SourceNotFoundError, match="not a regular file"):
        move_file(source, destination)


def test_move_file_missing_destination_raises(tmp_path: Path) -> None:
    """A destination that does not exist is never created implicitly."""
    source = _write(tmp_path / "photo.jpg")

    with pytest.raises(DestinationUnwritableError) as caught:
        move_file(source, tmp_path / "Missing")

    assert caught.value.destination == tmp_path / "Missing"
    assert source.exists()


def test_move_file_destination_is_file_raises(tmp_path: Path) -> None:
    """A destination path that is a file is rejected."""
    source = _write(tmp_path / "photo.jpg")
    destination = _write(tmp_path / "not-a-folder")

    with pytest.raises(DestinationUnwritableError, match="not a directory"):
        move_file(source, destination)


@NOT_ROOT
def test_move_file_readonly_destination_raises(tmp_path: Path) -> None:
    """A read-only destination fails before the file is touched."""
    source = _write(tmp_path / "photo.jpg")
    destination = tmp_path / "Good"
    destination.mkdir()
    destination.chmod(0o500)
    try:
        with pytest.raises(DestinationUnwritableError, match="not writable"):
            move_file(source, destination)
    finally:
        destination.chmod(0o700)
    assert source.exists()


def test_move_file_same_directory_raises(tmp_path: Path) -> None:
    """Moving a file into its own folder is a caller bug, not a rename."""
    source = _write(tmp_path / "photo.jpg")

    with pytest.raises(SameFileError):
        move_file(source, tmp_path)


def test_move_file_across_devices_copies_then_unlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ``EXDEV`` rename falls back to copy, verification and unlink."""
    source = _write(tmp_path / "photo.jpg", "payload")
    destination = tmp_path / "Good"
    destination.mkdir()
    monkeypatch.setattr(file_ops.os, "rename", _raise_exdev)

    result = move_file(source, destination)

    assert result.read_text(encoding="utf-8") == "payload"
    assert not source.exists()


def test_move_file_failed_cross_device_copy_keeps_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed fallback copy raises and leaves the original untouched."""
    source = _write(tmp_path / "photo.jpg", "payload")
    destination = tmp_path / "Good"
    destination.mkdir()
    monkeypatch.setattr(file_ops.os, "rename", _raise_exdev)

    def fail_copy(src: object, dst: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(file_ops.shutil, "copy2", fail_copy)

    with pytest.raises(FileOperationError, match="cross-device copy failed"):
        move_file(source, destination)

    assert source.exists()
    assert not (destination / "photo.jpg").exists()


def test_move_file_reports_unexpected_rename_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Errors other than ``EXDEV`` are wrapped, not silently retried."""
    source = _write(tmp_path / "photo.jpg")
    destination = tmp_path / "Good"
    destination.mkdir()

    def fail_rename(src: object, dst: object) -> None:
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(file_ops.os, "rename", fail_rename)

    with pytest.raises(FileOperationError, match="could not move"):
        move_file(source, destination)


def test_copy_file_keeps_the_source(tmp_path: Path) -> None:
    """Copying leaves the original in place and reports the new path."""
    source = _write(tmp_path / "photo.jpg", "payload")
    destination = tmp_path / "Good"
    destination.mkdir()

    result = copy_file(source, destination)

    assert result == destination / "photo.jpg"
    assert source.exists()
    assert result.read_text(encoding="utf-8") == "payload"


def test_copy_file_avoids_collisions(tmp_path: Path) -> None:
    """Copying twice yields ``photo_1.jpg`` rather than an overwrite."""
    source = _write(tmp_path / "photo.jpg", "payload")
    destination = tmp_path / "Good"
    destination.mkdir()
    _write(destination / "photo.jpg", "resident")

    result = copy_file(source, destination)

    assert result.name == "photo_1.jpg"
    assert (destination / "photo.jpg").read_text(encoding="utf-8") == "resident"


def test_remove_file_deletes_only_the_given_file(tmp_path: Path) -> None:
    """Removal takes exactly one file and leaves its neighbours alone."""
    doomed = _write(tmp_path / "doomed.jpg")
    keeper = _write(tmp_path / "keeper.jpg")

    remove_file(doomed)

    assert not doomed.exists()
    assert keeper.exists()


def test_remove_file_missing_path_raises(tmp_path: Path) -> None:
    """Removing a missing path is an error, not a silent no-op."""
    with pytest.raises(SourceNotFoundError):
        remove_file(tmp_path / "ghost.jpg")


def test_reverse_move_restores_the_original_path(tmp_path: Path) -> None:
    """Undo puts the file back where it came from."""
    source = _write(tmp_path / "photo.jpg")
    destination = tmp_path / "Good"
    destination.mkdir()
    moved = move_file(source, destination)

    restored = reverse_move(source, moved)

    assert restored == source
    assert restored.exists()
    assert not moved.exists()


def test_reverse_move_recreates_missing_parents(tmp_path: Path) -> None:
    """A deleted source folder is recreated instead of failing the undo."""
    source = _write(tmp_path / "session" / "photo.jpg")
    destination = tmp_path / "Good"
    destination.mkdir()
    moved = move_file(source, destination)
    source.parent.rmdir()

    restored = reverse_move(source, moved)

    assert restored == source
    assert restored.exists()


def test_reverse_move_uses_a_fresh_name_when_original_is_taken(tmp_path: Path) -> None:
    """A file the user put back manually is never overwritten by undo."""
    source = _write(tmp_path / "photo.jpg", "original")
    destination = tmp_path / "Good"
    destination.mkdir()
    moved = move_file(source, destination)
    _write(source, "manual replacement")

    restored = reverse_move(source, moved)

    assert restored.name == "photo_1.jpg"
    assert source.read_text(encoding="utf-8") == "manual replacement"
    assert restored.read_text(encoding="utf-8") == "original"


def test_reverse_move_missing_destination_raises(tmp_path: Path) -> None:
    """Undoing a move whose file vanished reports the problem."""
    with pytest.raises(SourceNotFoundError):
        reverse_move(tmp_path / "photo.jpg", tmp_path / "Good" / "photo.jpg")


def test_expand_path_expands_home() -> None:
    """A leading ``~`` becomes the user's home directory."""
    expanded = expand_path("~/photo.jpg")

    assert expanded == Path.home() / "photo.jpg"
    assert expanded.is_absolute()


def test_expand_path_accepts_path_objects(tmp_path: Path) -> None:
    """Both ``str`` and ``Path`` inputs resolve to an absolute path."""
    assert expand_path(tmp_path) == tmp_path.resolve()


@NOT_ROOT
def test_is_writable_directory_rejects_read_only_folders(tmp_path: Path) -> None:
    """Writability is checked for the folder itself."""
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        assert not is_writable_directory(folder)
    finally:
        folder.chmod(0o700)


def test_is_writable_directory_accepts_normal_folders(tmp_path: Path) -> None:
    """A freshly created directory is writable."""
    assert is_writable_directory(tmp_path)


def test_is_writable_directory_rejects_files(tmp_path: Path) -> None:
    """A file is not a directory, however writable it is."""
    assert not is_writable_directory(_write(tmp_path / "photo.jpg"))


def test_errors_expose_both_paths(tmp_path: Path) -> None:
    """Every failure carries the paths so the UI can explain itself."""
    error = FileOperationError(
        "boom", source=tmp_path / "a.jpg", destination=tmp_path / "Good" / "a.jpg"
    )

    assert error.source == tmp_path / "a.jpg"
    assert error.destination == tmp_path / "Good" / "a.jpg"
    assert str(error) == "boom"
