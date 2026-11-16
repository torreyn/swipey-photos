"""Persisted application configuration and XDG path helpers.

Responsibility
    Define the configuration schema as frozen dataclasses, provide sane
    defaults, read and write the user's JSON file, validate every value, and
    expose the XDG location used for it. No other module reads environment
    variables or hard-codes a config path, so tests can redirect everything by
    setting ``XDG_CONFIG_HOME``.

Public API
    CONFIG_VERSION, APP_DIR_NAME, CONFIG_FILE_NAME, THEMES
    ConfigError                     the file could not be read or parsed
    ConfigValidationError           a value is out of range or unknown
    WindowConfig(width, height)     remembered window size
    Config(version, last_folder, window, theme)
    config_dir() / config_path()    $XDG_CONFIG_HOME/image-swiper/config.json
    default_config()                defaults used when no file exists yet
    load_config(path=None) -> Config
    save_config(config, path=None) -> Path
    validate_config(config) -> None
    to_dict(config) / from_dict(data)

Behaviour
    * A missing file is not an error: defaults are returned. A malformed file
      raises :class:`ConfigError`; the caller decides whether to fall back.
    * Unknown keys and a newer ``version`` only warn (forward compatibility).
    * Writes are atomic: a temporary file in the same directory is fsynced,
      chmodded ``0o600`` and moved into place with ``os.replace``, so a crash
      never leaves a half-written config behind. The directory is ``0o700``.
    * ``last_folder`` is stored as an absolute, expanded path string or ``null``.

Schema reference and examples: ``docs/CONFIGURATION.md``.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .logging_setup import get_logger

LOGGER = get_logger(__name__)

CONFIG_VERSION = 1
APP_DIR_NAME = "image-swiper"
CONFIG_FILE_NAME = "config.json"
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES: tuple[str, ...] = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_SIZE = 200
MAX_WINDOW_SIZE = 20000

_KNOWN_KEYS: frozenset[str] = frozenset({"version", "last_folder", "window", "theme"})
_WINDOW_KEYS: frozenset[str] = frozenset({"width", "height"})


class ConfigError(Exception):
    """Raised when the configuration file cannot be read or parsed."""


class ConfigValidationError(ConfigError):
    """Raised when a configuration value is unknown or out of range."""


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """Remembered main-window size in logical pixels."""

    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT


@dataclass(frozen=True, slots=True)
class Config:
    """Everything the application persists between runs."""

    version: int = CONFIG_VERSION
    last_folder: Path | None = None
    window: WindowConfig = field(default_factory=WindowConfig)
    theme: str = THEME_SYSTEM


def config_dir() -> Path:
    """Return ``$XDG_CONFIG_HOME/image-swiper`` (``~/.config/...`` by default)."""
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / APP_DIR_NAME


def config_path() -> Path:
    """Return the absolute path of ``config.json`` inside :func:`config_dir`."""
    return config_dir() / CONFIG_FILE_NAME


def default_config() -> Config:
    """Return the configuration used when no file exists yet."""
    return Config()


def to_dict(config: Config) -> dict[str, object]:
    """Convert ``config`` into a JSON-serialisable dictionary."""
    return {
        "version": config.version,
        "last_folder": str(config.last_folder) if config.last_folder is not None else None,
        "window": {"width": config.window.width, "height": config.window.height},
        "theme": config.theme,
    }


def from_dict(data: Mapping[str, object]) -> Config:
    """Build a :class:`Config` from parsed JSON, warning about unknown keys.

    Raises:
        ConfigError: the structure is not an object with the expected shape.
        ConfigValidationError: a value has the wrong type.
    """
    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        LOGGER.warning("ignoring unknown config keys: %s", ", ".join(unknown))

    version = _as_int(data.get("version", CONFIG_VERSION), "version")
    if version > CONFIG_VERSION:
        LOGGER.warning(
            "config version %s is newer than supported version %s; using defaults",
            version,
            CONFIG_VERSION,
        )
        return default_config()

    window_data = _as_dict(data.get("window", {}), "window")
    unknown_window = sorted(set(window_data) - _WINDOW_KEYS)
    if unknown_window:
        LOGGER.warning("ignoring unknown window keys: %s", ", ".join(unknown_window))
    window = WindowConfig(
        width=_as_int(window_data.get("width", DEFAULT_WINDOW_WIDTH), "window.width"),
        height=_as_int(window_data.get("height", DEFAULT_WINDOW_HEIGHT), "window.height"),
    )

    return Config(
        version=CONFIG_VERSION,
        last_folder=_as_optional_path(data.get("last_folder")),
        window=window,
        theme=_as_str(data.get("theme", THEME_SYSTEM), "theme"),
    )


def validate_config(config: Config) -> None:
    """Raise :class:`ConfigValidationError` when any value is unusable.

    All problems are collected first so the user sees the complete list rather
    than fixing the file one error at a time.
    """
    problems: list[str] = []
    if config.version != CONFIG_VERSION:
        problems.append(f"version must be {CONFIG_VERSION}, got {config.version}")
    if config.theme not in THEMES:
        problems.append(f"theme must be one of {', '.join(THEMES)}, got {config.theme!r}")
    for name in ("width", "height"):
        value = getattr(config.window, name)
        if not MIN_WINDOW_SIZE <= value <= MAX_WINDOW_SIZE:
            problems.append(
                f"window.{name} must be between {MIN_WINDOW_SIZE} and {MAX_WINDOW_SIZE}, "
                f"got {value}"
            )
    if problems:
        raise ConfigValidationError("; ".join(problems))


def load_config(path: Path | None = None) -> Config:
    """Read and validate the configuration file.

    Args:
        path: Explicit file to read; defaults to :func:`config_path`.

    Returns:
        The parsed configuration, or :func:`default_config` when the file does
        not exist yet.

    Raises:
        ConfigError: the file exists but cannot be read or is not JSON.
        ConfigValidationError: the file parses but a value is unusable.
    """
    target = Path(path).expanduser() if path is not None else config_path()
    if not target.exists():
        LOGGER.debug("no config file at %s; using defaults", target)
        return default_config()

    try:
        raw_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read {target}: {exc.strerror}") from exc

    try:
        raw: object = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file {target} is not valid JSON: {exc.msg}") from exc

    config = from_dict(_as_dict(raw, "config"))
    validate_config(config)
    LOGGER.debug("loaded config from %s", target)
    return config


def save_config(config: Config, path: Path | None = None) -> Path:
    """Validate ``config`` and write it atomically to disk.

    Returns:
        The path that was written.

    Raises:
        ConfigValidationError: ``config`` contains an unusable value.
        ConfigError: the directory or file could not be written.
    """
    validate_config(config)
    target = Path(path).expanduser() if path is not None else config_path()
    payload = json.dumps(to_dict(config), indent=2, sort_keys=True) + "\n"

    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        descriptor, raw_name = tempfile.mkstemp(dir=target.parent, prefix=".config-", suffix=".tmp")
        temporary = Path(raw_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, FILE_MODE)
        os.replace(temporary, target)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ConfigError(f"could not write {target}: {exc.strerror}") from exc

    LOGGER.debug("saved config to %s", target)
    return target


def _as_dict(value: object, what: str) -> dict[str, object]:
    """Return ``value`` as a string-keyed dictionary or raise ConfigError."""
    if not isinstance(value, dict):
        raise ConfigError(f"{what} must be a JSON object, got {type(value).__name__}")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{what} keys must be strings, got {type(key).__name__}")
        result[key] = item
    return result


def _as_int(value: object, what: str) -> int:
    """Return ``value`` as an ``int`` (rejecting ``bool``) or raise."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError(f"{what} must be an integer, got {value!r}")
    return value


def _as_str(value: object, what: str) -> str:
    """Return ``value`` as a ``str`` or raise ConfigValidationError."""
    if not isinstance(value, str):
        raise ConfigValidationError(f"{what} must be a string, got {value!r}")
    return value


def _as_optional_path(value: object) -> Path | None:
    """Return ``value`` as an expanded :class:`Path`, ``None``, or raise."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigValidationError(f"last_folder must be a string or null, got {value!r}")
    if not value.strip():
        return None
    return Path(value).expanduser()
