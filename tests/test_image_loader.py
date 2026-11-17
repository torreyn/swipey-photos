"""Tests for ``core/image_loader.py``: scanning, filtering and decoding."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from swipey_photos.core.image_loader import (
    SUPPORTED_EXTENSIONS,
    ImageLoader,
    ImageLoaderError,
    natural_key,
    subfolders,
)

NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses file permission checks",
)

MakeImages = Callable[..., list[Path]]


def test_supported_extensions_cover_the_documented_set() -> None:
    """Every extension the app promises is accepted."""
    expected = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
    assert expected <= SUPPORTED_EXTENSIONS


def test_load_finds_every_supported_format(tmp_path: Path, make_images: MakeImages) -> None:
    """One image per supported container format is enough to prove dispatch."""
    formats = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tiff"}
    for fmt in formats:
        make_images(tmp_path, count=1, prefix=f"shot_{fmt}_", fmt=fmt)

    paths = ImageLoader(tmp_path).load()

    assert {path.suffix for path in paths} == set(formats.values())


def test_load_accepts_jpeg_spelling_and_uppercase(tmp_path: Path, make_images: MakeImages) -> None:
    """``.jpeg`` and ``.JPG`` are the same format to the user."""
    created = make_images(tmp_path, count=1, prefix="lower_")
    created[0].rename(created[0].with_suffix(".jpeg"))
    upper = make_images(tmp_path, count=1, prefix="upper_")[0]
    upper.rename(upper.with_suffix(".JPG"))

    names = [path.name for path in ImageLoader(tmp_path).load()]

    assert sorted(names) == ["lower_1.jpeg", "upper_1.JPG"]


def test_load_skips_unsupported_and_hidden_files(tmp_path: Path, make_images: MakeImages) -> None:
    """Documents, archives and dotfiles are never treated as images."""
    make_images(tmp_path, count=1, prefix="valid_")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "archive.zip").write_bytes(b"PK\x03\x04")
    image = make_images(tmp_path, count=1, prefix="hidden_")[0]
    image.rename(tmp_path / ".hidden.jpg")

    paths = ImageLoader(tmp_path).load()

    assert [path.name for path in paths] == ["valid_1.jpg"]


def test_load_skips_subfolders(tmp_path: Path, make_images: MakeImages) -> None:
    """Scanning is non-recursive, so destination folders stay out of the queue."""
    make_images(tmp_path, count=1, prefix="root_")
    nested = tmp_path / "Good"
    make_images(nested, count=2, prefix="moved_")

    paths = ImageLoader(tmp_path).load()

    assert [path.name for path in paths] == ["root_1.jpg"]


def test_load_sorts_naturally(tmp_path: Path, make_images: MakeImages) -> None:
    """``IMG_2`` comes before ``IMG_10``, not after it."""
    for number in (10, 2, 1):
        make_images(tmp_path, count=1, start=number)

    names = [path.name for path in ImageLoader(tmp_path).load()]

    assert names == ["IMG_1.jpg", "IMG_2.jpg", "IMG_10.jpg"]


def test_natural_key_is_case_insensitive() -> None:
    """Sorting ignores case but keeps digits numeric."""
    assert natural_key(Path("A.jpg")) < natural_key(Path("b.jpg"))
    assert natural_key(Path("IMG_2.jpg")) < natural_key(Path("img_10.jpg"))


def test_corrupt_images_are_skipped_by_default(tmp_path: Path, make_images: MakeImages) -> None:
    """A file with an image extension but broken bytes never reaches the UI."""
    make_images(tmp_path, count=1, prefix="good_")
    (tmp_path / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0 truncated")

    paths = ImageLoader(tmp_path).load()

    assert [path.name for path in paths] == ["good_1.jpg"]


def test_corrupt_images_are_listed_when_validation_is_off(
    tmp_path: Path, make_images: MakeImages
) -> None:
    """Fast mode trades validation for speed and trusts the extension."""
    make_images(tmp_path, count=1, prefix="good_")
    (tmp_path / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0 truncated")

    paths = ImageLoader(tmp_path, validate=False).load()

    assert [path.name for path in paths] == ["broken.jpg", "good_1.jpg"]


@NOT_ROOT
def test_unreadable_files_are_skipped(tmp_path: Path, make_images: MakeImages) -> None:
    """Permission problems are logged and the file is skipped."""
    make_images(tmp_path, count=1, prefix="readable_")
    locked = make_images(tmp_path, count=1, prefix="locked_")[0]
    locked.chmod(0o000)
    try:
        paths = ImageLoader(tmp_path).load()
    finally:
        locked.chmod(0o600)

    assert [path.name for path in paths] == ["readable_1.jpg"]


def test_missing_folder_raises(tmp_path: Path) -> None:
    """A folder that does not exist cannot be scanned."""
    with pytest.raises(ImageLoaderError, match="does not exist"):
        ImageLoader(tmp_path / "ghost")


def test_file_instead_of_folder_raises(tmp_path: Path) -> None:
    """A file path is rejected with a clear message."""
    source = tmp_path / "photos"
    source.write_text("nope", encoding="utf-8")

    with pytest.raises(ImageLoaderError, match="not a folder"):
        ImageLoader(source)


@NOT_ROOT
def test_unreadable_folder_raises(tmp_path: Path, make_images: MakeImages) -> None:
    """An unlistable folder surfaces as a loader error, not a crash."""
    folder = tmp_path / "private"
    make_images(folder, count=1)
    folder.chmod(0o000)
    try:
        with pytest.raises(ImageLoaderError, match="could not read"):
            ImageLoader(folder).load()
    finally:
        folder.chmod(0o700)


def test_load_is_cached_until_reload(tmp_path: Path, make_images: MakeImages) -> None:
    """Repeated ``load`` calls do not rescan and stay equal."""
    make_images(tmp_path, count=2)
    loader = ImageLoader(tmp_path)

    first = loader.load()
    make_images(tmp_path, count=1, prefix="late_")
    second = loader.load()
    refreshed = loader.reload()

    assert first == second
    assert [path.name for path in refreshed] == ["IMG_1.jpg", "IMG_2.jpg", "late_1.jpg"]


def test_images_property_is_empty_before_load(tmp_path: Path, make_images: MakeImages) -> None:
    """The cache is only filled by an explicit scan."""
    make_images(tmp_path, count=1)
    loader = ImageLoader(tmp_path)

    assert loader.images == ()
    assert len(loader.load()) == 1
    assert len(loader.images) == 1


def test_custom_extensions_replace_the_defaults(tmp_path: Path, make_images: MakeImages) -> None:
    """Callers may restrict or extend the accepted suffixes."""
    make_images(tmp_path, count=1, prefix="photo_")
    make_images(tmp_path, count=1, prefix="shot_", fmt="PNG")

    loader = ImageLoader(tmp_path, extensions=["png"])

    assert loader.extensions == frozenset({".png"})
    assert [path.name for path in loader.load()] == ["shot_1.png"]


def test_validate_image_reports_decodability(tmp_path: Path, make_images: MakeImages) -> None:
    """The helper is usable on its own and never raises."""
    good = make_images(tmp_path, count=1)[0]
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")

    loader = ImageLoader(tmp_path, validate=False)

    assert loader.validate_image(good)
    assert not loader.validate_image(broken)


def test_load_preview_downscales_the_longest_edge(tmp_path: Path, make_images: MakeImages) -> None:
    """A large photo is shrunk for display, keeping its aspect ratio."""
    path = make_images(tmp_path, count=1, size=(400, 300))[0]

    image, original_size = ImageLoader(tmp_path).load_preview(path, max_edge=100)

    assert original_size == (400, 300)
    assert image.size == (100, 75)
    assert image.mode == "RGB"


def test_load_preview_applies_exif_orientation(tmp_path: Path, make_images: MakeImages) -> None:
    """A rotated JPEG is returned upright with the corrected original size."""
    path = make_images(tmp_path, count=1, size=(64, 48), exif_orientation=6)[0]

    image, original_size = ImageLoader(tmp_path).load_preview(path)

    assert original_size == (48, 64)
    assert image.size == (48, 64)


def test_load_preview_keeps_transparency(tmp_path: Path) -> None:
    """PNGs with an alpha channel stay RGBA instead of turning black."""
    path = tmp_path / "logo.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 0)).save(path)

    image, _ = ImageLoader(tmp_path).load_preview(path)

    assert image.mode == "RGBA"


def test_load_preview_rejects_non_positive_edge(tmp_path: Path, make_images: MakeImages) -> None:
    """A zero or negative limit is a programming error."""
    path = make_images(tmp_path, count=1)[0]

    with pytest.raises(ValueError, match="max_edge"):
        ImageLoader(tmp_path).load_preview(path, max_edge=0)


def test_load_preview_reports_undecodable_files(tmp_path: Path) -> None:
    """Decode failures are wrapped in a loader error."""
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"\xff\xd8\xff\xe0 truncated")

    with pytest.raises(ImageLoaderError, match="could not decode"):
        ImageLoader(tmp_path, validate=False).load_preview(broken)


def test_next_candidates_looks_ahead(tmp_path: Path, make_images: MakeImages) -> None:
    """The UI can prefetch the next one or two images."""
    for number in (1, 2, 3, 4):
        make_images(tmp_path, count=1, start=number)
    loader = ImageLoader(tmp_path)

    assert [path.name for path in loader.next_candidates(0)] == ["IMG_2.jpg", "IMG_3.jpg"]
    assert [path.name for path in loader.next_candidates(3)] == []
    assert loader.next_candidates(0, lookahead=0) == []


def test_animated_gif_previews_only_the_first_frame(tmp_path: Path) -> None:
    """An animated GIF is shown as a still of its first frame."""
    first = Image.new("RGB", (40, 30), (220, 20, 20))
    second = Image.new("RGB", (40, 30), (20, 20, 220))
    path = tmp_path / "animation.gif"
    first.save(path, "GIF", save_all=True, append_images=[second], duration=100, loop=0)

    image, size = ImageLoader(tmp_path).load_preview(path)

    assert size == (40, 30)
    assert image.size == (40, 30)
    assert getattr(image, "n_frames", 1) == 1
    red, _green, blue = image.getpixel((0, 0))[:3]
    assert red > 150 and blue < 100


def test_large_image_is_downscaled_for_display(tmp_path: Path, make_images: MakeImages) -> None:
    """A huge photo keeps its original size in the report but not in memory."""
    path = make_images(tmp_path, count=1, size=(4000, 3000))[0]

    image, size = ImageLoader(tmp_path).load_preview(path)

    assert size == (4000, 3000)
    assert image.size == (1600, 1200)


def test_repr_names_the_folder(tmp_path: Path) -> None:
    """The repr is stable enough for logs and debugging."""
    loader = ImageLoader(tmp_path)

    assert "ImageLoader(source_folder=" in repr(loader)
    assert str(tmp_path) in repr(loader)


def test_subfolders_lists_children_sorted_naturally(
    tmp_path: Path, make_images: MakeImages
) -> None:
    """A folder whose photos live one level down can name those folders."""
    for name in ("holiday_10", "holiday_2", "empty"):
        (tmp_path / name).mkdir()
        if name != "empty":
            make_images(tmp_path / name, count=1)

    found = subfolders(tmp_path, require_images=True)

    assert [path.name for path in found] == ["holiday_2", "holiday_10"]
    assert [path.name for path in subfolders(tmp_path)] == ["empty", "holiday_2", "holiday_10"]


def test_subfolders_ignores_hidden_and_category_folders(
    tmp_path: Path, make_images: MakeImages
) -> None:
    """Sort destinations and dot-folders are never suggested as a next step."""
    for name in (".cache", "Good", "bad", "Album"):
        (tmp_path / name).mkdir()
        make_images(tmp_path / name, count=1)

    assert [path.name for path in subfolders(tmp_path)] == ["Album"]


def test_subfolders_honours_the_limit(tmp_path: Path) -> None:
    """The hint stays short even in a folder full of subfolders."""
    for number in range(5):
        (tmp_path / f"set_{number}").mkdir()

    assert len(subfolders(tmp_path, limit=2)) == 2
    assert len(subfolders(tmp_path, limit=0)) == 5


def test_subfolders_tolerates_a_missing_folder(tmp_path: Path) -> None:
    """The hint is best-effort: no folder, no suggestions, no exception."""
    assert subfolders(tmp_path / "ghost") == []


def test_subfolders_accepts_custom_extensions(tmp_path: Path, make_images: MakeImages) -> None:
    """The extension filter matches the loader's own rules."""
    (tmp_path / "jpgs").mkdir()
    (tmp_path / "texts").mkdir()
    make_images(tmp_path / "jpgs", count=1)
    (tmp_path / "texts" / "notes.txt").write_text("hello", encoding="utf-8")

    assert [path.name for path in subfolders(tmp_path, require_images=True)] == ["jpgs"]
    assert subfolders(tmp_path, require_images=True, extensions=["txt"]) == [tmp_path / "texts"]
