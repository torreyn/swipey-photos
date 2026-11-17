# Packaging and distribution

How ImageSwiper gets from this repository onto a user's desktop, and what each
artefact contains. Everything described here lives in [`packaging/`](../packaging)
and is covered by `tests/test_packaging.py`.

| Artefact | Built from | Who uses it |
| --- | --- | --- |
| wheel + sdist | `python -m build` | `pip install`, distributions, AppImage |
| `image-swiper.desktop` | `packaging/` | every menu, dock and task bar |
| icon theme tree | `packaging/icons/hicolor/` (generated) | the desktop entry's `Icon=` |
| AppDir / AppImage | `packaging/appimage/build-appimage.sh` | users without Python |
| Flatpak | not shipped — see [Flatpak](#4-flatpak) | — |

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
~/.local/share/applications/image-swiper.desktop
~/.local/share/icons/hicolor/16x16/apps/image-swiper.png
~/.local/share/icons/hicolor/24x24/apps/image-swiper.png
~/.local/share/icons/hicolor/32x32/apps/image-swiper.png
~/.local/share/icons/hicolor/48x48/apps/image-swiper.png
~/.local/share/icons/hicolor/64x64/apps/image-swiper.png
~/.local/share/icons/hicolor/128x128/apps/image-swiper.png
~/.local/share/icons/hicolor/256x256/apps/image-swiper.png
~/.local/share/icons/hicolor/scalable/apps/image-swiper.svg
```

The menu entry appears the next time the desktop shell rescans its application
directories (immediately on most shells; log out and back in otherwise). The app
shows up as **ImageSwiper → Photo Sorter**.

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
| desktop file name | `image_swiper.app.DESKTOP_FILE_NAME` → `image-swiper` |
| `StartupWMClass` | the same constant, set with `QApplication.setDesktopFileName` |
| `Icon=` | `image_swiper.ui.branding.ICON_NAME` → `image-swiper` |
| installed icon files | `<ICON_NAME>.{svg,png}` |

`tests/test_packaging.py::test_desktop_identity_matches_the_qt_application`
fails when one of them drifts.

### Why the entry has no `MimeType` and no `%f`

ImageSwiper sorts a *folder*; it does not open a single image. Registering as an
image viewer would pass the launcher a file path the CLI would then reject.
`Exec=image-swiper` is therefore correct and intentional.

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

The wheel installs the package, `py.typed` and the `image-swiper` console script.
The sdist additionally carries `tests/`, `docs/` and `packaging/`, which is what
lets a distribution build the desktop entry from a source tarball.


---

## 3. AppImage

`packaging/appimage/build-appimage.sh` produces a single file that runs on any
x86-64 Linux distribution — no Python, no PyQt6, no `pip`.

```bash
uv python install 3.13                                   # relocatable CPython
./packaging/appimage/build-appimage.sh --staging-only    # AppDir only
APPIMAGETOOL=/path/to/appimagetool ./packaging/appimage/build-appimage.sh
```

| Option | Effect |
| --- | --- |
| `--python PATH` | interpreter to bundle (default: `$APPIMAGE_PYTHON`, then `uv python find 3.13`) |
| `--output DIR` | staging directory and artefact location (default: `build/appimage`) |
| `--staging-only` | build `ImageSwiper.AppDir` and stop before `appimagetool` |
| `--appimagetool PATH` | the packaging tool (default: `$APPIMAGETOOL`, then `PATH`) |
| `-h`, `--help` | usage |

What the script does:

1. Copies the interpreter's prefix into `ImageSwiper.AppDir/usr` and refuses a
   distribution Python that links a shared `libpython` — that library would be
   missing on the target machine. python-build-standalone builds (what
   `uv python install` downloads) are relocatable and work.
2. Installs ImageSwiper and its dependencies into the bundle's `site-packages`
   with `uv pip install --target` (falling back to `pip`). On a machine without
   network access pass a wheelhouse:
   `APPIMAGE_PIP_ARGS="--no-index --find-links /path/to/wheels"`.
3. Trims what a QtWidgets app never loads (QML, Quick3D, Designer, translations,
   `test`, `tkinter`, `ensurepip`, `__pycache__`) — the staged AppDir drops from
   about 390 MB to about 270 MB before squashfs compression.
4. Writes `AppRun` (runs the bundled interpreter, ignoring any inherited
   `APPDIR`), the desktop entry, `.DirIcon` and the scalable icon.
5. Runs `appimagetool` and writes `image-swiper-<version>-<arch>.AppImage`.

`appimagetool` is published separately
([AppImage/appimagetool](https://github.com/AppImage/appimagetool/releases)); the
script never downloads anything by itself. Without it, the AppDir is still
complete, so `--staging-only` plus a manual `appimagetool` call is a valid path.

Verified on the build machine: the staged `AppRun --version` prints the version,
and `AppRun --dry-run FOLDER` starts the real window offscreen without touching
the files. `tests/test_packaging.py` checks the script's syntax and `--help`,
but the AppImage build itself needs the network and is not part of CI.

---

## 4. Flatpak

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

Until then the AppImage is the supported way to run ImageSwiper without a
Python environment.

---

## 5. Distribution packages

References for a `.deb`/`.rpm`/`PKGBUILD`:

| Step | Command |
| --- | --- |
| install the package | `python -m pip install --root "$pkgdir" --prefix /usr .` or the wheel into `$pkgdir/usr/lib/python3/dist-packages` |
| desktop entry + icons | `./packaging/install-desktop.sh --prefix /usr --destdir "$pkgdir"` |
| dependencies | `python3-pyqt6` **or** a vendored PyQt6; the shared libraries listed in [README → Requirements](../README.md#requirements) |
| optional | `hicolor-icon-theme`, `desktop-file-utils`, `shared-mime-info` |

The sdist contains everything those steps need, including `packaging/`.

---

## 6. Checklist before tagging a release

1. `QT_QPA_PLATFORM=offscreen python packaging/render_icons.py` — icons match
   `branding.py` (the suite also fails if the tree is incomplete).
2. `ruff check . && ruff format --check . && mypy && pytest -q`.
3. `desktop-file-validate packaging/image-swiper.desktop` (run automatically by
   the suite when the tool is installed).
4. `./packaging/install-desktop.sh --prefix /usr --destdir /tmp/stage` and check
   the tree; `--uninstall` must remove it again.
5. `python -m build`, then install the wheel in a throwaway venv and run
   `image-swiper --version`.
6. Optional: build the AppImage and start it on a machine without Python.
7. Tag `vX.Y.Z`, upload the wheel, sdist and AppImage.
