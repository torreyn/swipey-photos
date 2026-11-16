"""Shared pytest fixtures for the ImageSwiper test suite.

Fixtures
    ``make_images``
        Factory that writes real images with Pillow:
        ``make_images(tmp_path, count=3, prefix="IMG_", start=1, fmt="JPEG",
        size=(64, 48))``. ``exif_orientation`` produces rotated files and
        ``corrupt=True`` truncated ones, so the suite needs no binary fixtures.
    ``sample_folder``
        ``tmp_path/photos`` containing three valid images.
    ``config``
        A :class:`~image_swiper.utils.config.Config` with test-friendly values.
    ``xdg_dirs``
        Overrides ``XDG_CONFIG_HOME``/``XDG_DATA_HOME``/``XDG_STATE_HOME``/
        ``XDG_CACHE_HOME`` so no test can touch the developer's real files.
    ``isolated_logging``
        Routes the ``image_swiper`` logger into ``tmp_path/logs`` and detaches
        the handlers again afterwards.

Conventions
    * Tests never touch the developer's real Pictures folder or real config:
      always ``tmp_path`` plus the ``xdg_dirs`` fixture.
    * Test files mirror the source tree: ``tests/test_sorter.py`` covers
      ``src/image_swiper/core/sorter.py``.
    * GUI tests use ``qtbot`` from pytest-qt and must be marked
      ``@pytest.mark.gui``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image

from image_swiper.utils.config import Config, WindowConfig
from image_swiper.utils.logging_setup import LOGGER_NAME, setup_logging

SUFFIXES: dict[str, str] = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "WEBP": ".webp",
}


@pytest.fixture
def make_images() -> Callable[..., list[Path]]:
    """Return a factory that writes valid or deliberately broken images."""

    def factory(
        directory: Path,
        *,
        count: int = 3,
        prefix: str = "IMG_",
        start: int = 1,
        fmt: str = "JPEG",
        size: tuple[int, int] = (64, 48),
        exif_orientation: int | None = None,
        corrupt: bool = False,
    ) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        suffix = SUFFIXES[fmt]
        created: list[Path] = []
        for offset in range(count):
            number = start + offset
            path = directory / f"{prefix}{number}{suffix}"
            if corrupt:
                path.write_bytes(b"\xff\xd8\xff\xe0 this is not a real jpeg")
            else:
                image = Image.new("RGB", size, (number * 37 % 256, 80, 160))
                if exif_orientation is None:
                    image.save(path, fmt)
                else:
                    exif = image.getexif()
                    exif[274] = exif_orientation
                    image.save(path, fmt, exif=exif)
            created.append(path)
        return created

    return factory


@pytest.fixture
def sample_folder(tmp_path: Path, make_images: Callable[..., list[Path]]) -> Path:
    """Return a folder holding three valid images, ready to be sorted."""
    folder = tmp_path / "photos"
    make_images(folder, count=3)
    return folder


@pytest.fixture
def config() -> Config:
    """Return a small, deterministic configuration for tests."""
    return Config(window=WindowConfig(width=640, height=480), theme="dark")


@pytest.fixture
def xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Point every XDG base directory at a temporary location."""
    mapping = {
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_STATE_HOME": tmp_path / "state",
        "XDG_CACHE_HOME": tmp_path / "cache",
    }
    for variable, value in mapping.items():
        monkeypatch.setenv(variable, str(value))
    return mapping


@pytest.fixture
def isolated_logging(tmp_path: Path) -> Iterator[Path]:
    """Write application logs into ``tmp_path`` and clean up afterwards."""
    log_file = setup_logging(level="DEBUG", log_dir=tmp_path / "logs", force=True)
    try:
        yield log_file
    finally:
        logger = logging.getLogger(LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(logging.WARNING)
