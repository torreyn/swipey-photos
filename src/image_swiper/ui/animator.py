"""Deck-level animation choreography for the swipe stage.

Responsibility
    Sequence what happens *around* a card: the next card flying in or fading in
    after a commit, batch transitions during undo, and the timing table the whole
    UI shares. The per-card transitions already live where they belong — the
    card flies itself out on commit and springs itself back when a drag is
    aborted (see :class:`~image_swiper.ui.swipe_card.SwipeCard`) — so
    ``CardAnimator`` is responsible for the transitions the stage owns:

    * **fly-in** — the replacement card enters from the opposite side, or fades
      in when the swipe direction is vertical;
    * **stage fades** — dimming the stage while a batch action runs;
    * **timing policy** — one place that decides durations and easing for the
      whole UI, including the reduced-motion fallback.

    It also decides what to do when input arrives mid-animation: the finishing
    animation is stopped, the affected widget is snapped to a defined end state,
    and the new transition starts, so a fast keyboard user never queues up a
    backlog.

Planned public API
    class CardAnimator(QObject):
        finished: pyqtSignal(str)          # "fly_in" | "stage_fade"
        def __init__(self, stage: QWidget, *, duration_ms: int = 250,
                     parent: QObject | None = None) -> None
        def fly_in(self, card: QWidget, from_direction: str | None = None) -> None
        def fade_stage(self, opacity: float) -> None
        def stop(self) -> None
        def set_duration(self, duration_ms: int) -> None

Design notes
    * Durations default to 250 ms to match the card's fly-out and are clamped to
      a sane range (60-600 ms); the window may override them through
      :meth:`CardAnimator.set_duration`.
    * Easing: ``QEasingCurve.Type.OutCubic`` for fly-in, ``InOutQuad`` for stage
      fades.
    * Animations must not block: no ``QEventLoop`` spinning, no ``wait()``.
    * Respect the user's reduced-motion preference (``QStyleHints`` /
      ``QGuiApplication``) by falling back to near-instant transitions — the
      card already supports this through ``duration_ms=0``.
    * Reuse one animation group per target instead of creating and deleting
      groups per gesture: deferred deletions racing against widget destruction
      are the classic source of shutdown crashes in Qt apps.

Not implemented yet (planned; the per-card animations already live in SwipeCard).
"""
