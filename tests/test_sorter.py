"""Tests for ``core/sorter.py``: queue state, moves and undo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from image_swiper.core.folder_manager import CategoryError, FolderManager, SourceFolderError
from image_swiper.core.image_loader import ImageLoader
from image_swiper.core.sorter import (
    MissingImageError,
    MoveRecord,
    NoCurrentImageError,
    Sorter,
    UndoError,
)

MakeImages = Callable[..., list[Path]]


def test_first_image_is_current(sample_folder: Path) -> None:
    """A fresh sorter starts at the first image, alphabetically."""
    sorter = Sorter(sample_folder)

    assert sorter.current_image() == sample_folder / "IMG_1.jpg"
    assert sorter.index == 0
    assert sorter.total == 3
    assert sorter.remaining_count == 3
    assert not sorter.finished


def test_constructor_creates_the_category_folders(sample_folder: Path) -> None:
    """Sorting implies the destinations exist."""
    Sorter(sample_folder)

    for name in ("Good", "Bad", "Great", "OK"):
        assert (sample_folder / name).is_dir()


def test_advance_moves_the_cursor_without_moving_files(sample_folder: Path) -> None:
    """Skipping leaves the file where it is."""
    sorter = Sorter(sample_folder)

    following = sorter.advance()

    assert following == sample_folder / "IMG_2.jpg"
    assert sorter.index == 1
    assert (sample_folder / "IMG_1.jpg").exists()
    assert sorter.remaining_count == 2


def test_advance_past_the_end_returns_none(sample_folder: Path) -> None:
    """Running off the end is normal, not an error."""
    sorter = Sorter(sample_folder)
    for _ in range(3):
        sorter.advance()

    assert sorter.advance() is None
    assert sorter.current_image() is None
    assert sorter.finished
    assert sorter.remaining_count == 0


def test_categorize_moves_the_file_and_returns_a_record(sample_folder: Path) -> None:
    """The record is the complete audit trail of one move."""
    sorter = Sorter(sample_folder)
    current = sorter.current_image()
    assert current is not None

    record = sorter.categorize("Good")

    assert isinstance(record, MoveRecord)
    assert record.source == current
    assert record.destination == sample_folder / "Good" / current.name
    assert record.destination.exists()
    assert not current.exists()
    assert record.category == "Good"
    assert record.index == 0
    assert record.filename == current.name


def test_categorize_shows_the_next_image(sample_folder: Path) -> None:
    """The cursor does not need adjusting after a move."""
    sorter = Sorter(sample_folder)

    sorter.categorize("Great")

    assert sorter.current_image() == sample_folder / "IMG_2.jpg"
    assert sorter.index == 0
    assert sorter.total == 3
    assert sorter.remaining_count == 2


def test_categorize_counts_categories(sample_folder: Path) -> None:
    """Counts follow the user's decisions and empty at the end."""
    sorter = Sorter(sample_folder)

    sorter.categorize("Good")
    sorter.categorize("Good")
    sorter.categorize("Bad")

    assert sorter.counts == {"Good": 2, "Bad": 1}
    assert sorter.finished
    assert sorter.total == 3


def test_categorize_normalises_category_case(sample_folder: Path) -> None:
    """``ok`` is recorded and stored as ``OK``."""
    sorter = Sorter(sample_folder)

    record = sorter.categorize("ok")

    assert record.category == "OK"
    assert record.destination.parent.name == "OK"


def test_categorize_unknown_category_raises_before_moving(sample_folder: Path) -> None:
    """Validation happens first, so nothing moves on a typo."""
    sorter = Sorter(sample_folder)
    current = sorter.current_image()

    with pytest.raises(CategoryError):
        sorter.categorize("Fantastic")

    assert current is not None
    assert current.exists()
    assert sorter.counts == {}


def test_categorize_when_finished_raises(sample_folder: Path) -> None:
    """There is nothing left to categorise once the queue is exhausted."""
    sorter = Sorter(sample_folder)
    for _ in range(3):
        sorter.advance()

    with pytest.raises(NoCurrentImageError):
        sorter.categorize("Good")


def test_categorize_drops_a_vanished_image(sample_folder: Path) -> None:
    """An externally deleted image is skipped, and the caller can continue."""
    sorter = Sorter(sample_folder)
    vanished = sorter.current_image()
    assert vanished is not None
    vanished.unlink()

    with pytest.raises(MissingImageError):
        sorter.categorize("Good")

    assert sorter.remaining_count == 2
    assert sorter.current_image() == sample_folder / "IMG_2.jpg"
    assert sorter.counts == {}


def test_undo_restores_the_file_and_the_cursor(sample_folder: Path) -> None:
    """Undo puts the image back at its original path and makes it current."""
    sorter = Sorter(sample_folder)
    original = sorter.current_image()
    assert original is not None
    sorter.categorize("Good")
    assert not original.exists()

    record = sorter.undo()

    assert record is not None
    assert record.category == "Good"
    assert original.exists()
    assert not record.destination.exists()
    assert sorter.current_image() == original
    assert sorter.index == 0
    assert sorter.remaining_count == 3


def test_undo_with_empty_history_returns_none(sample_folder: Path) -> None:
    """Undo is a no-op at the start of a session."""
    sorter = Sorter(sample_folder)

    assert sorter.undo() is None


def test_undo_twice_restores_both_moves(sample_folder: Path) -> None:
    """The stack is last-in-first-out."""
    sorter = Sorter(sample_folder)
    first = sorter.current_image()
    assert first is not None
    sorter.categorize("Good")
    second = sorter.current_image()
    assert second is not None
    sorter.categorize("Bad")

    assert sorter.undo() is not None
    assert sorter.undo() is not None
    assert sorter.undo() is None

    assert first.exists()
    assert second.exists()
    assert sorter.counts == {}
    assert sorter.remaining_count == 3


def test_undo_after_advancing_returns_to_the_restored_image(sample_folder: Path) -> None:
    """The restored image becomes current even if the user had moved on."""
    sorter = Sorter(sample_folder)
    original = sorter.current_image()
    assert original is not None
    sorter.categorize("Good")
    sorter.advance()
    assert sorter.index == 1

    sorter.undo()

    assert sorter.current_image() == original
    assert sorter.index == 0


def test_undo_never_overwrites_a_replacement(sample_folder: Path) -> None:
    """A file the user dropped back manually is preserved."""
    sorter = Sorter(sample_folder)
    original = sorter.current_image()
    assert original is not None
    sorter.categorize("Good")
    original.write_bytes(b"manual replacement")

    sorter.undo()

    restored = sorter.current_image()
    assert restored is not None
    assert restored.name == "IMG_1_1.jpg"
    assert original.read_bytes() == b"manual replacement"
    assert restored.read_bytes() != b"manual replacement"


def test_undo_reports_a_missing_destination(sample_folder: Path) -> None:
    """If the moved file vanished, undo refuses instead of guessing."""
    sorter = Sorter(sample_folder)
    record = sorter.categorize("Good")
    record.destination.unlink()

    with pytest.raises(UndoError):
        sorter.undo()

    assert len(sorter.history) == 1


def test_history_is_ordered_oldest_first(sample_folder: Path) -> None:
    """History reads chronologically."""
    sorter = Sorter(sample_folder)
    sorter.categorize("Good")
    sorter.categorize("Bad")

    categories = [record.category for record in sorter.history]

    assert categories == ["Good", "Bad"]


def test_undo_limit_keeps_only_recent_moves(sample_folder: Path) -> None:
    """The stack is bounded so memory cannot grow without limit."""
    sorter = Sorter(sample_folder, undo_limit=1)

    sorter.categorize("Good")
    sorter.categorize("Bad")

    assert len(sorter.history) == 1
    assert sorter.history[0].category == "Bad"


def test_zero_undo_limit_disables_undo(sample_folder: Path) -> None:
    """``undo_limit=0`` is a supported configuration."""
    sorter = Sorter(sample_folder, undo_limit=0)

    sorter.categorize("Good")

    assert sorter.history == ()
    assert sorter.undo() is None


def test_negative_undo_limit_is_rejected(sample_folder: Path) -> None:
    """A negative stack size is a programming error."""
    with pytest.raises(ValueError, match="undo_limit"):
        Sorter(sample_folder, undo_limit=-1)


def test_on_record_callback_receives_each_move(sample_folder: Path) -> None:
    """The UI subscribes through this callback instead of Qt signals."""
    seen: list[MoveRecord] = []
    sorter = Sorter(sample_folder, on_record=seen.append)

    record = sorter.categorize("Good")

    assert seen == [record]


def test_reload_picks_up_images_added_mid_session(
    sample_folder: Path, make_images: MakeImages
) -> None:
    """A refresh rescans the folder without losing history."""
    sorter = Sorter(sample_folder)
    sorter.categorize("Good")
    make_images(sample_folder, count=1, prefix="NEW_")

    queue = sorter.reload()

    assert [path.name for path in queue] == ["IMG_2.jpg", "IMG_3.jpg", "NEW_1.jpg"]
    assert sorter.index == 0
    assert sorter.total == 4
    assert len(sorter.history) == 1


def test_reset_clears_state_without_touching_files(sample_folder: Path) -> None:
    """Reset starts a clean session over the images still in the folder."""
    sorter = Sorter(sample_folder)
    sorter.categorize("Good")

    sorter.reset()

    assert sorter.counts == {}
    assert sorter.history == ()
    assert sorter.index == 0
    assert sorter.remaining_count == 2
    assert (sample_folder / "Good" / "IMG_1.jpg").exists()


def test_collaborators_can_be_injected(sample_folder: Path) -> None:
    """Tests and the UI may pass a prepared manager and loader."""
    manager = FolderManager(sample_folder)
    loader = ImageLoader(sample_folder)

    sorter = Sorter(sample_folder, folder_manager=manager, image_loader=loader)

    assert sorter.folder_manager is manager
    assert sorter.image_loader is loader
    assert sorter.current_image() == sample_folder / "IMG_1.jpg"


def test_missing_source_folder_raises(tmp_path: Path) -> None:
    """A sorter cannot be built without a real folder."""
    with pytest.raises(SourceFolderError):
        Sorter(tmp_path / "ghost")


def test_repr_summarises_the_session(sample_folder: Path) -> None:
    """The repr shows cursor, total and undo depth."""
    sorter = Sorter(sample_folder)
    sorter.categorize("Good")

    text = repr(sorter)

    assert "Sorter(source_folder=" in text
    assert "index=0" in text
    assert "total=3" in text
    assert "undo=1" in text
