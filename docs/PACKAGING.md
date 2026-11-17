# Packaging and distribution

How Swipey Photos gets from this repository onto a user's desktop, and what each
artefact contains. The desktop integration lives in [`packaging/`](../packaging),
the binary recipe in [`scripts/build.sh`](../scripts/build.sh) plus
[`swipey-photos.spec`](../swipey-photos.spec), and all of it is covered by
`tests/test_packaging.py`.

| Artefact | Built from | Who uses it |
| --- | --- | --- |
| wheel + sdist | `python -m build` | `pip install`, distributions, AppImage |
| `swipey-photos.desktop` | `packaging/` | every menu, dock and task bar |
| icon theme tree | `packaging/icons/hicolor/` (generated) | the desktop entry's `Icon=` |
| one-file binary | `scripts/build.sh` + `swipey-photos.spec` | users with Python but no packaging tools |
| AppDir / AppImage | `packaging/appimage/build-appimage.sh` | users without Python **or** Qt libraries |
| GitHub Release | `.github/workflows/release.yml` | anyone who wants a download instead of a build |
| Flatpak | not shipped — see [Flatpak](#5-flatpak) | — |

---

## 1. Desktop integration

### Install for the current user

```bash
pip install .                                  # the launcher needs this on PATH
./packaging/install-desktop.sh                 # ~/.local/share
```

`pipx install .` works too and keeps the app out of your global site-packages.

`install-desktop.sh` copies files only; it never touches your Python
environment. It writes:

```text
~/.local/share/applications/swipey-photos.desktop
~/.local/share/icons/hicolor/16x16/apps/swipey-photos.png
~/.local/share/icons/hicolor/24x24/apps/swipey-photos.png
~/.local/share/icons/hicolor/32x32/apps/swipey-photos.png
~/.local/share/icons/hicolor/48x48/apps/swipey-photos.png
~/.local/share/icons/hicolor/64x64/apps/swipey-photos.png
~/.local/share/icons/hicolor/128x128/apps/swipey-photos.png
~/.local/share/icons/hicolor/256x256/apps/swipey-photos.png
~/.local/share/icons/hicolor/scalable/apps/swipey-photos.svg
```

The menu entry appears the next time the desktop shell rescans its application
directories (immediately on most shells; log out and back in otherwise). The app
shows up as **Swipey Photos → Photo Sorter**.

| Option | Effect |
| --- | --- |
| `--prefix DIR` | install below `DIR/share` instead of `~/.local` (`sudo … --prefix /usr` for all users) |
| `--destdir DIR` | prepend `DIR` to every path and skip cache updates, for distribution packaging |
| `--uninstall` | remove the entry and icons again |
| `-h`, `--help` | usage |

Without `--prefix`, `$XDG_DATA_HOME` wins when it is set, so the script honours
a non-standard data directory. Icon-cache and desktop-database updates only run
for installations (not for `--destdir`) and are skipped when the helper tool or
`hicolor/index.theme` is missing.

### System-wide installation

```bash
sudo pip install .                     # or: sudo pipx install .
sudo ./packaging/install-desktop.sh --prefix /usr
```

Distribution packages should stage instead:

```bash
./packaging/install-desktop.sh --prefix /usr --destdir "$pkgdir"
```

### One identity string

Four values must agree, or the window appears with a generic icon or a duplicate
task-bar entry:

| Value | Source |
| --- | --- |
| desktop file name | `swipey_photos.app.DESKTOP_FILE_NAME` → `swipey-photos` |
| `StartupWMClass` | the same constant, set with `QApplication.setDesktopFileName` |
| `Icon=` | `swipey_photos.ui.branding.ICON_NAME` → `swipey-photos` |
| installed icon files | `<ICON_NAME>.{svg,png}` |

`tests/test_packaging.py::test_desktop_identity_matches_the_qt_application`
fails when one of them drifts.

### Why the entry has no `MimeType` and no `%f`

Swipey Photos sorts a *folder*; it does not open a single image. Registering as an
image viewer would pass the launcher a file path the CLI would then reject.
`Exec=swipey-photos` is therefore correct and intentional.

### Regenerating the icons

The brand mark is painted by `ui/branding.py` (no binary assets in `src/`). The
files under `packaging/icons/` are generated from it:

```bash
QT_QPA_PLATFORM=offscreen python packaging/render_icons.py
git diff --stat packaging/icons          # commit the result
```

The SVG is produced by replaying the same painter code into a `QSvgGenerator`,
so the vector and raster versions always show the same mark. `ICON_SIZES` in
`branding.py` decides which PNG sizes exist; the desktop entry uses the scalable
one, and window managers pick the closest raster size.

---

## 2. Wheel and sdist

```bash
python -m build                                   # dist/*.whl, dist/*.tar.gz
python -m twine check dist/*                      # if twine is installed
```

The wheel installs the package, `py.typed` and the `swipey-photos` console script.
The sdist additionally carries `tests/`, `docs/`, `packaging/`, `scripts/` and
`swipey-photos.spec`, which is what lets a distribution build the desktop entry or
a standalone binary from a source tarball alone.

---

## 3. Standalone binary (PyInstaller)

`scripts/build.sh` writes `dist/swipey-photos`: one executable that runs on a
machine without Python. The release workflow uploads it as
`swipey-photos-<version>-linux-x86_64`.

```bash
./scripts/build.sh                        # venv + PyInstaller, ~2 minutes cold
./scripts/build.sh --clean                # rebuild the venv as well
PYTHON=python3.12 ./scripts/build.sh      # pick the interpreter explicitly
```

| Piece | Where | Note |
| --- | --- | --- |
| recipe | [`swipey-photos.spec`](../swipey-photos.spec) | one file, windowed, `pathex=["src"]`, 256 px icon |
| launcher | `packaging/pyinstaller/entry.py` | imports `swipey_photos.__main__.main`; see below |
| entry point | `src/swipey_photos/__main__.py` | the same module the console script wraps |
| build env | `build/venv` | `pip install ".[binary]"`; your shell's venv is untouched |
| output | `dist/swipey-photos` | one file; `du -h` reports about 70 MB |

The launcher exists because PyInstaller runs the file named in `Analysis` as
top-level code: pointing it at `src/swipey_photos/__main__.py` fails with
`attempted relative import with no known parent package`, since that module uses
`from . import __version__`. Importing the package from a three-line launcher
keeps the normal `__package__` context, and `tests/test_packaging.py` fails if the
spec ever goes back to the module file.

Bundled: CPython, PyQt6 (Qt libraries plus the `platforms` and `imageformats`
plugins) and Pillow. **Not** bundled: glibc and the X11 client libraries, so a
minimal container still needs `libxcb-cursor0`, `libxkbcommon-x11-0`, `libegl1`
and friends — the list is in
[README → Installation](../README.md#1-system-packages-qt-runtime--python-tooling).
When you cannot install those, build the AppImage in §4 instead.

The script verifies `dist/swipey-photos --version` against
`swipey_photos.__version__`. A deeper manual check, on a throwaway folder:

```bash
QT_QPA_PLATFORM=offscreen dist/swipey-photos --dry-run ~/Pictures/to-sort
```

Startup is slower than a `pip install`: the one-file bootloader extracts the
bundle into a temporary directory on every run, so expect about a second before
the window appears. The AppImage in §4 trades the same way with a squashfs image.

A hand-written spec is required here: a `pyi-makespec` default run cannot import
`swipey_photos` from a src-layout checkout, because `src/` is not on `sys.path`.
Everything else in the file is the stock one-file recipe, and
`tests/test_packaging.py` pins its shape (name, no `COLLECT`, windowed, icon
exists) so an edit cannot silently switch to one-directory output.

Verified on the build machine (Python 3.13, PyInstaller 6.22, ~70 MB):
`--version` prints `Swipey Photos 1.0.0`, `--help` lists the documented flags, and
`QT_QPA_PLATFORM=offscreen ./swipey-photos --dry-run <copy-of-photos>` starts a
session, prefetches three previews (so Pillow's JPEG plugin is inside the bundle)
and leaves every file where it was. PyInstaller logs
`Ignoring icon; supported only on Windows and macOS!` once — expected on Linux,
where the icon comes from the icon theme instead of the ELF header.

---

## 4. AppImage

`packaging/appimage/build-appimage.sh` produces a single file that runs on any
x86-64 Linux distribution — no Python, no PyQt6, no `pip`. Every tagged release
attaches it as `swipey-photos-<tag>-linux-x86_64.AppImage`; the commands below
rebuild it from the checkout.

```bash
uv python install 3.13                                   # relocatable CPython
./packaging/appimage/build-appimage.sh --staging-only    # AppDir only
APPIMAGETOOL=/path/to/appimagetool ./packaging/appimage/build-appimage.sh
```

| Option | Effect |
| --- | --- |
| `--python PATH` | interpreter to bundle (default: `$APPIMAGE_PYTHON`, then `uv python find 3.13`) |
| `--output DIR` | staging directory and artefact location (default: `build/appimage`) |
| `--staging-only` | build `SwipeyPhotos.AppDir` and stop before `appimagetool` |
| `--appimagetool PATH` | the packaging tool (default: `$APPIMAGETOOL`, then `PATH`) |
| `-h`, `--help` | usage |

What the script does:

1. Copies the interpreter's prefix into `SwipeyPhotos.AppDir/usr` and refuses a
   distribution Python that links a shared `libpython` — that library would be
   missing on the target machine. python-build-standalone builds (what
   `uv python install` downloads) are relocatable and work.
2. Installs Swipey Photos and its dependencies into the bundle's `site-packages`
   with `uv pip install --target` (falling back to `pip`). On a machine without
   network access pass a wheelhouse:
   `APPIMAGE_PIP_ARGS="--no-index --find-links /path/to/wheels"`.
3. Trims what a QtWidgets app never loads (QML, Quick3D, Designer, translations,
   `test`, `tkinter`, `ensurepip`, `__pycache__`) — the staged AppDir drops from
   about 390 MB to about 270 MB before squashfs compression.
4. Writes `AppRun` (runs the bundled interpreter, ignoring any inherited
   `APPDIR`), the desktop entry, `.DirIcon` and the scalable icon.
5. Runs `appimagetool` and writes `swipey-photos-<version>-<arch>.AppImage`.

`appimagetool` is published separately
([AppImage/appimagetool](https://github.com/AppImage/appimagetool/releases)); the
script never downloads anything by itself. Without it, the AppDir is still
complete, so `--staging-only` plus a manual `appimagetool` call is a valid path.
Upstream's `appimagetool` is itself an AppImage and needs FUSE to start, so on a
machine with neither `/dev/fuse` nor `libfuse.so.2` — CI runners, most
containers — the script reruns it with `--appimage-extract-and-run`.

Releases carry the result as `swipey-photos-<tag>-linux-x86_64.AppImage`.
`.github/workflows/release.yml` runs this same script (interpreter from
`astral-sh/setup-uv`, appimagetool from upstream), so the published file and a
local build come from one recipe, and the job smoke-tests the file the way a
FUSE-less runner can: `APPIMAGE_EXTRACT_AND_RUN=1 ./…AppImage --version`.

Verified on the build machine (1.0.0, Python 3.13.16, appimagetool continuous
`11d54c9`): the AppDir is 269 MB, the AppImage 84 MB. `--version` prints
`Swipey Photos 1.0.0`, including under `env -i PATH=/usr/bin:/bin`, so no Python
from the host is involved;
`QT_QPA_PLATFORM=offscreen ./swipey-photos-1.0.0-x86_64.AppImage --dry-run FOLDER`
starts a session and finds the images. `--appimage-extract` shows `AppRun`,
`.DirIcon`, `swipey-photos.desktop`, `swipey-photos.svg` and `usr/`, with the
app under `usr/lib/python3.13/site-packages/swipey_photos/`.
`tests/test_packaging.py` pins the script's syntax, `--help`, the FUSE fallback
and the release job.

---

## 5. Flatpak

Not shipped yet, on purpose. The desktop entry, `StartupWMClass` and icon names
are already Flatpak-compatible; what is missing is the runtime:

- `org.gnome.Platform` does not include PyQt6.
- Building PyQt6 from source inside a manifest needs Qt 6 headers, `sip` and a
  30+ minute compile; the alternative — a `python3-PyQt6` module assembled from
  PyPI wheels — must be pinned per runtime version.
- The app also wants the same PyQt6 version as the wheels tested in CI.

A future manifest therefore needs, at minimum: `org.freedesktop.Sdk` 24.08+ with
the `org.freedesktop.Sdk.Extension.python3` extension or an explicit CPython
module, a `python3-PyQt6` module built from pinned wheels, `--share=ipc`,
`--socket=x11`, `--socket=wayland`, `--device=dri` and
`--filesystem=home` (the app sorts user folders in place, so a portal-based
folder picker would need additional work).

Until then the AppImage is the supported way to run Swipey Photos without a
Python environment.

---

## 6. Distribution packages

References for a `.deb`/`.rpm`/`PKGBUILD`:

| Step | Command |
| --- | --- |
| install the package | `python -m pip install --root "$pkgdir" --prefix /usr .` or the wheel into `$pkgdir/usr/lib/python3/dist-packages` |
| desktop entry + icons | `./packaging/install-desktop.sh --prefix /usr --destdir "$pkgdir"` |
| dependencies | `python3-pyqt6` **or** a vendored PyQt6; the shared libraries listed in [README → Requirements](../README.md#requirements) |
| optional | `hicolor-icon-theme`, `desktop-file-utils`, `shared-mime-info` |

The sdist contains everything those steps need, including `packaging/`.

---

## 7. Checklist before tagging a release

1. `QT_QPA_PLATFORM=offscreen python packaging/render_icons.py` — icons match
   `branding.py` (the suite also fails if the tree is incomplete).
2. Move the `[Unreleased]` entries in [`CHANGELOG.md`](../CHANGELOG.md) into the
   new version's section; `tests/test_packaging.py` fails until the shipped
   version has one.
3. `ruff check . && ruff format --check . && mypy && pytest -q`.
4. `desktop-file-validate packaging/swipey-photos.desktop` (run automatically by
   the suite when the tool is installed).
5. `./packaging/install-desktop.sh --prefix /usr --destdir /tmp/stage` and check
   the tree; `--uninstall` must remove it again.
6. `python -m build`, then install the wheel in a throwaway venv and run
   `swipey-photos --version`.
7. `./scripts/build.sh`, then `dist/swipey-photos --version` and one real sorting
   session on a scratch folder.
8. Optional: `./packaging/appimage/build-appimage.sh`, then run the resulting
   `build/appimage/swipey-photos-<version>-<arch>.AppImage --version`; on a
   machine without Python, also start one sorting session. CI builds and
   attaches the same file on the tag (§4), so this is a rehearsal, not a gate.
9. Tag `vX.Y.Z` and push it — `.github/workflows/release.yml` attaches the
   binary, the AppImage, the wheel and the sdist to the Release.
