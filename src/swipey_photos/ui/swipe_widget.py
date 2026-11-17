"""The swipe stage: hosts the card, swaps images and forwards decisions.

Responsibility
    Own the *area* the user drags in, not the gesture itself. ``SwipeWidget``
    keeps one :class:`~swipey_photos.ui.swipe_card.SwipeCard` centred and covering
    the stage, hands it the next preview pixmap and re-emits the card's
    committed category as :attr:`SwipeWidget.swipe_committed`, which is the only
    thing the main window needs to know about a gesture. It never touches the
    filesystem and never decodes images itself; the window supplies pixmaps.

Relationship to SwipeCard
    The per-image behaviour lives in ``ui/swipe_card.py`` and is deliberately
    self-contained: rendering, the drag state machine, the rotation limits, the
    GOOD/BAD/GREAT/OK badge, the fly-out animation and the keyboard map all live
    there, so the card can be demoed on its own::

        python -m swipey_photos.ui.swipe_card

    This module adds what needs a stage around the card: a geometry owner, a
    caption line, image hand-off (``set_pixmap`` re-arms the card) and an
    *interactive* flag the window clears while a move is in flight. Deck-level
    animation choreography (the next card flying in) belongs to
    :mod:`swipey_photos.ui.animator` and is not part of this widget.

Public API
    class CardStage(QWidget):              # geometry owner around one card
        card -> SwipeCard
    class SwipeWidget(QWidget):
        swipe_committed: pyqtSignal(str)   # category name, forwarded
        show_image(pixmap, *, caption="", from_direction=None) -> None
        clear() -> None
        is_empty() -> bool
        trigger_swipe(category) -> None
        set_interactive(enabled) -> None
        card -> SwipeCard
        animator -> CardAnimator

Geometry contract
    The card positions *itself* while being dragged, so it must not be put in a
    layout: :class:`CardStage` assigns its geometry in ``resizeEvent`` with a
    small inset for the drop shadow. Everything else uses ordinary layouts.

Input rules
    * ``set_interactive(False)`` disables the card (no drag, no focused-widget
      key handling) and ignores :meth:`SwipeWidget.trigger_swipe`, so a second
      decision cannot be started while the previous move is still running.
    * The card is given focus after :meth:`SwipeWidget.show_image`, which keeps
      arrow keys working without the window doing anything special.
    * The gesture reminder lives on the footer buttons (``ui/main_window.py``),
      so the stage itself shows nothing but the card, its caption and the
      surrounding chrome.

Animation
    Handing over an image also starts the deck-level entrance animation through
    :class:`~swipey_photos.ui.animator.CardAnimator`: the new card fades in over
    150 ms, and slides in from the opposite side when the window passes the
    direction of the previous decision. ``animation_ms=0`` makes it instant.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QResizeEvent
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from .animator import DEFAULT_DURATION_MS, CardAnimator
from .swipe_card import SwipeCard

CAPTION_STYLE = "color: palette(mid); font-size: 11pt;"
"""Stylesheet for the filename line under the card."""


STAGE_MARGIN = 0
"""Inset the stage leaves around the card.

The card paints its own margin (``swipe_card.DEFAULT_MARGIN``) and keeps
``(0, 0)`` as its resting position, so the stage must hand it the full rectangle:
any offset here would be undone by the card's next ``reset()``.
"""


class CardStage(QWidget):
    """Widget whose only job is to size a card to fill it.

    The card cannot live in a layout because it moves itself during a drag;
    instead this container owns the geometry decision in :meth:`resizeEvent`
    and exposes the card it created.

    Args:
        parent: Optional Qt parent.
        margin: Inset in pixels between the stage edge and the card. Zero by
            default; see :data:`STAGE_MARGIN` for the reason.
    """

    def __init__(self, parent: QWidget | None = None, *, margin: int = STAGE_MARGIN) -> None:
        """Create the card and remember the inset to apply on resize."""
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self._margin = max(0, margin)
        self.card = SwipeCard(self)
        self.card.setObjectName("swipe_card")

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Stretch the card to the stage size minus the configured margin."""
        inset = self._margin
        self.card.setGeometry(self.rect().adjusted(inset, inset, -inset, -inset))
        super().resizeEvent(event)


class SwipeWidget(QWidget):
    """Stage that shows one image at a time and reports committed swipes.

    Signals:
        swipe_committed: Emitted with the canonical category name (``"Good"``,
            ``"Bad"``, ``"Great"`` or ``"OK"``) once the card has flown out.
    """

    swipe_committed = pyqtSignal(str, arguments=["category"])

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = STAGE_MARGIN,
        show_caption: bool = True,
        animation_ms: int = DEFAULT_DURATION_MS,
    ) -> None:
        """Build the stage, the card and the caption.

        Args:
            parent: Optional Qt parent.
            margin: Inset between the stage edge and the card, in pixels.
            show_caption: Display a filename line under the card.
            animation_ms: Duration of the entrance animation; ``0`` disables it.
        """
        super().__init__(parent)  # type: ignore[arg-type]  # PyQt6 types parent as Self
        self.setObjectName("swipe_widget")
        self._stage = CardStage(self, margin=margin)
        self._has_image = False
        self._interactive = True
        self._show_caption = show_caption

        self._caption = QLabel("", self)
        self._caption.setObjectName("swipe_caption")
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setStyleSheet(CAPTION_STYLE)
        self._caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._stage, stretch=1)
        if show_caption:
            layout.addWidget(self._caption)

        self._animator = CardAnimator(self._stage, duration_ms=animation_ms, parent=self)
        self._stage.card.swiped.connect(self._on_swiped)
        self._set_caption("")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def card(self) -> SwipeCard:
        """The card this stage hosts; use it for demos, tests and shortcuts."""
        return self._stage.card

    @property
    def animator(self) -> CardAnimator:
        """The deck-level animator used for card entrances."""
        return self._animator

    def show_image(
        self,
        pixmap: QPixmap | None,
        *,
        caption: str = "",
        from_direction: str | None = None,
    ) -> None:
        """Display *pixmap* on a freshly armed card.

        Args:
            pixmap: Already-decoded image; ``None`` shows the empty placeholder.
            caption: Filename or size hint under the card; empty hides the line.
            from_direction: Category of the previous decision, so the new card
                enters from the opposite side; ``None`` fades it in place.
        """
        self.card.set_pixmap(pixmap)
        self._has_image = pixmap is not None and not pixmap.isNull()
        self._set_caption(caption)
        if self._has_image:
            self._animator.fly_in(self.card, from_direction)
        if self._interactive:
            self.card.setEnabled(True)
            self.card.setFocus(Qt.FocusReason.OtherFocusReason)

    def clear(self) -> None:
        """Remove the current image and caption, leaving an empty stage."""
        self._animator.stop()
        self.card.clear_image()
        self._has_image = False
        self._set_caption("")

    def is_empty(self) -> bool:
        """Return ``True`` when no image is on the stage."""
        return not self._has_image

    def trigger_swipe(self, category: str) -> None:
        """Commit *category* as if the user had swiped, unless busy or empty.

        Args:
            category: Category name, matched case-insensitively by the card.

        Raises:
            ValueError: *category* is unknown while the stage is interactive;
                calls made while it is not interactive are ignored silently so a
                late key press cannot raise out of a menu handler.
        """
        if not self._interactive or self.is_empty():
            return
        self.card.trigger_swipe(category)

    def set_interactive(self, enabled: bool) -> None:
        """Enable or disable committing new decisions.

        Args:
            enabled: ``True`` while the window waits for input, ``False`` while
                a move is in flight (the card is disabled and the stage shows a
                busy cursor).
        """
        self._interactive = enabled
        self.card.setEnabled(enabled)
        if enabled:
            self._stage.unsetCursor()
            self._caption.unsetCursor()
        else:
            self._stage.setCursor(Qt.CursorShape.BusyCursor)
            self._caption.setCursor(Qt.CursorShape.BusyCursor)

    def is_interactive(self) -> bool:
        """Return ``True`` when a new decision can be committed."""
        return self._interactive

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_swiped(self, category: str) -> None:
        """Forward the card's decision to the window."""
        self.swipe_committed.emit(category)

    def _set_caption(self, caption: str) -> None:
        """Show *caption* under the card, or hide the line when it is empty."""
        self._caption.setText(caption)
        self._caption.setToolTip(caption)
        self._caption.setVisible(self._show_caption and bool(caption))
