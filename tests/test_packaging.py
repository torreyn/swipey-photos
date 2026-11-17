"""Release contract for everything outside ``src/``.

These tests are what keeps the release artefacts honest: the ``.desktop`` entry,
the icon theme tree, the install and build scripts, the PyInstaller recipe, the
GitHub workflows, the changelog and the sdist manifest are validated here instead
of by eyeballing a diff. They mirror the repository layout the way the other
modules mirror ``src/``.

Conventions
    * Nothing here needs a display, except the icon tests, which are marked
      ``gui`` because ``QPixmap`` requires a ``QGuiApplication``.
    * The shell scripts run with ``--destdir``/``--prefix`` pointed at
      ``tmp_path``; no test writes to ``$HOME`` or to ``$XDG_DATA_HOME``.
    * ``desktop-file-validate`` is used when the distribution provides it and
      skipped otherwise, so the suite stays usable on minimal systems.
    * The workflow assertions need PyYAML (part of the ``dev`` extra) and skip
      without it; the YAML is parsed, not grepped, because that is the failure
      mode GitHub would reject.
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from swipey_photos import app
from swipey_photos.ui import branding, swipe_card

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DESKTOP_FILE = PACKAGING / "swipey-photos.desktop"
ICON_TREE = PACKAGING / "icons" / "hicolor"
INSTALLER = PACKAGING / "install-desktop.sh"
BUILDER = PACKAGING / "appimage" / "build-appimage.sh"
SPEC_FILE = ROOT / "swipey-photos.spec"
BUILD_SCRIPT = ROOT / "scripts" / "build.sh"
WORKFLOWS = ROOT / ".github" / "workflows"
CHANGELOG = ROOT / "CHANGELOG.md"


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


def _workflow(name: str) -> dict[str, Any]:
    """Parse one GitHub workflow; skips when PyYAML is missing."""
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _job_runs(workflow: dict[str, Any], job: str) -> str:
    """Return every ``run:``/``uses:`` value of *job* as one searchable string."""
    steps = workflow["jobs"][job]["steps"]
    return "\n".join(str(step.get("run") or step.get("uses") or "") for step in steps)


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
    # accept: Swipey Photos sorts folders.
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

    entry = stage / "usr" / "share" / "applications" / "swipey-photos.desktop"
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
    assert (data_home / "applications" / "swipey-photos.desktop").is_file()
    assert (data_home / "icons" / "hicolor" / "256x256" / "apps" / "swipey-photos.png").is_file()


@pytest.mark.parametrize("script", [INSTALLER, BUILDER, BUILD_SCRIPT])
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


@pytest.mark.parametrize("script", [INSTALLER, BUILDER, BUILD_SCRIPT])
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


def test_appimage_builder_copes_with_a_machine_without_fuse() -> None:
    """CI runners and containers have no libfuse, so appimagetool must self-extract."""
    script = BUILDER.read_text(encoding="utf-8")

    # appimagetool ships as an AppImage: without a runtime it cannot mount itself.
    assert "--appimage-extract-and-run" in script
    assert "/dev/fuse" in script
    assert "libfuse" in script


def test_sdist_ships_the_packaging_directory() -> None:
    """Packagers build from the sdist, so it has to contain ``packaging/``."""
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    assert "/packaging" in include
    # Same reasoning for the binary recipe: a maintainer must be able to unpack
    # the sdist, run scripts/build.sh and get the released executable.
    assert "/swipey-photos.spec" in include
    assert "/scripts" in include
    assert "/CHANGELOG.md" in include


def test_pyinstaller_spec_freezes_a_one_file_windowed_binary() -> None:
    """One file, not a directory, started from the console-script entry point."""
    spec = SPEC_FILE.read_text(encoding="utf-8")

    assert 'name="swipey-photos"' in spec
    assert "console=False" in spec
    collect_calls = [line for line in spec.splitlines() if line.lstrip().startswith("COLLECT(")]
    assert not collect_calls, "COLLECT() would produce a directory instead of one file"
    # The launcher, not src/swipey_photos/__main__.py: PyInstaller runs the entry
    # script as top-level code, which breaks __main__.py's relative imports.
    assert '"entry.py"' in spec
    assert "pathex=[str(SRC)]" in spec, "src/ has to be importable during the analysis"
    assert 'excludes=["tkinter"]' in spec


def test_pyinstaller_launcher_delegates_to_the_console_entry_point() -> None:
    """The frozen binary must behave exactly like the ``swipey-photos`` script."""
    launcher = (PACKAGING / "pyinstaller" / "entry.py").read_text(encoding="utf-8")

    assert "from swipey_photos.__main__ import main" in launcher
    assert "SystemExit(main())" in launcher


def test_pyinstaller_spec_points_at_a_shipped_icon() -> None:
    """The ``icon=`` argument must name a file that exists, not a stale path."""
    spec = SPEC_FILE.read_text(encoding="utf-8")
    icon = ICON_TREE / "256x256" / "apps" / f"{branding.ICON_NAME}.png"

    assert '"packaging" / "icons" / "hicolor" / "256x256"' in spec
    assert f'"{branding.ICON_NAME}.png"' in spec
    assert icon.is_file()


def test_build_script_is_executable_and_documents_its_contract() -> None:
    """``scripts/build.sh`` is run directly, so its mode is part of the contract."""
    assert os.access(BUILD_SCRIPT, os.X_OK), "commit scripts/build.sh with mode 755"

    result = subprocess.run(
        ["sh", str(BUILD_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_script_env(),
    )

    assert result.returncode == 0, result.stderr
    assert "dist/swipey-photos" in result.stdout
    assert "PIP_ARGS" in result.stdout


def test_ci_workflow_runs_the_documented_checks() -> None:
    """Lint, format, types and coverage run on the pinned image for 3.11 and 3.12."""
    ci = _workflow("ci.yml")
    matrix = ci["jobs"]["checks"]["strategy"]["matrix"]["python-version"]
    runs = _job_runs(ci, "checks")

    assert {"3.11", "3.12"} <= set(matrix)
    assert "ruff check ." in runs
    assert "ruff format --check ." in runs
    assert "mypy" in runs
    assert "--cov=swipey_photos" in runs
    # PyQt6 needs the xcb libraries before the first import, not just in the
    # GUI leg, because the unit tests import Qt too.
    assert "libxkbcommon-x11-0" in runs


def test_ci_workflow_runs_the_gui_tests_under_xvfb() -> None:
    """The offscreen plugin is not the xcb plugin a real desktop loads."""
    runs = _job_runs(_workflow("ci.yml"), "gui-xvfb")

    assert "xvfb-run" in runs
    assert "-m gui" in runs


def test_workflows_pin_a_fixed_runner_image() -> None:
    """``ubuntu-latest`` moves to a new Ubuntu on its own; these builds must not.

    The AppImage is staged against the host's Qt client libraries and
    appimagetool, so a surprise image bump is a release failure, not an
    upgrade. ``ubuntu-latest`` starts migrating to Ubuntu 26 on 2026-10-19.
    """
    for name in ("ci.yml", "release.yml"):
        workflow = _workflow(name)
        for job, config in workflow["jobs"].items():
            assert config["runs-on"] == "ubuntu-24.04", f"{name}: {job} floats its runner image"


def test_release_workflow_attaches_every_artefact_to_a_tagged_release() -> None:
    """A ``v*`` tag produces one release with binary, AppImage, wheel and sdist."""
    release = _workflow("release.yml")
    # PyYAML resolves the unquoted `on:` key to boolean True (YAML 1.1).
    triggers = release.get("on") or release.get(True)

    assert triggers["push"]["tags"] == ["v*"]
    assert "workflow_dispatch" in triggers

    jobs = release["jobs"]
    assert jobs["publish"]["needs"] == ["binary", "appimage", "dist"]
    assert jobs["publish"]["permissions"]["contents"] == "write"
    assert release["permissions"]["contents"] == "read", "only the publish job may write"

    binary_runs = _job_runs(release, "binary")
    assert "swipey-photos.spec" in binary_runs
    assert "--version" in binary_runs, "the binary is smoke-tested before it is uploaded"

    # The AppImage is built from the documented recipe, not from a copy of it.
    appimage_runs = _job_runs(release, "appimage")
    assert "packaging/appimage/build-appimage.sh" in appimage_runs
    assert "uv python install" in appimage_runs, "the bundle needs a relocatable CPython"
    assert "appimagetool-x86_64.AppImage" in appimage_runs
    assert "APPIMAGE_EXTRACT_AND_RUN=1" in appimage_runs, "runners ship no libfuse2"
    assert "--version" in appimage_runs, "the AppImage is smoke-tested before it is uploaded"

    assert "softprops/action-gh-release" in _job_runs(release, "publish")
    upload = next(
        step for step in jobs["publish"]["steps"] if "gh-release" in str(step.get("uses", ""))
    )
    assert upload["with"]["files"] == "release-assets/*"
    assert upload["with"]["tag_name"]


def test_changelog_follows_keep_a_changelog() -> None:
    """The changelog opens with Unreleased and already knows the shipped version."""
    from swipey_photos import __version__

    changelog = CHANGELOG.read_text(encoding="utf-8")

    assert changelog.startswith("# Changelog")
    assert "Keep a Changelog" in changelog
    assert "## [Unreleased]" in changelog
    assert f"## [{__version__}]" in changelog, "tag the version before releasing it"
