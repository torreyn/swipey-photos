"""The swipeable image card: one image, gesture physics, feedback and fly-out.

Responsibility
    Render a single image as a card (fitted, centred, rounded, subtly shadowed)
    and turn pointer or keyboard input into a discrete sorting *decision*.
    :class:`SwipeCard` owns four things and nothing else: the pixmap it shows,
    the drag and rotation state, the colour-coded feedback badge, and the
    fly-out animation that ends a gesture by emitting
    :attr:`SwipeCard.swiped`.

    It deliberately knows nothing about folders, files, the queue or the
    sorter. It never opens a file except through the
    :meth:`SwipeCard.set_image` convenience, never moves anything and never
    decides what ``"Good"`` means: the owner hands it a ``QPixmap`` and gets a
    category name back. That keeps it drop-in reusable and trivial to demo.

Gesture model
    press ─▶ DRAGGING ─release below threshold─▶ spring back to the rest pose
                  │
                  └─release past threshold─▶ FLY_OUT ─▶ ``swiped(category)``

    * Translation follows the pointer 1:1 using *global* coordinates, because
      the widget itself moves under the cursor while dragging; local deltas
      would feed the card's own movement back into the calculation.
    * Rotation is proportional to the horizontal travel and saturates at
      :data:`DEFAULT_MAX_ROTATION` degrees (15° by default).
    * A category is committed once the dominant axis passes its threshold:
      25 % of the card width horizontally, 20 % of the height vertically. The
      axes are compared after dividing by their own threshold, so the larger
      horizontal threshold does not make vertical flicks comparatively easier.
    * Releasing earlier animates the card home with an ``OutBack`` curve, which
      reads as a spring instead of a linear slide.

Feedback
    While dragging, a label is painted over the image: ``GOOD`` to the right
    (green), ``BAD`` to the left (red), ``GREAT`` upwards (gold) and ``OK``
    downwards (blue). Its opacity follows the drag progress, so the pending
    decision is visible before the user lets go.

Public API
    SwipeCard(parent=None, *, duration_ms=250, spring_back_ms=220,
              horizontal_threshold_ratio=0.25, vertical_threshold_ratio=0.20,
              max_rotation=15.0, margin=12, corner_radius=18)
        swiped: pyqtSignal(str)             # "Good" | "Bad" | "Great" | "OK"
        set_pixmap(pixmap, *, reset=True)   # show the next image
        set_image(path)                     # convenience for demos and tests
        clear_image()                       # back to the empty placeholder
        trigger_swipe(category)             # keyboard or programmatic commit
        reset(*, animated=False)            # reuse the card for the next image
        scaled_pixmap()                     # what is actually drawn
        direction_for_offset(offset), progress_for_offset(offset)
        pixmap, fade, rotation, drag_offset, progress, direction,
        is_animating, home_position, max_rotation, horizontal_threshold,
        vertical_threshold

Threading and lifetime
    Everything runs on the GUI thread. The animations are
    ``QPropertyAnimation`` instances inside a ``QParallelAnimationGroup``
    parented to the card, so they are destroyed with it and are safe to stop
    mid-flight. ``duration_ms=0`` and ``spring_back_ms=0`` make every
    transition instant, which is how the tests stay deterministic without
    sleeping.

Standalone demo (no session, no files, no other module)::

    python -m image_swiper.ui.swipe_card
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import QApplication, QWidget

GOOD = "Good"
BAD = "Bad"
GREAT = "Great"
OK = "OK"

CATEGORIES: tuple[str, ...] = (GOOD, BAD, GREAT, OK)
"""The four decisions a card can emit, in the sorter's canonical spelling."""

DEFAULT_DURATION_MS = 250
"""Fly-out duration; long enough to read as motion, short enough to feel snappy."""

DEFAULT_SPRING_BACK_MS = 220
"""Duration of the abort animation that returns an unfinished drag home."""

DEFAULT_HORIZONTAL_THRESHOLD_RATIO = 0.25
"""Fraction of the card width that commits a left/right swipe."""

DEFAULT_VERTICAL_THRESHOLD_RATIO = 0.20
"""Fraction of the card height that commits an up/down swipe."""

DEFAULT_MAX_ROTATION = 15.0
"""Maximum tilt in degrees, reached when the horizontal threshold is passed."""

DEFAULT_MARGIN = 12
"""Inset in pixels between the widget edge and the card, room for the shadow."""

DEFAULT_CORNER_RADIUS = 18
"""Corner radius of the card plate, in pixels."""

_EXIT_MARGIN = 24
"""Extra pixels the card travels past the window edge so it is fully gone."""

_CANONICAL: dict[str, str] = {name.casefold(): name for name in CATEGORIES}
_BADGE_TEXT: dict[str, str] = {GOOD: "GOOD", BAD: "BAD", GREAT: "GREAT", OK: "OK"}
CATEGORY_COLORS: dict[str, str] = {
    GOOD: "#3ddc84",
    BAD: "#ff5b5b",
    GREAT: "#f2c14e",
    OK: "#4aa3ff",
}
"""One colour per category, shared by the drag badge and the window's buttons."""
_BADGE_COLOR: dict[str, str] = CATEGORY_COLORS
_OFFSCREEN: dict[str, tuple[int, int]] = {
    GOOD: (1, 0),
    BAD: (-1, 0),
    GREAT: (0, -1),
    OK: (0, 1),
}

_FLY_OUT = "fly_out"
"""Transition marker: the card is leaving after a committed swipe."""

_SPRING_BACK = "spring_back"
"""Transition marker: the card is returning home after an aborted drag."""


def _normalize_category(value: str) -> str:
    """Return the canonical spelling of *value*, matched case-insensitively.

    Args:
        value: A category name such as ``"Good"``, ``"good"`` or ``" OK "``.

    Returns:
        The matching name from :data:`CATEGORIES`.

    Raises:
        ValueError: If *value* is not one of the four known categories.
    """
    if isinstance(value, str):
        canonical = _CANONICAL.get(value.strip().casefold())
        if canonical is not None:
            return canonical
    raise ValueError(f"unknown swipe category {value!r}; expected one of {CATEGORIES}")


def _badge_color(category: str, alpha: int) -> QColor:
    """Return the feedback colour for *category*, with *alpha* from 0 to 255."""
    color = QColor(_BADGE_COLOR[category])
    color.setAlpha(max(0, min(255, alpha)))
    return color


class SwipeCard(QWidget):
    """One image, dragged away to commit a sorting decision.

    The card paints a rounded plate with a subtle drop shadow, fits the image
    inside it without distorting the aspect ratio, and follows the pointer while
    the user drags. Letting go past a threshold flies the card out of the window
    and emits :attr:`swiped` with ``"Good"``, ``"Bad"``, ``"Great"`` or
    ``"OK"``; letting go earlier springs it back and emits nothing.

    The widget is input-complete: it handles the mouse gesture, the arrow and
    WASD keys, and exposes :meth:`trigger_swipe` so a window-level action or a
    test can commit a decision without synthesising input.

    Signals:
        swiped: Emitted with the canonical category name once the fly-out
            animation has finished. A release that never crosses a threshold
            emits nothing, and a swipe requested while one is already in flight
            is ignored, so each image yields at most one decision.

    Example:
        >>> card = SwipeCard()
        >>> card.swiped.connect(print)          # doctest: +SKIP
        >>> card.set_pixmap(QPixmap("photo.jpg"))   # doctest: +SKIP
        >>> card.trigger_swipe("Good")          # doctest: +SKIP

    Notes:
        The card moves itself, so give it a parent that assigns geometry (for
        example a stage widget's ``resizeEvent``) instead of a layout manager:
        a layout would fight the drag by re-positioning the widget.

    Attributes:
        swiped: ``pyqtSignal(str)`` carrying the committed category.
    """

    swiped = pyqtSignal(str, arguments=["category"])

    # Arrow keys and WASD both commit a swipe, matching the README key map.
    _KEY_CATEGORIES: ClassVar[dict[int, str]] = {
        int(Qt.Key.Key_Right): GOOD,
        int(Qt.Key.Key_D): GOOD,
        int(Qt.Key.Key_Left): BAD,
        int(Qt.Key.Key_A): BAD,
        int(Qt.Key.Key_Up): GREAT,
        int(Qt.Key.Key_W): GREAT,
        int(Qt.Key.Key_Down): OK,
        int(Qt.Key.Key_S): OK,
    }

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        duration_ms: int = DEFAULT_DURATION_MS,
        spring_back_ms: int = DEFAULT_SPRING_BACK_MS,
        horizontal_threshold_ratio: float = DEFAULT_HORIZONTAL_THRESHOLD_RATIO,
        vertical_threshold_ratio: float = DEFAULT_VERTICAL_THRESHOLD_RATIO,
        max_rotation: float = DEFAULT_MAX_ROTATION,
        margin: int = DEFAULT_MARGIN,
        corner_radius: int = DEFAULT_CORNER_RADIUS,
    ) -> None:
        """Create an empty card that is ready to accept a pixmap.

        Args:
            parent: Optional parent widget; see the class notes about geometry.
            duration_ms: Fly-out duration in milliseconds. ``0`` commits
                instantly, which is what the tests use.
            spring_back_ms: Duration of the abort animation. ``0`` snaps the
                card back without animating.
            horizontal_threshold_ratio: Share of the card width that commits a
                left/right swipe (default a quarter).
            vertical_threshold_ratio: Share of the card height that commits an
                up/down swipe (default a fifth).
            max_rotation: Tilt in degrees at the horizontal threshold; the
                rotation is clamped to ``±max_rotation``.
            margin: Inset between the widget edge and the card, leaving room
                for the shadow.
            corner_radius: Corner radius of the card plate in pixels.
        """
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)

        self._duration_ms = max(0, int(duration_ms))
        self._spring_back_ms = max(0, int(spring_back_ms))
        self._horizontal_threshold_ratio = max(0.0, float(horizontal_threshold_ratio))
        self._vertical_threshold_ratio = max(0.0, float(vertical_threshold_ratio))
        self._max_rotation = abs(float(max_rotation))
        self._margin = max(0, int(margin))
        self._corner_radius = max(0, int(corner_radius))

        self._pixmap: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._scaled_key: tuple[int, int, int] | None = None

        self._home_pos = QPoint()
        self._home_locked = False
        self._drag_origin = QPointF()
        self._drag_anchor = QPointF()
        self._drag_offset = QPointF()
        self._dragging = False

        self._rotation = 0.0
        self._fade = 1.0
        self._direction: str | None = None
        self._progress = 0.0

        self._group: QParallelAnimationGroup | None = None
        self._transition: str | None = None
        self._pending_category: str | None = None
        self._animating = False

    # ------------------------------------------------------------------
    # Qt properties: animation targets that painters and tests can read
    # ------------------------------------------------------------------

    def _get_fade(self) -> float:
        """Return the opacity applied to the whole card (1.0 = fully visible)."""
        return self._fade

    def _set_fade(self, value: float) -> None:
        """Set the card opacity; the fly-out animation drives this property."""
        self._fade = max(0.0, min(1.0, float(value)))
        self.update()

    fade = pyqtProperty(float, _get_fade, _set_fade)

    def _get_rotation(self) -> float:
        """Return the current tilt in degrees (positive tilts clockwise)."""
        return self._rotation

    def _set_rotation(self, value: float) -> None:
        """Set the tilt in degrees; the spring-back animation drives this too."""
        self._rotation = float(value)
        self.update()

    rotation = pyqtProperty(float, _get_rotation, _set_rotation)

    def _get_progress(self) -> float:
        """Return how far the current drag is towards committing, from 0 to 1.

        The value is measured against the threshold of the dominant axis, so it
        reaches 1.0 exactly when releasing would commit a swipe. It drives the
        overlay opacity and is animated back to 0 during a spring-back.
        """
        return self._progress

    def _set_progress(self, value: float) -> None:
        """Set the drag progress; the spring-back animation fades it back to 0."""
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    progress = pyqtProperty(float, _get_progress, _set_progress)

    # ------------------------------------------------------------------
    # Read-only state, useful for the owning window and for tests
    # ------------------------------------------------------------------

    @property
    def pixmap(self) -> QPixmap | None:
        """The source pixmap currently shown, or ``None`` when the card is empty."""
        return self._pixmap

    @property
    def drag_offset(self) -> QPointF:
        """Offset of the card from its resting position, in widget pixels."""
        return QPointF(self._drag_offset)

    @property
    def direction(self) -> str | None:
        """Category the current drag would commit, or ``None`` when centred."""
        return self._direction

    @property
    def is_animating(self) -> bool:
        """``True`` while a fly-out or spring-back animation is running."""
        return self._animating

    @property
    def home_position(self) -> QPoint:
        """The resting position the card springs back to."""
        return QPoint(self._home_pos)

    def lock_home(self) -> QPoint:
        """Freeze the resting position at the card's current position.

        A deck-level entrance animation (see
        :class:`~image_swiper.ui.animator.CardAnimator`) moves the card without
        dragging it. Without this lock, :meth:`moveEvent` would mistake the
        animated position for the new home and the card would settle off-centre.
        While the lock is held, moves never update :attr:`home_position`.

        Returns:
            The position that is now the home the card must return to.
        """
        if not self._home_locked:
            self._home_pos = self.pos()
            self._home_locked = True
        return QPoint(self._home_pos)

    def unlock_home(self) -> None:
        """Re-enable automatic home tracking after :meth:`lock_home`.

        The recorded home is kept; the next move the card makes while idle (a
        parent resize, for example) records a new one.
        """
        self._home_locked = False

    @property
    def max_rotation(self) -> float:
        """Tilt in degrees reached at the horizontal threshold."""
        return self._max_rotation

    @property
    def horizontal_threshold(self) -> float:
        """Horizontal travel in pixels that commits a left or right swipe."""
        return max(1.0, self.width() * self._horizontal_threshold_ratio)

    @property
    def vertical_threshold(self) -> float:
        """Vertical travel in pixels that commits an up or down swipe."""
        return max(1.0, self.height() * self._vertical_threshold_ratio)

    # ------------------------------------------------------------------
    # Public API: the image
    # ------------------------------------------------------------------

    def set_pixmap(self, pixmap: QPixmap | None, *, reset: bool = True) -> None:
        """Show *pixmap* and prepare the card for a fresh gesture.

        Args:
            pixmap: Image to display. ``None`` and null pixmaps show the
                "No image" placeholder instead of raising.
            reset: Move the card back to its resting position and clear the
                drag state (the default). Pass ``False`` only when the caller
                positions the card itself, for example during a fly-in.
        """
        self._pixmap = None if pixmap is None or pixmap.isNull() else QPixmap(pixmap)
        self._invalidate_scaled()
        if reset:
            self.reset()
        self.update()

    def set_image(self, path: str | Path) -> bool:
        """Load *path* and display it, returning ``False`` if it cannot be read.

        The card normally receives an already-decoded ``QPixmap`` from the
        loading layer, which is where EXIF orientation and decode failures are
        handled. This helper exists so the widget can be exercised on its own
        (demo, manual smoke test) without pulling in the rest of the app; it
        knows nothing about folders or categories.

        Args:
            path: Filesystem path to an image Qt can decode.

        Returns:
            ``True`` when the image was decoded and is now displayed.
        """
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self.set_pixmap(pixmap)
        return True

    def clear_image(self) -> None:
        """Forget the current image and paint the empty placeholder instead."""
        self._pixmap = None
        self._invalidate_scaled()
        self.update()

    def scaled_pixmap(self) -> QPixmap | None:
        """Return the image exactly as it is drawn: fitted, centred, colour kept.

        The scaled copy is cached per widget size and per source pixmap, so
        repeated paints and resize storms never re-scale a large photo. ``None``
        means there is nothing to draw (empty card, or a zero-sized area).

        The aspect ratio is preserved, so after scaling one dimension fills the
        available area and the other stays smaller.
        """
        if self._pixmap is None:
            return None
        area = self._image_area().size().toSize()
        if area.width() <= 0 or area.height() <= 0:
            return None
        key = (area.width(), area.height(), self._pixmap.cacheKey())
        if self._scaled is None or self._scaled_key != key:
            self._scaled = self._pixmap.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scaled_key = key
        return self._scaled

    # ------------------------------------------------------------------
    # Public API: gestures and decisions
    # ------------------------------------------------------------------

    def reset(self, *, animated: bool = False) -> None:
        """Put the card back in its rest pose so it can show the next image.

        Stops any running animation, clears the drag and overlay state, restores
        full opacity and zero rotation, and moves the card home. The current
        pixmap is kept; call :meth:`set_pixmap` to replace it.

        Args:
            animated: Return home with the spring animation instead of snapping
                there. Opacity is restored immediately either way, because the
                card is only transparent while it flies out.
        """
        self._stop_animations()
        self._clear_gesture_state()
        self._home_locked = False
        if animated and self._spring_back_ms > 0:
            self._start_spring_back()
            return
        self.move(self._home_pos)
        self.update()

    def trigger_swipe(self, category: str) -> None:
        """Commit a swipe for *category* without a pointer gesture.

        This is the entry point for keyboard shortcuts, toolbar actions and
        tests. The card flies out in the direction that belongs to the category,
        and :attr:`swiped` is emitted once that animation has finished, exactly
        as it is for a released drag.

        Args:
            category: ``"Good"``, ``"Bad"``, ``"Great"`` or ``"OK"``, matched
                case-insensitively.

        Raises:
            ValueError: If *category* is not one of :data:`CATEGORIES`.

        Notes:
            A call that arrives while another animation is already running is
            ignored, so key auto-repeat cannot commit two decisions for one
            image.
        """
        canonical = _normalize_category(category)
        if self._animating:
            return
        self._dragging = False
        self._drag_origin = QPointF()
        self._direction = canonical
        self._progress = 1.0
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._start_fly_out(canonical)

    def direction_for_offset(self, offset: QPointF) -> str | None:
        """Return the category that releasing at *offset* would commit.

        The two axes are compared after dividing by their own threshold, so the
        dominant axis wins even though the horizontal threshold is larger.

        Args:
            offset: Displacement from the resting position, in widget pixels.

        Returns:
            The category for the dominant axis, or ``None`` for a zero offset.
        """
        normalised_x = offset.x() / self.horizontal_threshold
        normalised_y = offset.y() / self.vertical_threshold
        if abs(normalised_x) < 1e-9 and abs(normalised_y) < 1e-9:
            return None
        if abs(normalised_x) >= abs(normalised_y):
            return GOOD if normalised_x > 0 else BAD
        return OK if normalised_y > 0 else GREAT

    def progress_for_offset(self, offset: QPointF) -> float:
        """Return how close *offset* is to the nearest threshold, from 0.0 to 1.0.

        Args:
            offset: Displacement from the resting position, in widget pixels.

        Returns:
            ``1.0`` once the dominant axis has travelled far enough to commit.
        """
        normalised_x = offset.x() / self.horizontal_threshold
        normalised_y = offset.y() / self.vertical_threshold
        return min(1.0, max(abs(normalised_x), abs(normalised_y)))

    def sizeHint(self) -> QSize:
        """Suggest a 3:2 preview area to any layout that asks for a size."""
        return QSize(640, 480)

    # ------------------------------------------------------------------
    # Input handling: the drag state machine
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Begin a drag and remember where the pointer started.

        Global coordinates are recorded because the card moves under the cursor:
        a local origin would move with the widget and double the delta after the
        first step. A card that is flying out, or that has already flown out,
        ignores presses; one that is springing back stops the animation and
        continues from wherever it is, keeping the original rest position as its
        return target.
        """
        if event is None or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._transition == _FLY_OUT or self._fade < 1.0:
            # A card that is already leaving (or has left) cannot be grabbed.
            # A spring-back *can* be caught: the drag resumes from where the
            # card was at that instant, which is what a user expects.
            event.ignore()
            return
        self._stop_animations()
        if self._drag_offset.isNull():
            # At rest: the parent may have repositioned us since the last
            # ``moveEvent`` was delivered, so trust the current position.
            self._home_pos = self.pos()
        self._drag_origin = event.globalPosition()
        self._drag_anchor = QPointF(self.pos() - self._home_pos)
        self._dragging = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Translate and tilt the card, and refresh the feedback overlay.

        The translation follows the pointer one-to-one from the press origin,
        plus whatever offset the card already had. The tilt is proportional to
        the horizontal travel and saturates at :attr:`max_rotation`, so the card
        leans into long drags without ever spinning.
        """
        if event is None or not self._dragging:
            super().mouseMoveEvent(event)
            return
        offset = self._drag_anchor + (event.globalPosition() - self._drag_origin)
        self._drag_offset = offset
        self.move(self._home_pos + offset.toPoint())
        self._rotation = self._rotation_for_offset(offset)
        self._direction = self.direction_for_offset(offset)
        self._progress = self.progress_for_offset(offset)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        """Commit the swipe when the threshold is crossed, else spring back."""
        if event is None or not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()
        category = self._direction
        if category is not None and self._progress >= 1.0:
            self.trigger_swipe(category)
            return
        self._start_spring_back()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Map the arrow keys and WASD to swipes and pass every other key on.

        ``→``/``D`` commit ``Good``, ``←``/``A`` commit ``Bad``, ``↑``/``W``
        commit ``Great`` and ``↓``/``S`` commit ``OK``. Unhandled keys reach the
        base implementation so window-level shortcuts keep working even while
        the card has focus.
        """
        if event is None:
            return
        category = self._KEY_CATEGORIES.get(int(event.key()))
        if category is None:
            super().keyPressEvent(event)
            return
        event.accept()
        self.trigger_swipe(category)

    def moveEvent(self, event: QMoveEvent | None) -> None:
        """Track the resting position whenever the card is idle.

        A parent repositions the card on resize and on first show; recording
        that position as home keeps the spring-back target and the fly-out
        origin correct. Moves the card performs itself (drag or animation) are
        ignored, otherwise "home" would follow the card off-screen — and so are
        moves made while a deck-level entrance animation holds the home lock.
        """
        if (
            not self._home_locked
            and not self._dragging
            and not self._animating
            and self._drag_offset.isNull()
        ):
            self._home_pos = self.pos()
        super().moveEvent(event)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Paint the plate, the image, the shadow and the feedback badge."""
        del event
        area = self._image_area()
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.setOpacity(self._fade)
        if area.width() <= 0.0 or area.height() <= 0.0:
            painter.end()
            return
        centre = area.center()
        painter.translate(centre)
        painter.rotate(self._rotation)
        painter.translate(-centre.x(), -centre.y())
        self._paint_shadow(painter, area)
        self._paint_plate(painter, area)
        self._paint_image(painter, area)
        self._paint_badge(painter, area)
        painter.end()

    # ------------------------------------------------------------------
    # Painting helpers
    # ------------------------------------------------------------------

    def _image_area(self) -> QRectF:
        """Return the card rectangle: the widget inset by the shadow margin."""
        margin = float(self._margin)
        return QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)

    def _invalidate_scaled(self) -> None:
        """Drop the cached scaled pixmap after the source image changed."""
        self._scaled = None
        self._scaled_key = None

    def _paint_shadow(self, painter: QPainter, rect: QRectF) -> None:
        """Draw a soft drop shadow as stacked translucent rounded rectangles."""
        painter.setPen(Qt.PenStyle.NoPen)
        radius = float(self._corner_radius)
        for offset, alpha in ((8.0, 8), (5.0, 12), (2.0, 18)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(rect.translated(0.0, offset), radius, radius)

    def _plate_path(self, rect: QRectF) -> QPainterPath:
        """Return the rounded rectangle shared by the plate and the image clip."""
        path = QPainterPath()
        radius = float(self._corner_radius)
        path.addRoundedRect(rect, radius, radius)
        return path

    def _paint_plate(self, painter: QPainter, rect: QRectF) -> None:
        """Fill the card plate and outline it with a hairline border."""
        path = self._plate_path(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(24, 26, 32))
        painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.drawPath(path)

    def _paint_image(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the scaled image, centred and clipped to the rounded plate."""
        scaled = self.scaled_pixmap()
        if scaled is None:
            painter.setPen(QColor(150, 156, 168))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No image")
            return
        painter.save()
        painter.setClipPath(self._plate_path(rect))
        position = QPointF(
            rect.x() + (rect.width() - scaled.width()) / 2.0,
            rect.y() + (rect.height() - scaled.height()) / 2.0,
        )
        painter.drawPixmap(position, scaled)
        painter.restore()

    def _paint_badge(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the GOOD/BAD/GREAT/OK badge, faded in with the drag progress.

        The badge sits in the middle of the plate so it stays readable while the
        card is tilted, and its alpha tracks :attr:`progress` so it fades in
        gradually instead of popping into view.
        """
        category = self._direction
        if category is None or self._progress <= 0.0:
            return
        alpha = round(255 * min(1.0, self._progress))
        label = _BADGE_TEXT[category]
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(16, int(rect.height() * 0.11)))
        painter.save()
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_height = float(metrics.height())
        box = QRectF(
            rect.center().x() - metrics.horizontalAdvance(label) / 2.0 - text_height * 0.45,
            rect.center().y() - text_height * 0.75,
            metrics.horizontalAdvance(label) + text_height * 0.9,
            text_height * 1.5,
        )
        painter.setPen(QPen(_badge_color(category, alpha), max(2.0, rect.height() * 0.006)))
        painter.setBrush(_badge_color(category, alpha // 8))
        painter.drawRoundedRect(box, text_height * 0.3, text_height * 0.3)
        painter.setPen(_badge_color(category, alpha))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    # ------------------------------------------------------------------
    # Gesture maths and animation choreography
    # ------------------------------------------------------------------

    def _rotation_for_offset(self, offset: QPointF) -> float:
        """Return the tilt for *offset*: proportional to travel, then clamped.

        A full :attr:`max_rotation` is reached when the pointer is at the
        horizontal threshold, so the tilt doubles as a progress indicator.
        """
        ratio = offset.x() / self.horizontal_threshold
        return self._max_rotation * max(-1.0, min(1.0, ratio))

    def _clear_gesture_state(self) -> None:
        """Forget the drag and restore the neutral look (opaque, upright, no badge)."""
        self._dragging = False
        self._drag_origin = QPointF()
        self._drag_anchor = QPointF()
        self._drag_offset = QPointF()
        self._rotation = 0.0
        self._fade = 1.0
        self._direction = None
        self._progress = 0.0

    def _offscreen_position(self, category: str) -> QPoint:
        """Return a position outside the window, in the direction of *category*.

        The card has to travel half the sum of the window span and its own size
        to clear the edge completely: a card centred in a window only needs to
        move by its own width plus the surrounding gap, not by a full window
        width on top of that. Keeping the distance minimal is what makes the
        fly-out glide for the whole animation instead of teleporting out of
        view in the first few milliseconds.
        """
        step_x, step_y = _OFFSCREEN[category]
        window = self.window()
        span_x = max(window.width(), self.width())
        span_y = max(window.height(), self.height())
        travel_x = (span_x + self.width()) / 2.0 + _EXIT_MARGIN
        travel_y = (span_y + self.height()) / 2.0 + _EXIT_MARGIN
        origin = self.pos()
        return QPoint(
            round(origin.x() + step_x * travel_x),
            round(origin.y() + step_y * travel_y),
        )

    def _start_fly_out(self, category: str) -> None:
        """Animate the card out of the window and emit the decision afterwards.

        Position and opacity are animated together, so the card slides away with
        ``OutCubic`` easing while fading to transparent. :attr:`swiped` is only
        emitted when the group reports ``finished``, which means an owner that
        reacts to the signal never sees a half-departed card.
        """
        self._pending_category = category
        self._transition = _FLY_OUT
        self._animating = True
        group = self._prepare_group()
        duration = self._duration_ms
        curve = QEasingCurve.Type.OutCubic
        self._add_property_animation(
            group, b"pos", self.pos(), self._offscreen_position(category), duration, curve
        )
        self._add_property_animation(group, b"fade", self._fade, 0.0, duration, curve)
        group.start()

    def _start_spring_back(self) -> None:
        """Animate the card home and back to zero rotation.

        ``OutBack`` overshoots slightly before settling, which reads as a spring
        rather than a linear slide. A zero duration snaps instead, so tests and
        reduced-motion setups never wait on the clock.
        """
        if self._spring_back_ms <= 0:
            self.reset()
            return
        self._transition = _SPRING_BACK
        self._animating = True
        group = self._prepare_group()
        duration = self._spring_back_ms
        curve = QEasingCurve.Type.OutBack
        self._add_property_animation(group, b"pos", self.pos(), self._home_pos, duration, curve)
        self._add_property_animation(group, b"rotation", self._rotation, 0.0, duration, curve)
        self._add_property_animation(group, b"progress", self._progress, 0.0, duration, curve)
        group.start()

    def _on_animation_finished(self) -> None:
        """Finish whichever transition just ran and settle into its end state.

        The transition is cleared *first*: if an owner reacts to
        :attr:`swiped` by resetting or loading the next image, that re-entrant
        call must not be mistaken for a second completion.
        """
        transition = self._transition
        self._transition = None
        self._animating = False
        if transition == _FLY_OUT:
            category = self._pending_category
            self._pending_category = None
            if category is not None:
                self.swiped.emit(category)
        elif transition == _SPRING_BACK:
            self._clear_gesture_state()
        self.update()

    def _stop_animations(self) -> None:
        """Stop any running transition without emitting anything.

        The transition marker is cleared *before* stopping, because aborting an
        animation must never commit a decision the user did not make. The group
        itself is reused rather than deleted, so a card that is destroyed
        mid-flight leaves no deferred deletes behind.
        """
        self._transition = None
        self._pending_category = None
        self._animating = False
        if self._group is not None:
            self._group.stop()
            self._group.clear()

    def _prepare_group(self) -> QParallelAnimationGroup:
        """Return the reusable animation group, cleared and ready for a new run.

        One group per card keeps the object graph stable: creating and deleting
        a group per gesture would leave deferred deletes racing against the
        widget's own destruction when a window closes mid-animation.
        """
        group = self._group
        if group is None:
            group = QParallelAnimationGroup(self)
            group.finished.connect(self._on_animation_finished)
            self._group = group
        else:
            group.stop()
            group.clear()
        return group

    def _add_property_animation(
        self,
        group: QParallelAnimationGroup,
        name: bytes,
        start: float | QPoint,
        end: float | QPoint,
        duration_ms: int,
        curve: QEasingCurve.Type,
    ) -> None:
        """Append one configured ``QPropertyAnimation`` to *group*.

        Args:
            group: Group that takes ownership of the animation.
            name: Qt property name as bytes, for example ``b"pos"`` or
                ``b"fade"``. ``fade`` and ``rotation`` are the
                ``pyqtProperty`` descriptors on this class, which is what makes
                them animatable by Qt.
            start: Value to animate from.
            end: Value to animate to.
            duration_ms: Duration; ``0`` jumps straight to *end*.
            curve: Easing curve used for the interpolation.
        """
        animation = QPropertyAnimation(self, name, group)
        animation.setDuration(max(0, duration_ms))
        animation.setEasingCurve(curve)
        animation.setStartValue(start)
        animation.setEndValue(end)
        group.addAnimation(animation)


_DEMO_INSET = (24, 24, -24, -24)
"""Margin the demo stage leaves around the card so its shadow stays visible."""


def _demo_pixmap(size: QSize | None = None) -> QPixmap:
    """Return a generated placeholder image so the demo needs no asset file.

    Args:
        size: Pixel size of the generated image; 3:2 by default so it is easy to
            see that the card fits it without distorting the aspect ratio.

    Returns:
        A gradient with simple geometry and a caption drawn on top.
    """
    size = QSize(1200, 800) if size is None else size
    pixmap = QPixmap(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0.0, 0.0, float(size.width()), float(size.height()))
    gradient.setColorAt(0.0, QColor("#1f4e79"))
    gradient.setColorAt(1.0, QColor("#7b3f9d"))
    painter.fillRect(pixmap.rect(), gradient)
    painter.setPen(QPen(QColor(255, 255, 255, 90), 8.0))
    painter.drawEllipse(QPointF(size.width() * 0.72, size.height() * 0.28), 90.0, 90.0)
    painter.drawLine(
        QPointF(0.0, size.height() * 0.78),
        QPointF(float(size.width()), size.height() * 0.62),
    )
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(24, size.width() // 16))
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 225))
    painter.drawText(
        pixmap.rect().adjusted(0, int(size.height() * 0.74), 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Placeholder image",
    )
    painter.end()
    return pixmap


class SwipeCardDemo(QWidget):
    """Minimal stage that keeps one :class:`SwipeCard` filling the window.

    The demo exists to exercise the widget in isolation: drag with the mouse or
    press an arrow key/WASD and the card prints what it would have told the
    sorter. Every commit deals a fresh placeholder, so it can be swiped forever.

    It also demonstrates the geometry contract: a stage widget assigns the card
    geometry in ``resizeEvent`` instead of putting it in a layout, because the
    card moves itself while being dragged.
    """

    def __init__(self) -> None:
        """Build the stage, the card and the placeholder image."""
        super().__init__()
        self.setWindowTitle("SwipeCard demo — drag, arrow keys or WASD")
        self.resize(960, 720)
        self.card = SwipeCard(self)
        self.card.set_pixmap(_demo_pixmap())
        self.card.swiped.connect(self._on_swiped)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Keep the card covering the window, inset far enough to show its shadow."""
        self.card.setGeometry(self.rect().adjusted(*_DEMO_INSET))
        super().resizeEvent(event)

    def _on_swiped(self, category: str) -> None:
        """Report the decision and deal a fresh card."""
        print(f"swiped -> {category}")
        self.card.set_pixmap(_demo_pixmap())


def _demo_main(argv: list[str] | None = None) -> int:
    """Run the standalone demo.

    Args:
        argv: Argument list handed to ``QApplication``; defaults to ``sys.argv``.

    Returns:
        The Qt event loop's exit code.
    """
    app = QApplication(list(sys.argv if argv is None else argv))
    stage = SwipeCardDemo()
    stage.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual demo entry point
    raise SystemExit(_demo_main())
