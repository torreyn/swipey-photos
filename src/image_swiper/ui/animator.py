"""Animation choreography for the swipe card.

Responsibility
    Keep all timing and easing out of :class:`SwipeWidget`. ``CardAnimator``
    builds and owns the ``QPropertyAnimation``/``QParallelAnimationGroup``
    instances that move, rotate and fade the card for the three transitions the
    app needs:

    * **fly-out** — the committed card leaves the window in the swipe direction;
    * **fly-in** — the next card enters from the opposite side (or fades in);
    * **spring-back** — an interrupted drag returns to the neutral position.

    It also decides what to do when input arrives mid-animation: the finishing
    animation is stopped, the card is snapped to a defined end state, and the
    new transition starts, so a fast keyboard user never queues up a backlog.

Planned public API
    class CardAnimator(QObject):
        finished: pyqtSignal(str)          # "fly_out" | "fly_in" | "spring_back"
        def __init__(self, card: QWidget, *, duration_ms: int = 180,
                     parent: QObject | None = None) -> None
        def fly_out(self, direction: str) -> None
        def fly_in(self, from_direction: str | None = None) -> None
        def spring_back(self) -> None
        def stop(self) -> None
        def set_duration(self, duration_ms: int) -> None

Design notes
    * Durations default to 180 ms and are clamped to a sane range (60-600 ms);
      the window may override them through :meth:`CardAnimator.set_duration`.
    * Easing: ``QEasingCurve.Type.OutCubic`` for fly-out/fly-in,
      ``OutBack`` for spring-back.
    * Animations must not block: no ``QEventLoop`` spinning, no ``wait()``.
    * Respect the user's reduced-motion preference (``QStyleHints`` /
      ``QGuiApplication``) by falling back to near-instant transitions.
    * Every animation must be safe to delete mid-flight (window close, undo).

Not implemented yet (milestone M2).
"""
