"""The swipeable image card.

Responsibility
    Display exactly one image and turn pointer input into a discrete sorting
    decision. ``SwipeWidget`` renders the preview pixmap (fit-to-area, preserved
    aspect ratio, centred), follows the pointer while dragging, shows the
    directional feedback overlay, and emits a signal when a gesture is
    committed. It never touches the filesystem and never loads images itself.

Gesture state machine
    IDLE ──press──▶ DRAGGING ──release below threshold──▶ SPRING_BACK ──▶ IDLE
                        │
                        ├──release past threshold──▶ COMMITTED
                        └──key press──▶ COMMITTED (animated by the owner)

    While ``DRAGGING`` the card is translated by the pointer delta and rotated
    proportionally to the horizontal offset (capped, e.g. ±12°). The dominant
    axis decides the direction: horizontal wins ties, vertical requires a larger
    travel (configurable) so sideways flicks stay easy.

Feedback
    * Right drag → green tint + "GOOD" badge; left → red + "BAD";
      up → blue + "GREAT"; down → amber + "OK".
    * Opacity/rotation of the badge scales with drag progress, so the user can
      see the pending decision before releasing.
    * Threshold is a constructor argument with a 120 px default, and the
      vertical threshold defaults to 100 px, so the UI can tune them later.

Planned public API
    class SwipeWidget(QWidget):
        swipe_committed: pyqtSignal(str)           # category name
        drag_progress_changed: pyqtSignal(float)   # -1.0 … 1.0, for the owner
        def set_image(pixmap: QPixmap, *, caption: str = "") -> None
        def clear_image(self) -> None
        def reset_position(self, *, animated: bool = True) -> None
        def play_fling_out(direction: str) -> None
        def set_interactive(self, enabled: bool) -> None

Accessibility / input
    * Keys handled by the window, not the widget, so shortcuts keep working
      when the card is not focused.
    * Touchscreens work through synthetic mouse events; a future M4 addition is
      ``QNativeGestureEvent`` support for touchpad flicks where the compositor
      provides them.

Not implemented yet (milestone M2).
"""
