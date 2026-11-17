# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the single-file ImageSwiper executable.

Build it with ``./scripts/build.sh``, or by hand from an environment that has the
project and PyInstaller installed:

    pip install ".[binary]"
    pyinstaller --clean --noconfirm image-swiper.spec

The result is ``dist/image-swiper``: one file carrying CPython, PyQt6 and Pillow,
so the target machine needs no Python. It still needs the Qt platform libraries
(``libxcb-cursor0``, ``libegl1``, …) listed in the README — a bundled Qt cannot
ship glibc or the X11 client libraries it links against.

Why a spec file instead of command-line flags: the frozen app must import
``image_swiper`` from ``src/``, which a plain ``pyinstaller src/...`` run cannot
resolve without ``--paths``. Keeping the recipe next to the source means CI,
``scripts/build.sh`` and a packager all get the same binary.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve()  # noqa: F821  # SPECPATH is injected by PyInstaller
SRC = ROOT / "src"
ICON = ROOT / "packaging" / "icons" / "hicolor" / "256x256" / "apps" / "image-swiper.png"

# ``packaging/pyinstaller/entry.py`` delegates to the same ``main()`` the console
# script wraps, so the frozen binary accepts exactly the documented CLI
# (``--version``, ``--dry-run``, …). It cannot point at
# ``src/image_swiper/__main__.py`` directly: PyInstaller runs that file as
# top-level code, which breaks its relative imports.
a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    # No data files: the window icon is painted at runtime by ui/branding.py,
    # and the icon theme tree is installed by packaging/install-desktop.sh.
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# No COLLECT() below: the EXE takes the binaries and data directly, which is the
# one-file layout (a temporary extraction directory at run time).
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="image-swiper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windowed: this is a GUI application. Linux has no console-subsystem bit, so
    # the flag is inert here; ``--version``/``--help`` still print to stdout.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Only Windows and macOS embed an icon in the executable; on Linux PyInstaller
    # logs "Ignoring icon" and the menu icon comes from packaging/icons/hicolor
    # via install-desktop.sh. The argument stays so the recipe is portable.
    icon=str(ICON),
)
