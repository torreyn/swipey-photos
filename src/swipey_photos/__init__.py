"""Swipey Photos — sort a folder of images with Tinder-style swipe gestures.

A small Linux desktop application built with PyQt6. The user opens a folder,
sees one image at a time, and swipes it in one of four directions; the file is
moved into the matching subfolder (``Good/``, ``Bad/``, ``Great/`` or ``OK/``)
and the next image is shown.

Package layout (imports point strictly downwards)::

    app.py        →  ui/  →  core/  →  utils/

Attributes:
    __version__: The installed package version, sourced from ``pyproject.toml``
        by the Hatch version hook. Do not hard-code this value elsewhere.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
