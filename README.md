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
[![Status](https://img.shields.io/badge/status-core%20implemented-orange.svg)](#project-status)

> **Name note.** `ImageSwiper` is the working title, and the package/CLI
> identifiers (`image_swiper`, `image-swiper`) follow it. The suggested
> product name is **FlickSort** — shorter, pronounceable, and describes the
> interaction better. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#13-naming)
> for the rename checklist (it is a mechanical `grep` + two metadata edits).

---

## Screenshots

![ImageSwiper main window — placeholder mock-up](docs/assets/screenshot-main.svg)

*Placeholder mock-up. Real screenshots (main window, drag feedback, summary
screen) will replace this once the UI layer is implemented. Drop `*.png` files
into [`docs/assets/`](docs/assets/) and reference them here.*

---

## Project status

`v0.1.0` is a **core-only** release. The Qt-free business layer is implemented
and tested — image loading with EXIF handling, the four-way sorter with undo,
the folder manager, collision-safe file operations, JSON configuration and
rotating logs (164 tests, green on Python 3.11–3.13 in CI). The UI layer
(`app.py`, the widgets, the animator) and the CLI are still documented
placeholders, so `image-swiper` exits with `NotImplementedError` until the
swipe UI lands. See the [roadmap](#roadmap) for what is next.

---

## Features

Planned for v1.0 (see the roadmap for what is already implemented):

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
  human-editable JSON config.
- **Predictable buckets.** `Good/`, `Bad/`, `Great/` and `OK/` are created inside
  the folder you open, and a file is never overwritten — collisions gain a
  `_1`, `_2` suffix instead.
- **Safe failure modes.** Unreadable or corrupt images are reported and skipped
  instead of crashing the session.

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

### 2. Clone and create a virtual environment

```bash
git clone https://github.com/torreyn/image-swiper.git
cd image-swiper

python3 -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
python -m pip install --upgrade pip
```

### 3. Install ImageSwiper

Editable install with dev tooling (recommended for contributing):

```bash
pip install -e ".[dev]"
```

Runtime-only install:

```bash
pip install -r requirements.txt
pip install -e .            # optional: gives you the `image-swiper` command
```

### 4. Verify the installation

```bash
python -c "import image_swiper; print(image_swiper.__version__)"
image-swiper --version      # once the CLI milestone lands
```

> **Flatpak / AppImage:** not packaged yet. The app has no runtime dependency
> outside PyPI + the Qt system libraries above, so both are feasible later.

---

## Usage

1. **Launch** the app:

   ```bash
   image-swiper                      # opens the folder picker
   image-swiper ~/Pictures/unsorted  # skip the picker
   ```

2. **Pick a folder.** ImageSwiper scans it for supported image files
   (`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tif`, `.tiff`).
3. **Swipe.** Drag the photo with the mouse, flick it with a touchscreen, or
   press an arrow/WASD key. Release past roughly a third of the window width
   (or press a key) to commit; release earlier and the card springs back.
4. **Watch it move.** The file is moved into `Good/`, `Bad/`, `Great/` or `OK/`
   inside the folder you opened. The next image slides in.
5. **Undo** with <kbd>Ctrl</kbd>+<kbd>Z</kbd> if you misflicked.
6. **Finish.** When the folder is drained, a summary shows how many images went
   where, and lets you open the destination folders.

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
  "theme": "system",
  "version": 1,
  "window": { "height": 800, "width": 1200 }
}
```

`theme` is `system`, `light` or `dark`; `last_folder` is reopened at start-up and
may be `null`. Unknown keys are ignored with a warning, so a file from a newer
build still loads. The file is replaced atomically with mode `0600`.

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
│   │   ├── main_window.py     # shell: menus, toolbar, status bar, session wiring
│   │   ├── swipe_widget.py    # image card: rendering, drag, thresholds, badges
│   │   ├── animator.py        # fly-out / fly-in / spring-back animations
│   │   └── workers.py         # QRunnable adapters: scan, preview decode, move
│   ├── core/                  # toolkit-agnostic logic (no Qt imports)
│   │   ├── image_loader.py    # folder scanning, validation, decode, prefetch
│   │   ├── sorter.py          # queue cursor, category moves, undo stack
│   │   └── folder_manager.py  # category folders, validation, collision-free moves
│   └── utils/                 # reusable helpers, no UI/core knowledge
│       ├── file_ops.py        # collision-safe moves, reverse moves, path helpers
│       ├── config.py          # JSON defaults/load/save, XDG paths
│       └── logging_setup.py   # rotating file logs + optional console handler
├── tests/                     # pytest suites mirroring src/ (pytest-qt for GUI)
├── docs/
│   ├── README.md              # documentation index and reading order
│   ├── ARCHITECTURE.md        # layers, contracts, data flow, state machines
│   ├── CONFIGURATION.md       # every option, defaults, precedence
│   ├── DEVELOPMENT.md         # setup, commands, conventions, test strategy
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
| **M2 — Swipe UI** | `swipe_widget`, `animator`, keyboard bindings, state machine | ⬜ planned |
| **M3 — Sorting** | `folder_manager`, `sorter`, `file_ops`, collision handling | ✅ done |
| **M4 — Comfort** | Undo, config UI, summary screen, logging, error reporting | 🟡 partial — undo, config and logging done |
| **M5 — Distribution** | `.desktop` file, icons, AppImage/Flatpak, 1.0 | ⬜ planned |

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
