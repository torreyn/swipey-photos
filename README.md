# ImageSwiper

> Sort a folder of photos by feel, not by filename.

**ImageSwiper** is a Linux desktop application for culling and sorting image
folders with Tinder-style swipe gestures. Point it at a folder, swipe each
picture left, right, up or down, and ImageSwiper moves it into the matching
subfolder. No tagging dialogs, no multi-select gymnastics — one decisive
gesture per photo.

[![ci](https://github.com/torreyn/image-swiper/actions/workflows/ci.yml/badge.svg)](https://github.com/torreyn/image-swiper/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-6-green.svg)](https://www.qt.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-v1.0%20released-green.svg)](#project-status)

> **Name note.** `ImageSwiper` is the working title, and the package/CLI
> identifiers (`image_swiper`, `image-swiper`) follow it. The suggested
> product name is **FlickSort** — shorter, pronounceable, and describes the
> interaction better. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#13-naming)
> for the rename checklist (it is a mechanical `grep` + two metadata edits).

---

## Screenshots

![ImageSwiper main window — placeholder mock-up](docs/assets/screenshot-main.svg)

*Placeholder mock-up. The application now runs, so a real screenshot of the main
window, the drag feedback and the summary can replace this image at any time —
drop `*.png` files into [`docs/assets/`](docs/assets/) and reference them here
(`QT_QPA_PLATFORM=offscreen` plus `QWidget.grab()` is enough to capture one).*

---

## Project status

`v1.0.0` is the **first packaged release**: the core loop, the comfort pass and
the desktop integration all ship together. The Qt-free business layer is
implemented and tested — image loading with EXIF handling, the four-way sorter
with undo, the folder manager, collision-safe file operations, JSON
configuration and rotating logs. The Qt side is wired up too: the swipe card
(drag physics, rotation, directional feedback, drop shadow, fly-out), the stage
around it with its gesture legend, the welcome screen with recent folders, the
completion summary and the main window (menus, progress, footer buttons, live
status-bar counts, config persistence). Install it from a checkout with
`pip install .`, run it with `image-swiper` or `python -m image_swiper`, and sort a
folder end to end (388 tests, green on Python 3.11–3.13 in CI). `packaging/` adds
the `.desktop` entry, the generated icon theme and an AppImage build script — see
[`docs/PACKAGING.md`](docs/PACKAGING.md).

---

## Features

Everything below ships in v1.0 unless marked otherwise:

- **Four-way swipe sorting.** Each gesture maps to one destination folder:

  | Gesture | Keyboard | Destination (default) | Meaning |
  | --- | --- | --- | --- |
  | Swipe **right** → | <kbd>→</kbd> / <kbd>D</kbd> | `Good/` | Keep, usable |
  | Swipe **left** ← | <kbd>←</kbd> / <kbd>A</kbd> | `Bad/` | Reject |
  | Swipe **up** ↑ | <kbd>↑</kbd> / <kbd>W</kbd> | `Great/` | Best-of-set / portfolio |
  | Swipe **down** ↓ | <kbd>↓</kbd> / <kbd>S</kbd> | `OK/` | Neutral / undecided |

- **Non-destructive by design.** Images are *moved* (default) or *copied* into
  target subfolders — never deleted. Name collisions are resolved by suffixing,
  never by overwriting.
- **Undo.** <kbd>Ctrl</kbd>+<kbd>Z</kbd> moves the last image back where it
  came from, up to a configurable history depth.
- **Keyboard-first alternative.** Arrows and WASD mirror every swipe, so the
  whole app is usable without a mouse or touchscreen.
- **Respects your pixels.** EXIF orientation is applied, huge images are
  downscaled for display only, and the originals are never re-encoded.
- **Snappy navigation.** Background decoding + prefetch of the next images so
  moving through a large folder stays responsive.
- **Remembers context.** Last folder, window size and theme are persisted to a
  human-editable JSON config; *View → Dark Mode* switches palettes live.
- **Looks the part.** Rounded card with a blurred drop shadow, a 150 ms fade-in
  for each new image, a `← Bad ↓ OK ↑ Great → Good` hint under the card and a
  live per-category summary bar at the bottom.
- **Safe to try.** `image-swiper --dry-run FOLDER` logs what it *would* move and
  leaves every file untouched, so you can rehearse a sort first.
- **Fits your desktop.** `packaging/install-desktop.sh` adds a menu entry and a
  `hicolor` icon set (no desktop-file editing by hand), and
  `packaging/appimage/build-appimage.sh` bundles Python and PyQt6 into a single
  AppImage for machines without either. Details in
  [`docs/PACKAGING.md`](docs/PACKAGING.md).
- **Predictable buckets.** `Good/`, `Bad/`, `Great/` and `OK/` are created inside
  the folder you open, and a file is never overwritten — collisions gain a
  `_1`, `_2` suffix instead.
- **Safe failure modes.** Unreadable or corrupt images are skipped with a
  status-bar warning, animated GIFs show their first frame, huge images are
  downscaled for display while the original moves untouched, and permission
  errors are reported with the operating system's own message.

### Non-goals (v1.x)

- Cloud sync, AI/ML auto-tagging, RAW development, or editing pixels.
- Database-backed libraries. ImageSwiper operates directly on your folder.
- Windows/macOS builds. The code stays portable, but Linux is the target.

---

## Requirements

| Requirement | Version / notes |
| --- | --- |
| Linux | X11 or Wayland (tested on Debian/Ubuntu, Fedora, Arch) |
| Python | **3.11+** (uses `ExceptionGroup`, modern typing, `slots` dataclasses) |
| Qt | Qt 6.6+ via **PyQt6** (installed from PyPI, not from `apt`) |
| Pillow | 10+ — image validation, EXIF orientation, thumbnails |
| RAM | ~300 MB comfortable for a 5 000-image folder |

### PyQt6 vs. PySide6

The project targets **PyQt6**, as specified in the packaging metadata. Both
bindings expose the same Qt 6 API surface for everything this app needs
(`QWidget`, `QPropertyAnimation`, `QThreadPool`, `QGraphicsView`).

One caveat worth knowing up front: PyQt6 is **GPL v3 / commercial**, while
PySide6 is **LGPL v3**. If you ever plan to ship ImageSwiper as a closed-source
binary, either buy a Riverbank licence or switch the binding. Because all Qt
imports live in `image_swiper/ui/` (and `app.py`), the switch is confined to
the UI layer — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#2-toolkit-decision).

---

## Installation

### 1. System packages (Qt runtime + Python tooling)

PyQt6 wheels bundle Qt itself, but Qt still needs a handful of system
libraries (notably the XCB platform plugin pieces on X11).

**Debian / Ubuntu / Linux Mint**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
    libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 \
    libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 \
    libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-xfixes0
```

**Fedora**

```bash
sudo dnf install -y python3 python3-pip python3-virtualenv \
    mesa-libGL libxkbcommon-x11 xcb-util-cursor xcb-util-wm \
    xcb-util-keysyms xcb-util-renderutil dbus-libs
```

**Arch / Manjaro**

```bash
sudo pacman -S --needed python python-pip python-virtualenv \
    mesa libxkbcommon-x11 xcb-util-cursor xcb-util-wm \
    xcb-util-keysyms xcb-util-renderutil dbus
```

> Missing `libxcb-cursor0` is the single most common cause of
> `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`.

### 2. Install ImageSwiper

Not on PyPI yet — install from a checkout or from a release wheel:

```bash
git clone https://github.com/torreyn/image-swiper.git
cd image-swiper

python3 -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
python -m pip install --upgrade pip
pip install -e ".[dev]"            # contributing; or: pip install dist/*.whl
```

Runtime-only install from the checkout:

```bash
pip install -r requirements.txt
pip install -e .            # optional: gives you the `image-swiper` command
```

### 3. Verify the installation

```bash
python -c "import image_swiper; print(image_swiper.__version__)"
image-swiper --version      # prints "ImageSwiper 1.0.0"
```

### 4. Add it to your application menu

```bash
./packaging/install-desktop.sh                      # this user (~/.local/share)
sudo ./packaging/install-desktop.sh --prefix /usr   # every user
```

The entry appears as **ImageSwiper → Photo Sorter** with its own icon.
`--uninstall` removes it again; `--destdir` stages a distribution package.
Paths, icon regeneration and the AppImage build live in
[`docs/PACKAGING.md`](docs/PACKAGING.md).

> A menu launcher does not inherit an activated virtualenv: it runs
> `image-swiper` from `PATH`. If you installed into `.venv`, either point the
> install step at a user prefix (`pipx install .` or `pip install --user .`) or
> edit `Exec=` in the installed `.desktop` file to the absolute path of the
> script.

> **No Python on the target machine?** A single-file AppImage is buildable from
> the checkout with `packaging/appimage/build-appimage.sh`. Flatpak is not
> shipped yet; [`docs/PACKAGING.md`](docs/PACKAGING.md#4-flatpak) explains what a
> manifest would need.

---

## Usage

1. **Launch** the app:

   ```bash
   image-swiper                      # reopens the last folder, or the picker
   image-swiper ~/Pictures/unsorted  # skip the picker
   image-swiper --dry-run ~/Pictures/unsorted   # rehearse: files are never moved
   ```

   `--dry-run` logs `dry run: would move …` for every decision, updates the
   counters and undo history exactly as usual, and marks the window title with
   `(dry run)` — the safe way to try the app on a folder you are not ready to
   sort. `--config PATH` reads and writes an alternative settings file and
   `-v` echoes the log to stderr.

2. **Pick a folder.** On a first run ImageSwiper shows a welcome page with a big
   *Select Folder* button and the five folders you opened last. It scans the
   chosen folder for supported image files (`.jpg`, `.jpeg`, `.png`, `.webp`,
   `.bmp`, `.gif`, `.tif`, `.tiff`).
3. **Swipe.** Drag the photo with the mouse, flick it with a touchscreen, or
   press an arrow/WASD key. Release past roughly a third of the window width
   (or press a key) to commit; release earlier and the card springs back. The
   four footer buttons (*Bad*, *OK*, *Good*, *Great*) do the same for anyone who
   prefers clicking.
4. **Watch it move.** The file is moved into `Good/`, `Bad/`, `Great/` or `OK/`
   inside the folder you opened. The next image appears and the header counts
   `Image 3 of 47`.
5. **Undo** with <kbd>Ctrl</kbd>+<kbd>Z</kbd> if you misflicked.
6. **Finish.** When the folder is drained, a summary shows how many images went
   where, and offers to rescan the folder, pick another one, or quit.

ImageSwiper **never deletes or overwrites** anything. Subfolders it creates look
like this:

```text
~/Pictures/unsorted/
├── Bad/
├── Good/
├── Great/
├── OK/
├── DSC_0001.jpg          ← still to sort
└── DSC_0002.jpg
```

Already-sorted subfolders (and any folder listed as a destination) are skipped
during the scan, so re-running the app on the same parent folder will not
recycle files.

### Keyboard shortcuts

Every swipe has a keyboard equivalent, so the app works on a laptop keyboard,
a remote session, or for users who cannot use a pointing device.

| Action | Keys | Notes |
| --- | --- | --- |
| **Good** (swipe right) | <kbd>→</kbd> or <kbd>D</kbd> | moves to `Good/` |
| **Bad** (swipe left) | <kbd>←</kbd> or <kbd>A</kbd> | moves to `Bad/` |
| **Great** (swipe up) | <kbd>↑</kbd> or <kbd>W</kbd> | moves to `Great/` |
| **OK** (swipe down) | <kbd>↓</kbd> or <kbd>S</kbd> | moves to `OK/` |
| Undo last move | <kbd>Ctrl</kbd>+<kbd>Z</kbd> | restores the previous file |
| Skip for now | <kbd>Space</kbd> | leaves the file in place, shows it again later |
| Open folder… | <kbd>Ctrl</kbd>+<kbd>O</kbd> | choose another source folder |
| Rescan folder | <kbd>F5</kbd> or <kbd>Ctrl</kbd>+<kbd>R</kbd> | picks up newly added files |
| Toggle fullscreen | <kbd>F11</kbd> | distraction-free culling |
| Shortcut help | <kbd>F1</kbd> or <kbd>?</kbd> | overlay with this table |
| Quit | <kbd>Ctrl</kbd>+<kbd>Q</kbd> | window state is saved |

WASD keys are ignored while a text field (e.g. a folder-path input) has focus.
Arrow keys always work.

---

## Configuration

ImageSwiper is configured with a single human-editable JSON file:

```text
${XDG_CONFIG_HOME:-~/.config}/image-swiper/config.json
```

The file is written on first save (when the window closes). A minimal example:

```json
{
  "last_folder": "/home/you/Pictures/to-sort",
  "recent_folders": [
    "/home/you/Pictures/to-sort",
    "/home/you/Pictures/2024-06-trip"
  ],
  "theme": "system",
  "version": 1,
  "window": { "height": 800, "width": 1200 }
}
```

`theme` is `system`, `light` or `dark`; *View → Dark Mode* writes the value when
the user toggles it, and `system` follows the desktop's colour scheme.
`last_folder` is reopened at start-up and may be `null`. `recent_folders` holds at
most five folders, newest first, and feeds the welcome page's shortcut list.
Unknown keys are ignored with a warning, so a file from a newer build still
loads. The file is replaced atomically with mode `0600`.

Logs are written to
`${XDG_DATA_HOME:-~/.local/share}/image-swiper/logs/image-swiper.log`, rotated at
2 MiB with three backups.

Full key-by-key reference, precedence rules and migration notes:
**[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**.

---

## Project structure

```text
image-swiper/
├── src/image_swiper/          # importable package (src layout)
│   ├── __init__.py            # version + public package docstring
│   ├── __main__.py            # `python -m image_swiper` / `image-swiper` entry point
│   ├── app.py                 # QApplication bootstrap, wiring, lifecycle
│   ├── py.typed               # PEP 561 marker (type info ships with the wheel)
│   ├── ui/                    # Qt-only layer (all PyQt6 imports live here)
│   │   ├── main_window.py     # shell: menus, status bar, three-page session wiring
│   │   ├── welcome_screen.py  # "Select Folder" empty state + recent folders
│   │   ├── completion_screen.py # per-category summary, restart/pick/quit
│   │   ├── swipe_card.py      # one image: drag, rotation, badge, fly-out (gui)
│   │   ├── swipe_widget.py    # stage: hosts the card, feeds images, forwards swipes
│   │   ├── animator.py        # card entrance fade/slide, timing, easing
│   │   ├── workers.py         # thread-pool preview prefetch + cache
│   │   ├── image_utils.py     # Pillow → QImage/QPixmap conversion
│   │   ├── theme.py           # light/dark palettes, system preference
│   │   ├── shortcut_overlay.py # F1/? keyboard reference grid
│   │   └── branding.py        # generated window icon and welcome logo
│   ├── core/                  # toolkit-agnostic logic (no Qt imports)
│   │   ├── image_loader.py    # folder scanning, validation, decode, prefetch
│   │   ├── sorter.py          # queue cursor, category moves, undo stack
│   │   └── folder_manager.py  # category folders, validation, collision-free moves
│   └── utils/                 # reusable helpers, no UI/core knowledge
│       ├── file_ops.py        # collision-safe moves, reverse moves, path helpers
│       ├── config.py          # JSON defaults/load/save, XDG paths, recent folders
│       └── logging_setup.py   # rotating file logs + optional console handler
├── tests/                     # pytest suites mirroring src/ (pytest-qt for GUI)
├── packaging/                 # desktop integration, no Python imports needed
│   ├── image-swiper.desktop   # menu entry: Exec=image-swiper, Icon=image-swiper
│   ├── install-desktop.sh     # install/uninstall entry + icons (prefix/destdir)
│   ├── icons/hicolor/         # generated PNG sizes + one scalable SVG
│   ├── render_icons.py        # regenerate the icon tree from ui/branding.py
│   └── appimage/build-appimage.sh  # bundle CPython + PyQt6 into one AppImage
├── docs/
│   ├── README.md              # documentation index and reading order
│   ├── ARCHITECTURE.md        # layers, contracts, data flow, state machines
│   ├── CONFIGURATION.md       # every option, defaults, precedence
│   ├── DEVELOPMENT.md         # setup, commands, conventions, test strategy
│   ├── PACKAGING.md           # desktop entry, icons, AppImage, distro notes
│   └── assets/                # screenshots and mock-ups
├── pyproject.toml             # metadata, deps, tool config, entry point
├── requirements.txt           # runtime pins for plain pip workflows
├── README.md
├── CONTRIBUTING.md
├── LICENSE                    # MIT
└── .gitignore                 # Python + PyQt + VSCode + Linux noise
```

Dependency direction is strictly one-way — `utils` ← `core` ← `ui` ← `app` —
and is enforced by review plus `tests/test_architecture.py`, which parses the
imports with `ast` and fails on any Qt import below `ui/`. Details and rationale:
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| **M0 — Scaffolding** | Layout, packaging, docs, module contracts, CI pipeline | ✅ done |
| **M1 — Image pipeline** | `image_loader`, EXIF handling, prefetching, fixture tests | ✅ done |
| **M2 — Swipe UI** | `swipe_card` (card, drag, badge, fly-out), `swipe_widget` stage, main window, welcome/summary pages, deck fly-in (`animator`) | ✅ done |
| **M3 — Sorting** | `folder_manager`, `sorter`, `file_ops`, collision handling | ✅ done |
| **M4 — Comfort** | Undo, config UI + dark mode, summary screen, logging, error reporting, rescan/full-screen/shortcut keys, shortcut overlay, prefetch workers, `--dry-run`, edge-case messaging | ✅ done |
| **M5 — Distribution** | `.desktop` file, icons, AppImage/Flatpak, 1.0 | ✅ done (v1.0.0; Flatpak deferred, see [PACKAGING §4](docs/PACKAGING.md#4-flatpak)) |

---

## Development quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m image_swiper            # run from source
pytest -q                         # unit tests
QT_QPA_PLATFORM=offscreen pytest -q -m gui   # headless GUI tests
ruff check . && ruff format --check .
mypy
```

Conventions, fixtures and the definition of done for a PR are in
**[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**.

---

## Contributing

Contributions are welcome — bug reports, UX feedback, translations, and code.
Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** before opening a pull
request. In short:

1. Search existing issues, then open one describing the change.
2. Fork, branch from `main` (`feat/…`, `fix/…`, `docs/…`).
3. Keep the layer boundaries: no Qt imports in `core/` or `utils/`.
4. Add or update tests; `pytest` and `ruff check .` must pass.
5. Use [Conventional Commits](https://www.conventionalcommits.org/) style.
6. Open the PR and reference the issue.

This project follows the
[Contributor Covenant, v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## FAQ

**Does it delete rejected photos?**
No. Rejected images are moved to `Bad/` (or your configured folder). Nothing is
ever deleted by ImageSwiper.

**Will it touch files already in `Good/`?**
No. Destination folders are excluded from the scan, so only not-yet-sorted
images in the selected folder are shown.

**Does it work on Wayland?**
Yes. Gestures are handled inside the app window, so no compositor-level gesture
permissions are needed.

**Can I use a touchscreen or touchpad?**
Touchscreens send synthetic mouse events, which the card already supports.
Two-finger touchpad "flick" gestures depend on the compositor; the keyboard
bindings are the reliable fallback.

---

## License

Released under the [MIT License](LICENSE) — © 2026 ImageSwiper contributors.

Qt is © The Qt Company and is used through PyQt6 (GPL v3 / commercial) or
PySide6 (LGPL v3); see [Requirements](#pyqt6-vs-pyside6). Pillow is licensed
under the HPND licence.
