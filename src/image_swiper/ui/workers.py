"""Background worker adapters between Qt and the synchronous core layer.

Responsibility
    Keep the GUI thread responsive. Core functions are deliberately synchronous
    and Qt-free; this module wraps them in ``QRunnable`` objects that run on a
    bounded ``QThreadPool`` and report results through a small signals object
    that lives on the GUI thread.

    Today it implements *prefetching*: while the user looks at one photo,
    :class:`PreviewPrefetcher` decodes the next few with Pillow so the following
    swipe shows instantly instead of paying the decode cost on the GUI thread.

Public API
    DEFAULT_LOOKAHEAD, PREVIEW_CACHE_SIZE, POOL_SIZE   tuning constants
    PreviewSignals(ready, failed)                     queued worker -> GUI signals
    PreviewWorker(loader, path, *, signals, cancelled, max_edge)
        ``QRunnable`` decoding one preview off the GUI thread.
    PreviewPrefetcher(loader, *, lookahead=3, max_edge=..., cache_size=6, pool=None)
        prefetch(paths), take(path), is_pending(path), cached_paths(), clear(),
        shutdown(), signals ``ready(str)`` and ``failed(str, str)``.

Threading contract
    * Workers receive only plain data (``Path``, ints) plus a reference to the
      thread-safe :class:`~image_swiper.core.image_loader.ImageLoader`; they
      never touch a widget.
    * Results travel as signals, which Qt queues onto the GUI thread. The worker
      converts pixels to ``QImage`` (thread-safe); ``QPixmap`` conversion
      happens in the receiver, never in the worker.
    * ``run()`` never lets an exception escape: decode errors are logged and
      reported through ``failed``, and an unexpected error is logged with its
      traceback before being reported the same way.
    * Cancellation is cooperative through a shared :class:`threading.Event`, so
      ``clear()`` and window shutdown cannot leave a worker writing into a dead
      cache. Results that arrive after a cancel are dropped.
    * The pool is bounded (two threads by default) so prefetching cannot starve
      the rest of the machine, and it belongs to the prefetcher, so closing a
      window waits only for its own jobs.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage

from ..core.image_loader import DEFAULT_PREVIEW_EDGE, ImageLoader, ImageLoaderError
from ..utils.logging_setup import get_logger
from .image_utils import qimage_from_pil

LOGGER = get_logger(__name__)

DEFAULT_LOOKAHEAD = 3
"""How many upcoming previews to decode ahead of the current image."""

PREVIEW_CACHE_SIZE = 6
"""How many decoded previews stay in memory before the oldest is dropped."""

POOL_SIZE = 2
"""Worker threads used for prefetching; decoding is I/O- plus CPU-bound."""


class PreviewSignals(QObject):
    """Signals emitted by :class:`PreviewWorker` and owned by the prefetcher.

    A worker is a ``QRunnable`` and therefore not a ``QObject``, so it cannot
    define signals itself. Keeping them in one long-lived object also means the
    pool never has to marshal per-job objects back to the GUI thread.
    """

    ready = pyqtSignal(str, object, object, arguments=["path", "image", "size"])
    """``(path, QImage, (width, height))`` for a decoded preview."""

    failed = pyqtSignal(str, str, arguments=["path", "message"])
    """``(path, message)`` when a preview could not be decoded."""


class PreviewWorker(QRunnable):
    """Decode one image for display, off the GUI thread.

    Args:
        loader: The session loader; it is stateless while decoding, so several
            workers may share one instance.
        path: Image to decode.
        signals: Long-lived signals object to report through.
        cancelled: Set when the result has become useless.
        max_edge: Longest edge of the decoded preview, in pixels.
    """

    def __init__(
        self,
        loader: ImageLoader,
        path: Path,
        *,
        signals: PreviewSignals,
        cancelled: threading.Event,
        max_edge: int = DEFAULT_PREVIEW_EDGE,
    ) -> None:
        super().__init__()
        self._loader = loader
        self._path = Path(path)
        self._signals = signals
        self._cancelled = cancelled
        self._max_edge = max_edge
        self.setAutoDelete(True)

    def run(self) -> None:
        """Decode the preview and emit exactly one of ``ready``/``failed``."""
        if self._cancelled.is_set():
            return
        try:
            image, size = self._loader.load_preview(self._path, max_edge=self._max_edge)
        except ImageLoaderError as exc:
            LOGGER.warning("prefetch failed for %s: %s", self._path, exc)
            self._emit_failure(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive, Pillow is quirky
            LOGGER.exception("unexpected error while prefetching %s", self._path)
            self._emit_failure(str(exc) or "decode failed")
            return
        if self._cancelled.is_set():
            return
        try:
            self._signals.ready.emit(str(self._path), qimage_from_pil(image), size)
        except RuntimeError:  # pragma: no cover - prefetcher already deleted
            LOGGER.debug("dropped prefetch result for %s: prefetcher is gone", self._path)

    def _emit_failure(self, message: str) -> None:
        """Report a decode failure, tolerating a prefetcher that shut down."""
        try:
            self._signals.failed.emit(str(self._path), message)
        except RuntimeError:  # pragma: no cover - prefetcher already deleted
            LOGGER.debug("dropped prefetch failure for %s: prefetcher is gone", self._path)


class PreviewPrefetcher(QObject):
    """Decode the next few previews in the background and hand them back.

    The window asks for a preview with :meth:`take`; a cache hit costs nothing,
    a miss means the caller decodes synchronously as before. After showing an
    image the window calls :meth:`prefetch` with the upcoming paths, so the next
    decision usually finds its preview already decoded.

    Signals:
        ready: Emitted with a path once its preview is cached. The window does
            not have to listen; it is there for tests and for a future
            "show as soon as it is ready" behaviour.
        failed: Emitted with ``(path, message)`` when a worker cannot decode a
            file. The window keeps reporting through its normal synchronous path.

    Args:
        loader: Loader of the active session.
        lookahead: Maximum number of images prefetched per call.
        max_edge: Longest edge of a decoded preview, in pixels.
        cache_size: Number of decoded previews kept in memory.
        pool: Optional thread pool; defaults to a private two-thread pool.
        parent: Optional Qt parent.
    """

    ready = pyqtSignal(str, arguments=["path"])
    failed = pyqtSignal(str, str, arguments=["path", "message"])

    def __init__(
        self,
        loader: ImageLoader,
        *,
        lookahead: int = DEFAULT_LOOKAHEAD,
        max_edge: int = DEFAULT_PREVIEW_EDGE,
        cache_size: int = PREVIEW_CACHE_SIZE,
        pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self._loader = loader
        self._lookahead = max(0, lookahead)
        self._max_edge = max_edge
        self._cache_size = max(1, cache_size)
        self._pool = pool if pool is not None else QThreadPool(self)
        if pool is None:
            self._pool.setMaxThreadCount(POOL_SIZE)
        self._signals = PreviewSignals(self)  # type: ignore[arg-type]  # parent typed as Self
        self._signals.ready.connect(self._on_ready)
        self._signals.failed.connect(self._on_failed)
        self._cache: OrderedDict[str, tuple[QImage, tuple[int, int]]] = OrderedDict()
        self._pending: set[str] = set()
        self._cancelled = threading.Event()

    @property
    def lookahead(self) -> int:
        """Maximum number of previews started by a single :meth:`prefetch`."""
        return self._lookahead

    def prefetch(self, paths: Iterable[str | Path]) -> None:
        """Start decoding upcoming *paths* in the background.

        Only the first ``lookahead`` new paths are started: images already
        cached or already in flight are skipped, so calling this after every
        swipe never builds up a backlog.

        Args:
            paths: Upcoming image paths, nearest first.
        """
        if self._lookahead == 0:
            return
        started = 0
        for raw in paths:
            if started >= self._lookahead:
                break
            key = str(Path(raw))
            if key in self._cache:
                self._cache.move_to_end(key)
                continue
            if key in self._pending:
                continue
            self._pending.add(key)
            self._pool.start(
                PreviewWorker(
                    self._loader,
                    Path(raw),
                    signals=self._signals,
                    cancelled=self._cancelled,
                    max_edge=self._max_edge,
                )
            )
            started += 1
        if started:
            LOGGER.debug("prefetching %d preview(s)", started)

    def take(self, path: str | Path) -> tuple[QImage, tuple[int, int]] | None:
        """Return the cached preview for *path*, removing it from the cache.

        Returns:
            ``(image, original_size)`` exactly as
            :meth:`~image_swiper.core.image_loader.ImageLoader.load_preview`
            would, or ``None`` when the preview is not ready yet.
        """
        key = str(Path(path))
        cached = self._cache.get(key)
        if cached is None:
            return None
        del self._cache[key]
        return cached

    def is_pending(self, path: str | Path) -> bool:
        """Return ``True`` while a worker is decoding *path*."""
        return str(Path(path)) in self._pending

    def cached_paths(self) -> tuple[str, ...]:
        """Return the paths currently cached, oldest first."""
        return tuple(self._cache)

    def clear(self) -> None:
        """Drop the cache and abandon queued work, keeping the prefetcher usable."""
        self._cancelled.set()
        self._pool.clear()
        self._cache.clear()
        self._pending.clear()
        self._cancelled = threading.Event()
        LOGGER.debug("prefetch cache cleared")

    def shutdown(self, timeout_ms: int = 1000) -> None:
        """Cancel outstanding work and wait briefly for running workers.

        Args:
            timeout_ms: How long to wait for a decode that is already running;
                the call never blocks longer than this.
        """
        self._cancelled.set()
        self._pool.clear()
        self._cache.clear()
        self._pending.clear()
        if self._pool.waitForDone(timeout_ms):
            LOGGER.debug("prefetch pool stopped")
        else:
            LOGGER.debug("prefetch worker still running after %d ms", timeout_ms)

    # ------------------------------------------------------------------
    # Worker callbacks, always delivered on the GUI thread
    # ------------------------------------------------------------------

    def _on_ready(self, path: str, image: object, size: object) -> None:
        """Cache a decoded preview, dropping results that arrived too late."""
        self._pending.discard(path)
        if self._cancelled.is_set():
            return
        if not isinstance(image, QImage) or not isinstance(size, tuple):  # pragma: no cover
            LOGGER.warning("ignoring malformed prefetch result for %s", path)
            return
        self._cache[path] = (image, cast("tuple[int, int]", size))
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        self.ready.emit(path)

    def _on_failed(self, path: str, message: str) -> None:
        """Forget a failed request; the synchronous path will report it."""
        self._pending.discard(path)
        LOGGER.debug("prefetch of %s failed: %s", path, message)
        self.failed.emit(path, message)
