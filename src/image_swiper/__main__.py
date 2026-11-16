"""Command-line entry point for ImageSwiper.

This module is the only supported way to start the application. It is reachable
in two ways:

* ``python -m image_swiper`` — used while developing from a source checkout.
* ``image-swiper`` — the console script declared in ``pyproject.toml`` as
  ``image-swiper = image_swiper.__main__:main``.

Responsibilities
    1. Parse the small command-line surface (an optional starting folder,
       ``--version``, ``--config``, ``--log-level``, ``--verbose`` and
       ``--dry-run``).
       Argument parsing lives here rather than in :mod:`image_swiper.app` so the
       app module stays importable without touching ``sys.argv``.
    2. Configure logging with :func:`image_swiper.utils.logging_setup.setup_logging`
       before anything can fail, so startup problems reach the log file.
    3. Delegate to :func:`image_swiper.app.run` and return its exit code.

Design notes
    * ``--version`` is answered before Qt is imported, so it also works on a
      machine where no display (or no Qt platform plugin) is available.
    * A failure to set up logging is reported on stderr and is *not* fatal: a
      read-only data directory must not prevent sorting photos.
    * ``main()`` never calls ``sys.exit`` itself; the ``if __name__`` block and
      the console-script wrapper do that, which keeps it unit-testable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .app import run
from .utils.logging_setup import LoggingSetupError, setup_logging

LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
"""Levels accepted by ``--log-level``."""


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser used by :func:`main`.

    Returns:
        A parser for ``image-swiper [FOLDER] [options]`` with ``--help`` text
        that mirrors the documented CLI.
    """
    parser = argparse.ArgumentParser(
        prog="image-swiper",
        description=(
            "Sort a folder of photos into Good, Bad, Great and OK subfolders by "
            "swiping or pressing a key."
        ),
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        help="folder to open immediately instead of showing the folder picker",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the version and exit",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="read and write this configuration file instead of the XDG default",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVELS,
        metavar="LEVEL",
        help=f"file log level, one of {', '.join(LOG_LEVELS)} (default: INFO)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log at DEBUG level and echo the log to stderr",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "log what would be moved without touching any file; useful for trying "
            "the app on a folder you do not want to sort yet"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code.

    Args:
        argv: Optional argument vector to use instead of ``sys.argv[1:]``.
            Useful for tests that exercise the CLI without spawning a process.

    Returns:
        ``0`` on a clean shutdown, non-zero on startup failure.
    """
    args = build_parser().parse_args(argv)

    level = "DEBUG" if args.verbose else args.log_level
    try:
        log_file = setup_logging(level=level, console=args.verbose)
    except (LoggingSetupError, ValueError) as exc:
        print(f"warning: logging is unavailable ({exc})", file=sys.stderr)
    else:
        if args.verbose:
            print(f"logging to {log_file}", file=sys.stderr)

    if args.version:
        print(f"ImageSwiper {__version__}")
        return 0

    return run(
        argv=[sys.argv[0]],
        config_path=args.config,
        folder=args.folder,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
