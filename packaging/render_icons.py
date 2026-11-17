#!/usr/bin/env python3
"""Regenerate ``packaging/icons`` from :mod:`image_swiper.ui.branding`.

The application paints its brand mark at runtime, but desktop integration needs
real files: ``packaging/image-swiper.desktop`` points ``Icon=image-swiper`` at
the icon theme, and AppImage bundlers copy the same tree. This script is the
bridge — run it after any change to ``branding.py`` and commit the result::

    QT_QPA_PLATFORM=offscreen python packaging/render_icons.py

The ``QT_QPA_PLATFORM`` prefix is only needed on a headless machine (CI, a
container, an SSH session): ``QPixmap`` needs a platform plugin, and the
offscreen one is enough because nothing is ever shown. ``tests/test_packaging.py``
renders the same mark and fails when the committed files drift.

Options:
    --out DIR     write the hicolor tree below DIR (default: packaging/icons)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
"""Repository root, used to import ``src/`` without an editable install."""

DEFAULT_OUTPUT = ROOT / "packaging" / "icons"
"""Where the committed icon tree lives."""


def build_parser() -> argparse.ArgumentParser:
    """Return the parser for ``render_icons.py``."""
    parser = argparse.ArgumentParser(
        prog="render_icons.py",
        description="Regenerate the freedesktop icon tree from ui/branding.py.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="DIR",
        help="write the hicolor tree below DIR (default: packaging/icons)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Render the icons and print every file that was written.

    Args:
        argv: Argument vector, ``sys.argv[1:]`` when ``None``.

    Returns:
        ``0``; the script only fails through an exception (for example a Qt
        platform plugin that cannot start).
    """
    args = build_parser().parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))

    from PyQt6.QtWidgets import QApplication

    from image_swiper.ui.branding import export_icons

    # Keep a reference: PyQt drops the application object (and with it the
    # backing store QPixmap needs) as soon as nothing points at it any more.
    _app = QApplication.instance() or QApplication([sys.argv[0]])

    for path in export_icons(args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
