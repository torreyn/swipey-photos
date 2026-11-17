"""Tests for the deck-level animator (``ui/animator.py``).

Coverage
    * timing policy: the documented 150 ms default, clamping to 60-600 ms and
      ``0`` meaning "instant";
    * ``fly_in``: one ``finished("fly_in")`` per animation, a transparent start
      state, an optional slide from the opposite side, and a home position that
      survives the transition;
    * interruption: a second ``fly_in`` replaces the first, ``stop`` snaps the
      card home without emitting ``finished``;
    * the stage never receives a graphics effect (nesting one above the card's
      own drop shadow stops Qt from painting the card);
    * robustness: a card deleted mid-flight does not crash the animator and the
      animation objects are reused instead of leaking.

The tests run offscreen. Long durations are only used where the interruption
itself is the subject, and every wait is bounded by ``qtbot`` timeouts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QParallelAnimationGroup, QPoint, QPropertyAnimation
from PyQt6.QtWidgets import QWidget

from swipey_photos.ui.animator import (
    DEFAULT_DURATION_MS,
    FLY_IN,
    MAX_DURATION_MS,
    MIN_DURATION_MS,
    CardAnimator,
)
from swipey_photos.ui.swipe_card import SwipeCard

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


@pytest.fixture
def stage(qtbot: QtBot) -> QWidget:
    """Return a shown 400x300 stage that can host a card."""
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 300)
    widget.show()
    return widget


@pytest.fixture
def card(stage: QWidget) -> SwipeCard:
    """Return a card filling *stage*, exactly as ``CardStage`` would place it."""
    created = SwipeCard(stage)
    created.setGeometry(stage.rect())
    return created


def test_default_duration_is_the_documented_fade_in() -> None:
    """A fresh animator uses the 150 ms card fade-in from the docs."""
    animator = CardAnimator()

    assert DEFAULT_DURATION_MS == 150
    assert animator.duration_ms == 150


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(10, MIN_DURATION_MS), (60, 60), (250, 250), (5000, MAX_DURATION_MS), (0, 0), (-5, 0)],
)
def test_set_duration_clamps_and_allows_zero(requested: int, expected: int) -> None:
    """Durations are clamped to the documented range; ``0`` disables animation."""
    animator = CardAnimator()

    animator.set_duration(requested)

    assert animator.duration_ms == expected


def test_fly_in_fades_the_card_in_and_emits_once(
    qtbot: QtBot, card: SwipeCard, stage: QWidget
) -> None:
    """The card starts transparent, ends opaque at home, and reports one finish."""
    animator = CardAnimator(stage, duration_ms=80)
    emissions: list[str] = []
    animator.finished.connect(emissions.append)

    with qtbot.waitSignal(animator.finished, timeout=2000) as blocker:
        animator.fly_in(card)

    assert blocker.args == [FLY_IN]
    assert emissions == [FLY_IN]
    assert card.property("fade") == 1.0
    assert card.pos() == card.home_position


def test_fly_in_slides_from_the_opposite_side(
    qtbot: QtBot, card: SwipeCard, stage: QWidget
) -> None:
    """Sorting right means the next card enters from the left."""
    animator = CardAnimator(stage, duration_ms=80)
    home = QPoint(card.pos())

    animator.fly_in(card, "Good")

    assert card.pos().x() < home.x()
    assert card.pos().y() == home.y()

    with qtbot.waitSignal(animator.finished, timeout=2000):
        pass
    assert card.pos() == home


def test_fly_in_without_a_direction_does_not_move_the_card(stage: QWidget, card: SwipeCard) -> None:
    """No direction means a pure fade: the card never leaves its home."""
    animator = CardAnimator(stage, duration_ms=0)
    home = QPoint(card.pos())

    animator.fly_in(card)

    assert card.pos() == home
    assert card.home_position == home


def test_instant_fly_in_applies_the_end_state_immediately(stage: QWidget, card: SwipeCard) -> None:
    """With duration 0 the card is opaque at home before ``fly_in`` returns."""
    animator = CardAnimator(stage, duration_ms=0)
    emissions: list[str] = []
    animator.finished.connect(emissions.append)

    animator.fly_in(card, "Bad")

    assert emissions == [FLY_IN]
    assert card.property("fade") == 1.0
    assert card.pos() == card.home_position


def test_second_fly_in_replaces_the_first(qtbot: QtBot, card: SwipeCard, stage: QWidget) -> None:
    """A fast keyboard user gets one finish for the animation that survives."""
    animator = CardAnimator(stage, duration_ms=300)
    emissions: list[str] = []
    animator.finished.connect(emissions.append)

    animator.fly_in(card, "Good")
    animator.fly_in(card, "Bad")

    with qtbot.waitSignal(animator.finished, timeout=2000) as blocker:
        pass

    assert blocker.args == [FLY_IN]
    assert emissions == [FLY_IN]
    assert card.pos() == card.home_position
    assert card.property("fade") == 1.0


def test_stop_snaps_the_card_home_without_finishing(
    qtbot: QtBot, card: SwipeCard, stage: QWidget
) -> None:
    """Stopping mid-flight leaves a usable card and emits nothing."""
    animator = CardAnimator(stage, duration_ms=400)
    emissions: list[str] = []
    animator.finished.connect(emissions.append)
    home = QPoint(card.pos())

    animator.fly_in(card, "Great")
    animator.stop()

    assert card.pos() == home
    assert card.property("fade") == 1.0
    qtbot.wait(450)
    assert emissions == []


def test_animation_objects_are_reused(stage: QWidget, card: SwipeCard) -> None:
    """Repeated entrances reuse one group and two animations, never leak."""
    animator = CardAnimator(stage, duration_ms=0)
    animator.fly_in(card)
    groups = len(animator.findChildren(QParallelAnimationGroup))
    animations = len(animator.findChildren(QPropertyAnimation))

    for _ in range(5):
        animator.fly_in(card, "OK")

    assert len(animator.findChildren(QParallelAnimationGroup)) == groups
    assert len(animator.findChildren(QPropertyAnimation)) == animations


def test_animator_never_puts_an_effect_on_the_stage(qtbot: QtBot, stage: QWidget) -> None:
    """The stage stays effect-free; Qt cannot composite an effect inside one.

    The card carries its own ``QGraphicsDropShadowEffect``. Nesting that inside
    a stage-wide ``QGraphicsOpacityEffect`` makes Qt stop painting the card as
    soon as the card moves (the entrance slide), so ``CardAnimator`` must never
    install an effect on the stage — the entrance fades the card's own painted
    ``fade`` property instead.
    """
    animator = CardAnimator(stage, duration_ms=0)
    card = SwipeCard(stage)
    qtbot.addWidget(card)
    card.setGeometry(stage.rect())

    animator.fly_in(card, "Good")
    animator.stop()

    assert stage.graphicsEffect() is None
    assert card.graphicsEffect() is not None  # the card keeps its drop shadow


def test_deleting_the_card_mid_flight_does_not_crash(qtbot: QtBot, stage: QWidget) -> None:
    """A card destroyed during its entrance is dropped, not animated further."""
    animator = CardAnimator(stage, duration_ms=300)
    doomed = SwipeCard(stage)
    doomed.setGeometry(stage.rect())

    animator.fly_in(doomed, "Good")
    doomed.deleteLater()
    qtbot.wait(60)

    survivor = SwipeCard(stage)
    survivor.setGeometry(stage.rect())
    with qtbot.waitSignal(animator.finished, timeout=2000) as blocker:
        animator.fly_in(survivor, "Bad")

    assert blocker.args == [FLY_IN]
    assert survivor.pos() == survivor.home_position
