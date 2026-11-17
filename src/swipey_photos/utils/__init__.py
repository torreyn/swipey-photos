"""Cross-cutting helpers shared by the core and UI layers.

Responsibility
    Small, dependency-light utilities that know nothing about images, swipe
    gestures or widgets: safe filesystem primitives, persisted configuration,
    logging setup and handing a URL to the desktop's browser.

Contains
    file_ops.py       Collision-safe move/copy, reverse move for undo, unique
                      filename generation, path expansion and validation.
    config.py         Frozen default config, JSON load/save, XDG config paths,
                      schema validation and forward-compatible migrations.
    logging_setup.py  Idempotent logging configuration (rotating file handler
                      plus an optional console handler); no Qt imports.
    browser.py        Open a URL through ``xdg-open``/``gio open``/``webbrowser``
                      and report when no launcher could take it; no Qt imports.

Boundary rules
    * May import the standard library and, at most, Pillow-adjacent helpers.
      Never ``core``, never ``ui``, never ``PyQt6``.
    * No user interaction: these functions raise typed exceptions and let the
      caller decide how to report them.
    * Pure functions where possible; anything touching the filesystem takes
      explicit ``Path`` arguments so tests can use ``tmp_path``.

See ``docs/ARCHITECTURE.md`` and ``docs/CONFIGURATION.md``.
"""
