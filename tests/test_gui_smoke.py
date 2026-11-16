"""GUI harness smoke test (milestone M0).

The widget-level tests live in ``tests/test_swipe_card.py``, ``test_swipe_widget.py``,
``test_welcome_screen.py``, ``test_completion_screen.py``, ``test_main_window.py``
and ``test_app.py``. This module keeps the documented headless command honest —
it proves that PyQt6 imports, that ``pytest-qt`` creates a ``QApplication`` for
us, and that widgets can be constructed without a display:

    QT_QPA_PLATFORM=offscreen pytest -q -m gui

Without a file like this, ``pytest -m gui`` exits with code 5 ("no tests
collected") and any CI job using the documented command fails for the wrong
reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication


@pytest.mark.gui
def test_pytest_qt_can_create_an_application(qapp: QApplication) -> None:
    """pytest-qt supplies a live QApplication, so widget tests need no setup."""
    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtWidgets import QWidget

    widget = QWidget()
    assert widget.isEnabled()
    assert not widget.isVisible()
    assert qapp.platformName(), "Qt should report a platform plugin name"
    assert QT_VERSION_STR.startswith("6."), QT_VERSION_STR
