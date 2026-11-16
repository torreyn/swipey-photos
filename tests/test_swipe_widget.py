"""Tests for the swipe stage (``ui/swipe_widget.py``).

Coverage
    * image hand-off: ``show_image`` arms the card, the caption follows the
      filename, ``clear`` returns to the empty state;
    * signal forwarding: the card's ``swiped`` becomes ``swipe_committed`` with
      the canonical category, including for lower-case input;
    * the interactive gate: ``set_interactive(False)`` disables the card and
      makes ``trigger_swipe`` a no-op, so a move in flight cannot be doubled;
    * the geometry contract: the card fills the stage and is not in a layout.

Animations are left at their production duration here (250 ms); the tests wait
on the signal or on a condition instead of sleeping, so they stay deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel

from image_swiper.ui.swipe_widget import CardStage, SwipeWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


def _pixmap(width: int = 120, height: int = 80) -> QPixmap:
    """Return a small filled pixmap, cheap enough for widget tests."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.darkCyan)
    return pixmap


def _stage(widget: SwipeWidget) -> CardStage:
    """Return the stage container that owns the card."""
    stage = widget.findChild(CardStage)
    assert stage is not None
    return stage


def _caption(widget: SwipeWidget) -> QLabel:
    """Return the caption label under the card."""
    label = widget.findChild(QLabel, "swipe_caption")
    assert label is not None
    return label


def test_starts_empty(qtbot: QtBot) -> None:
    """A fresh stage shows the placeholder and no caption."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)

    assert widget.is_empty()
    assert widget.card.scaled_pixmap() is None
    assert not _caption(widget).isVisible()


def test_show_image_arms_the_card_and_caption(qtbot: QtBot) -> None:
    """The image lands on the card and the caption names the file."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 320)
    widget.show()

    widget.show_image(_pixmap(), caption="IMG_1.jpg")

    assert not widget.is_empty()
    assert widget.card.scaled_pixmap() is not None
    assert _caption(widget).text() == "IMG_1.jpg"
    assert _caption(widget).isVisible()


def test_clear_returns_to_the_empty_state(qtbot: QtBot) -> None:
    """Clearing the stage hides both the image and the caption."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.show_image(_pixmap(), caption="IMG_1.jpg")

    widget.clear()

    assert widget.is_empty()
    assert widget.card.scaled_pixmap() is None
    assert not _caption(widget).isVisible()


def test_null_pixmap_counts_as_empty(qtbot: QtBot) -> None:
    """A null pixmap is a placeholder, not an image to swipe."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)

    widget.show_image(QPixmap())

    assert widget.is_empty()


def test_caption_can_be_switched_off(qtbot: QtBot) -> None:
    """A stage without captions never shows the label."""
    widget = SwipeWidget(show_caption=False)
    qtbot.addWidget(widget)
    widget.show()

    widget.show_image(_pixmap(), caption="IMG_1.jpg")

    assert not _caption(widget).isVisible()


def test_legend_shows_the_gesture_map(qtbot: QtBot) -> None:
    """The key map is visible under the card."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.show()

    assert widget.legend.text() == "← Bad    ↓ OK    ↑ Great    → Good"
    assert widget.legend.isVisible()


def test_legend_can_be_switched_off(qtbot: QtBot) -> None:
    """A bare stage hides the hint together with the caption."""
    widget = SwipeWidget(show_legend=False)
    qtbot.addWidget(widget)
    widget.show()

    assert not widget.legend.isVisible()


def test_show_image_fades_the_card_in(qtbot: QtBot) -> None:
    """A new card enters transparent and becomes opaque when it settles."""
    widget = SwipeWidget(animation_ms=120)
    qtbot.addWidget(widget)
    widget.resize(400, 320)
    widget.show()

    widget.show_image(_pixmap(), caption="IMG_1.jpg")
    assert widget.card.fade < 1.0

    qtbot.waitUntil(lambda: widget.card.fade == pytest.approx(1.0), timeout=2000)
    assert widget.card.pos() == widget.card.home_position


def test_show_image_without_animation_is_instant(qtbot: QtBot) -> None:
    """``animation_ms=0`` is the reduced-motion path: no animation at all."""
    widget = SwipeWidget(animation_ms=0)
    qtbot.addWidget(widget)
    widget.resize(400, 320)
    widget.show()

    widget.show_image(_pixmap())

    assert widget.card.fade == pytest.approx(1.0)
    assert widget.card.pos() == widget.card.home_position
    assert widget.animator.duration_ms == 0


def test_clear_stops_a_running_entrance(qtbot: QtBot) -> None:
    """Clearing the stage mid-animation leaves nothing animating."""
    widget = SwipeWidget(animation_ms=200)
    qtbot.addWidget(widget)
    widget.resize(400, 320)
    widget.show()
    widget.show_image(_pixmap())

    widget.clear()

    assert widget.card.fade == pytest.approx(1.0)
    assert widget.card.pos() == widget.card.home_position


def test_swipe_is_forwarded_canonically(qtbot: QtBot) -> None:
    """The stage re-emits the category the card committed."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.resize(600, 400)
    widget.show()
    widget.show_image(_pixmap())

    with qtbot.waitSignal(widget.swipe_committed, timeout=3000) as blocker:
        widget.trigger_swipe("good")

    assert blocker.args == ["Good"]


def test_non_interactive_stage_ignores_commits(qtbot: QtBot) -> None:
    """A move in flight must not accept a second decision."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.resize(600, 400)
    widget.show()
    widget.show_image(_pixmap())
    emitted: list[str] = []
    widget.swipe_committed.connect(emitted.append)

    widget.set_interactive(False)
    widget.trigger_swipe("Good")

    assert not widget.is_interactive()
    assert not widget.card.isEnabled()
    assert emitted == []

    widget.set_interactive(True)
    assert widget.card.isEnabled()


def test_empty_stage_ignores_commits(qtbot: QtBot) -> None:
    """There is nothing to swipe before an image arrives."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    emitted: list[str] = []
    widget.swipe_committed.connect(emitted.append)

    widget.trigger_swipe("Good")

    assert emitted == []


def test_card_fills_the_stage(qtbot: QtBot) -> None:
    """The stage owns the card geometry instead of a layout."""
    widget = SwipeWidget()
    qtbot.addWidget(widget)
    widget.resize(500, 380)
    widget.show()

    stage = _stage(widget)
    assert widget.card.parentWidget() is stage
    assert widget.card.geometry() == stage.rect()
    assert widget.card.pos().x() == 0
    assert widget.card.pos().y() == 0
