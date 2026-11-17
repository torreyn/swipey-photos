"""Tests for ``utils/logging_setup.py``: handlers, rotation and namespace."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from swipey_photos.utils.logging_setup import (
    BACKUP_COUNT,
    LOG_FILENAME,
    LOGGER_NAME,
    MAX_BYTES,
    LoggingSetupError,
    get_logger,
    logs_dir,
    setup_logging,
)

NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permission checks",
)


@pytest.fixture(autouse=True)
def _reset_logger() -> Iterator[None]:
    """Detach handlers before and after each test in this module."""
    logger = logging.getLogger(LOGGER_NAME)

    def detach() -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    detach()
    try:
        yield
    finally:
        detach()
        logger.setLevel(logging.WARNING)


def _file_handlers() -> list[RotatingFileHandler]:
    """Return the rotating handlers currently attached to the app logger."""
    return [
        handler
        for handler in logging.getLogger(LOGGER_NAME).handlers
        if isinstance(handler, RotatingFileHandler)
    ]


def _console_handlers() -> list[logging.Handler]:
    """Return stream handlers that are not file handlers."""
    return [
        handler
        for handler in logging.getLogger(LOGGER_NAME).handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, RotatingFileHandler)
    ]


def test_setup_creates_the_log_file(tmp_path: Path) -> None:
    """Logging is ready as soon as setup returns."""
    log_file = setup_logging(level="DEBUG", log_dir=tmp_path / "logs")

    assert log_file == tmp_path / "logs" / LOG_FILENAME
    assert log_file.exists()


def test_records_reach_the_file(tmp_path: Path) -> None:
    """Module loggers write through the shared handler."""
    log_file = setup_logging(level="DEBUG", log_dir=tmp_path / "logs")

    get_logger("test.writer").info("hello from the test suite")

    assert "hello from the test suite" in log_file.read_text(encoding="utf-8")
    assert f"{LOGGER_NAME}.test.writer" in log_file.read_text(encoding="utf-8")


def test_rotation_limits_are_configured(tmp_path: Path) -> None:
    """The file cannot grow without bound."""
    setup_logging(log_dir=tmp_path / "logs")

    handler = _file_handlers()[0]

    assert handler.maxBytes == MAX_BYTES
    assert handler.backupCount == BACKUP_COUNT


def test_repeated_setup_is_idempotent(tmp_path: Path) -> None:
    """Calling setup twice must not duplicate records."""
    first = setup_logging(log_dir=tmp_path / "logs")
    second = setup_logging(log_dir=tmp_path / "logs")

    assert first == second
    assert len(_file_handlers()) == 1


def test_force_rebuilds_the_handler(tmp_path: Path) -> None:
    """``force`` replaces the handler in place."""
    setup_logging(log_dir=tmp_path / "logs")

    setup_logging(log_dir=tmp_path / "logs", force=True)

    assert len(_file_handlers()) == 1


def test_console_handler_is_opt_in(tmp_path: Path) -> None:
    """Desktop launches stay quiet; the CLI passes ``console=True``."""
    setup_logging(log_dir=tmp_path / "logs")
    assert _console_handlers() == []

    setup_logging(log_dir=tmp_path / "logs", console=True)

    assert len(_console_handlers()) == 1


def test_unknown_level_names_raise(tmp_path: Path) -> None:
    """A typo in the level must fail loudly at start-up."""
    with pytest.raises(ValueError, match="unknown log level"):
        setup_logging(level="CHATTY", log_dir=tmp_path / "logs")


def test_level_filters_noisy_records(tmp_path: Path) -> None:
    """``level`` really filters, it is not decorative."""
    log_file = setup_logging(level="WARNING", log_dir=tmp_path / "logs")
    logger = get_logger("quiet")

    logger.info("dropped")
    logger.error("kept")

    contents = log_file.read_text(encoding="utf-8")
    assert "kept" in contents
    assert "dropped" not in contents


def test_numeric_levels_are_accepted(tmp_path: Path) -> None:
    """Programmatic callers may pass ``logging.DEBUG`` directly."""
    log_file = setup_logging(level=logging.DEBUG, log_dir=tmp_path / "logs")

    get_logger("numeric").debug("numeric level works")

    assert "numeric level works" in log_file.read_text(encoding="utf-8")


def test_logs_dir_follows_xdg_data_home(xdg_dirs: dict[str, Path]) -> None:
    """Logs live beside application data, per the XDG spec."""
    assert logs_dir() == xdg_dirs["XDG_DATA_HOME"] / "swipey-photos" / "logs"


def test_logs_dir_falls_back_to_local_share(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented default is ``~/.local/share/swipey-photos/logs``."""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    assert logs_dir() == Path.home() / ".local" / "share" / "swipey-photos" / "logs"


def test_get_logger_keeps_one_namespace() -> None:
    """Short names are prefixed once, full names are left alone."""
    assert get_logger("sorter").name == "swipey_photos.sorter"
    assert get_logger("swipey_photos.core.sorter").name == "swipey_photos.core.sorter"
    assert get_logger(LOGGER_NAME).name == LOGGER_NAME


@NOT_ROOT
def test_setup_reports_an_unusable_directory(tmp_path: Path) -> None:
    """A read-only parent is an error the caller can show to the user."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(LoggingSetupError, match="could not create log directory"):
            setup_logging(log_dir=locked / "logs")
    finally:
        locked.chmod(0o700)


def test_log_directory_is_private(tmp_path: Path) -> None:
    """Logs contain paths, so the directory is created owner-only."""
    directory = tmp_path / "logs"

    setup_logging(log_dir=directory)

    assert directory.stat().st_mode & 0o777 == 0o700
