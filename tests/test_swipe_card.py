"""Behavioural tests for the swipe card widget (``ui/swipe_card.py``).

Coverage
    * fit-to-area rendering that keeps the aspect ratio, plus the empty state;
    * drag translation, proportional/clamped rotation and threshold maths,
      including the dominant-axis rule for diagonal drags;
    * commit versus spring-back on release, and the category emitted once the
      fly-out animation has finished;
    * the keyboard map (arrows and WASD), ``trigger_swipe`` validation, case
      folding and the guard that ignores a second swipe mid-flight;
    * re-arming the card with ``set_pixmap``/``reset``, catching a spring-back,
      and the import check that keeps the widget free of ``core``/``utils``.

Conventions
    Every test builds the card with ``duration_ms=0`` and ``spring_back_ms=0``
    so nothing waits on the clock (see ``docs/DEVELOPMENT.md``). Drags are
    posted as real ``QMouseEvent`` objects with explicit *global* coordinates:
    the card moves under the cursor while dragging, so pytest-qt's
    ``mouseMove(widget, pos)`` would map the local position through the moving
    widget and double the delta.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from image_swiper.ui import swipe_card
from image_swiper.ui.swipe_card import DEFAULT_MARGIN, SwipeCard

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui

SIZE = (400, 300)
"""Card geometry used throughout: 100 px horizontal and 60 px vertical threshold."""


def _send(
    card: SwipeCard,
    kind: QEvent.Type,
    global_pos: QPoint,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> None:
    """Post one mouse event at the widget centre but at *global_pos* globally.

    The local position stays in the middle of the card on purpose: while the
    card follows the pointer, the cursor does not move relative to the widget,
    only relative to the screen.
    """
    app = QApplication.instance()
    assert app is not None
    app.sendEvent(
        card,
        QMouseEvent(
            kind,
            QPointF(card.rect().center()),
            QPointF(global_pos),
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def _press(card: SwipeCard) -> QPoint:
    """Press the left button in the middle of the card; return the global origin."""
    origin = card.mapToGlobal(card.rect().center())
    _send(
        card,
        QEvent.Type.MouseButtonPress,
        origin,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    return origin


def _move(card: SwipeCard, origin: QPoint, delta: QPoint) -> None:
    """Drag the pointer to ``origin + delta`` without releasing it."""
    _send(
        card,
        QEvent.Type.MouseMove,
        origin + delta,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
    )


def _release(card: SwipeCard, origin: QPoint, delta: QPoint) -> None:
    """Release the left button at ``origin + delta``."""
    _send(
        card,
        QEvent.Type.MouseButtonRelease,
        origin + delta,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )


def _drag(card: SwipeCard, delta: QPoint, *, steps: int = 3) -> None:
    """Press, move in *steps* increments and release *delta* away from the centre."""
    origin = _press(card)
    for step in range(1, steps + 1):
        _move(
            card,
            origin,
            QPoint(round(delta.x() * step / steps), round(delta.y() * step / steps)),
        )
    _release(card, origin, delta)


@pytest.fixture
def pixmap() -> QPixmap:
    """Return a small, uniform 3:2 image so pixel checks stay predictable."""
    image = QPixmap(300, 200)
    image.fill(QColor("#123456"))
    return image


@pytest.fixture
def card(qtbot: QtBot, pixmap: QPixmap) -> SwipeCard:
    """Return a 400x300 card with instant animations and an image loaded."""
    widget = SwipeCard(duration_ms=0, spring_back_ms=0)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    widget.set_pixmap(pixmap)
    return widget


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_scaled_pixmap_fits_the_card_without_distortion(card: SwipeCard) -> None:
    """The drawn image fills one axis and keeps the source aspect ratio."""
    scaled = card.scaled_pixmap()
    assert scaled is not None
    usable_width = SIZE[0] - 2 * DEFAULT_MARGIN
    usable_height = SIZE[1] - 2 * DEFAULT_MARGIN
    assert scaled.width() <= usable_width
    assert scaled.height() <= usable_height
    assert scaled.width() == usable_width or scaled.height() == usable_height
    assert scaled.width() / scaled.height() == pytest.approx(300 / 200, rel=0.01)


def test_empty_card_paints_a_placeholder(qtbot: QtBot) -> None:
    """A card without an image still paints, and reports no pixmap."""
    widget = SwipeCard(duration_ms=0)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    assert widget.pixmap is None
    assert widget.scaled_pixmap() is None
    assert not widget.grab().isNull()


def test_clear_image_forgets_the_pixmap(card: SwipeCard) -> None:
    """``clear_image`` drops the image without touching the geometry."""
    card.clear_image()
    assert card.pixmap is None
    assert card.scaled_pixmap() is None
    assert card.size().width() == SIZE[0]


def test_set_image_loads_files_and_reports_failures(
    qtbot: QtBot,
    tmp_path: Path,
    make_images: Callable[..., list[Path]],
) -> None:
    """The convenience loader decodes real files and rejects broken ones."""
    created = make_images(tmp_path, count=1, fmt="PNG")
    widget = SwipeCard(duration_ms=0)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)

    assert widget.set_image(created[0]) is True
    assert widget.pixmap is not None

    broken = tmp_path / "broken.png"
    broken.write_bytes(b"definitely not a png")
    assert widget.set_image(broken) is False
    assert widget.pixmap is not None, "a failed load must keep the current image"


def test_set_pixmap_accepts_none_and_null_pixmaps(qtbot: QtBot, pixmap: QPixmap) -> None:
    """``None`` and null pixmaps fall back to the placeholder instead of raising."""
    widget = SwipeCard(duration_ms=0)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    widget.set_pixmap(pixmap)
    widget.set_pixmap(None)
    assert widget.pixmap is None
    widget.set_pixmap(QPixmap())
    assert widget.pixmap is None


# ---------------------------------------------------------------------------
# Drag maths
# ---------------------------------------------------------------------------


def test_thresholds_are_a_share_of_the_card_size(card: SwipeCard) -> None:
    """Horizontal commits at 25 % of the width, vertical at 20 % of the height."""
    assert card.horizontal_threshold == pytest.approx(SIZE[0] * 0.25)
    assert card.vertical_threshold == pytest.approx(SIZE[1] * 0.20)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(25, 3.75), (60, 9.0), (100, 15.0), (400, 15.0), (-60, -9.0), (-400, -15.0)],
)
def test_rotation_is_proportional_and_clamped(
    card: SwipeCard,
    delta: int,
    expected: float,
) -> None:
    """The tilt scales with horizontal travel and saturates at 15 degrees."""
    origin = _press(card)
    _move(card, origin, QPoint(delta, 0))
    assert card.rotation == pytest.approx(expected)
    assert abs(card.rotation) <= card.max_rotation


def test_vertical_dragging_does_not_tilt_the_card(card: SwipeCard) -> None:
    """Rotation follows the horizontal axis only, which is what feels natural."""
    origin = _press(card)
    _move(card, origin, QPoint(0, -80))
    assert card.rotation == pytest.approx(0.0)


def test_card_follows_the_pointer_one_to_one(card: SwipeCard) -> None:
    """The card is translated by exactly the pointer delta from the press."""
    origin = _press(card)
    _move(card, origin, QPoint(40, -30))
    assert card.pos() == QPoint(40, -30)
    assert card.drag_offset == QPointF(40, -30)


def test_direction_uses_the_dominant_normalised_axis(card: SwipeCard) -> None:
    """Diagonal drags are resolved after dividing each axis by its threshold."""
    assert card.direction_for_offset(QPointF(140, 50)) == "Good"
    assert card.direction_for_offset(QPointF(-140, 50)) == "Bad"
    assert card.direction_for_offset(QPointF(50, 70)) == "OK"
    assert card.direction_for_offset(QPointF(-50, -70)) == "Great"
    assert card.direction_for_offset(QPointF(0, 0)) is None


def test_progress_tracks_the_dominant_axis(card: SwipeCard) -> None:
    """Progress reaches 1.0 exactly at the threshold of the leading axis."""
    assert card.progress_for_offset(QPointF(50, 0)) == pytest.approx(0.5)
    assert card.progress_for_offset(QPointF(0, 30)) == pytest.approx(0.5)
    assert card.progress_for_offset(QPointF(-100, 0)) == pytest.approx(1.0)
    assert card.progress_for_offset(QPointF(0, -90)) == pytest.approx(1.0)


def test_dragging_paints_the_feedback_badge(card: SwipeCard) -> None:
    """The overlay changes what is rendered at the centre of the card."""
    centre = card.rect().center()
    idle = card.grab().toImage().pixelColor(centre)
    origin = _press(card)
    _move(card, origin, QPoint(60, 0))
    assert card.direction == "Good"
    assert card.progress == pytest.approx(0.6)
    dragging = card.grab().toImage().pixelColor(centre)
    assert dragging != idle


# ---------------------------------------------------------------------------
# Releasing a drag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("delta", "category"),
    [
        (QPoint(150, 0), "Good"),
        (QPoint(-150, 0), "Bad"),
        (QPoint(0, -80), "Great"),
        (QPoint(0, 80), "OK"),
    ],
)
def test_release_past_the_threshold_emits_the_category(
    qtbot: QtBot,
    card: SwipeCard,
    delta: QPoint,
    category: str,
) -> None:
    """Neither axis has to be exact: each direction maps to one category."""
    origin = _press(card)
    _move(card, origin, delta)
    with qtbot.waitSignal(card.swiped, timeout=1000) as blocker:
        _release(card, origin, delta)
    assert blocker.args == [category]
    assert card.is_animating is False, "duration_ms=0 means the fly-out is already done"


@pytest.mark.parametrize(
    "delta",
    [QPoint(60, 0), QPoint(-99, 0), QPoint(0, 50), QPoint(0, -59), QPoint(30, -30)],
)
def test_release_below_the_threshold_springs_back_silently(
    qtbot: QtBot,
    card: SwipeCard,
    delta: QPoint,
) -> None:
    """An unfinished drag returns to the rest pose and commits nothing."""
    origin = _press(card)
    _move(card, origin, delta)
    with qtbot.assertNotEmitted(card.swiped):
        _release(card, origin, delta)
    assert card.pos() == QPoint(0, 0)
    assert card.rotation == pytest.approx(0.0)
    assert card.progress == pytest.approx(0.0)
    assert card.direction is None
    assert card.fade == pytest.approx(1.0)
    assert card.is_animating is False


def test_committed_card_leaves_the_window_and_fades(qtbot: QtBot, card: SwipeCard) -> None:
    """After a commit the card is off to the left and fully transparent."""
    with qtbot.waitSignal(card.swiped, timeout=1000):
        card.trigger_swipe("Bad")
    assert card.pos().x() <= -SIZE[0]
    assert card.fade == pytest.approx(0.0)


def test_press_is_ignored_while_the_card_is_leaving(qtbot: QtBot, pixmap: QPixmap) -> None:
    """A flying card cannot be grabbed, so a swipe never turns into a drag."""
    widget = SwipeCard(duration_ms=200)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    widget.set_pixmap(pixmap)
    widget.trigger_swipe("Good")
    assert widget.is_animating

    origin = _press(widget)
    _move(widget, origin, QPoint(-40, 0))
    assert widget.direction == "Good", "the pending decision must not change"
    with qtbot.waitSignal(widget.swiped, timeout=2000) as blocker:
        _release(widget, origin, QPoint(-40, 0))
    assert blocker.args == ["Good"]


def test_catching_a_spring_back_continues_the_drag(qtbot: QtBot, pixmap: QPixmap) -> None:
    """Pressing during the spring-back resumes the drag instead of ignoring it."""
    widget = SwipeCard(duration_ms=0, spring_back_ms=200)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    widget.set_pixmap(pixmap)

    _drag(widget, QPoint(60, 0))
    assert widget.is_animating, "60 px is below the 100 px threshold, so it springs back"
    qtbot.wait(20)

    origin = _press(widget)
    assert widget.is_animating is False, "the press must stop the spring-back"
    with qtbot.waitSignal(widget.swiped, timeout=1000) as blocker:
        _move(widget, origin, QPoint(160, 0))
        _release(widget, origin, QPoint(160, 0))
    assert blocker.args == ["Good"]


# ---------------------------------------------------------------------------
# Keyboard and programmatic swipes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "category"),
    [
        (Qt.Key.Key_Right, "Good"),
        (Qt.Key.Key_D, "Good"),
        (Qt.Key.Key_Left, "Bad"),
        (Qt.Key.Key_A, "Bad"),
        (Qt.Key.Key_Up, "Great"),
        (Qt.Key.Key_W, "Great"),
        (Qt.Key.Key_Down, "OK"),
        (Qt.Key.Key_S, "OK"),
    ],
)
def test_keyboard_commits_the_same_swipe(
    qtbot: QtBot,
    card: SwipeCard,
    key: Qt.Key,
    category: str,
) -> None:
    """Arrows and WASD both go through the shared fly-out animation."""
    with qtbot.waitSignal(card.swiped, timeout=1000) as blocker:
        qtbot.keyClick(card, key)
    assert blocker.args == [category]


def test_unmapped_keys_are_passed_on(qtbot: QtBot, card: SwipeCard) -> None:
    """Letters outside WASD must not commit anything."""
    with qtbot.assertNotEmitted(card.swiped):
        qtbot.keyClick(card, Qt.Key.Key_Z)
    assert card.pos() == QPoint(0, 0)


@pytest.mark.parametrize(
    ("value", "category"),
    [("Good", "Good"), ("good", "Good"), (" OK ", "OK"), ("great", "Great")],
)
def test_trigger_swipe_normalises_the_category(
    qtbot: QtBot,
    card: SwipeCard,
    value: str,
    category: str,
) -> None:
    """Category names are matched case-insensitively and trimmed."""
    with qtbot.waitSignal(card.swiped, timeout=1000) as blocker:
        card.trigger_swipe(value)
    assert blocker.args == [category]


def test_trigger_swipe_rejects_unknown_categories(card: SwipeCard) -> None:
    """A typo in an action table fails loudly instead of sorting into nothing."""
    with pytest.raises(ValueError, match="unknown swipe category"):
        card.trigger_swipe("Meh")
    assert card.pos() == QPoint(0, 0)


def test_second_swipe_is_ignored_while_the_first_flies_out(
    qtbot: QtBot,
    pixmap: QPixmap,
) -> None:
    """Key auto-repeat cannot commit two decisions for one image."""
    widget = SwipeCard(duration_ms=150)
    qtbot.addWidget(widget)
    widget.setGeometry(0, 0, *SIZE)
    widget.set_pixmap(pixmap)
    with qtbot.waitSignal(widget.swiped, timeout=2000) as blocker:
        widget.trigger_swipe("Good")
        assert widget.is_animating
        widget.trigger_swipe("Bad")
    assert blocker.args == ["Good"]


# ---------------------------------------------------------------------------
# Reuse and boundaries
# ---------------------------------------------------------------------------


def test_reset_restores_the_rest_pose_and_keeps_the_image(card: SwipeCard) -> None:
    """``reset`` clears the gesture state so the card can show the next photo."""
    origin = _press(card)
    _move(card, origin, QPoint(120, 20))
    card.reset()
    assert card.pos() == QPoint(0, 0)
    assert card.rotation == pytest.approx(0.0)
    assert card.fade == pytest.approx(1.0)
    assert card.progress == pytest.approx(0.0)
    assert card.direction is None
    assert card.pixmap is not None


def test_set_pixmap_re_arms_the_card_after_a_swipe(
    qtbot: QtBot,
    card: SwipeCard,
    pixmap: QPixmap,
) -> None:
    """Loading the next image puts the card back home and fully opaque."""
    with qtbot.waitSignal(card.swiped, timeout=1000):
        card.trigger_swipe("Great")
    card.set_pixmap(pixmap)
    assert card.pos() == QPoint(0, 0)
    assert card.fade == pytest.approx(1.0)
    assert card.direction is None
    assert card.is_animating is False
    assert card.scaled_pixmap() is not None


def test_card_depends_on_nothing_but_qt() -> None:
    """The widget must stay reusable: no core, no utils, no session knowledge."""
    module_path = Path(swipe_card.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = [
        name for name in imported if name.startswith(("image_swiper.core", "image_swiper.utils"))
    ]
    assert not forbidden, f"the swipe card must not import {forbidden}"
    assert "PyQt6.QtWidgets" in imported
