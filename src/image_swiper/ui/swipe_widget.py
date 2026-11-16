"""The swipe stage: hosts the card and turns gestures into session signals.

Responsibility
    Own the *area* the user drags in, not the gesture itself. ``SwipeWidget``
    keeps one :class:`~image_swiper.ui.swipe_card.SwipeCard` centred and covering
    the stage, hands it the next preview pixmap, and re-emits the card's
    committed category together with the stage-level signals the main window
    needs (empty deck, prefetch request). It never touches the filesystem and
    never loads images itself; the session façade supplies pixmaps.

Relationship to SwipeCard
    The per-image behaviour is implemented in ``ui/swipe_card.py`` and is
    deliberately self-contained: rendering, the drag state machine, the rotation
    limits, the GOOD/BAD/GREAT/OK badge, the fly-out animation and the keyboard
    map all live there, so the card can be demoed and tested on its own::

        python -m image_swiper.ui.swipe_card

    ``SwipeWidget`` adds what needs more than one image: sizing the stage,
    swapping pixmaps after a commit (``set_pixmap`` re-arms the card),
    requesting the next preview before the current one leaves, and forwarding
    ``swiped`` to the window. It also owns the stage-level shortcuts so they
    keep working when the card does not have focus.

Planned public API
    class SwipeWidget(QWidget):
        swipe_committed: pyqtSignal(str)        # category name, forwarded
        deck_depleted: pyqtSignal()             # no more images to show
        def show_image(pixmap: QPixmap, *, caption: str = "") -> None
        def clear(self) -> None
        def is_empty(self) -> bool
        def trigger_swipe(self, category: str) -> None
        def set_interactive(self, enabled: bool) -> None
        @property
        def card(self) -> SwipeCard

Gesture rules (implemented by SwipeCard)
    * IDLE → DRAGGING on press; release below the threshold springs back,
      release past it flies out and emits the category.
    * Translation follows the pointer; rotation is proportional to horizontal
      travel and capped at 15°.
    * Thresholds are ratios of the stage size: 25 % of the width horizontally,
      20 % of the height vertically, so the gestures scale with the window.
    * Feedback: right → green ``GOOD``, left → red ``BAD``, up → gold
      ``GREAT``, down → blue ``OK``; opacity follows the drag progress.

Accessibility / input
    * The card keeps focus and handles the arrow keys and WASD itself; the stage
      duplicates them as window-level shortcuts so they work regardless of
      focus.
    * Touchscreens work through synthetic mouse events; ``QNativeGestureEvent``
      support for touchpad flicks is a later addition.

Not implemented yet (milestone M2).
"""
