"""Generated brand assets: the window icon and the welcome-screen logo.

Responsibility
    Produce the application's visual identity at runtime instead of shipping
    binary files: one rounded tile with a stack of photo cards and two chevrons
    pointing at the ``Bad`` and ``Good`` directions. ``app.py`` uses
    :func:`app_icon` for the window/task-bar icon and :class:`WelcomeScreen`
    uses :func:`logo_pixmap` for its large logo, so both always agree.

Public API
    APP_DISPLAY_NAME: str       human-readable product name
    TAGLINE: str                one-line explanation under the logo
    ICON_NAME: str              installed icon stem, shared with the .desktop file
    ICON_SIZES: tuple[int,...]  pixel sizes baked into the QIcon
    SVG_SIZE: int               view-box edge of the exported scalable icon
    logo_pixmap(size=128) -> QPixmap
    app_icon() -> QIcon
    export_icons(directory) -> list[Path]
        Write the mark as a freedesktop ``hicolor`` tree for desktop installs.

Behaviour
    * Drawing is pure ``QPainter`` on a transparent pixmap: no image files, no
      fonts from disk, so the look is identical on every machine and the test
      suite can assert that the pixmap is simply not null.
    * Chevron colours are taken from :data:`image_swiper.ui.swipe_card.CATEGORY_COLORS`
      so the logo, the drag badge and the footer buttons share one palette.
    * Sizes below 24 px drop the cards and keep only the chevrons, which is what
      stays legible in a window title bar.
    * :func:`export_icons` is the only thing that writes files, and only when a
      packager asks for it (``packaging/render_icons.py``); the app itself never
      touches the disk for branding.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtSvg import QSvgGenerator

from .swipe_card import CATEGORY_COLORS

APP_DISPLAY_NAME = "ImageSwiper"
"""Product name used in window titles, the About box and the icon tooltip."""

TAGLINE = "Sort a folder of photos with a swipe."
"""One-line description shown under the welcome-screen title."""

ICON_NAME = "image-swiper"
"""Stem of the exported icon files; matches the desktop entry's ``Icon=`` key."""

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)
"""Pixel sizes baked into the application icon, smallest first."""

SVG_SIZE = 512
"""Edge length of the exported scalable icon's view box, in user units."""

_TILE_START = "#1f4e79"
"""Gradient start of the brand tile (deep blue)."""

_TILE_END = "#7b3f9d"
"""Gradient end of the brand tile (violet)."""


def logo_pixmap(size: int = 128) -> QPixmap:
    """Return the brand mark rendered at *size* x *size* pixels.

    Args:
        size: Edge length in device pixels; must be positive.

    Returns:
        A transparent pixmap with the rounded tile, the card stack and the two
        swipe chevrons painted on it.

    Raises:
        ValueError: *size* is zero or negative.
    """
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        _paint_logo(painter, float(size))
    finally:
        painter.end()
    return pixmap


def app_icon() -> QIcon:
    """Return the multi-resolution application icon.

    Every size in :data:`ICON_SIZES` is rendered separately, which keeps small
    title-bar icons crisp instead of letting Qt downscale one large pixmap.
    """
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(logo_pixmap(size))
    return icon


def export_icons(directory: Path | str, *, sizes: Sequence[int] = ICON_SIZES) -> list[Path]:
    """Write the brand mark as a freedesktop icon theme tree.

    Desktop integration needs real files: the ``Icon=`` key of
    ``packaging/image-swiper.desktop`` is resolved through the icon theme, not
    through Qt. The files land exactly where every theme and cache tool expects
    them::

        <directory>/hicolor/scalable/apps/image-swiper.svg
        <directory>/hicolor/<N>x<N>/apps/image-swiper.png

    Args:
        directory: Root that receives the ``hicolor`` tree, usually
            ``packaging/icons``.
        sizes: Pixel sizes to render; defaults to :data:`ICON_SIZES`.

    Returns:
        The written paths: the scalable icon first, then one PNG per size from
        small to large.

    Raises:
        ValueError: *sizes* is empty or contains a non-positive value.
        RuntimeError: Qt could not encode one of the files.

    The PNGs come from :func:`logo_pixmap` and the SVG replays the same painter
    code into a :class:`QSvgGenerator`, so the raster and vector versions cannot
    drift apart. Both paths need a live ``QGuiApplication`` (``QPixmap`` has no
    backing store without one), which is why this is a packaging-time helper
    rather than something the app calls while starting up.
    """
    if not sizes:
        raise ValueError("sizes must not be empty")
    if any(size <= 0 for size in sizes):
        raise ValueError(f"sizes must be positive, got {list(sizes)}")

    root = Path(directory)
    written: list[Path] = []

    scalable = root / "hicolor" / "scalable" / "apps" / f"{ICON_NAME}.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    _write_svg(scalable)
    written.append(scalable)

    for size in sizes:
        target = root / "hicolor" / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not logo_pixmap(size).save(str(target), "PNG"):
            raise RuntimeError(f"could not write {target}")
        written.append(target)

    return written


def _write_svg(path: Path) -> None:
    """Render the brand mark into *path* as a scalable SVG document."""
    generator = QSvgGenerator()
    generator.setFileName(str(path))
    generator.setSize(QSize(SVG_SIZE, SVG_SIZE))
    generator.setViewBox(QRect(0, 0, SVG_SIZE, SVG_SIZE))
    generator.setTitle(APP_DISPLAY_NAME)
    generator.setDescription(TAGLINE)
    painter = QPainter(generator)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        _paint_logo(painter, float(SVG_SIZE))
    finally:
        painter.end()


def _paint_logo(painter: QPainter, size: float) -> None:
    """Paint the tile, the card stack and the chevrons for a *size* square."""
    radius = size * 0.24
    painter.setPen(Qt.PenStyle.NoPen)
    gradient = QLinearGradient(0.0, 0.0, size, size)
    gradient.setColorAt(0.0, QColor(_TILE_START))
    gradient.setColorAt(1.0, QColor(_TILE_END))
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0.0, 0.0, size, size), radius, radius)

    if size >= 24:
        _paint_card_stack(painter, size)
    _paint_chevrons(painter, size)


def _paint_card_stack(painter: QPainter, size: float) -> None:
    """Draw two translucent cards behind one solid card in the middle."""
    painter.setPen(Qt.PenStyle.NoPen)
    if size >= 24:
        painter.setBrush(QColor(255, 255, 255, 55))
        for tilt in (-7.0, 7.0):
            painter.save()
            painter.translate(size * 0.5, size * 0.5)
            painter.rotate(tilt)
            painter.drawRoundedRect(
                QRectF(-size * 0.28, -size * 0.32, size * 0.56, size * 0.62),
                size * 0.06,
                size * 0.06,
            )
            painter.restore()

    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawRoundedRect(
        QRectF(size * 0.24, size * 0.20, size * 0.52, size * 0.60),
        size * 0.06,
        size * 0.06,
    )


def _paint_chevrons(painter: QPainter, size: float) -> None:
    """Draw the ``Bad``/``Good`` chevrons on top of the front card."""
    width = max(1.5, size * 0.075)
    centre_y = size * 0.5
    for colour, direction in ((CATEGORY_COLORS["Bad"], -1.0), (CATEGORY_COLORS["Good"], 1.0)):
        tip_x = size * (0.5 + direction * 0.17)
        tail_x = tip_x - direction * size * 0.09
        pen = QPen(QColor(colour), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(tail_x, centre_y - size * 0.10),
                    QPointF(tip_x, centre_y),
                    QPointF(tail_x, centre_y + size * 0.10),
                ]
            )
        )
