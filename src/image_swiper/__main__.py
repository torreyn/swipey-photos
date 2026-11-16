"""Command-line entry point for ImageSwiper.

This module is the only supported way to start the application. It is reachable
in two ways:

* ``python -m image_swiper`` — used while developing from a source checkout.
* ``image-swiper`` — the console script declared in ``pyproject.toml`` as
  ``image-swiper = image_swiper.__main__:main``.

Responsibilities (to be implemented in milestone M1):

1. Parse command-line arguments (``--version``, ``--verbose``, ``--config``,
   ``--move-mode``, optional starting folder). Argument parsing is intentionally
   kept here rather than in :mod:`image_swiper.app`, so the app module stays
   importable without touching ``sys.argv``.
2. Configure logging via :func:`image_swiper.utils.logging_setup.setup_logging`.
3. Delegate to :func:`image_swiper.app.run` and return its exit code.

The function below is a placeholder so the console-script entry point resolves
while the project is still scaffolding. It must not contain application logic.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code.

    Args:
        argv: Optional argument vector to use instead of ``sys.argv[1:]``.
            Useful for tests that exercise the CLI without spawning a process.

    Returns:
        ``0`` on a clean shutdown, non-zero on startup failure.

    Raises:
        NotImplementedError: Always, until the CLI milestone lands.
    """
    del argv  # Unused until the CLI milestone.
    raise NotImplementedError(
        "ImageSwiper is still scaffolding: the CLI and UI are not implemented yet. "
        "See docs/ARCHITECTURE.md and the roadmap in README.md."
    )


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
