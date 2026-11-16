"""Qt-side conversions for the previews the core layer decodes.

Responsibility
    The only place that turns a Pillow image into a ``QImage`` or ``QPixmap``.
    ``core`` must stay Qt-free and widgets must never touch the filesystem, so
    this module is the narrow bridge between the two: it copies the decoded
    pixels into a detached ``QImage`` (RGB888 or RGBA8888) which the GUI thread
    then wraps in a ``QPixmap``.

Public API
    qimage_from_pil(image) -> QImage
    pixmap_from_pil(image) -> QPixmap

Threading
    ``qimage_from_pil`` is safe to call from a worker thread: ``QImage`` is a
    value type and is not tied to the GUI thread, which is exactly what
    :class:`~image_swiper.ui.workers.PreviewPrefetcher` relies on. ``QPixmap``
    is not, so ``pixmap_from_pil`` must run on the GUI thread.
"""

from __future__ import annotations

from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def qimage_from_pil(image: Image.Image) -> QImage:
    """Convert a Pillow image into a detached :class:`QImage`.

    Args:
        image: A decoded preview, in ``RGB`` or ``RGBA`` mode (other modes are
            converted, so callers cannot produce a mis-strided buffer).

    Returns:
        An RGB888 or RGBA8888 ``QImage`` that owns its pixels, so the temporary
        Pillow buffer can be garbage-collected immediately.
    """
    if image.mode == "RGBA":
        rgba = image.tobytes("raw", "RGBA")
        width = image.width
        buffer = QImage(rgba, width, image.height, 4 * width, QImage.Format.Format_RGBA8888)
        return buffer.copy()
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    width = rgb.width
    buffer = QImage(
        rgb.tobytes("raw", "RGB"),
        width,
        rgb.height,
        3 * width,
        QImage.Format.Format_RGB888,
    )
    return buffer.copy()


def pixmap_from_pil(image: Image.Image) -> QPixmap:
    """Return *image* as a :class:`QPixmap` ready for the card (GUI thread only)."""
    return QPixmap.fromImage(qimage_from_pil(image))
