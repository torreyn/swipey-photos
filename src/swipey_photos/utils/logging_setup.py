"""Logging configuration shared by the CLI, UI and core layers.

Responsibility
    Configure the standard :mod:`logging` hierarchy exactly once and write a
    rotating log file under the XDG data directory so that long sorting
    sessions can never fill the disk. Provides the single namespace every
    module logs through. Qt's own message handler lives in the UI layer, which
    keeps this module importable without Qt.

Public API
    LOGGER_NAME, LOG_FILENAME, LOG_FORMAT, MAX_BYTES, BACKUP_COUNT
    LoggingSetupError               the log directory or file is unusable
    logs_dir()                      $XDG_DATA_HOME/swipey-photos/logs
    setup_logging(level, log_dir, console, force) -> Path
        Idempotent; returns the log file path. ``RotatingFileHandler`` with
        ``maxBytes=2 MiB`` and ``backupCount=3``.
    get_logger(name)                logger inside the ``swipey_photos`` tree

Conventions
    * ``LOGGER = get_logger(__name__)`` at module import time.
    * ``INFO`` lifecycle events, ``DEBUG`` per-image decisions, ``WARNING``
      skipped files and degraded behaviour, ``ERROR`` failed moves (always
      with the path).
    * Never log file contents; paths are acceptable because the app is local.
    * No ``print()`` anywhere in ``src/``; the only stdout is ``--version``.
    * ``propagate`` stays enabled so pytest's ``caplog`` sees every record.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "swipey_photos"
APP_DIR_NAME = "swipey-photos"
LOG_FILENAME = "swipey-photos.log"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
DIRECTORY_MODE = 0o700


class LoggingSetupError(Exception):
    """Raised when the log directory or the log file cannot be created."""


def logs_dir() -> Path:
    """Return the log directory, ``$XDG_DATA_HOME/swipey-photos/logs``."""
    root = os.environ.get("XDG_DATA_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME / "logs"


def get_logger(name: str) -> logging.Logger:
    """Return a logger inside the single ``swipey_photos`` namespace."""
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def _coerce_level(level: str | int) -> int:
    """Translate a level name such as ``"info"`` into its numeric value."""
    if isinstance(level, int):
        return level
    resolved = logging.getLevelNamesMapping().get(level.strip().upper())
    if resolved is None:
        raise ValueError(f"unknown log level: {level!r}")
    return resolved


def _detach_handlers() -> None:
    """Remove and close every handler on the application logger."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _file_handler_for(log_file: Path) -> RotatingFileHandler | None:
    """Return the handler already writing to ``log_file``, if any."""
    for handler in logging.getLogger(LOGGER_NAME).handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_file:
            return handler
    return None


def _has_console_handler() -> bool:
    """Return ``True`` when a non-file stream handler is attached."""
    return any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler)
        for handler in logging.getLogger(LOGGER_NAME).handlers
    )


def setup_logging(
    *,
    level: str | int = "INFO",
    log_dir: Path | None = None,
    console: bool = False,
    force: bool = False,
) -> Path:
    """Configure the application logger and return the active log file path.

    Args:
        level: Level name (``"DEBUG"`` .. ``"CRITICAL"``) or numeric level.
        log_dir: Override for the log directory; defaults to :func:`logs_dir`.
        console: Also echo records to stderr (CLI runs, not desktop launches).
        force: Rebuild the handlers even when already configured (tests).

    Raises:
        ValueError: ``level`` is not a known logging level.
        LoggingSetupError: the log directory or log file cannot be created.

    The call is idempotent: repeated calls with the same arguments reuse the
    existing handlers instead of stacking duplicates.
    """
    directory = Path(log_dir).expanduser() if log_dir is not None else logs_dir()
    log_file = directory / LOG_FILENAME
    numeric_level = _coerce_level(level)
    logger = logging.getLogger(LOGGER_NAME)

    existing = _file_handler_for(log_file)
    if existing is not None and not force and (not console or _has_console_handler()):
        existing.setLevel(numeric_level)
        logger.setLevel(numeric_level)
        return log_file

    try:
        directory.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    except OSError as exc:
        raise LoggingSetupError(
            f"could not create log directory {directory}: {exc.strerror}"
        ) from exc

    _detach_handlers()
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        raise LoggingSetupError(f"could not open log file {log_file}: {exc.strerror}") from exc
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)
    logger.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(numeric_level)
        logger.addHandler(stream_handler)

    logger.debug("logging initialised: file=%s level=%s console=%s", log_file, level, console)
    return log_file
