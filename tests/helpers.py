"""Small stand-ins shared by the GUI test modules.

``FakeFileDialog`` replaces ``QFileDialog`` inside a UI module (PyQt6's own
class is a SIP type and cannot be monkeypatched), so tests can drive the folder
picker without opening a real modal dialog. The fixture ``fake_file_dialog`` in
``conftest.py`` wires it into every module that calls
``QFileDialog.getExistingDirectory``.
"""

from __future__ import annotations

from typing import ClassVar


class FakeFileDialog:
    """Canned-answer stand-in for ``QFileDialog``.

    Attributes:
        result: Directory returned by :meth:`getExistingDirectory`; an empty
            string simulates the user cancelling the dialog.
        calls: Every argument tuple the widget passed, so a test can assert on
            the dialog title, the starting directory and the options.
    """

    result = ""
    calls: ClassVar[list[tuple[object, ...]]] = []

    class Option:
        """The subset of ``QFileDialog.Option`` the widgets pass through."""

        ShowDirsOnly = 1
        DontResolveSymlinks = 2

    @classmethod
    def getExistingDirectory(cls, *args: object) -> str:
        """Record the call and return the configured :attr:`result`."""
        cls.calls.append(args)
        return cls.result
