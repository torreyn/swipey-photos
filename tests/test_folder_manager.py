"""Tests for ``core/folder_manager.py``: layout, validation and move logging."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from image_swiper.core.folder_manager import (
    CATEGORIES,
    CategoryError,
    FolderManager,
    SourceFolderError,
    normalize_category,
)
from image_swiper.utils.file_ops import SourceNotFoundError

LOGGER_NAME = "image_swiper"


def test_constructor_creates_all_category_folders(sample_folder: Path) -> None:
    """A new session gets the four destination folders immediately."""
    FolderManager(sample_folder)

    for name in CATEGORIES:
        assert (sample_folder / name).is_dir()


def test_existing_folders_are_left_alone(sample_folder: Path) -> None:
    """Re-opening a folder must never disturb its current contents."""
    good = sample_folder / "Good"
    good.mkdir()
    marker = good / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    FolderManager(sample_folder)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_missing_source_folder_raises(tmp_path: Path) -> None:
    """Sorting a folder that does not exist is a hard error."""
    with pytest.raises(SourceFolderError, match="does not exist"):
        FolderManager(tmp_path / "ghost")


def test_file_as_source_raises(tmp_path: Path) -> None:
    """A file is not a folder, even if its name looks like one."""
    source = tmp_path / "photos"
    source.write_text("not a folder", encoding="utf-8")

    with pytest.raises(SourceFolderError, match="not a folder"):
        FolderManager(source)


def test_create_false_leaves_the_layout_untouched(sample_folder: Path) -> None:
    """``create=False`` allows read-only inspection."""
    manager = FolderManager(sample_folder, create=False)

    assert not (sample_folder / "Good").exists()
    assert manager.category_folders == {name: sample_folder / name for name in CATEGORIES}


def test_category_folders_property_is_a_copy(sample_folder: Path) -> None:
    """Callers cannot corrupt the internal mapping."""
    manager = FolderManager(sample_folder)

    mapping = manager.category_folders
    mapping.clear()

    assert len(manager.category_folders) == len(CATEGORIES)


def test_ensure_folders_recreates_a_deleted_folder(sample_folder: Path) -> None:
    """A folder deleted mid-session is recreated on demand."""
    manager = FolderManager(sample_folder)
    (sample_folder / "OK").rmdir()

    manager.ensure_folders()

    assert (sample_folder / "OK").is_dir()


def test_move_image_returns_the_final_path(sample_folder: Path) -> None:
    """The returned path is the file's real location after the move."""
    manager = FolderManager(sample_folder)
    image = sample_folder / "IMG_1.jpg"

    result = manager.move_image(image, "Good")

    assert result == sample_folder / "Good" / "IMG_1.jpg"
    assert result.exists()
    assert not image.exists()


def test_move_image_resolves_a_collision(sample_folder: Path) -> None:
    """A name already present in the destination gains a ``_1`` suffix."""
    manager = FolderManager(sample_folder)
    first = manager.move_image(sample_folder / "IMG_1.jpg", "Good")
    replacement = sample_folder / "IMG_1.jpg"
    replacement.write_bytes(b"second version")

    second = manager.move_image(replacement, "Good")

    assert first.name == "IMG_1.jpg"
    assert second.name == "IMG_1_1.jpg"
    assert second.read_bytes() == b"second version"
    assert first.read_bytes() != b"second version"


def test_move_image_counts_up_on_repeated_collisions(sample_folder: Path) -> None:
    """Every extra same-named file gets the next free number."""
    manager = FolderManager(sample_folder)
    names: list[str] = []
    for _ in range(3):
        candidate = sample_folder / "photo.jpg"
        candidate.write_bytes(b"x")
        names.append(manager.move_image(candidate, "Bad").name)

    assert names == ["photo.jpg", "photo_1.jpg", "photo_2.jpg"]


def test_move_image_accepts_any_category_case(sample_folder: Path) -> None:
    """``ok`` is stored as the canonical ``OK`` folder."""
    manager = FolderManager(sample_folder)

    result = manager.move_image(sample_folder / "IMG_2.jpg", "ok")

    assert result.parent.name == "OK"


def test_move_image_unknown_category_raises(sample_folder: Path) -> None:
    """An unknown category is rejected before anything moves."""
    manager = FolderManager(sample_folder)
    image = sample_folder / "IMG_1.jpg"

    with pytest.raises(CategoryError) as caught:
        manager.move_image(image, "Excellent")

    assert isinstance(caught.value, ValueError)
    assert image.exists()


def test_move_image_missing_file_raises(sample_folder: Path) -> None:
    """A vanished image is reported with the path attached."""
    manager = FolderManager(sample_folder)

    with pytest.raises(SourceNotFoundError) as caught:
        manager.move_image(sample_folder / "ghost.jpg", "Good")

    assert caught.value.source == sample_folder / "ghost.jpg"


def test_move_image_recreates_a_deleted_destination(sample_folder: Path) -> None:
    """A destination removed mid-session is recreated rather than failing."""
    manager = FolderManager(sample_folder)
    (sample_folder / "Great").rmdir()

    result = manager.move_image(sample_folder / "IMG_3.jpg", "Great")

    assert result.exists()
    assert result.parent.name == "Great"


def test_move_image_logs_every_move(sample_folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    """An INFO record names the file and its final path."""
    manager = FolderManager(sample_folder)
    image = sample_folder / "IMG_1.jpg"

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        result = manager.move_image(image, "Good")

    messages = [record.getMessage() for record in caplog.records]
    assert any("moved IMG_1.jpg" in message for message in messages)
    assert any(str(result) in message for message in messages)


def test_move_image_logs_collision_renames(
    sample_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A rename caused by a collision is visible in the log."""
    manager = FolderManager(sample_folder)
    manager.move_image(sample_folder / "IMG_1.jpg", "Good")
    replacement = sample_folder / "IMG_1.jpg"
    replacement.write_bytes(b"second")

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        manager.move_image(replacement, "Good")

    messages = [record.getMessage() for record in caplog.records]
    assert any("collision avoided" in message for message in messages)


def test_move_image_logs_failures(sample_folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A failed move is logged at ERROR, with the category."""
    manager = FolderManager(sample_folder)

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME), pytest.raises(SourceNotFoundError):
        manager.move_image(sample_folder / "ghost.jpg", "Bad")

    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any("ghost.jpg" in record.getMessage() for record in errors)


def test_destination_for_returns_the_category_folder(sample_folder: Path) -> None:
    """``destination_for`` maps a name to its folder without moving anything."""
    manager = FolderManager(sample_folder)

    assert manager.destination_for("Great") == sample_folder / "Great"
    with pytest.raises(CategoryError):
        manager.destination_for("Nope")


def test_is_inside_detects_children(sample_folder: Path) -> None:
    """The helper distinguishes descendants from siblings."""
    assert FolderManager.is_inside(sample_folder / "Good" / "a.jpg", sample_folder)
    assert FolderManager.is_inside(sample_folder, sample_folder)
    assert not FolderManager.is_inside(sample_folder, sample_folder / "Good")


def test_normalize_category_trims_and_ignores_case() -> None:
    """User input such as ``" good "`` still resolves canonically."""
    assert normalize_category(" good ") == "Good"
    assert normalize_category("BAD") == "Bad"
    assert normalize_category("Great") == "Great"


def test_normalize_category_rejects_unknown_values() -> None:
    """The error lists the accepted names."""
    with pytest.raises(CategoryError, match="expected one of"):
        normalize_category("nope")


def test_repr_names_the_source_folder(sample_folder: Path) -> None:
    """The repr is useful in a debugger or log line."""
    manager = FolderManager(sample_folder)

    assert "FolderManager(source_folder=" in repr(manager)
    assert str(sample_folder) in repr(manager)
