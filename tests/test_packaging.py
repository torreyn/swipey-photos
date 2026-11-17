"""Desktop-integration contract for the files under ``packaging/``.

These tests are what keeps the release artefacts honest: the ``.desktop`` entry,
the icon theme tree and the two shell scripts are validated here instead of by
eyeballing a diff. They mirror ``packaging/`` the way the other modules mirror
``src/``.

Conventions
    * Nothing here needs a display, except the icon tests, which are marked
      ``gui`` because ``QPixmap`` requires a ``QGuiApplication``.
    * The shell scripts run with ``--destdir``/``--prefix`` pointed at
      ``tmp_path``; no test writes to ``$HOME`` or to ``$XDG_DATA_HOME``.
    * ``desktop-file-validate`` is used when the distribution provides it and
      skipped otherwise, so the suite stays usable on minimal systems.
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from image_swiper import app
from image_swiper.ui import branding, swipe_card

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DESKTOP_FILE = PACKAGING / "image-swiper.desktop"
ICON_TREE = PACKAGING / "icons" / "hicolor"
INSTALLER = PACKAGING / "install-desktop.sh"
BUILDER = PACKAGING / "appimage" / "build-appimage.sh"


def _desktop_entry() -> configparser.RawConfigParser:
    """Parse the desktop entry with case-sensitive keys, as the spec requires."""
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str  # type: ignore[assignment]
    parser.read(DESKTOP_FILE, encoding="utf-8")
    return parser


def _script_env(**overrides: str) -> dict[str, str]:
    """Return an environment for the shell scripts without XDG leaks."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/nonexistent"),
    }
    env.update(overrides)
    return env


def test_desktop_entry_declares_every_key_launchers_need() -> None:
    """The entry must be launchable from a menu without further tooling."""
    entry = _desktop_entry()["Desktop Entry"]

    assert entry["Type"] == "Application"
    assert entry["Version"] == "1.5"
    assert entry["Name"] == branding.APP_DISPLAY_NAME
    assert entry["Exec"]
    assert entry["TryExec"] == entry["Exec"]
    assert entry["Terminal"] == "false"
    assert entry["Categories"].startswith("Graphics;")
    assert entry["Categories"].endswith(";"), "spec requires a trailing semicolon"


def test_desktop_entry_passes_desktop_file_validate() -> None:
    """`desktop-file-validate` is the reference implementation of the spec."""
    validator = shutil.which("desktop-file-validate")
    if validator is None:
        pytest.skip("desktop-file-utils is not installed")

    result = subprocess.run(
        [validator, str(DESKTOP_FILE)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_desktop_entry_launches_the_packaged_console_script() -> None:
    """`Exec` must name the entry point declared in ``pyproject.toml``."""
    entry = _desktop_entry()["Desktop Entry"]
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = metadata["project"]["scripts"]

    executable = entry["Exec"].split()[0]
    assert executable in scripts

    # A %f/%U field code would hand the app a single *file*, which it does not
    # accept: ImageSwiper sorts folders.
    assert "%" not in entry["Exec"]
    assert "MimeType" not in entry


def test_desktop_identity_matches_the_qt_application() -> None:
    """Icon stem, desktop-file name and WM_CLASS come from one string."""
    entry = _desktop_entry()["Desktop Entry"]

    assert app.DESKTOP_FILE_NAME == DESKTOP_FILE.stem == branding.ICON_NAME
    assert entry["Icon"] == branding.ICON_NAME
    assert entry["StartupWMClass"] == app.DESKTOP_FILE_NAME


def test_icon_tree_covers_every_size_the_app_renders() -> None:
    """Every size in ``ICON_SIZES`` ships as a PNG, plus one scalable SVG."""
    expected_dirs = {f"{size}x{size}" for size in branding.ICON_SIZES}
    actual_dirs = {path.name for path in ICON_TREE.glob("*x*") if path.is_dir()}

    assert actual_dirs == expected_dirs
    assert (ICON_TREE / "scalable" / "apps" / f"{branding.ICON_NAME}.svg").is_file()

    for size in branding.ICON_SIZES:
        icon = ICON_TREE / f"{size}x{size}" / "apps" / f"{branding.ICON_NAME}.png"
        with Image.open(icon) as image:
            assert image.size == (size, size)
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0))[3] == 0, f"{icon} needs a transparent corner"


def test_scalable_icon_carries_the_brand_palette() -> None:
    """The committed SVG is the mark, not a stale placeholder."""
    svg = (ICON_TREE / "scalable" / "apps" / f"{branding.ICON_NAME}.svg").read_text(
        encoding="utf-8"
    )

    assert "<svg" in svg
    assert 'viewBox="0 0 512 512"' in svg
    assert branding.APP_DISPLAY_NAME in svg
    for colour in ("#1f4e79", "#7b3f9d"):
        assert colour in svg, f"missing tile gradient stop {colour}"
    for category in ("Bad", "Good"):
        assert swipe_card.CATEGORY_COLORS[category].lower() in svg.lower()


@pytest.mark.gui
def test_scalable_icon_renders_the_mark(qtbot: object) -> None:
    """A renderer must see a transparent corner and the opaque middle card."""
    renderer = QSvgRenderer(str(ICON_TREE / "scalable" / "apps" / f"{branding.ICON_NAME}.svg"))
    assert renderer.isValid()

    image = QImage(QSize(256, 256), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    assert image.pixelColor(2, 2).alpha() == 0
    assert image.pixelColor(128, 128).red() > 200
    assert image.pixelColor(128, 128).green() > 200


@pytest.mark.gui
def test_export_icons_writes_a_complete_hicolor_tree(qtbot: object, tmp_path: Path) -> None:
    """``branding.export_icons`` is the source the committed tree came from."""
    written = branding.export_icons(tmp_path, sizes=(48, 64))

    assert [path.name for path in written] == [
        f"{branding.ICON_NAME}.svg",
        f"{branding.ICON_NAME}.png",
        f"{branding.ICON_NAME}.png",
    ]
    scalable = tmp_path / "hicolor" / "scalable" / "apps" / f"{branding.ICON_NAME}.svg"
    assert scalable.is_file()
    for size in (48, 64):
        icon = tmp_path / "hicolor" / f"{size}x{size}" / "apps" / f"{branding.ICON_NAME}.png"
        with Image.open(icon) as image:
            assert image.size == (size, size)


@pytest.mark.parametrize("sizes", [(), (0,), (-8,)])
def test_export_icons_rejects_impossible_sizes(sizes: tuple[int, ...]) -> None:
    """A zero-sized icon would silently produce an unusable theme entry."""
    with pytest.raises(ValueError):
        branding.export_icons(Path("/nonexistent"), sizes=sizes)


def test_installer_installs_and_removes_the_desktop_files(tmp_path: Path) -> None:
    """The installer writes the documented layout and can undo itself."""
    stage = tmp_path / "stage"

    install = subprocess.run(
        ["sh", str(INSTALLER), "--prefix", "/usr", "--destdir", str(stage)],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(),
    )
    assert install.returncode == 0, install.stderr

    entry = stage / "usr" / "share" / "applications" / "image-swiper.desktop"
    assert entry.read_text(encoding="utf-8") == DESKTOP_FILE.read_text(encoding="utf-8")
    icons = sorted((stage / "usr" / "share" / "icons" / "hicolor").glob("*x*/apps/*.png"))
    assert len(icons) == len(branding.ICON_SIZES)
    assert (stage / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps").is_dir()

    remove = subprocess.run(
        ["sh", str(INSTALLER), "--prefix", "/usr", "--destdir", str(stage), "--uninstall"],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(),
    )
    assert remove.returncode == 0, remove.stderr
    assert not entry.exists()
    assert not list((stage / "usr" / "share" / "icons" / "hicolor").glob("*x*/apps/*"))


def test_installer_defaults_to_xdg_data_home(tmp_path: Path) -> None:
    """Without --prefix the files go to ``$XDG_DATA_HOME``, not to ``$HOME``."""
    data_home = tmp_path / "xdg"

    result = subprocess.run(
        ["sh", str(INSTALLER)],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(XDG_DATA_HOME=str(data_home)),
    )

    assert result.returncode == 0, result.stderr
    assert (data_home / "applications" / "image-swiper.desktop").is_file()
    assert (data_home / "icons" / "hicolor" / "256x256" / "apps" / "image-swiper.png").is_file()


@pytest.mark.parametrize("script", [INSTALLER, BUILDER])
def test_scripts_reject_unknown_arguments(script: Path) -> None:
    """Unknown options must fail loudly instead of half-doing the job."""
    result = subprocess.run(
        ["sh", str(script), "--nonsense"],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(),
    )

    assert result.returncode == 2
    assert "unknown argument" in result.stderr


@pytest.mark.parametrize("script", [INSTALLER, BUILDER])
def test_shell_scripts_are_syntactically_valid(script: Path) -> None:
    """``sh -n`` catches what a Python-only test run would otherwise miss."""
    result = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_appimage_builder_documents_its_contract() -> None:
    """``--help`` must be reachable without Python or appimagetool present."""
    result = subprocess.run(
        ["sh", str(BUILDER), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(),
    )

    assert result.returncode == 0
    assert "--staging-only" in result.stdout
    assert "APPIMAGE_PIP_ARGS" in result.stdout


def test_sdist_ships_the_packaging_directory() -> None:
    """Packagers build from the sdist, so it has to contain ``packaging/``."""
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    assert "/packaging" in include
