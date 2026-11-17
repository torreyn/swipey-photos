"""Entry point for the PyInstaller build.

PyInstaller executes the file named in the ``Analysis`` call as top-level code,
so pointing it straight at ``src/image_swiper/__main__.py`` breaks that module's
relative imports with ``attempted relative import with no known parent package``.
Importing the package here keeps the normal ``__package__`` context and mirrors
the console script declared in ``pyproject.toml``
(``image-swiper = image_swiper.__main__:main``).

Nothing else belongs in this file: no argument parsing, no logging setup, no
imports of ``app`` (that would pull Qt into the startup path of ``--version``).
"""

from __future__ import annotations

from image_swiper.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
