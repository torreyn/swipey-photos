# Development guide

Everything needed to hack on ImageSwiper: environment setup, commands, test
strategy, debugging Qt on Linux, and the release checklist.

## 1. Toolchain

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.11+ (3.12 recommended) | runtime, typing, `slots` dataclasses |
| PyQt6 | 6.6+ | Qt 6 bindings |
| Pillow | 10+ | image validation, EXIF, previews |
| pytest + pytest-qt + pytest-cov | 8.2+ / 4.4+ / 5.0+ | unit tests, GUI tests, coverage |
| ruff | latest | lint, import sorting and formatting (`ruff check` + `ruff format`) |
| mypy | 1.10+ | strict typing for `src/` |
| build | 1.2+ | sdist/wheel verification |
| PyYAML | 6.0+ | `tests/test_packaging.py` parses the workflow files |
| PyInstaller | 6.10+ | only for `pip install ".[binary]"` / `scripts/build.sh` |
| Xvfb | optional | `xvfb-run -a pytest -m gui`, the way CI's `gui (xvfb)` job runs |
| desktop-file-utils | optional | `desktop-file-validate` for `packaging/*.desktop` (the test skips without it) |

System Qt libraries (XCB plugin pieces) are listed in
[README → Installation](../README.md#1-system-packages-qt-runtime--python-tooling).
Missing `libxcb-cursor0` produces the classic
`Could not load the Qt platform plugin "xcb"` error.

## 2. First-run setup

```bash
git clone https://github.com/torreyn/image-swiper.git
cd image-swiper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verify:

```bash
python -c "import image_swiper, PyQt6, PIL; print(image_swiper.__version__)"
pytest -q
ruff check .
mypy
```

**pip-free alternative.** Some distributions ship `python3` without pip or
`python3-venv` (this is common on Debian/Ubuntu minimal installs). `uv` creates
the environment and installs the same extras without touching system Python:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Both routes produce an identical `.venv/`; only the installer differs.

## 3. Common commands

| Task | Command |
| --- | --- |
| Run from source | `python -m image_swiper` |
| Run the installed script | `image-swiper` |
| Run with a folder | `image-swiper ~/Pictures/unsorted` |
| Unit tests | `pytest -q` |
| GUI tests (no display) | `QT_QPA_PLATFORM=offscreen pytest -q -m gui` |
| All tests, verbose | `pytest -vv` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
| Check formatting | `ruff format --check .` |
| Types | `mypy` |
| Build artefacts | `python -m build` |
| Inspect the wheel | `python -m zipfile -l dist/*.whl` |
| Coverage | `pytest -q --cov=image_swiper --cov-report=term-missing` |
| Coverage report for a reviewer | `pytest -q --cov=image_swiper --cov-report=html && xdg-open htmlcov/index.html` |
| Standalone binary | `./scripts/build.sh` → `dist/image-swiper` (network, ~2 min) |
| GUI tests on a real X plugin | `xvfb-run -a pytest -q -m gui` |

`pytest` is configured in `pyproject.toml` with `pythonpath = ["src"]`, so tests
run against the working tree without reinstalling. Markers `gui` and
`integration` are registered; `--strict-markers` turns typos into failures.

## 4. Test strategy

```text
tests/
├── conftest.py              # make_images, sample_folder, config, dialogs, xdg_dirs
├── helpers.py               # FakeFileDialog stand-in for the folder picker
├── test_architecture.py     # layer rules (no Qt in core/utils, docstrings)
├── test_package.py          # version + entry point + importability
├── test_packaging.py        # desktop entry, icon tree, install/build scripts,
│                            #   PyInstaller spec, workflows, changelog
├── test_gui_smoke.py        # PyQt6/pytest-qt harness works headless (gui)
├── test_file_ops.py         # collision naming, EXDEV fallback, reverse moves
├── test_folder_manager.py   # category folders, validation, collision suffixes
├── test_config.py           # defaults, round-trip, validation, recents, XDG overrides
├── test_image_loader.py     # scanning, EXIF, corrupt files, preview bounds
├── test_logging_setup.py    # rotation, levels, namespace, log directory
├── test_sorter.py           # queue cursor, counters, undo, vanished files
├── test_swipe_card.py       # fit/aspect, shadow effect, resize refit, drag maths, badge (gui)
├── test_swipe_widget.py     # stage: image hand-off, caption, no legend, fade-in (gui)
├── test_animator.py         # card entrance, interruption, cleanup (gui)
├── test_workers.py          # prefetch lookahead, cache, cancellation, failures (gui)
├── test_theme.py            # dark/light palettes, system fallback (gui)
├── test_welcome_screen.py   # picker, recent-folder list, emit rules (gui)
├── test_completion_screen.py # summary text, counts, button signals (gui)
├── test_main_window.py      # three-page flow, moves, undo, rescan, full screen,
│                            #   dark mode, prefetch, --dry-run, edge cases (gui)
├── test_shortcut_overlay.py # shortcut table, key caps, reuse, Esc (gui)
└── test_app.py              # CLI flags, run(), dry-run forwarding, identity (gui)
```

Principles:

- **Generated fixtures, not binaries.** `make_images()` writes real JPEG/PNG
  files with Pillow into `tmp_path`; `corrupt=True` writes a truncated file to
  test graceful failure.
- **No developer state.** Fixtures point `XDG_CONFIG_HOME`, `XDG_DATA_HOME`,
  `XDG_STATE_HOME` and `HOME` at `tmp_path` subdirectories.
- **Filesystem assertions are explicit.** After a move, assert the destination
  exists, the source is gone, and no other file changed.
- **GUI tests run offscreen** in CI: `QT_QPA_PLATFORM=offscreen`. Use
  `qtbot.mousePress/mouseMove/mouseRelease` and `qtbot.keyClick` rather than
  sleeping. The `gui (xvfb)` job runs the same subset again under `xvfb-run`,
  which loads the real `xcb` plugin — use it locally with
  `xvfb-run -a pytest -q -m gui` when a failure smells plugin-specific.
- **Deterministic animations.** Tests pass `duration_ms=0` (or call
  `animator.stop()`); never `time.sleep()` for animation completion.
- **Regression tests for bugs.** The test must fail on the old code.

## 5. Debugging Qt on Linux

```bash
# Why won't the window appear?
QT_DEBUG_PLUGINS=1 python -m image_swiper 2>&1 | head -40

# Verbose Qt internal logging
QT_LOGGING_RULES="qt.qpa.*=true" python -m image_swiper

# Force a specific platform plugin
QT_QPA_PLATFORM=xcb python -m image_swiper
QT_QPA_PLATFORM=wayland python -m image_swiper

# Headless (CI, containers, SSH)
QT_QPA_PLATFORM=offscreen python -m image_swiper
```

Other tips:

- Run `image-swiper --log-level DEBUG` (once M1 lands) and tail
  `~/.local/share/image-swiper/logs/image-swiper.log`.
- `strace -f -e trace=rename,openat image-swiper` is the fastest way to see what
  is actually touching the filesystem.
- If the UI freezes, the cause is almost always blocking I/O on the GUI thread;
  check that new core calls go through `ui/workers.py`.
- HiDPI issues: `QT_SCALE_FACTOR=1.5` or `QT_SCREEN_SCALE_FACTORS=2` reproduce
  scaling problems without a 4K display.

## 6. Changing things safely

### Adding a configuration key

1. Add the field to the right dataclass in `utils/config.py` with a default.
2. Add it to `validate_config()` with range/type checks.
3. Update `to_dict()` and `from_dict()` (unknown keys must keep working).
4. Document it in `docs/CONFIGURATION.md` (key reference **and** example).
5. Add tests: default value, round-trip, invalid value handling.

### Adding a category

1. Extend `CATEGORIES` in `core/folder_manager.py`.
2. Map a swipe direction and its keys in `MainWindow` (`FOOTER_ORDER`,
   `CATEGORY_SHORTCUTS`, `CATEGORY_HINTS`) — the footer buttons, the summary
   rows and the status bar all iterate `CATEGORIES`, so they follow for free.
3. Extend `CATEGORY_COLORS` in `ui/swipe_card.py` (the badge, footer buttons and
   summary swatches share it) and the direction map used by the fly-out.
4. Update the README shortcut table and `docs/ARCHITECTURE.md`.
5. Add sorter tests for the new destination and its undo path.

### Changing the move algorithm

`utils/file_ops.py` is the only allowed place. Any change must preserve the
invariants in [ARCHITECTURE §8.3](ARCHITECTURE.md#83-invariants) and ship with
tests for: existing destination name, cross-device fallback, missing parent
directory, permission denied, and source == destination.

## 7. Packaging

```bash
python -m build                 # sdist + wheel into dist/
python -m zipfile -l dist/image_swiper-1.0.0-py3-none-any.whl

# Verify a clean install in a throwaway venv
python3 -m venv /tmp/is-verify
/tmp/is-verify/bin/pip install dist/*.whl
/tmp/is-verify/bin/python -c "import image_swiper; print(image_swiper.__version__)"
/tmp/is-verify/bin/image-swiper --help
```

The wheel must contain `image_swiper/py.typed` and all subpackages. The version
is read from `src/image_swiper/__init__.py` via Hatch, so bumping it in one
place is enough (do not also edit `pyproject.toml`).

The sdist also carries `packaging/`, which is where the desktop entry, the icon
theme and the AppImage script live. Their contract — `Icon=` matches the
installed files, `Exec=` names the console script, `StartupWMClass` matches
`app.DESKTOP_FILE_NAME` — is enforced by `tests/test_packaging.py`, so a broken
launcher fails `pytest` instead of a user's menu. Desktop install:

```bash
./packaging/install-desktop.sh --prefix /usr --destdir /tmp/stage   # inspect
QT_QPA_PLATFORM=offscreen python packaging/render_icons.py          # after branding changes
```

### Standalone binary

`scripts/build.sh` creates `build/venv`, installs the project with the `binary`
extra and runs PyInstaller against `image-swiper.spec`:

```bash
./scripts/build.sh                 # -> dist/image-swiper
./scripts/build.sh --clean         # throw the venv away and rebuild it
./scripts/build.sh --help          # --venv, --output, --clean, PIP_ARGS
```

The spec is a one-file, windowed build of `packaging/pyinstaller/entry.py` (which
imports `image_swiper.__main__.main` — PyInstaller runs its entry file as
top-level code, so `__main__.py`'s relative imports would fail there) with
`pathex=["src"]`, so the frozen app resolves `image_swiper` exactly like the
console script does. `tkinter` is the only exclusion — a missing hidden import
only surfaces at run time, and a few MB are not worth that risk.
`tests/test_packaging.py` pins the shape of the spec (name, one file, windowed,
existing icon), so a careless edit fails `pytest` instead of the release job.

The script ends with `dist/image-swiper --version` and compares it with
`image_swiper.__version__`. For a deeper check, run the binary offscreen against
a throwaway folder and quit with <kbd>Ctrl</kbd>+<kbd>Q</kbd>:

```bash
QT_QPA_PLATFORM=offscreen dist/image-swiper --dry-run /tmp/photos-to-sort
```

The result is **not static**: it carries CPython, PyQt6 and Pillow, but Qt still
links against the system `libxcb-*` and `libEGL` libraries from the README. Use
`packaging/appimage/build-appimage.sh` when the target machine has none of them.

[PACKAGING.md](PACKAGING.md) documents the file layout, the AppImage build and
the Flatpak status.

If `python -m build` fails with
`The virtual environment was not created successfully because ensurepip is not
available`, the system interpreter lacks `python3-venv` and the build backend
cannot create its *isolated* environment. Either install the OS package
(`sudo apt install python3.12-venv`) or build without isolation, which reuses the
active venv's backend:

```bash
uv pip install hatchling twine      # or: pip install hatchling twine
python -m build --no-isolation
twine check dist/*
```

## 8. Release checklist

1. `git switch -c release/x.y.z`
2. Bump `__version__` in `src/image_swiper/__init__.py`.
3. Move the `[Unreleased]` entries in [`CHANGELOG.md`](../CHANGELOG.md) into a new
   `## [x.y.z] - YYYY-MM-DD` section and add the compare link at the bottom —
   `tests/test_packaging.py` fails when the shipped version has no section.
4. Update the README roadmap and any changed docs (`CONFIGURATION.md` keys).
5. Regenerate the icons if `ui/branding.py` changed (§7) and rerun
   `desktop-file-validate packaging/image-swiper.desktop`.
6. `ruff check . && ruff format --check . && mypy && pytest -q`
7. `python -m build` and verify the wheel in a clean venv (see §7).
8. `./scripts/build.sh` and smoke-test `dist/image-swiper --version`.
9. Smoke-test on X11 **and** Wayland, with at least one real photo folder.
10. Install the desktop entry and check the menu icon, then `--uninstall`.
11. Tag `vX.Y.Z` and push the tag: `.github/workflows/release.yml` builds the
    binary, the wheel and the sdist, and attaches them to the GitHub Release.
    Check the release page — the assets should be `image-swiper-X.Y.Z-linux-x86_64`,
    `image_swiper-X.Y.Z-py3-none-any.whl` and `image_swiper-X.Y.Z.tar.gz`.
    (If a runner dies mid-release, re-run the workflow with *Run workflow* and
    the tag as input instead of re-tagging.)
12. Announce changes; keep the previous minor's config schema readable.

## 9. Continuous integration

`.github/workflows/ci.yml` is the source of truth. It runs on every push to
`main` and on every pull request, in a Python 3.11 / 3.12 / 3.13 matrix with
`fail-fast: false` so one broken interpreter does not hide the others:

1. `ruff check .`
2. `ruff format --check .` — this is the project's `black`; a second formatter
   would make the two disagree on parenthesized asserts
3. `mypy` — no arguments; `[tool.mypy]` already pins `files` and `strict`
4. `pytest -q --cov=image_swiper --cov-report=term-missing --cov-report=xml`
   with `QT_QPA_PLATFORM=offscreen`; the XML is uploaded as the `coverage-xml`
   artefact from the 3.13 leg. Coverage is reported, not enforced, so a PR that
   adds branches without tests shows up in review instead of blocking the build.

The job apt-installs the Qt platform libraries (`libgl1`, `libxcb-cursor0`, …)
because PyQt6 loads them at import time; the offscreen plugin then keeps the
GUI tests display-free. Reproduce a CI run locally with:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```

A second job, `gui (xvfb)`, runs only the `gui`-marked tests under
`xvfb-run -a -s "-screen 0 1280x1024x24"`. The offscreen plugin never loads the
`xcb` plugin a real desktop uses, so this leg is what catches a missing
`libxcb-*` package or a window-manager assumption. It is also the fastest way to
reproduce a "passes in CI, fails on my machine" report in reverse.

`pip install -e ".[dev]"` means a dependency added to `pyproject.toml` reaches
CI without editing the workflow, and the `setup-python` pip cache is keyed on
`pyproject.toml` for the same reason. If a step starts failing only on a new
Python version, add that version to `requires-python`, the classifiers and the
matrix together.

The packaging tests live inside the same `pytest` run: they parse
`packaging/image-swiper.desktop`, compare the icon tree with
`ui/branding.ICON_SIZES`, run the install and build scripts against `tmp_path`,
`sh -n` the scripts, check the shape of `image-swiper.spec`, parse both workflow
files with PyYAML and pin the changelog format. `desktop-file-validate` runs when
the runner provides it (it is part of `desktop-file-utils`, which the Ubuntu
image already has). The AppImage build itself is *not* in CI — it needs a
relocatable CPython plus the network — so it is verified by hand before a
release (§8); the PyInstaller binary *is* built, in the release workflow only.

A third job, `package`, builds the sdist and wheel once (Python 3.13), asserts
that the sdist contains `packaging/image-swiper.desktop` and the scalable icon,
installs the wheel into a clean virtual environment and runs
`image-swiper --version`, then uploads `dist/*` as a build artefact.

`.github/workflows/release.yml` is separate because it costs real time and only
runs on a `v*` tag (or by hand with *Run workflow*). It builds the one-file
binary with the same `image-swiper.spec` that `scripts/build.sh` uses, smoke-tests
`--version` and `--help`, runs `python -m build` plus `twine check`, and attaches
the three assets to the GitHub Release with `generate_release_notes`. The AppImage
is deliberately not part of it: `appimagetool` and a python-build-standalone
interpreter are large downloads best done on a workstation (§8).

## 10. Editor setup (VSCode)

`.gitignore` ignores most of `.vscode/` but allows `settings.json`,
`extensions.json`, `launch.json` and `tasks.json` to be committed. Useful
settings:

```jsonc
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "editor.formatOnSave": true,
  "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" },
  "ruff.lineLength": 100,
  "files.trimTrailingWhitespace": true
}
```

Recommended extensions: `ms-python.python`, `charliermarsh.ruff`,
`ms-python.mypy-type-checker`.

## 11. Troubleshooting the dev environment

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: image_swiper` | run `pip install -e .` from the repo root, or use `pythonpath = ["src"]` (already set for pytest) |
| Tests collect nothing | `testpaths` points at `tests/`; run from the repo root |
| `qt.qpa.plugin: Could not load ... "xcb"` | install `libxcb-cursor0` and friends (README) |
| GUI tests fail on a headless box | `QT_QPA_PLATFORM=offscreen` |
| Wrong Qt binding imported | this project targets PyQt6; uninstall PySide6 from the venv if present |
| `pip install -e .` rebuilds constantly | editable installs with Hatch are cheap; if it is slow, check for a network-mounted venv |
| mypy complains about Qt stubs | ensure `PyQt6-stubs` is *not* installed alongside PyQt6, which ships its own stubs |
| `scripts/build.sh` aborts: `could not create a venv` | the interpreter lacks `ensurepip`; install `python3.12-venv` or point `PYTHON=` at one that has it |
| `dist/image-swiper` starts, then `Could not load the Qt platform plugin "xcb"` | the binary bundles Qt but not the X11 client libraries — install the README system packages, or build the AppImage |
