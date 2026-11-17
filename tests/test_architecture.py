"""Architecture guardrails for the layered design.

The rules below are documented in ``docs/ARCHITECTURE.md`` and
``CONTRIBUTING.md``; this module turns them into failing tests so the design
cannot rot silently:

* ``core`` and ``utils`` never import a Qt binding.
* ``core`` never imports ``ui``.
* ``utils`` never imports ``core`` or ``ui``.
* every module explains its responsibility in a docstring.
* our own functions, methods and signals are ``snake_case`` and classes are
  ``PascalCase``; only Qt virtual overrides keep Qt's camelCase spelling.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
PACKAGE_ROOT = SRC_ROOT / "swipey_photos"
QT_BINDINGS = {"PyQt6", "PySide6"}
QT_FREE_LAYERS = ("core", "utils")

SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][A-Za-z0-9]*$")

# The only sanctioned camelCase in ``src/``: Qt dispatches virtual methods by
# their exact name, so M2's widget subclasses cannot rename them.
QT_OVERRIDES = frozenset(
    {
        "changeEvent",
        "closeEvent",
        "contextMenuEvent",
        "dragEnterEvent",
        "dragLeaveEvent",
        "dragMoveEvent",
        "dropEvent",
        "enterEvent",
        "event",
        "eventFilter",
        "focusInEvent",
        "focusOutEvent",
        "hideEvent",
        "keyPressEvent",
        "keyReleaseEvent",
        "leaveEvent",
        "minimumSizeHint",
        "mouseDoubleClickEvent",
        "mouseMoveEvent",
        "mousePressEvent",
        "mouseReleaseEvent",
        "moveEvent",
        "paintEvent",
        "resizeEvent",
        "showEvent",
        "sizeHint",
        "wheelEvent",
    }
)


def _module_name(path: Path) -> str:
    """Return the dotted import name for a file below ``src/``."""
    parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path) -> set[str]:
    """Return every absolute module name imported by ``path``.

    Relative imports are resolved against the importing file's package so that
    ``from ..ui import main_window`` in ``core/sorter.py`` becomes
    ``swipey_photos.ui`` and can be checked like any absolute import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name = _module_name(path)
    package_parts = module_name.split(".")
    if path.name != "__init__.py":
        package_parts = package_parts[:-1]

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                if node.module:
                    base = [*base, *node.module.split(".")]
                imported.add(".".join(base))
            elif node.module:
                imported.add(node.module)
    return imported


def _layer_files(layer: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", QT_FREE_LAYERS)
def test_layer_does_not_import_qt(layer: str) -> None:
    """Qt objects must not leak below the UI layer."""
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in _layer_files(layer)
        for module in _imported_modules(path)
        if module.split(".")[0] in QT_BINDINGS
    ]
    assert not violations, "Qt import(s) outside swipey_photos/ui:\n" + "\n".join(violations)


def test_core_does_not_import_ui() -> None:
    """Dependencies point downwards only: ``core`` must not know about widgets."""
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in _layer_files("core")
        for module in _imported_modules(path)
        if module == "swipey_photos.ui" or module.startswith("swipey_photos.ui.")
    ]
    assert not violations, "\n".join(violations)


def test_utils_does_not_import_core_or_ui() -> None:
    """``utils`` is the bottom of the stack and must stay dependency-free."""
    forbidden = ("swipey_photos.core", "swipey_photos.ui")
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} imports {module}"
        for path in _layer_files("utils")
        for module in _imported_modules(path)
        if any(module == name or module.startswith(f"{name}.") for name in forbidden)
    ]
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "path",
    sorted(PACKAGE_ROOT.rglob("*.py")),
    ids=lambda path: str(path.relative_to(PACKAGE_ROOT)),
)
def test_every_module_documents_its_responsibility(path: Path) -> None:
    """Each module starts with a docstring describing what it owns."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring = ast.get_docstring(tree)
    assert docstring, f"{path.relative_to(PACKAGE_ROOT)} has no module docstring"
    assert len(docstring.split()) >= 10, (
        f"{path.relative_to(PACKAGE_ROOT)} docstring is too terse to explain its role"
    )


def _package_files() -> list[Path]:
    """Return every module in the shipped package."""
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_functions_and_methods_use_snake_case() -> None:
    """Our API is snake_case; only Qt virtual overrides may be camelCase."""
    violations: list[str] = []
    for path in _package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            name = node.name
            is_dunder = name.startswith("__") and name.endswith("__")
            if name in QT_OVERRIDES or is_dunder:
                continue
            if not SNAKE_CASE.match(name):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} {name}()")
    assert not violations, "functions and methods must be snake_case:\n" + "\n".join(violations)


def test_classes_use_pascal_case() -> None:
    """Classes, enums, exceptions and dataclasses are PascalCase."""
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} {node.name}"
        for path in _package_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.ClassDef) and not PASCAL_CASE.match(node.name)
    ]
    assert not violations, "classes must be PascalCase:\n" + "\n".join(violations)
