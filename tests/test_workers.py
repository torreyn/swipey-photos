"""Tests for the background preview prefetcher (``ui/workers.py``).

Coverage
    * a prefetched preview can be taken as ``(QImage, original_size)`` and is
      removed from the cache when it is used;
    * ``lookahead`` bounds how much work one call starts, so swiping quickly
      cannot queue a backlog;
    * the cache is bounded and evicts the oldest entry;
    * ``clear`` drops cached work and ``shutdown`` releases the pool;
    * a corrupt file is reported through the ``failed`` signal instead of an
      exception escaping a worker thread;
    * a cancelled worker decodes nothing and emits nothing.

The prefetcher owns a private ``QThreadPool``, so every test waits on an
observable condition (``qtbot.waitUntil``) and shuts the prefetcher down.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from image_swiper.core.image_loader import ImageLoader
from image_swiper.ui.workers import (
    DEFAULT_LOOKAHEAD,
    PreviewPrefetcher,
    PreviewSignals,
    PreviewWorker,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


@pytest.fixture
def images(tmp_path: Path, make_images: object) -> list[Path]:
    """Return four small valid images inside ``tmp_path``."""
    factory = make_images
    assert callable(factory)
    return factory(tmp_path, count=4, size=(80, 60))


@pytest.fixture
def prefetcher(tmp_path: Path, images: list[Path]) -> PreviewPrefetcher:
    """Return a prefetcher over the images that is shut down afterwards."""
    del images
    instance = PreviewPrefetcher(ImageLoader(tmp_path, validate=False))
    yield instance
    instance.shutdown()


def test_prefetch_then_take_returns_the_decoded_preview(
    qtbot: QtBot, prefetcher: PreviewPrefetcher, images: list[Path]
) -> None:
    """A cached preview arrives as a QImage plus the orientation-corrected size."""
    prefetcher.prefetch(images)

    qtbot.waitUntil(lambda: len(prefetcher.cached_paths()) == DEFAULT_LOOKAHEAD, timeout=5000)
    preview = prefetcher.take(images[0])

    assert preview is not None
    image, size = preview
    assert (image.width(), image.height()) == (80, 60)
    assert size == (80, 60)
    assert prefetcher.take(images[0]) is None


def test_take_returns_none_before_the_worker_finishes(
    prefetcher: PreviewPrefetcher, images: list[Path]
) -> None:
    """A cache miss is a normal answer, not an error."""
    assert prefetcher.take(images[0]) is None


def test_lookahead_bounds_the_number_of_jobs(
    qtbot: QtBot, tmp_path: Path, images: list[Path]
) -> None:
    """One call starts at most ``lookahead`` decodes, however many paths it gets."""
    prefetcher = PreviewPrefetcher(
        ImageLoader(tmp_path, validate=False), lookahead=2, cache_size=10
    )
    try:
        prefetcher.prefetch(images)
        qtbot.waitUntil(lambda: len(prefetcher.cached_paths()) == 2, timeout=5000)
        qtbot.wait(100)

        assert len(prefetcher.cached_paths()) == 2
    finally:
        prefetcher.shutdown()


def test_prefetching_twice_does_not_duplicate_work(
    qtbot: QtBot, prefetcher: PreviewPrefetcher, images: list[Path]
) -> None:
    """Paths that are cached or in flight are skipped on the next call."""
    prefetcher.prefetch(images)
    qtbot.waitUntil(lambda: bool(prefetcher.cached_paths()), timeout=5000)

    prefetcher.prefetch(images)
    qtbot.wait(100)

    cached = prefetcher.cached_paths()
    assert len(cached) == len(set(cached))


def test_cache_evicts_the_oldest_entry(qtbot: QtBot, tmp_path: Path, images: list[Path]) -> None:
    """A small cache keeps the newest preview and forgets the oldest."""
    prefetcher = PreviewPrefetcher(ImageLoader(tmp_path, validate=False), lookahead=1, cache_size=1)
    try:
        prefetcher.prefetch([images[0]])
        qtbot.waitUntil(lambda: len(prefetcher.cached_paths()) == 1, timeout=5000)

        prefetcher.prefetch([images[1]])
        qtbot.waitUntil(lambda: prefetcher.cached_paths() == (str(images[1]),), timeout=5000)

        assert prefetcher.cached_paths() == (str(images[1]),)
    finally:
        prefetcher.shutdown()


def test_clear_drops_the_cache(
    qtbot: QtBot, prefetcher: PreviewPrefetcher, images: list[Path]
) -> None:
    """``clear`` empties the cache and keeps the prefetcher usable."""
    prefetcher.prefetch(images)
    qtbot.waitUntil(lambda: bool(prefetcher.cached_paths()), timeout=5000)

    prefetcher.clear()

    assert prefetcher.cached_paths() == ()
    assert prefetcher.take(images[0]) is None


def test_failed_decode_is_reported(qtbot: QtBot, tmp_path: Path, make_images: object) -> None:
    """A corrupt file emits ``failed`` and is not cached."""
    factory = make_images
    assert callable(factory)
    broken = factory(tmp_path, count=1, corrupt=True)[0]
    prefetcher = PreviewPrefetcher(ImageLoader(tmp_path, validate=False))
    try:
        with qtbot.waitSignal(prefetcher.failed, timeout=5000) as blocker:
            prefetcher.prefetch([broken])

        assert blocker.args[0] == str(broken)
        assert prefetcher.cached_paths() == ()
    finally:
        prefetcher.shutdown()


def test_worker_never_lets_an_exception_escape(tmp_path: Path, make_images: object) -> None:
    """``run()`` turns a decode error into the ``failed`` signal."""
    factory = make_images
    assert callable(factory)
    broken = factory(tmp_path, count=1, corrupt=True)[0]
    signals = PreviewSignals()
    failures: list[tuple[str, str]] = []
    signals.failed.connect(lambda path, message: failures.append((path, message)))

    PreviewWorker(
        ImageLoader(tmp_path, validate=False),
        broken,
        signals=signals,
        cancelled=threading.Event(),
    ).run()

    assert [path for path, _message in failures] == [str(broken)]


def test_cancelled_worker_does_nothing(tmp_path: Path, make_images: object) -> None:
    """A cancelled worker neither decodes nor reports."""
    factory = make_images
    assert callable(factory)
    path = factory(tmp_path, count=1)[0]
    signals = PreviewSignals()
    decoded: list[str] = []
    failures: list[str] = []
    signals.ready.connect(lambda name, _image, _size: decoded.append(name))
    signals.failed.connect(lambda name, _message: failures.append(name))
    cancelled = threading.Event()
    cancelled.set()

    PreviewWorker(
        ImageLoader(tmp_path, validate=False),
        path,
        signals=signals,
        cancelled=cancelled,
    ).run()

    assert decoded == []
    assert failures == []
