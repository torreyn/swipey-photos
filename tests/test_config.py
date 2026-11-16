"""Tests for ``utils/config.py``: defaults, JSON round-trip and validation."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

import pytest

from image_swiper.utils.config import (
    CONFIG_VERSION,
    Config,
    ConfigError,
    ConfigValidationError,
    WindowConfig,
    config_dir,
    config_path,
    default_config,
    from_dict,
    load_config,
    save_config,
    to_dict,
    validate_config,
)

LOGGER_NAME = "image_swiper"
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")


def _write_json(path: Path, payload: object) -> Path:
    """Write ``payload`` as JSON at ``path`` and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_config_uses_the_documented_values() -> None:
    """Defaults are stable; the UI relies on them before the first save."""
    config = default_config()

    assert config.version == CONFIG_VERSION
    assert config.last_folder is None
    assert config.window == WindowConfig(width=1200, height=800)
    assert config.theme == "system"


def test_config_dir_follows_xdg(xdg_dirs: dict[str, Path]) -> None:
    """``XDG_CONFIG_HOME`` decides where the file lives."""
    assert config_dir() == xdg_dirs["XDG_CONFIG_HOME"] / "image-swiper"
    assert config_path() == config_dir() / "config.json"


def test_config_dir_falls_back_to_dot_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the variable the documented path ``~/.config`` is used."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert config_dir() == Path.home() / ".config" / "image-swiper"


def test_missing_file_returns_defaults(xdg_dirs: dict[str, Path]) -> None:
    """First launch is not an error."""
    assert load_config() == default_config()


def test_round_trip_preserves_every_field(xdg_dirs: dict[str, Path], tmp_path: Path) -> None:
    """Saving then loading returns an equal configuration."""
    config = Config(
        last_folder=tmp_path / "photos",
        window=WindowConfig(width=1024, height=768),
        theme="light",
    )

    written = save_config(config)

    assert written == config_path()
    assert load_config() == config


def test_saved_file_contains_the_documented_keys(xdg_dirs: dict[str, Path]) -> None:
    """The on-disk schema is plain, indented JSON."""
    save_config(Config(theme="dark"))

    payload = json.loads(config_path().read_text(encoding="utf-8"))

    assert payload == {
        "version": CONFIG_VERSION,
        "last_folder": None,
        "window": {"width": 1200, "height": 800},
        "theme": "dark",
    }


@POSIX_ONLY
def test_saved_file_is_private(xdg_dirs: dict[str, Path]) -> None:
    """Configuration may contain private paths, so it is owner-only."""
    save_config(Config())

    assert stat.S_IMODE(config_path().stat().st_mode) == 0o600


def test_save_creates_missing_parent_directories(tmp_path: Path) -> None:
    """A custom path gets its parents created."""
    target = tmp_path / "deep" / "nested" / "config.json"

    save_config(Config(), target)

    assert target.exists()


def test_atomic_write_leaves_no_temporary_files(xdg_dirs: dict[str, Path]) -> None:
    """The tempfile used for atomicity is renamed into place."""
    save_config(Config())

    assert [entry.name for entry in config_dir().iterdir()] == ["config.json"]


def test_malformed_json_raises(tmp_path: Path) -> None:
    """A corrupt file is surfaced, not silently replaced by defaults."""
    target = tmp_path / "config.json"
    target.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(target)


def test_non_object_json_raises(tmp_path: Path) -> None:
    """A JSON array is not a configuration."""
    target = _write_json(tmp_path / "config.json", [1, 2, 3])

    with pytest.raises(ConfigError, match="must be a JSON object"):
        load_config(target)


def test_unknown_top_level_keys_only_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Forward compatibility: a newer build may add keys."""
    target = _write_json(tmp_path / "config.json", {"theme": "dark", "mystery": 42})

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        config = load_config(target)

    assert config.theme == "dark"
    assert any("mystery" in record.getMessage() for record in caplog.records)


def test_unknown_window_keys_only_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Nested unknown keys behave like top-level ones."""
    target = _write_json(tmp_path / "config.json", {"window": {"width": 800, "depth": 3}})

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        config = load_config(target)

    assert config.window == WindowConfig(width=800, height=800)
    assert any("depth" in record.getMessage() for record in caplog.records)


def test_newer_config_version_falls_back_to_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A file from a future release is not parsed half-way."""
    target = _write_json(tmp_path / "config.json", {"version": CONFIG_VERSION + 1, "theme": "dark"})

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        config = load_config(target)

    assert config == default_config()
    assert any("newer" in record.getMessage() for record in caplog.records)


def test_invalid_theme_raises(tmp_path: Path) -> None:
    """Themes are a closed set."""
    target = _write_json(tmp_path / "config.json", {"theme": "neon"})

    with pytest.raises(ConfigValidationError, match="theme must be one of"):
        load_config(target)


def test_window_size_bounds_are_enforced(tmp_path: Path) -> None:
    """Absurd window sizes are rejected with the allowed range."""
    target = _write_json(tmp_path / "config.json", {"window": {"width": 10, "height": 900}})

    with pytest.raises(ConfigValidationError, match=r"window\.width must be between"):
        load_config(target)


def test_validation_collects_every_problem() -> None:
    """The user sees all problems at once, not one per attempt."""
    broken = Config(theme="neon", window=WindowConfig(width=1, height=50000))

    with pytest.raises(ConfigValidationError) as caught:
        validate_config(broken)

    message = str(caught.value)
    assert "theme" in message
    assert "window.width" in message
    assert "window.height" in message


def test_save_refuses_invalid_configuration(xdg_dirs: dict[str, Path]) -> None:
    """Nothing is written when validation fails."""
    with pytest.raises(ConfigValidationError):
        save_config(Config(theme="neon"))

    assert not config_path().exists()


def test_last_folder_is_stored_as_a_string(tmp_path: Path) -> None:
    """Paths survive the JSON round-trip."""
    payload = to_dict(Config(last_folder=tmp_path / "photos"))

    assert payload["last_folder"] == str(tmp_path / "photos")


def test_blank_last_folder_becomes_none(tmp_path: Path) -> None:
    """An empty string means "no folder chosen", not the current directory."""
    target = _write_json(tmp_path / "config.json", {"last_folder": "   "})

    assert load_config(target).last_folder is None


def test_from_dict_accepts_an_empty_object() -> None:
    """A file containing ``{}`` is valid and yields defaults."""
    assert from_dict({}) == default_config()


def test_from_dict_requires_integer_sizes(tmp_path: Path) -> None:
    """``"800"`` is a string, not a width."""
    target = _write_json(tmp_path / "config.json", {"window": {"width": "800"}})

    with pytest.raises(ConfigValidationError, match="must be an integer"):
        load_config(target)


def test_load_accepts_an_explicit_path(tmp_path: Path) -> None:
    """The UI can point the loader at a project-local file."""
    target = _write_json(tmp_path / "custom.json", {"theme": "light"})

    assert load_config(target).theme == "light"
