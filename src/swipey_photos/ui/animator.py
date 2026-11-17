"""Deck-level animation choreography for the swipe stage.

Responsibility
    Sequence what happens *around* a card: the replacement card fading (and,
    when a direction is known, sliding) in after a commit, plus the timing
    policy the whole UI shares. The per-card transitions already live where they
    belong — the card flies itself out on commit and springs itself back when a
    drag is aborted (see :class:`~swipey_photos.ui.swipe_card.SwipeCard`) — so
    ``CardAnimator`` owns only the transitions the stage drives.

    It also decides what to do when input arrives mid-animation: the running
    animation is stopped, the affected widget is snapped to a defined state and
    the new transition starts, so a fast keyboard user never builds a backlog.

Public API
    DEFAULT_DURATION_MS, MIN_DURATION_MS, MAX_DURATION_MS   timing policy
    class CardAnimator(QObject):
        finished: pyqtSignal(str)      # "fly_in"
        __init__(stage=None, *, duration_ms=DEFAULT_DURATION_MS, parent=None)
        fly_in(card, from_direction=None)
        stop()
        set_duration(duration_ms)
        duration_ms -> int

Design notes
    * Durations default to 150 ms — the fade-in of a freshly dealt card — and
      are clamped to 60-600 ms; ``set_duration(0)`` disables animation and makes
      every transition instant, which is how reduced-motion users are served
      and what the tests rely on.
    * Easing: ``OutCubic`` for the fly-in (fast start, soft landing).
    * One ``QParallelAnimationGroup`` with two reusable ``QPropertyAnimation``
      objects serves every card. Animations are retargeted with
      ``setTargetObject`` instead of being created and deleted per gesture:
      deferred deletions racing against widget destruction are the classic
      source of shutdown crashes in Qt applications.
    * A card destroyed mid-flight is detected through its ``destroyed`` signal,
      which stops the group and drops the reference, so neither the animator nor
      the animations touch a deleted C++ object.
    * Nothing here blocks: no ``QEventLoop`` spinning, no ``wait()``.
    * The stage itself deliberately gets **no** ``QGraphicsOpacityEffect``. Qt
      composites a widget effect by rendering that widget's subtree, and a child
      that carries its own effect (the card's drop shadow) inside an ancestor
      effect breaks that path as soon as the child moves: the stage then paints
      nothing at all. Entrances therefore fade the card through its own painted
      ``fade`` property, which needs no effect and survives being animated while
      the card also moves.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    pyqtSignal,
)
from PyQt6.QtWidgets import QWidget

from ..utils.logging_setup import get_logger
from .swipe_card import SwipeCard

LOGGER = get_logger(__name__)

DEFAULT_DURATION_MS = 150
"""Default transition length: the 150 ms fade-in of a new card."""

MIN_DURATION_MS = 60
"""Shortest animatable duration; anything faster reads as a jump anyway."""

MAX_DURATION_MS = 600
"""Longest duration the window may ask for, so the UI never feels sluggish."""

FLY_IN_RATIO = 0.12
"""Share of the stage size a new card travels while flying in."""

FLY_IN_MIN_DISTANCE = 32.0
"""Minimum travel in pixels, so the entrance is visible on a small stage."""

FLY_IN = "fly_in"
"""Value carried by :attr:`CardAnimator.finished` after a fly-in."""

_DIRECTION_VECTORS: dict[str, tuple[int, int]] = {
    "good": (1, 0),
    "bad": (-1, 0),
    "great": (0, -1),
    "ok": (0, 1),
}
"""Swipe direction per category, case-folded; the entrance is the inverse."""


class CardAnimator(QObject):
    """Animate the stage around the card: the entrance of a freshly dealt card.

    Signals:
        finished: Emitted with ``"fly_in"`` when a transition completes
            normally. A transition that is interrupted by :meth:`stop` or by a
            newer transition emits nothing, so listeners always see exactly one
            ``finished`` per animation they started.

    Args:
        stage: Widget that hosts the cards; its size decides how far a fly-in
            travels. ``None`` falls back to the card's own size.
        duration_ms: Transition length in milliseconds; clamped by
            :meth:`set_duration`, and ``0`` means "instant".
        parent: Optional Qt parent.
    """

    finished = pyqtSignal(str, arguments=["transition"])

    def __init__(
        self,
        stage: QWidget | None = None,
        *,
        duration_ms: int = DEFAULT_DURATION_MS,
        parent: QObject | None = None,
    ) -> None:
        """Create the animator; no animation object is built until it is used."""
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self._stage = stage
        self._duration_ms = DEFAULT_DURATION_MS
        self.set_duration(duration_ms)

        self._card_group: QParallelAnimationGroup | None = None
        self._card_fade: QPropertyAnimation | None = None
        self._card_slide: QPropertyAnimation | None = None
        self._card: SwipeCard | None = None
        self._running: dict[QParallelAnimationGroup, str] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> int:
        """Duration of the next transition, in milliseconds (``0`` = instant)."""
        return self._duration_ms

    def set_duration(self, duration_ms: int) -> None:
        """Set the transition length, clamped to the documented range.

        Args:
            duration_ms: Requested duration. ``0`` or less disables animation,
                which is the documented reduced-motion opt-out; other values are
                clamped to :data:`MIN_DURATION_MS`-:data:`MAX_DURATION_MS`.
        """
        if duration_ms <= 0:
            self._duration_ms = 0
            return
        self._duration_ms = max(MIN_DURATION_MS, min(MAX_DURATION_MS, int(duration_ms)))

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def fly_in(self, card: SwipeCard, from_direction: str | None = None) -> None:
        """Deal *card* onto the stage with a fade, plus a slide when directed.

        The card is snapped to its start state (transparent, offset from home)
        before the animation begins, so calling this mid-flight replaces the
        previous entrance instead of queueing behind it.

        Args:
            card: The card to animate; it gains a short-lived home lock while it
                moves, so its resting position survives the transition.
            from_direction: Category the *previous* image was sorted into. The
                new card enters from the opposite side; ``None`` (or an unknown
                name) fades the card in place.
        """
        group = self._ensure_card_group()
        fade = self._card_fade
        slide = self._card_slide
        if fade is None or slide is None:  # pragma: no cover - created together
            return

        self._stop_group(group)
        self._release_card()

        home = QPoint(card.pos())
        offset = self._entry_offset(card, from_direction)

        card.lock_home()
        card.move(home + offset)
        card.setProperty("fade", 0.0)
        self._card = card
        card.destroyed.connect(self._on_card_destroyed)

        fade.setTargetObject(card)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(max(self._duration_ms, 1))
        slide.setTargetObject(card)
        slide.setStartValue(home + offset)
        slide.setEndValue(home)
        slide.setDuration(max(self._duration_ms, 1))

        if self._duration_ms == 0:
            card.move(home)
            card.setProperty("fade", 1.0)
            self._release_card()
            self.finished.emit(FLY_IN)
            return

        self._running[group] = FLY_IN
        group.start()

    def stop(self) -> None:
        """Stop every transition and snap the affected widgets to a stable state.

        The card is returned home, fully opaque and with its home tracking
        restored. Nothing is emitted, because an interrupted transition did not
        finish.
        """
        group = self._card_group
        if group is not None:
            self._stop_group(group)
        card = self._card
        self._release_card()
        if card is not None:
            try:
                card.move(card.home_position)
                card.setProperty("fade", 1.0)
            except RuntimeError:  # pragma: no cover - card already deleted
                LOGGER.debug("card vanished before the animation was stopped")

    # ------------------------------------------------------------------
    # Internals: animation objects, retargeting and completion
    # ------------------------------------------------------------------

    def _ensure_card_group(self) -> QParallelAnimationGroup:
        """Return the reusable card group, creating its two animations once."""
        if self._card_group is None:
            group = QParallelAnimationGroup(self)
            group.finished.connect(self._on_finished)
            fade = QPropertyAnimation(group)
            fade.setPropertyName(b"fade")
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            slide = QPropertyAnimation(group)
            slide.setPropertyName(b"pos")
            slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(fade)
            group.addAnimation(slide)
            self._card_group = group
            self._card_fade = fade
            self._card_slide = slide
        return self._card_group

    def _entry_offset(self, card: SwipeCard, direction: str | None) -> QPoint:
        """Return the offset a card starts from when entering for *direction*.

        The entrance is the inverse of the swipe direction: a card sorted into
        ``Good`` (to the right) is replaced by one arriving from the left. An
        unknown or missing direction yields a zero offset, i.e. a pure fade.
        """
        vector = _DIRECTION_VECTORS.get((direction or "").strip().casefold())
        if vector is None:
            return QPoint()
        if self._stage is not None:
            width, height = self._stage.width(), self._stage.height()
        else:
            width, height = card.width(), card.height()
        horizontal = max(round(width * FLY_IN_RATIO), int(FLY_IN_MIN_DISTANCE))
        vertical = max(round(height * FLY_IN_RATIO), int(FLY_IN_MIN_DISTANCE))
        return QPoint(-vector[0] * horizontal, -vector[1] * vertical)

    def _stop_group(self, group: QParallelAnimationGroup) -> None:
        """Stop *group* if it is running and forget that it had a pending name."""
        if group.state() != QAbstractAnimation.State.Stopped:
            group.stop()
        self._running.pop(group, None)

    def _release_card(self) -> None:
        """Forget the animated card and restore its automatic home tracking."""
        card = self._card
        self._card = None
        if card is None:
            return
        try:
            card.destroyed.disconnect(self._on_card_destroyed)
        except (RuntimeError, TypeError):  # pragma: no cover - deleted or never connected
            LOGGER.debug("card destroy hook was already gone", exc_info=True)
        try:
            card.unlock_home()
        except RuntimeError:  # pragma: no cover - deleted C++ object
            LOGGER.debug("card was deleted before its home lock was released")

    def _on_finished(self) -> None:
        """Translate the group's ``finished`` into our named signal."""
        sender = self.sender()
        if not isinstance(sender, QParallelAnimationGroup):
            return  # pragma: no cover - only our groups are connected
        transition = self._running.pop(sender, None)
        if transition is None:
            return
        if transition == FLY_IN:
            self._release_card()
        self.finished.emit(transition)

    def _on_card_destroyed(self, *_args: object) -> None:
        """Drop everything that points at a card deleted mid-transition."""
        LOGGER.debug("card destroyed during a transition; dropping it")
        self._card = None
        if self._card_group is not None:
            self._stop_group(self._card_group)
